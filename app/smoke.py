"""Packaged executable check over real HTTP with isolated temporary data."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import uvicorn


def check_executable() -> int:
    with tempfile.TemporaryDirectory(prefix="financial-assistant-check-") as folder:
        # This module is invoked before importing any application/database module.
        os.environ["FINANCIAL_ASSISTANT_DATA_DIR"] = folder
        from .main import app
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            server = uvicorn.Server(uvicorn.Config(
                app, loop="asyncio", http="h11", ws="none", log_level="warning", access_log=False,
            ))
            worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            worker.start()
            try:
                deadline = time.monotonic() + 30
                while not server.started:
                    if not worker.is_alive() or time.monotonic() > deadline:
                        raise RuntimeError("Packaged server did not start")
                    time.sleep(0.1)

                def request(path, payload=None, method=None):
                    data = json.dumps(payload).encode() if payload is not None else None
                    with urlopen(Request(base + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"}), timeout=5) as response:
                        return response.read()

                assert json.loads(request("/api/health"))["application"] == "FinancialAssistant"
                for path in ("/", "/static/app.js", "/static/money.js", "/static/table-sort.js", "/static/finance.js", "/static/jalali-picker.js", "/static/restore.js", "/static/help.js", "/static/base-data.js", "/static/dashboard-cash.js", "/static/styles.css", "/static/fonts/Vazirmatn-wght.woff2"):
                    assert request(path), f"Missing resource: {path}"
                assert json.loads(request("/api/calendar?year=1403&month=12"))["days"] == 30
                created = json.loads(request("/api/commitments", {
                    "title": "وام تست", "kind": "وام", "installment_amount": 1000,
                    "installment_count": 2, "first_due_date": "1405/07/01",
                }))
                rows = json.loads(request(f'/api/installments?commitment_id={created["id"]}'))
                request("/api/payments", {"installment_id": rows[0]["id"], "amount": 400, "paid_on": "1405/07/01"})
                try:
                    request(f'/api/commitments/{created["id"]}', {
                        "title": "وام تست", "kind": "وام", "repayment_amount": 200,
                    }, method="PATCH")
                except HTTPError as error:
                    assert error.code == 422, error.code
                    error.close()
                else:
                    raise AssertionError("Paid schedule was not protected")
                asset = json.loads(request("/api/assets", {"title":"دارایی تست", "kind":"طلا", "registered_on":"1405/07/01", "initial_value":1000, "current_value":1200}))
                assert len(json.loads(request(f'/api/assets/{asset["id"]}/history'))) == 1
                assert json.loads(request("/api/data-status"))["last_changed_at"]
                report = json.loads(request("/api/financial-report?month=1405-07"))
                assert report["summary"]["installment_total"] == 1000
                assert report["summary"]["commitment_total"] == 1000
                backup = json.loads(request("/api/backups", {}, method="POST"))
                from .services.backups import restore_backup
                restore_backup(Path(backup["path"]), Path(folder) / "restored.db")
            finally:
                server.should_exit = True
                worker.join(timeout=15)
                if worker.is_alive():
                    raise RuntimeError("Packaged server did not shut down")
        print("Executable check: OK (HTTP, assets, payments, backup, restore, shutdown)")
    return 0
