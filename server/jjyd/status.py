"""jjyd の現在の状態を JSON ファイルへ書き出す(画面のモニタ jjymon が読む)。

秒ごとの送信が終わった後に書くので、送信のタイミングには影響しない。書けなくても送信は続ける。
一時ファイルに書いてから置き換えるので、読む側が書きかけを見ることはない。
"""
import json
import logging
import os

log = logging.getLogger("jjyd.status")

DEFAULT_PATH = "/run/jjyd/status.json"


class StatusWriter:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self.fails = 0

    def write(self, status: dict) -> None:
        if self.fails >= 3:  # 書けない環境(ディレクトリが無いなど)では、警告を出し続けずに諦める
            return
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(status, f, separators=(",", ":"))
            os.replace(tmp, self.path)
            self.fails = 0
        except OSError as e:
            self.fails += 1
            log.warning("cannot write %s (%d): %s%s", self.path, self.fails, e,
                        "; status export disabled" if self.fails >= 3 else "")
