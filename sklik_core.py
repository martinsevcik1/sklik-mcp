from __future__ import annotations

import datetime as dt
import json
import os
import csv
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

import sklik_docs
from sklik_api import SklikError, client

HERE = Path(__file__).resolve().parent
ACCOUNTS_FILE = Path(os.environ.get("SKLIK_ACCOUNTS_FILE", HERE / "sklik_accounts.yaml")).expanduser()
LOG_DIR = Path(os.environ.get("SKLIK_LOG_DIR", ACCOUNTS_FILE.parent / "logs")).expanduser()
PLAN_TTL = 60 * 60
NEG = {"EXACT": "negativeExact", "PHRASE": "negativePhrase", "BROAD": "negativeBroad"}
NEG_BACK = {v: k for k, v in NEG.items()}
KW = {"EXACT": "exact", "PHRASE": "phrase", "BROAD": "broad"}
MONEY_DIV = 100.0


@dataclass
class Account:
    name: str
    user_id: int
    folder: Path | None
    active: bool


def _cfg() -> dict[str, Any]:
    if not ACCOUNTS_FILE.exists():
        raise SklikError(f"Chybí {ACCOUNTS_FILE}. Spusť install.py nebo sklik_setup.py.")
    return yaml.safe_load(ACCOUNTS_FILE.read_text(encoding="utf-8")) or {}


def _resolve(p: Any) -> Path | None:
    if not p:
        return None
    path = Path(str(p)).expanduser()
    return path if path.is_absolute() else ACCOUNTS_FILE.parent / path


def load_accounts() -> dict[str, Account]:
    data = _cfg()
    root = _resolve(data.get("clients_root"))
    out: dict[str, Account] = {}
    for name, info in (data.get("accounts") or {}).items():
        info = info or {}
        if not info.get("user_id"):
            continue
        folder = info.get("folder")
        if folder:
            folder = Path(str(folder)).expanduser()
            folder = folder if folder.is_absolute() else (root or ACCOUNTS_FILE.parent) / folder
        out[name] = Account(name, int(info["user_id"]), folder, bool(info.get("aktivni_sprava", False)))
    return out


def dpa_enabled() -> bool:
    if not ACCOUNTS_FILE.exists():
        return False
    return _cfg().get("dpa") is True


def clients_root() -> Path:
    return _resolve(_cfg().get("clients_root")) or HERE / "state"


def get_account(key: Any) -> Account:
    accs = load_accounts()
    k = str(key).strip()
    for a in accs.values():
        if k.lower() == a.name.lower() or re.sub(r"\D", "", k) == str(a.user_id):
            return a
    raise SklikError(f"Účet {k!r} není v sklik_accounts.yaml (nebo nemá user_id). Sklik MCP do něj nesmí, "
                     "ani číst. Povolené: " + ", ".join(accs))


def active_accounts(keys: list[str] | None) -> list[Account]:
    if keys:
        return [get_account(k) for k in keys]
    accs = list(load_accounts().values())
    return [a for a in accs if a.active] or accs


