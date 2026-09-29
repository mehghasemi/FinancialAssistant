from __future__ import annotations

import argparse
import json
import socket
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
            log_level="warning", log_config=None, access_log=False,
        ))
        print(f"FinancialAssistant: {url}\nData: {DATA_DIR}\nKeep this window open. Press Ctrl+C here to exit safely.")
        threading.Thread(target=open_application, args=(server, url), daemon=True).start()
        server.run(sockets=[listener])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
