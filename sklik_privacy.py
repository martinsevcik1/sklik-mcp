from __future__ import annotations

import re
from typing import Any

import sklik_core as core
from sklik_api import SklikError

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<![\w])(?:\+|00)?\d(?:[ \-/.]?\d){8,14}(?![\w])")

BLOCKED_METHODS = {
    "retargeting.emails.addEmail": "přidání e-mailů do seznamu pro e-mailový retargeting",
    "retargeting.emails.removeEmail": "odebrání e-mailů ze seznamu pro e-mailový retargeting",
}
HOW = ("Režim bez DPA (dpa: false v sklik_accounts.yaml) - do konverzace s Claudem nesmí jít osobní údaje. "
       "Udělej to ručně v rozhraní Skliku. Pokud máš plán Claude s DPA (Team, Enterprise, API), "
       "nastav v sklik_accounts.yaml dpa: true.")


def enabled() -> bool:
    return not core.dpa_enabled()


def mode_line() -> str:
    return ("Režim: s DPA (osobní údaje povolené)" if core.dpa_enabled()
            else "Režim: bez DPA (osobní údaje se do konverzace neposílají)")


def _is_phone(s: str) -> bool:
    return not (s.isdigit() and len(s) == 13)


def has_pii(text: str) -> bool:
    t = text or ""
    return bool(EMAIL.search(t)) or any(_is_phone(m.group(0)) for m in PHONE.finditer(t))


def redact(text: str) -> str:
    t = EMAIL.sub("[e-mail]", text or "")
    return PHONE.sub(lambda m: "[telefon]" if _is_phone(m.group(0)) else m.group(0), t)


def mask_emails(text: str) -> str:
    def m(x: re.Match) -> str:
        local, dom = x.group(0).split("@", 1)
        return f"{local[:2]}***@{dom}"
    return EMAIL.sub(m, text or "")


def check_method(method: str) -> None:
    if enabled() and method in BLOCKED_METHODS:
        raise SklikError(f"{method}: {BLOCKED_METHODS[method]}. {HOW}")


def clean_rows(rows: list[dict[str, Any]]) -> int:
    if not enabled():
        return 0
    n = 0
    for r in rows:
        for k, v in r.items():
            if k.rsplit(".", 1)[-1] == "query" and isinstance(v, str) and has_pii(v):
                r[k] = redact(v)
                n += 1
    return n
