# JJY タイムサーバ (Raspberry Pi 4)

```
ntp.nict.jp ──NTP──▶ chrony ──システム時刻──▶ jjyd ──GPIO18/23──▶ JJY HAT ──40/60kHz──▶ 電波時計
                       └──NTP──▶ 宅内LANのPC等
```

| ディレクトリ | 内容 |
|---|---|
| [hardware/](hardware/README.md) | 拡張基板(HAT)の回路・部品表・調整手順 |
| [hardware/kicad/](hardware/kicad) | KiCad 回路図・基板データ(40/60kHz 切替・RTC 搭載) |
| [server/jjyd/](server/jjyd) | JJY エンコーダと送信デーモン(Python) |
| [server/config/](server/config) | chrony(NICT同期+LAN向けNTP) と jjyd の設定 |
| [server/systemd/](server/systemd) | systemd ユニット |
| [scripts/install.sh](scripts/install.sh) | Raspberry Pi OS 向けインストーラ |

## 仕組み

- **時刻取得**: chrony が `ntp.nict.jp` に 64 秒以上の間隔で問い合わせ、システム時刻を数 ms 以内に保つ。
- **フレーム生成**: [encoder.py](server/jjyd/encoder.py) が JST で 60 秒分のコード(分・時・通算日・年・曜日・パリティ)を作る。
- **送信**: PWM0(GPIO18)が常時 40/60kHz を出し、GPIO23 が毎秒の頭で最大振幅にしてマーカー 0.2 s / "1" 0.5 s / "0" 0.8 s 後に 10% へ戻す。
- **RTC**: 基板上の DS3231 + CR2032 を使い、再起動直後でも前回同期から 24 時間以内なら送信を続ける(`[rtc]`、既定で有効)。
- **安全動作**: `chronyc tracking` が非同期なら送信停止。同期喪失後も `holdover_s`(既定6時間)までは送信継続。起動後に一度も同期していなければ送信しない。

## セットアップ

1. [hardware/README.md](hardware/README.md) に従い基板を製作し、Pi に載せる。
2. Pi にこのリポジトリを置き `sudo ./scripts/install.sh` → `sudo reboot`
3. 確認
   - `chronyc sources -v` / `chronyc tracking` で NICT に同期していること
   - `sudo systemctl start jjyd && journalctl -u jjyd -f`
   - `python3 -m jjyd --dry-run` でハード無しでもタイミングログを確認可能
4. 既定は西日本 60kHz(はがね山)。東日本にする場合は `/etc/jjyd.toml` の `khz = 40` にして jjyd を再起動(基板の共振コンデンサは GPIO26 でソフト切替される)。

## 開発・テスト

```
cd server
python -I tests/test_encoder.py        # エンコーダのラウンドトリップ/構造テスト
python -m jjyd --print-frame           # 現在の分のフレームを表示
```

## 注意

- 電波は**微弱無線局の範囲(322MHz以下: 3mで500µV/m以下)**に収め、時計のすぐそばでのみ受かる出力にすること。
- 精度は Linux のユーザ空間タイミング(数百 µs〜数 ms)で、電波時計の許容(数十 ms)には十分。未確認の点は実機での電界強度と受信確認。
- 未実機検証: ハードウェア回路・sysfs PWM・systemd 部分は Pi 上でまだ試していない。エンコーダのみ PC でテスト済み。

## ライセンス

- ソフトウェア(`server/`、`scripts/`): [MIT License](LICENSE)
- ハードウェア(`hardware/` の回路図・基板・ガーバー・BOM): [CERN-OHL-P-2.0](hardware/LICENSE)(許容型)
- 基板データには KiCad 標準ライブラリのフットプリント/シンボルが含まれる。KiCad ライブラリのライセンス(CC-BY-SA 4.0 とデザインへの使用に関する例外)に従う。

## 現状と注意

- 設計段階のデータです。**基板は未発注・未製造で、Raspberry Pi 実機でも未検証**です(エンコーダとタイムシンクの単体テストと、KiCad の ERC/DRC のみ確認済み)。
- 電波は微弱無線局の範囲に収めること。各国・地域の電波法に従う責任は利用者にあります。
- 部品の在庫・品番は変動します。発注前に必ず再確認してください([hardware/kicad/fab/README.md](hardware/kicad/fab/README.md))。
