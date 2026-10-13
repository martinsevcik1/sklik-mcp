from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from sklik_api import SklikError

BASE = "https://api.sklik.cz/v1"
SPEC_URL = BASE + "/openapi.json"
HERE = Path(__file__).resolve().parent
SPEC_FILE = HERE / "fenix_openapi.json"
TOKEN_FILE = Path(os.environ.get("SKLIK_FENIX_TOKEN_FILE", Path.home() / ".sklik" / "fenix.txt")).expanduser()
SPEC_CACHE = TOKEN_FILE.parent / "fenix_openapi.json"
FILE_PREFIX = "@soubor:"
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")

PLAIN = [
    ("POST", r"^/sklik/images/?$"),
    ("POST", r"^/sklik/campaigns/\d+/(groups/\d+/)?negative-keywords/?$"),
]
READ_POST = [
    r"^/sklik/suggest/ad/?$",
    r"^/nakupy/statistics/(item|category|aggregated)/?$",
]
BLOCKED = {
    r"^/nakupy/gdpr/revoke": "odvolání souhlasu GDPR jde jen ručně",
    r"^/sklik/event-measurement/activate": "aktivace SEM je nevratná, jen ručně v rozhraní",
    r"^/user/token": "token řeší MCP samo",
}


def _norm(path: str) -> str:
    p = "/" + path.strip().lstrip("/")
    return p.split("?", 1)[0]


def risk(method: str, path: str) -> str:
    m, p = method.upper(), _norm(path)
    for rx, why in BLOCKED.items():
        if re.search(rx, p):
            return "blocked:" + why
    if m == "GET" or (m == "POST" and any(re.search(rx, p) for rx in READ_POST)):
        return "read"
    if any(m == pm and re.search(rx, p) for pm, rx in PLAIN):
        return "plain"
    return "guarded"


def _refresh_token() -> str:
    if not TOKEN_FILE.exists():
        raise SklikError(f"Chybí refresh token Fénixu ({TOKEN_FILE}). Vytvoř ho v Skliku (Nástroje > API, rw) "
                         "a ulož do tohoto souboru, nebo použij sklik_fenix_import_token.")
    return _extract(TOKEN_FILE.read_text(encoding="utf-8", errors="ignore"))


def _extract(text: str) -> str:
    cands = re.findall(r"[A-Za-z0-9._~+/=-]{40,}", text or "")
    if not cands:
        raise SklikError("V souboru s tokenem jsem nenašel nic, co vypadá jako token (aspoň 40 znaků bez mezer).")
    return max(cands, key=len)


def save_token(tok: str) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(tok.strip() + "\n", encoding="utf-8")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    _tokens.clear()


def import_token(src: str) -> str:
    path = Path(src.strip().strip('"')).expanduser()
    if not path.is_file():
        raise SklikError(f"Soubor {path} neexistuje.")
    tok = _extract(path.read_text(encoding="utf-8", errors="ignore"))
    save_token(tok)
    return (f"Token (délka {len(tok)} znaků) uložen do {TOKEN_FILE}. Původní soubor {path.name} "
            "smaž ručně, ať token neleží v pracovní složce.")


_tokens: dict[int | None, tuple[str, float, str]] = {}
_lock = threading.Lock()


