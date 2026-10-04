from __future__ import annotations

import argparse
import json
import socket
import os
import logging
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

import uvicorn

HOST = "127.0.0.1"
PORT = 8000


def open_application(server, url: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not server.should_exit:
        if server.started:
            webbrowser.open_new_tab(url)
            return
        time.sleep(0.1)



def install_close_handler(server, stopped: threading.Event):
    """Windows sends CTRL_CLOSE_EVENT for the console window's close button."""
    if os.name != "nt":
        return lambda: None
    import ctypes
    from ctypes import wintypes
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetConsoleCtrlHandler.argtypes = [callback_type, wintypes.BOOL]
    kernel.SetConsoleCtrlHandler.restype = wintypes.BOOL

    def on_close(event):
        if event not in (2, 5, 6):  # close, logoff, shutdown
            return False  # Uvicorn handles Ctrl+C normally.
        server.should_exit = True
        # Keep the console handler alive while the server drains requests and
        # completes its lifespan backup, within Windows' close-event deadline.
        if not stopped.wait(4):
            logging.error("Application shutdown exceeded the console close deadline")
        return True

    callback = callback_type(on_close)
    if not kernel.SetConsoleCtrlHandler(callback, True):
        raise ctypes.WinError(ctypes.get_last_error())

    def remove():
        # Closure retains the callback for the entire server lifetime.
        kernel.SetConsoleCtrlHandler(callback, False)
    return remove


def main() -> int:
    parser = argparse.ArgumentParser(description="FinancialAssistant local application")
    parser.add_argument("--self-test", action="store_true", help="Check the executable using temporary data without opening a browser")
    args = parser.parse_args()
    if args.self_test:
        from .smoke import check_executable
        return check_executable()
    url = f"http://{HOST}:{PORT}"
    with socket.socket() as listener:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind((HOST, PORT))
        except OSError:
            try:
                with urlopen(url + "/api/health", timeout=2) as response:
                    health = json.load(response)
                if health.get("application") == "FinancialAssistant":
                    webbrowser.open_new_tab(url)
                    return 0
            except (URLError, OSError, ValueError):
                pass
            print(f"Port {PORT} is in use. Close the previous application and try again.")
            return 1
        from .main import app
        from .database import DATA_DIR
        server = uvicorn.Server(uvicorn.Config(
            app, host=HOST, port=PORT, loop="asyncio", http="h11", ws="none",
            log_level="warning", log_config=None, access_log=False, timeout_graceful_shutdown=1,
        ))
        print(f"FinancialAssistant: {url}\nData: {DATA_DIR}\nKeep this window open. Press Ctrl+C here to exit safely.")
        threading.Thread(target=open_application, args=(server, url), daemon=True).start()
        stopped = threading.Event()
        remove_handler = install_close_handler(server, stopped)
        try:
            server.run(sockets=[listener])
        finally:
            stopped.set()
            remove_handler()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