def state_dir(acc: Account, routine: str = "rutina_dotazy_sklik") -> Path:
    base = acc.folder if acc.folder else HERE / "state" / str(acc.user_id)
    d = Path(base) / routine
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_event(ev: dict[str, Any]) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ev = {"ts": dt.datetime.now().isoformat(timespec="seconds"), **ev}
        with (LOG_DIR / f"changes-{dt.date.today():%Y-%m}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception:
        pass


def call(acc: Account, method: str, *params: Any) -> dict[str, Any]:
    return client().call(method, *params, user_id=acc.user_id)


def paged(acc: Account, method: str, flt: dict[str, Any], cols: list[str] | None, key: str,
          page: int = 1000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        opts: dict[str, Any] = {"offset": offset, "limit": page}
        if cols:
            opts["displayColumns"] = cols
        batch = call(acc, method, flt, opts).get(key) or []
        out += batch
        if len(batch) < page:
            return out
        offset += page


def campaigns(acc: Account, ids: list[int] | None = None) -> list[dict[str, Any]]:
    flt: dict[str, Any] = {"isDeleted": False}
    if ids:
        flt["ids"] = [int(i) for i in ids]
    return paged(acc, "campaigns.list", flt, ["id", "name", "type", "status"], "campaigns")


def groups(acc: Account, campaign_ids: list[int] | None = None, ids: list[int] | None = None) -> list[dict[str, Any]]:
    flt: dict[str, Any] = {"isDeleted": False}
    if campaign_ids:
        flt["campaign"] = {"ids": [int(i) for i in campaign_ids]}
    if ids:
        flt["ids"] = [int(i) for i in ids]
    return paged(acc, "groups.list", flt, ["id", "name", "status", "campaign.id", "campaign.name"], "groups")


def negatives(acc: Account, group_ids: list[int] | None = None) -> list[dict[str, Any]]:
    flt: dict[str, Any] = {"isDeleted": False}
    if group_ids:
        flt["group"] = {"ids": [int(i) for i in group_ids]}
    return paged(acc, "keywords.negative.list", flt, None, "keywords")


def neg_match(mt: Any) -> str:
    m = str(mt or "").strip()
    if m in NEG_BACK:
        return NEG_BACK[m]
    return m.upper() if m.upper() in NEG else "BROAD"


def _neg_key(gid: Any, name: str, mt: str) -> tuple[str, str, str]:
    return (str(gid), " ".join(name.lower().split()), neg_match(mt))


@dataclass
class Plan:
    id: str
    account: Account
    title: str
    lines: list[str]
    kind: str
    payload: dict[str, Any]
    created: float = field(default_factory=time.time)
    guarded: bool = False


_plans: dict[str, Plan] = globals().get("_plans", {})
_lock = threading.Lock()
APPLY_HOOKS: list[Callable[[Plan], None]] = []


def _new_plan(acc: Account, title: str, lines: list[str], kind: str, payload: dict[str, Any],
              guarded: bool = False, checked: str = "Kontrola nanečisto ve Skliku: OK") -> str:
    p = Plan(uuid.uuid4().hex[:8], acc, title, lines, kind, payload, guarded=guarded)
    with _lock:
        for k in [k for k, v in _plans.items() if time.time() - v.created > PLAN_TTL]:
            _plans.pop(k, None)
        _plans[p.id] = p
    log_event({"type": "proposed", "plan_id": p.id, "account": acc.name, "user_id": acc.user_id,
               "title": title, "lines": lines, "guarded": guarded})
    how = (f"CHRÁNĚNÁ ZMĚNA: po náhledu a výslovném souhlasu uživatele s touto konkrétní změnou "
           f"sklik_apply_guarded_change(\"{p.id}\").") if guarded else \
        f"Po náhledu (sklik_preview_changes) a souhlasu uživatele: sklik_apply_change(\"{p.id}\")."
    return render_plan(p) + f"\n\n{checked}, zatím se nic nezměnilo.\n{how}"


def render_plan(p: Plan) -> str:
    age = int((time.time() - p.created) / 60)
    return "\n".join([f"PLÁN {p.id} - {p.account.name} (Sklik {p.account.user_id})"
                      + (" [CHRÁNĚNÁ ZMĚNA]" if p.guarded else ""),
                      f"{p.title} | vytvořen před {age} min"] + [f"- {l}" for l in p.lines])


def list_plans() -> list[Plan]:
    with _lock:
        for k in [k for k, v in _plans.items() if time.time() - v.created > PLAN_TTL]:
            _plans.pop(k, None)
        return list(_plans.values())


def discard_plan(pid: str) -> bool:
    with _lock:
        return _plans.pop(pid.strip(), None) is not None


def propose_negatives(account: str, target_id: Any, keywords: list[dict[str, str]], level: str = "group") -> str:
    acc = get_account(account)
    tid = int(re.sub(r"\D", "", str(target_id)))
    if level == "campaign":
        grps = groups(acc, campaign_ids=[tid])
        if not grps:
            raise SklikError(f"Kampaň {tid} nemá žádné sestavy (nebo neexistuje).")
        label = f"kampaň „{grps[0].get('campaign', {}).get('name', tid)}“ ({tid}), všechny sestavy ({len(grps)})"
    elif level == "group":
        grps = groups(acc, ids=[tid])
        if not grps:
            raise SklikError(f"Sestava {tid} v účtu {acc.name} nenalezena.")
        label = f"sestava „{grps[0].get('name')}“ (kampaň {grps[0].get('campaign', {}).get('name', '')})"
    else:
        raise SklikError("level je group nebo campaign.")
    gids = [int(g["id"]) for g in grps]
    have = {_neg_key((n.get("group") or {}).get("id"), n.get("name", ""), n.get("matchType", ""))
            for n in negatives(acc, gids)}
    items, skipped = [], []
    for k in keywords:
        mt = NEG.get(str(k.get("match_type", "EXACT")).upper())
        if not mt:
            raise SklikError(f"Neplatná shoda u {k.get('text')!r}.")
        name = " ".join(str(k["text"]).split())
        for gid in gids:
            if _neg_key(gid, name, mt) in have:
                skipped.append(name)
                continue
            have.add(_neg_key(gid, name, mt))
            items.append({"groupId": gid, "name": name, "matchType": mt})
    if not items:
        return f"Není co měnit - negativa už v cíli jsou ({', '.join(dict.fromkeys(skipped))})."
    call(acc, "keywords.negative.check", items)
    words = list(dict.fromkeys(f"{i['name']} ({NEG_BACK[i['matchType']].lower()})" for i in items))
    lines = [f"Cíl: {label}", f"Přidat vylučující ({len(words)}): {', '.join(words)}",
             f"Položek k založení: {len(items)}"]
    if skipped:
        lines.append(f"Už v cíli, vynecháno: {', '.join(dict.fromkeys(skipped))}")
    return _new_plan(acc, f"Přidat vylučující slova ({len(words)}×)", lines, "neg", {"items": items})


def propose_keywords(account: str, group_id: Any, keywords: list[dict[str, str]]) -> str:
    acc = get_account(account)
    gid = int(re.sub(r"\D", "", str(group_id)))
    items = []
    for k in keywords:
        mt = KW.get(str(k.get("match_type", "EXACT")).upper())
        if not mt:
            raise SklikError(f"Neplatná shoda u {k.get('text')!r}.")
        items.append({"groupId": gid, "name": " ".join(str(k["text"]).split()), "matchType": mt})
    call(acc, "keywords.check", items)
    lines = [f"Sestava {gid}: přidat klíčová slova ({len(items)}): "
             + ", ".join(f"{i['name']} ({i['matchType']})" for i in items),
             "CPC z výchozí nabídky sestavy, stav aktivní."]
    return _new_plan(acc, f"Přidat klíčová slova ({len(items)}×)", lines, "kw", {"items": items})


def apply_plan(pid: str, guarded: bool = False) -> str:
    with _lock:
        p = _plans.get(pid.strip())
        if p is None:
            raise SklikError(f"Plán {pid} neexistuje nebo vypršel. Vytvoř nový návrh.")
        if p.guarded and not guarded:
            raise SklikError(f"Plán {p.id} je chráněná změna. Proveď ho jen přes sklik_apply_guarded_change "
                             "po výslovném souhlasu uživatele.")
        if guarded and not p.guarded:
            raise SklikError(f"Plán {p.id} je běžná změna, použij sklik_apply_change.")
        _plans.pop(p.id, None)
    acc = p.account
    try:
        if p.kind == "neg":
            items = p.payload["items"]
            gids = sorted({i["groupId"] for i in items})
            have = {_neg_key((n.get("group") or {}).get("id"), n.get("name", ""), n.get("matchType", ""))
                    for n in negatives(acc, gids)}
            todo = [i for i in items if _neg_key(i["groupId"], i["name"], i["matchType"]) not in have]
            if todo:
                call(acc, "keywords.negative.create", todo)
            after = {_neg_key((n.get("group") or {}).get("id"), n.get("name", ""), n.get("matchType", ""))
                     for n in negatives(acc, gids)}
            missing = [i["name"] for i in todo if _neg_key(i["groupId"], i["name"], i["matchType"]) not in after]
            result = f"Založeno {len(todo)} vylučujících slov" + (f" ({len(items) - len(todo)} už existovalo)."
                                                                   if len(todo) < len(items) else ".")
            if missing:
                result += f"\nPOZOR - po zápisu chybí: {', '.join(dict.fromkeys(missing))}. Zkontroluj v rozhraní."
        elif p.kind == "kw":
            data = call(acc, "keywords.create", p.payload["items"])
            result = f"Přidáno klíčových slov: {len(data.get('keywordIds') or p.payload['items'])}."
        elif p.kind == "raw":
            data = call(acc, p.payload["method"], *p.payload["params"])
            data.pop("session", None)
            st = data.get("status")
            txt = json.dumps({k: v for k, v in data.items() if k not in ("status", "statusMessage")},
                             ensure_ascii=False)
            result = f"{p.payload['method']}: {st} {data.get('statusMessage', '')}" + \
                (f"\nOdpověď: {txt[:3000]}" if txt not in ("{}", "") else "")
            if st == 206:
                result += "\nPOZOR: provedeno s varováními (viz diagnostics)."
        elif p.kind == "fenix_images":
            import sklik_fenix as fenix
            done, failed = [], []
            for f in p.payload["files"]:
                try:
                    _, data = fenix.request(acc.user_id, "POST", "/sklik/images/", None, {"image": {"__file__": f}})
                    done.append(f"{data.get('name')}\t{data.get('id')}\t{data.get('width')}x{data.get('height')}")
                except SklikError as ex:
                    failed.append(f"{Path(f).name}: {ex}")
            result = f"Nahráno {len(done)} z {len(p.payload['files'])} obrázků (název, ID, rozměr):\n" + "\n".join(done)
            if failed:
                result += "\nNEPROŠLO:\n" + "\n".join(failed)
        elif p.kind == "fenix":
            import sklik_fenix as fenix
            pl = p.payload
            st, data = fenix.request(acc.user_id, pl["method"], pl["path"], pl.get("query"), pl.get("body"))
            txt = json.dumps(data, ensure_ascii=False)
            result = f"Fénix {pl['method']} {pl['path']}: HTTP {st}" + (f"\nOdpověď: {txt[:3000]}" if txt not in ("{}", "") else "")
        else:
            raise SklikError(f"Neznámý typ plánu {p.kind}.")
    except SklikError as ex:
        log_event({"type": "apply_failed", "plan_id": p.id, "account": acc.name, "user_id": acc.user_id,
                   "title": p.title, "error": str(ex)})
        return f"Provedení SELHALO: {ex}"
    log_event({"type": "applied", "plan_id": p.id, "account": acc.name, "user_id": acc.user_id,
               "title": p.title, "lines": p.lines, "result": result})
    for h in APPLY_HOOKS:
        try:
            h(p)
        except Exception:
            pass
    return f"PROVEDENO - {p.title} ({acc.name})\n{result}"


FILE_PREFIX = "@soubor:"
MAX_FILE = 10 * 1024 * 1024
UPLOAD_TYPES = (".jpg", ".jpeg", ".png", ".gif", ".webp")


def check_upload(path: Path) -> None:
    if not path.is_file():
        raise SklikError(f"Soubor {path} neexistuje.")
    if path.suffix.lower() not in UPLOAD_TYPES:
        raise SklikError(f"Soubor {path.name}: nahrát jde jen obrázek ({', '.join(UPLOAD_TYPES)}).")
    if path.stat().st_size > MAX_FILE:
        raise SklikError(f"Soubor {path} je větší než 10 MB.")
CHECK_SKIP = {"interests.update", "keywords.negative.set", "keywords.set"}


def _expand_files(v: Any, used: list[str]) -> Any:
    import base64
    if isinstance(v, str) and v.startswith(FILE_PREFIX):
        path = Path(v[len(FILE_PREFIX):].strip().strip('"')).expanduser()
        check_upload(path)
        used.append(f"{path.name} ({path.stat().st_size // 1024} kB)")
        return base64.b64encode(path.read_bytes()).decode("ascii")
    if isinstance(v, list):
        return [_expand_files(x, used) for x in v]
    if isinstance(v, dict):
        return {k: _expand_files(x, used) for k, x in v.items()}
    return v


def _dry_run(acc: Account, method: str, params: list[Any]) -> str:
    pre, op = method.rsplit(".", 1)
    chk = pre + ".check"
    if method in CHECK_SKIP or op not in ("create", "update", "add") or not sklik_docs.known(chk):
        return "Sklik pro tuto metodu kontrolu nanečisto nenabízí - zkontrolováno jen podle dokumentace"
    cp = json.loads(json.dumps(params))
    if op == "update" and cp and isinstance(cp[0], list) and cp[0] and all(
            isinstance(it, dict) and set(it) <= {"id", "status", "requestId", "adType"} for it in cp[0]):
        return "Jen změna stavu - Sklik pro ni kontrolu nanečisto nemá, zkontrolováno podle dokumentace"
    if method == "groups.update" and cp and isinstance(cp[0], list):
        for it in cp[0]:
            if isinstance(it, dict) and "id" in it:
                it["groupId"] = it.pop("id")
    if method in ("interests.negative.create", "interests.create") and cp and isinstance(cp[0], list):
        cp[0] = [{k: v for k, v in it.items() if k != "groupId"} for it in cp[0]]
    call(acc, chk, *cp)
    return f"Kontrola nanečisto ({chk}) ve Skliku: OK"


def _summary(v: Any) -> str:
    txt = json.dumps(v, ensure_ascii=False)
    txt = re.sub(r'"[A-Za-z0-9+/=]{200,}"', '"<soubor base64>"', txt)
    return txt if len(txt) <= 1500 else txt[:1500] + " ... (zkráceno, celé v plánu)"


def propose_raw(account: str, method: str, params: list[Any], reason: str = "") -> str:
    acc = get_account(account)
    method = method.strip()
    if not sklik_docs.known(method):
        near = sklik_docs.search(method, 10)
        raise SklikError(f"Metoda {method} v dokumentaci Drak není." + (f" Podobné: {', '.join(near)}" if near else ""))
    if not isinstance(params, list):
        raise SklikError("params musí být JSON pole (bez prvního parametru user).")
    import sklik_privacy
    sklik_privacy.check_method(method)
    r = sklik_docs.risk(method, params)
    if r == "blocked":
        raise SklikError(f"{method} je zakázaná: {sklik_docs.BLOCKED[method]}.")
    if r == "read":
        raise SklikError(f"{method} je čtecí metoda, použij sklik_call.")
    files: list[str] = []
    params = _expand_files(params, files)
    checked = _dry_run(acc, method, params)
    count = sum(len(p) for p in params if isinstance(p, list)) or 1
    d = sklik_docs.docs()[method]
    lines = [f"Metoda: {method} - {d.get('description', '')}", f"Počet položek: {count}"]
    if reason:
        lines.append(f"Důvod: {reason}")
    if files:
        lines.append("Soubory: " + ", ".join(files))
    lines.append("Parametry: " + _summary(params))
    if r == "guarded":
        lines.append("Chráněná změna (mění rozpočty, stavy, mazání, nastavení nebo přepisuje seznamy).")
    title = f"{method} ({count}×)" + (f" - {reason}" if reason else "")
    return _new_plan(acc, title, lines, "raw", {"method": method, "params": params}, guarded=(r == "guarded"),
                     checked=checked)


_limits: dict[str, Any] = {}


def api_limits(acc: Account) -> dict[str, Any]:
    if not _limits:
        data = call(acc, "api.limits")
        _limits.update(data.get("limits") or {})
        _limits["batch"] = {b.get("name"): b.get("limit") for b in data.get("batchCallLimits") or []}
    return _limits


def propose_fenix(account: str, method: str, path: str, body: Any = None, query: dict[str, Any] | None = None,
                  reason: str = "") -> str:
    import sklik_fenix as fenix
    acc = get_account(account)
    method = method.strip().upper()
    if method not in fenix.WRITE_METHODS:
        raise SklikError("Návrh je jen pro zápis (POST, PUT, PATCH, DELETE). Čtení přes sklik_fenix_call.")
    tpl, _ = fenix._find_op(method, path)
    r = fenix.risk(method, path)
    if r.startswith("blocked:"):
        raise SklikError(f"{method} {path} je zakázané: {r.split(':', 1)[1]}.")
    if r == "read":
        raise SklikError(f"{method} {path} jen čte, použij sklik_fenix_call.")
    files: list[str] = []
    body = fenix._expand_files(body, files)
    query = {k: v for k, v in (query or {}).items() if k != "dryRun"}
    if fenix.supports_dry_run(method, path):
        fenix.request(acc.user_id, method, path, {**query, "dryRun": True}, body)
        checked = "Kontrola nanečisto (dryRun) ve Skliku: OK"
    else:
        checked = "Fénix pro tento endpoint kontrolu nanečisto nenabízí - zkontrolováno jen podle dokumentace"
    lines = [f"Fénix: {method} {fenix._norm(path)} ({tpl})"]
    if reason:
        lines.append(f"Důvod: {reason}")
    if files:
        lines.append("Soubory: " + ", ".join(files))
    if query:
        lines.append("Parametry URL: " + json.dumps(query, ensure_ascii=False))
    if body is not None:
        lines.append("Tělo: " + _summary(body))
    if r == "guarded":
        lines.append("Chráněná změna (zakládá, zapíná, mění rozpočty, stavy nebo nastavení).")
    title = f"Fénix {method} {fenix._norm(path)}" + (f" - {reason}" if reason else "")
    return _new_plan(acc, title, lines, "fenix",
                     {"method": method, "path": fenix._norm(path), "query": query, "body": body},
                     guarded=(r == "guarded"), checked=checked)


def propose_fenix_images(account: str, files: list[str], reason: str = "") -> str:
    import sklik_fenix as fenix
    acc = get_account(account)
    paths, lines = [], []
    for f in files:
        path = Path(str(f).strip().strip('"')).expanduser()
        check_upload(path)
        paths.append(str(path))
        lines.append(f"{path.name} ({path.stat().st_size // 1024} kB)")
    if not paths:
        raise SklikError("Žádné soubory.")
    head = [f"Nahrát {len(paths)} obrázků do knihovny účtu (Fénix POST /sklik/images/)"] + ([f"Důvod: {reason}"] if reason else [])
    return _new_plan(acc, f"Nahrát obrázky ({len(paths)}×)" + (f" - {reason}" if reason else ""), head + lines,
                     "fenix_images", {"files": paths}, guarded=False,
                     checked="Soubory existují a mají povolenou velikost")


_CSV_NUM = re.compile(r"^[-+]?\d[\d\s.,]*%?$")


def csv_safe(v: Any) -> Any:
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") and not _CSV_NUM.match(v):
        return "'" + v
    return v


class SafeCsv:
    def __init__(self, fh: Any) -> None:
        self._w = csv.writer(fh, delimiter=";")

    def writerow(self, row: list[Any]) -> None:
        self._w.writerow([csv_safe(v) for v in row])
