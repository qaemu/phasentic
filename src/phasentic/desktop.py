"""Phasentic in its own window: the local server on a free port, shown with pywebview."""

from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


class _Api:
    """Functions the page calls through ``window.pywebview.api``."""

    def save_file(self, name: str, text: str) -> None:
        import webview

        chosen = webview.windows[0].create_file_dialog(webview.FileDialog.SAVE, save_filename=name)
        if chosen:
            Path(chosen if isinstance(chosen, str) else chosen[0]).write_text(text, encoding="utf-8")

    def open_url(self, url: str) -> None:
        if url.startswith(("http://", "https://")):
            webbrowser.open(url)


def main() -> None:
    from phasentic.references.factory import phasentic_home

    if sys.stderr is None:  # started without a console: keep errors in a log file
        log = phasentic_home() / "app.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(log, "w", encoding="utf-8", buffering=1)

    import os

    import uvicorn
    import webview

    os.environ["PHASENTIC_APP_WINDOW"] = "1"  # read by create_app when api.main is imported

    from phasentic.api.main import app

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    # ponytail: the port could be taken between probe and bind; uvicorn then fails and the log says so.
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():
            raise SystemExit("The Phasentic server did not start.")
        time.sleep(0.05)

    url = f"http://127.0.0.1:{port}/"
    if not _qt_can_start():
        # ponytail: no window possible; the browser tab works but the server runs until logout.
        print("Qt needs libxcb-cursor0 (sudo apt install libxcb-cursor0); opening the browser instead.")
        webbrowser.open(url)
        thread.join()
        return
    webview.create_window("Phasentic", url, js_api=_Api(), width=1400, height=900)
    web = Path(__file__).parent / "web"
    if sys.platform == "win32":
        webview.start(icon=str(web / "phasentic.ico"))
    else:  # macOS takes the icon from the app bundle
        webview.start(gui="qt" if sys.platform.startswith("linux") else None, icon=str(web / "logo-mark.svg"))
    server.should_exit = True


def _qt_can_start() -> bool:
    """Qt 6.5+ aborts on X11 without libxcb-cursor; only Linux uses Qt here."""
    import ctypes.util
    import os

    if not sys.platform.startswith("linux") or os.environ.get("WAYLAND_DISPLAY"):
        return True
    return ctypes.util.find_library("xcb-cursor") is not None


if __name__ == "__main__":
    main()
