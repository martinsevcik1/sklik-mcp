from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DOCS_FILE = Path(__file__).resolve().parent / "sklik_docs.json"

READ_LAST = {"list", "get", "check", "count", "createReport", "readReport", "stats", "search", "suggest", "version",
             "limits", "getCredit", "status", "getCategoryList", "listCategories", "listCampaignsTypes",
             "listConversionTypes", "listSearchServices", "listPredefinedRegions", "listLabels"}
BLOCKED = {"client.loginByToken": "přihlášení řeší MCP samo",
           "client.logout": "ukončilo by sezení MCP"}
ROUTINE = {"keywords.negative.create", "intends.negative.create", "interests.negative.create",
           "patterns.negative.create", "themes.negative.create", "retargeting.group.negative.add",
           "keywords.create", "sitelinks.create"}
NO_PARAMS = {"api.version"}
DOCS_VERSION = "11.27.0"
DOCS_DATE = "2026-10-12"
CHANGELOG_URL = "https://api.sklik.cz/drak/changelog.html"
_STATE = Path(__file__).resolve().parent / "logs" / "api_version.json"


def _vt(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def latest_api_version(force: bool = False) -> str | None:
    import datetime as dt
    import urllib.request
    today = dt.date.today().isoformat()
    try:
        st = json.loads(_STATE.read_text(encoding="utf-8")) if _STATE.exists() else {}
    except ValueError:
        st = {}
    if not force and st.get("checked") == today:
        return st.get("latest")
    try:
        with urllib.request.urlopen(CHANGELOG_URL, timeout=10) as r:
            html = r.read().decode("utf-8", "ignore")
        vers = re.findall(r"\b(\d{1,2}\.\d{1,3}\.\d{1,3})\b", html)
        latest = max(vers, key=_vt) if vers else None
    except Exception:
        return st.get("latest")
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps({"checked": today, "latest": latest}), encoding="utf-8")
    except OSError:
        pass
    return latest


def version_notice(force: bool = False) -> str:
    latest = latest_api_version(force)
    if latest and _vt(latest) > _vt(DOCS_VERSION):
        return (f"UPOZORNĚNÍ: Sklik API je ve verzi {latest}, dokumentace v MCP je z verze {DOCS_VERSION} "
                f"({DOCS_DATE}). Projdi changelog {CHANGELOG_URL} a podle potřeby aktualizuj MCP.")
    return ""


@lru_cache(maxsize=1)
def docs() -> dict[str, dict[str, Any]]:
    if not DOCS_FILE.exists():
        return {}
    return {m["method"]: m for m in json.loads(DOCS_FILE.read_text(encoding="utf-8"))}


def known(method: str) -> bool:
    return method in docs()


def is_read(method: str) -> bool:
    return method.rsplit(".", 1)[-1] in READ_LAST


def takes_user_id(method: str) -> bool:
    m = docs().get(method)
    if method in NO_PARAMS:
        return False
    return True if m is None else "userId" in m.get("params", "")


def takes_user(method: str) -> bool:
    return method not in NO_PARAMS


def risk(method: str, params: list[Any] | None = None) -> str:
    if method in BLOCKED:
        return "blocked"
    if is_read(method):
        return "read"
    if method == "keywords.create" and params and isinstance(params[0], list) and any(
            isinstance(it, dict) and (it.get("cpc") is not None or it.get("cpt") is not None) for it in params[0]):
        return "guarded"
    if method == "keywords.negative.set":
        return "guarded" if params and len(params) > 2 and params[2] else "routine"
    return "routine" if method in ROUTINE else "guarded"


def columns(method: str) -> list[str]:
    return list(docs().get(method, {}).get("columns") or [])


def help_text(method: str) -> str:
    m = docs().get(method)
    if not m:
        near = search(method, 15)
        return f"Metoda {method!r} v dokumentaci není." + (f" Podobné: {', '.join(near)}" if near else "")
    r = risk(method)
    out = [f"{m['method']}  [{m.get('section')}]  - {m.get('description', '')}",
           f"Typ v MCP: {dict(read='čtení (sklik_call)', routine='běžný zápis (plán + sklik_apply_change)', guarded='chráněný zápis (plán + sklik_apply_guarded_change)', blocked='zakázáno: ' + BLOCKED.get(method, ''))[r]}",
           "Parametry (první je user, ten doplní MCP; v params_json se posílají jen ty další):",
           "  " + m.get("params", ""),
           "Odpověď: " + m.get("response", "")]
    if m.get("columns"):
        out.append("displayColumns: " + ", ".join(m["columns"]))
    if m.get("notes"):
        out.append("Poznámky: " + m["notes"])
    if m.get("diagnostics"):
        out.append("Diagnostiky: " + ", ".join(m["diagnostics"]))
    return "\n".join(out)


def search(query: str, limit: int = 60) -> list[str]:
    q = query.strip().lower()
    if not q:
        return sorted(docs())
    words = [w for w in re.split(r"[\s.]+", q) if w]
    scored = []
    for name, m in docs().items():
        hay = (name + " " + m.get("section", "") + " " + m.get("description", "")).lower()
        score = sum(2 if w in name.lower() else 1 for w in words if w in hay)
        if score:
            scored.append((-score, name))
    return [n for _, n in sorted(scored)[:limit]]


def catalog(section: str | None = None) -> str:
    by: dict[str, list[str]] = {}
    for name, m in docs().items():
        if section and m.get("section") != section.lower():
            continue
        tag = {"read": "", "routine": " (z)", "guarded": " (Z!)", "blocked": " (x)"}[risk(name)]
        by.setdefault(m.get("section", "?"), []).append(name + tag)
    out = [f"Sklik Drak - {sum(len(v) for v in by.values())} metod. (z) běžný zápis, (Z!) chráněný zápis, (x) zakázáno, bez značky čtení."]
    for s in sorted(by):
        out.append(f"{s}: " + ", ".join(by[s]))
    return "\n".join(out)
