# JJY タイムサーバ (Raspberry Pi 4)

```
ntp.nict.jp ──NTP──▶ chrony ──システム時刻──▶ jjyd ──GPIO(ケーブル)──▶ JJY 送信ユニット ──40/60kHz(基板上のコイル)──▶ 電波時計
                       └──NTP──▶ 宅内LANのPC等
```

| ディレクトリ | 内容 |
|---|---|
| [hardware/](hardware/README.md) | 送信ユニット基板の回路・部品表・コイル・調整手順 |
| [hardware/kicad/](hardware/kicad) | KiCad 回路図・基板データ(100×96mm、J1 は上辺中央、基板上コイル、LCD、RTC) |
| [server/jjyd/](server/jjyd) | JJY エンコーダと送信デーモン(Python) |
| [server/config/](server/config) | chrony(NICT同期+LAN向けNTP) と jjyd の設定 |
| [server/systemd/](server/systemd) | systemd ユニット |
| [scripts/install.sh](scripts/install.sh) | Raspberry Pi OS 向けインストーラ |

## 仕組み

- **時刻取得**: chrony が `ntp.nict.jp` に 64 秒以上の間隔で問い合わせ、システム時刻を数 ms 以内に保つ。
- **フレーム生成**: [encoder.py](server/jjyd/encoder.py) が JST で 60 秒分のコード(分・時・通算日・年・曜日・パリティ)を作る。うるう秒は tzdata の leap-seconds.list から予定を読み、LS1/LS2 の予告(前月2日 9:00 JST 〜)と、実施月1日 8:59 JST の 61 秒(挿入)/59 秒(削除)フレームに対応する([leap.py](server/jjyd/leap.py)、`[leap]`)。挿入の 60 秒目は、カーネルが時計を1秒戻している間なので単調時計で送る。毎時 15 分・45 分も既定では通常フレームを送る。NICT 準拠の呼出符号フレーム(40〜49 秒に "JJY" のモールス、50〜55 秒を停波予告 ST に置き換え、年・曜日・うるう秒情報は送らない)は `[callsign] enabled = true` のときだけ送る(下の「法令・商標」参照)。
- **送信**: PWM0(GPIO18)が常時 40/60kHz を出し、GPIO23 が毎秒の頭で最大振幅にしてマーカー 0.2 s / "1" 0.5 s / "0" 0.8 s 後に 10% へ戻す。
- **表示**: 基板の LCD(16×2、I2C)に毎秒、日付・曜日・時刻・送信周波数・送信状態を表示する(`[lcd]`)。
- **送信信号 LED**: 低レベル期間だけ点灯する(ビット1=0.5秒、ビット0=0.2秒点灯して消灯、マーカー=0.8秒。`[signal]`)。
- **RTC が無い構成**(`JJY_RTC=0`): インストーラが `fake-hwclock` を入れ、時刻を 1 時間ごとと停止時に保存する(`systemd-timesyncd` を止めると、起動時の時計が古い保存時刻のままになるため)。起動直後のずれが縮まり、chrony が同期するまでの時計が実際に近くなる。jjyd は同期するまで送信しない。
- **RTC**: 基板上の DS3231 + CR2032 を使い、再起動直後でも前回同期から 24 時間以内なら送信を続ける(`[rtc]`、既定で有効)。
- **安全動作**: `chronyc tracking` が非同期なら送信停止。`local stratum 10` の自己参照(起動直後)や、同期先を選んだ後でもステップ補正が済むまで時計がずれている間(システム時刻のずれ 0.25 秒超)も、同期済みとみなさない(実機で起動直後に約 160 秒ずれていたため)。同期喪失後も `holdover_s`(既定6時間)までは送信継続。起動後に一度も同期していなければ送信しない。

## セットアップ

1. [hardware/README.md](hardware/README.md) に従い基板を製作し、Pi の GPIO ヘッダに**ケーブルでつなぐ**(40 ピンのフラットケーブル、またはジャンパ線)。基板は Pi のケースの外に置く。
2. Pi にこのリポジトリを置き `sudo ./scripts/install.sh` → `sudo reboot`
3. 確認
   - `chronyc sources -v` / `chronyc tracking` で NICT に同期していること
   - `sudo systemctl start jjyd && journalctl -u jjyd -f`
   - `python3 -m jjyd --dry-run` でハード無しでもタイミングログを確認可能
4. 既定は西日本 60kHz(はがね山)。東日本にする場合は `/etc/jjyd.toml` の `khz = 40` にして jjyd を再起動する(基板にスイッチは無く、周波数はソフトだけで切り替わる)。

## 開発・テスト

```
cd server
python -I tests/test_encoder.py        # エンコーダのラウンドトリップ/構造テスト
python -I tests/test_timesync.py       # 同期監視と RTC の判定
python -I tests/test_lcd_signal.py     # LCD 表示と信号 LED のタイミング
python -m jjyd --print-frame           # 現在の分のフレームを表示
```

## 法令・商標

- **免許**: 免許が要らないのは、電波が[著しく微弱な無線局](https://laws.e-gov.go.jp/law/325M50080000014)(電波法第4条第1号、施行規則第6条: 322MHz以下では 3m で 500µV/m 以下)の範囲に収まる場合だけです。超えると無免許開設(電波法第110条)です。基板の出力は計算値で約 40µV/m(hardware/README.md)ですが、**実機での測定(告示の方法)は未実施**です。測定せずに出力を上げたり、外付けアンテナをつないだりしないでください。
- **呼出符号**: 「JJY」は NICT の局の呼出符号であり、NICT の登録商標(T4355749)でもあります。既定では送らず(`[callsign] enabled = false`)、15・45 分も通常のフレームを送ります。電波時計の受信にはこれで十分です。有効にするのは、用途と責任を理解したうえで自分で判断する場合だけにしてください。基板・ソフトを頒布・販売する場合は商標の扱いにも注意してください。
- **利用範囲**: 自分の時計を合わせる目的に限り、他人の機器に影響しない範囲(時計のすぐそば)で使ってください。ここに書いたことは法的助言ではありません。最終的な適法性の確認は利用者の責任です。

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
