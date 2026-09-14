"""Entry point for the packaged desktop build.

`gaia serve` from a terminal already prints the URL, but a double-clicked
release has no terminal history to scroll back through, so this also opens
the browser once the server is about to be reachable.
"""

from __future__ import annotations

import sys
import threading
import time
import webbrowser

from gaia.cli import main
from gaia.config import settings


def _open_browser() -> None:
    time.sleep(1.5)
    webbrowser.open(f"http://{settings.host}:{settings.port}")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    sys.exit(main(["serve"]))
