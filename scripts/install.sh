#!/bin/sh
# Raspberry Pi OS (Bookworm) 上で root として実行: sudo ./scripts/install.sh
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)

apt-get update
apt-get install -y chrony python3-gpiozero python3-lgpio

# 他のNTPクライアントと競合しないように
systemctl disable --now systemd-timesyncd 2>/dev/null || true

# PWM0 を GPIO18 に出す
CFG=/boot/firmware/config.txt
grep -q '^dtoverlay=pwm,pin=18,func=2' "$CFG" || echo 'dtoverlay=pwm,pin=18,func=2' >> "$CFG"

mkdir -p /opt/timeserver
cp -r "$ROOT/server" /opt/timeserver/
install -m 644 "$ROOT/server/config/timeserver.conf" /etc/chrony/conf.d/timeserver.conf
[ -f /etc/jjyd.toml ] || install -m 644 "$ROOT/server/config/jjyd.toml" /etc/jjyd.toml
install -m 644 "$ROOT/server/systemd/jjyd.service" /etc/systemd/system/jjyd.service

# 基板上の DS3231 RTC を有効化する。RTC 未実装の基板なら JJY_RTC=0 で実行: sudo JJY_RTC=0 ./scripts/install.sh
if [ "${JJY_RTC:-1}" = "1" ]; then
    grep -q '^dtoverlay=i2c-rtc,ds3231' "$CFG" || echo 'dtoverlay=i2c-rtc,ds3231' >> "$CFG"
    apt-get remove -y fake-hwclock || true
    systemctl disable fake-hwclock 2>/dev/null || true
    # RTC からの時刻設定を udev に任せる (Raspberry Pi OS 標準手順)
    sed -i '/^if \[ -e \/run\/systemd\/system \]/,/^fi/ s/^/#/' /lib/udev/hwclock-set 2>/dev/null || true
    sed -i '/^\[rtc\]/,/^\[/ s/^enabled = false/enabled = true/' /etc/jjyd.toml 2>/dev/null || true
else
    sed -i '/^\[rtc\]/,/^\[/ s/^enabled = true/enabled = false/' /etc/jjyd.toml 2>/dev/null || true
fi

systemctl daemon-reload
systemctl enable --now chrony
systemctl restart chrony
systemctl enable jjyd
echo "インストール完了。PWMオーバーレイ反映のため再起動してください: sudo reboot"
