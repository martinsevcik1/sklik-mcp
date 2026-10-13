from __future__ import annotations

import http.client
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

import sklik_docs

BASE = "https://api.sklik.cz/drak/json/v5/"
TOKEN_FILE = Path.home() / ".sklik" / "sklik.yaml"


class SklikError(Exception):
    pass


def _token() -> str:
    if not TOKEN_FILE.exists():
        raise SklikError(f"Chybí {TOKEN_FILE}. Spusť sklik_setup.py.")
    data = yaml.safe_load(TOKEN_FILE.read_text(encoding="utf-8")) or {}
    tok = str(data.get("token", "")).strip()
    if not tok:
        raise SklikError(f"V {TOKEN_FILE} chybí token. Spusť sklik_setup.py.")
    return tok


class Client:
    def __init__(self, token: str | None = None) -> None:
        self._token = token
        self._session: str | None = None
        self._lock = threading.Lock()

    def _post(self, method: str, params: list[Any]) -> dict[str, Any]:
        body = json.dumps(params, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(BASE + method, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except (http.client.IncompleteRead, ConnectionResetError, TimeoutError) as ex:
                if attempt < 3:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise SklikError(f"{method}: přerušené spojení ({type(ex).__name__}), zkus menší rozsah.") from ex
            except urllib.error.HTTPError as ex:
                if ex.code == 429 and attempt < 3:
                    time.sleep(15 * (attempt + 1))
                    continue
                try:
                    data = json.loads(ex.read().decode("utf-8"))
                except Exception:
                    raise SklikError(f"{method}: HTTP {ex.code}") from ex
            status = int(data.get("status", 0))
            if status == 429 and attempt < 3:
                time.sleep(15 * (attempt + 1))
                continue
            return data
        return data

    def login(self) -> str:
        data = self._post("client.loginByToken", [self._token or _token()])
        if int(data.get("status", 0)) != 200 or not data.get("session"):
            raise SklikError(f"Přihlášení selhalo: {data.get('status')} {data.get('statusMessage')}")
        self._session = data["session"]
        return self._session

    def call(self, method: str, *params: Any, user_id: int | None = None) -> dict[str, Any]:
        with self._lock:
            if not self._session:
                self.login()
            for attempt in range(2):
                user: dict[str, Any] = {"session": self._session}
                if user_id is not None and sklik_docs.takes_user_id(method):
                    user["userId"] = int(user_id)
                data = self._post(method, [user, *params] if sklik_docs.takes_user(method) else list(params))
                status = int(data.get("status", 0))
                if status == 401 and attempt == 0:
                    self.login()
                    continue
                if data.get("session"):
                    self._session = data["session"]
                if status not in (200, 206):
                    diag = data.get("diagnostics") or []
                    raise SklikError(f"{method}: {status} {data.get('statusMessage', '')}"
                                     + (f" | {json.dumps(diag, ensure_ascii=False)[:1500]}" if diag else ""))
                return data
        raise SklikError(f"{method}: nepodařilo se obnovit přihlášení.")


def is_read_method(method: str) -> bool:
    return sklik_docs.is_read(method) and method not in sklik_docs.BLOCKED


_client: Client | None = None


def client() -> Client:
    global _client
    if _client is None:
        _client = Client()
    return _client