def _form(url: str, fields: dict[str, Any], bearer: str) -> dict[str, Any]:
    body = urllib.parse.urlencode({k: v for k, v in fields.items() if v is not None}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
        "Authorization": f"Bearer {bearer}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        raise SklikError(f"Fénix /user/token: HTTP {ex.code} {_err_text(ex)}") from None


def access_token(user_id: int | None) -> tuple[str, str]:
    with _lock:
        hit = _tokens.get(user_id)
        if hit and hit[1] > time.time() + 120:
            return hit[0], hit[2]
        data = _form(BASE + "/user/token", {"grant_type": "client_credentials",
                                            "user_id": user_id}, _refresh_token())
        tok = data.get("access_token") or data.get("accessToken")
        if not tok:
            raise SklikError("Fénix nevrátil access token: " + ", ".join(k for k in data if "token" not in k.lower()))
        ttl = int(data.get("expires_in") or data.get("expiresIn") or 3600)
        scope = str(data.get("scope") or "")
        _tokens[user_id] = (tok, time.time() + ttl, scope)
        return tok, scope


def _err_text(ex: urllib.error.HTTPError) -> str:
    try:
        raw = ex.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""
    try:
        data = json.loads(raw)
        return json.dumps(data.get("detail", data), ensure_ascii=False)[:2500]
    except ValueError:
        return raw[:500]


def _expand_files(v: Any, used: list[str]) -> Any:
    if isinstance(v, str) and v.startswith(FILE_PREFIX):
        path = Path(v[len(FILE_PREFIX):].strip().strip('"')).expanduser()
        from sklik_core import check_upload
        check_upload(path)
        used.append(f"{path.name} ({path.stat().st_size // 1024} kB)")
        return {"__file__": str(path)}
    if isinstance(v, list):
        return [_expand_files(x, used) for x in v]
    if isinstance(v, dict):
        return {k: _expand_files(x, used) for k, x in v.items()}
    return v


def _multipart(body: dict[str, Any]) -> tuple[bytes, str]:
    boundary = "----sklikmcp" + uuid.uuid4().hex
    out = bytearray()
    for k, v in body.items():
        out += f"--{boundary}\r\n".encode()
        if isinstance(v, dict) and "__file__" in v:
            p = Path(v["__file__"])
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            out += (f'Content-Disposition: form-data; name="{k}"; filename="{p.name}"\r\n'
                    f"Content-Type: {ctype}\r\n\r\n").encode()
            out += p.read_bytes() + b"\r\n"
        else:
            out += f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _has_file(v: Any) -> bool:
    if isinstance(v, dict):
        return "__file__" in v or any(_has_file(x) for x in v.values())
    if isinstance(v, list):
        return any(_has_file(x) for x in v)
    return False


def request(user_id: int | None, method: str, path: str, query: dict[str, Any] | None = None,
            body: Any = None) -> tuple[int, Any]:
    method = method.upper()
    url = BASE + _norm(path)
    q = []
    for k, v in (query or {}).items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            q += [(k, str(x).lower() if isinstance(x, bool) else str(x)) for x in v]
        else:
            q.append((k, str(v).lower() if isinstance(v, bool) else str(v)))
    if q:
        url += "?" + urllib.parse.urlencode(q)
    data, ctype = None, None
    if body is not None:
        if isinstance(body, dict) and _has_file(body):
            data, ctype = _multipart(body)
        else:
            data, ctype = json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json"
    for attempt in range(4):
        tok, _ = access_token(user_id)
        headers = {"Accept": "application/json", "Authorization": f"Bearer {tok}"}
        if ctype:
            headers["Content-Type"] = ctype
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                return resp.status, (json.loads(raw) if raw.strip() else {})
        except urllib.error.HTTPError as ex:
            if ex.code == 429 and attempt < 3:
                time.sleep(float(ex.headers.get("Retry-After") or 5 * (attempt + 1)))
                continue
            if ex.code == 401 and attempt == 0:
                with _lock:
                    _tokens.pop(user_id, None)
                continue
            raise SklikError(f"Fénix {method} {_norm(path)}: HTTP {ex.code} {_err_text(ex)}") from None
        except (TimeoutError, ConnectionResetError) as ex:
            if attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise SklikError(f"Fénix {method} {_norm(path)}: přerušené spojení ({type(ex).__name__}).") from ex
    raise SklikError(f"Fénix {method} {_norm(path)}: opakovaně odmítnuto (429).")


_spec: dict[str, Any] | None = None


def spec(refresh: bool = False) -> dict[str, Any]:
    global _spec
    if _spec is not None and not refresh:
        return _spec
    have = SPEC_CACHE if SPEC_CACHE.exists() else SPEC_FILE
    stale = not have.exists() or time.time() - have.stat().st_mtime > 7 * 24 * 3600
    if refresh or stale:
        try:
            with urllib.request.urlopen(urllib.request.Request(SPEC_URL, headers={"Accept": "application/json"}),
                                        timeout=60) as resp:
                raw = resp.read().decode("utf-8")
            if "paths" not in json.loads(raw):
                raise ValueError("bez paths")
            SPEC_CACHE.parent.mkdir(parents=True, exist_ok=True)
            SPEC_CACHE.write_text(raw, encoding="utf-8")
            have = SPEC_CACHE
        except Exception as ex:
            if not have.exists():
                raise SklikError(f"Nepodařilo se stáhnout dokumentaci Fénixu ({type(ex).__name__}).") from ex
    _spec = json.loads(have.read_text(encoding="utf-8"))
    return _spec


def endpoints(query: str | None = None) -> str:
    s = spec()
    rows = []
    for path, ops in s.get("paths", {}).items():
        for m, op in ops.items():
            if m.upper() not in ("GET",) + WRITE_METHODS:
                continue
            line = f"{m.upper()} {path}\t{op.get('summary', '')}\t[{risk(m, path).split(':')[0]}]"
            if not query or query.lower() in line.lower() or query.lower() in (op.get("description") or "").lower():
                rows.append(line)
    head = f"API Fénix {s.get('info', {}).get('version', '')} - {len(rows)} endpointů (read / plain = běžný zápis / guarded = chráněný)"
    return head + "\n" + "\n".join(rows)


def _find_op(method: str, path: str) -> tuple[str, dict[str, Any]]:
    s = spec()
    m, p = method.lower(), _norm(path)
    paths = s.get("paths", {})
    for cand in (p, p.rstrip("/") + "/", p.rstrip("/")):
        if cand in paths and m in paths[cand]:
            return cand, paths[cand][m]
    for tpl, ops in paths.items():
        rx = "^" + re.sub(r"\\\{[^}]+\\\}", r"[^/]+", re.escape(tpl.rstrip("/"))) + "/?$"
        if m in ops and re.match(rx, p):
            return tpl, ops[m]
    raise SklikError(f"{method.upper()} {p} v dokumentaci Fénixu není. Podívej se do sklik_fenix_endpoints.")


def supports_dry_run(method: str, path: str) -> bool:
    try:
        _, op = _find_op(method, path)
    except SklikError:
        return False
    return any(p.get("name") == "dryRun" for p in op.get("parameters", []))


_SKIP = ("example", "examples", "title")


def _schema_text(s: dict[str, Any], comp: dict[str, Any], ind: int = 0, seen: tuple = (), depth: int = 0) -> str:
    pad = "  " * ind
    if depth > 10:
        return pad + "...\n"
    if "$ref" in s:
        n = s["$ref"].split("/")[-1]
        if n in seen:
            return pad + f"<{n}> (viz výše)\n"
        return pad + f"<{n}>\n" + _schema_text(comp.get(n, {}), comp, ind + 1, seen + (n,), depth + 1)
    out = ""
    for key in ("oneOf", "anyOf", "allOf"):
        if key in s:
            alts = [x for x in s[key] if x.get("type") != "null"]
            if len(alts) == 1 and len(s[key]) == 2:
                out += _schema_text(alts[0], comp, ind, seen, depth + 1).replace(pad, pad, 1)
                continue
            disc = s.get("discriminator", {}).get("propertyName")
            out += pad + key + (f" (podle {disc})" if disc else "") + ":\n"
            for x in alts:
                out += _schema_text(x, comp, ind + 1, seen, depth + 1)
    if "properties" in s:
        req = set(s.get("required", []))
        for k, v in s["properties"].items():
            desc = " ".join((v.get("description") or "").split())[:200]
            attrs = [f"{a}={v[a]}" for a in ("type", "const", "enum", "minLength", "maxLength", "minimum",
                                              "maximum", "minItems", "maxItems", "default", "format") if a in v]
            out += pad + f"- {k}{' (povinné)' if k in req else ''} {' '.join(attrs)} {desc}\n"
            sub = v.get("items") if v.get("type") == "array" and "items" in v else v
            if any(x in sub for x in ("$ref", "oneOf", "anyOf", "allOf", "properties")):
                out += _schema_text(sub, comp, ind + 1, seen, depth + 1)
    elif not any(k in s for k in ("oneOf", "anyOf", "allOf")):
        if s.get("type") == "array" and "items" in s:
            out += pad + "pole:\n" + _schema_text(s["items"], comp, ind + 1, seen, depth + 1)
        else:
            attrs = [f"{a}={s[a]}" for a in ("type", "const", "enum", "minLength", "maxLength", "minimum",
                                              "maximum", "format") if a in s]
            if attrs:
                out += pad + " ".join(attrs) + "\n"
    return out


def help_text(method: str, path: str, variant: str | None = None) -> str:
    tpl, op = _find_op(method, path)
    comp = spec().get("components", {}).get("schemas", {})
    lines = [f"{method.upper()} {tpl} - {op.get('summary', '')} [{risk(method, tpl)}]",
             (op.get("description") or "").strip()]
    for prm in op.get("parameters", []):
        sch = json.dumps(prm.get("schema", {}), ensure_ascii=False)
        lines.append(f"param {prm.get('in')} {prm.get('name')}{' (povinný)' if prm.get('required') else ''}: "
                     f"{' '.join((prm.get('description') or '').split())[:200]} | {sch[:300]}")
    rb = op.get("requestBody")
    if rb:
        for ct, c in rb.get("content", {}).items():
            txt = _schema_text(c.get("schema", {}), comp, 1)
            if variant:
                blocks = re.split(r"(?m)^(?=    <)", txt)
                keep = [b for b in blocks if variant.lower() in b.split("\n", 1)[0].lower()]
                txt = "".join(keep) or txt
            lines.append(f"TĚLO ({ct}):\n{txt}")
    for code in ("200", "201"):
        r = op.get("responses", {}).get(code)
        if r and "content" in r:
            for ct, c in r["content"].items():
                lines.append(f"ODPOVĚĎ {code}:\n" + _schema_text(c.get("schema", {}), comp, 1)[:3000])
    out = "\n".join(lines)
    return out if len(out) < 30000 else out[:30000] + "\n... (zkráceno - zúž přes variant, např. Smart)"
