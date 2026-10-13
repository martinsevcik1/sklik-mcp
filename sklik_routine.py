from __future__ import annotations

import csv
import datetime as dt
import re
import unicodedata
from pathlib import Path
from typing import Any

import sklik_core as core
import sklik_privacy as privacy
from sklik_api import SklikError
from sklik_core import Account, active_accounts, call, get_account, state_dir
from sklik_xlsx import read_sheet, write_xlsx

THR_COST = 20.0
DECISIONS = "rozhodnuti.csv"
STOP = {"pro", "na", "do", "se", "ze", "od", "po", "jak", "co", "je", "cz", "com", "www", "the", "and", "nebo",
        "kde", "kolik", "pri", "při", "bez", "nad", "pod", "mezi"}
QUERY_COLS = ["query", "clicks", "impressions", "totalMoney", "conversions", "keyword.name", "group.id", "group.name",
              "campaign.id", "campaign.name"]


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _read_report(acc: Account, report_id: Any, total: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    limit, offset = 1000, 0
    while offset < max(total, 1):
        data = call(acc, "queries.readReport", report_id,
                    {"offset": offset, "limit": limit, "allowEmptyStatistics": False, "displayColumns": QUERY_COLS})
        batch = data.get("report") or []
        out += batch
        if len(batch) < limit:
            break
        offset += limit
    return out


def query_rows(acc: Account, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    created = call(acc, "queries.createReport",
                   {"dateFrom": start.isoformat(), "dateTo": end.isoformat()},
                   {"statGranularity": "total"})
    rid = created.get("reportId")
    total = int(created.get("totalCount") or 0)
    if not rid:
        raise SklikError("Sklik nevrátil reportId.")
    merged: dict[tuple[str, Any], dict[str, Any]] = {}
    for it in _read_report(acc, rid, total):
        stats = it.get("stats") or []
        if isinstance(stats, dict):
            stats = [stats]
        q = " ".join(str(it.get("query") or "").split())
        if not q:
            continue
        kw = (it.get("keyword") or {}).get("name", "") or ""
        grp = it.get("group") or {}
        camp = it.get("campaign") or {}
        r = merged.setdefault((q.lower(), grp.get("id")), {
            "query": q, "keyword": kw, "kws": [], "group_id": grp.get("id"), "group": grp.get("name", ""),
            "campaign_id": camp.get("id"), "campaign": camp.get("name", ""), "clicks": 0, "impr": 0,
            "cost": 0.0, "conv": 0.0})
        if kw and kw not in r["kws"]:
            r["kws"].append(kw)
        for st in stats:
            r["clicks"] += int(_num(st.get("clicks")))
            r["impr"] += int(_num(st.get("impressions")))
            r["cost"] += _num(st.get("totalMoney")) / core.MONEY_DIV
            r["conv"] += _num(st.get("conversions"))
    return list(merged.values())


def _decisions(acc: Account) -> dict[str, dict[str, str]]:
    p = state_dir(acc) / DECISIONS
    out: dict[str, dict[str, str]] = {}
    if p.exists():
        with p.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh, delimiter=";"):
                out[r["dotaz"].strip().lower()] = r
    return out


def mark(account: str, terms: list[str], decision: str, note: str = "") -> str:
    acc = get_account(account)
    if decision not in ("ponechat", "vyloucit", "pridat", "zasobnik"):
        raise SklikError("decision je ponechat, vyloucit, pridat nebo zasobnik.")
    p = state_dir(acc) / DECISIONS
    new = not p.exists()
    with p.open("a", encoding="utf-8-sig" if new else "utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        if new:
            w.writerow(["datum", "dotaz", "rozhodnuti", "poznamka"])
        for t in dict.fromkeys(x.strip() for x in terms if x.strip()):
            w.writerow([dt.date.today().isoformat(), t, decision, note])
    return f"Uloženo {len(terms)} dotazů jako „{decision}“ pro {acc.name} (Sklik)."


def _covered(words: list[str], negs: list[tuple[list[str], str]]) -> bool:
    ws, n = set(words), len(words)
    for nw, mt in negs:
        if not nw:
            continue
        if mt == "EXACT" and nw == words:
            return True
        if mt == "PHRASE" and any(words[i:i + len(nw)] == nw for i in range(n - len(nw) + 1)):
            return True
        if mt == "BROAD" and set(nw) <= ws:
            return True
    return False


def _fold(t: str) -> str:
    return unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()


def _tokens(t: str) -> list[str]:
    return [w for w in re.findall(r"[\w-]+", t.lower()) if len(w) >= 3 and not w.isdigit() and w not in STOP]


def _watchlist(acc: Account) -> list[str]:
    out: list[str] = []
    for d in (state_dir(acc), state_dir(acc, "rutina_dotazy")):
        p = d / "sledovat.txt"
        if p.exists():
            out += [l.strip().lower() for l in p.read_text(encoding="utf-8-sig").splitlines()
                    if l.strip() and not l.strip().startswith("#")]
    return list(dict.fromkeys(out))


def review(account: str, days: int = 7, max_rows: int = 150, min_clicks: int = 2,
           min_cost: float | None = None, no_click_rows: int = 40, word_rows: int = 25) -> str:
    acc = get_account(account)
    days = max(1, min(int(days), 90))
    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=days - 1)
    thr = THR_COST if min_cost is None else float(min_cost)
    rows = query_rows(acc, start, end)

    negs_by_group: dict[str, list[tuple[list[str], str]]] = {}
    neg_unknown = False
    try:
        for n in core.negatives(acc):
            gid = str((n.get("group") or {}).get("id"))
            negs_by_group.setdefault(gid, []).append((n.get("name", "").lower().split(), core.neg_match(n.get("matchType"))))
    except SklikError:
        neg_unknown = True
    negs_by_camp: dict[str, list[tuple[list[str], str]]] = {}
    try:
        import sklik_reports
        crow, _ = sklik_reports.run_report(acc, "keywords.campaign.negative", None, None, "total",
                                           {"isDeleted": False}, ["name", "matchType", "campaign.id"], True)
        for n in crow:
            negs_by_camp.setdefault(str(n.get("campaign.id")), []).append(
                (str(n.get("name", "")).lower().split(), core.neg_match(n.get("matchType"))))
    except SklikError:
        neg_unknown = True
    queued: list[tuple[list[str], str]] = []
    zp = state_dir(acc) / "zasobnik.csv"
    if zp.exists():
        with zp.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh, delimiter=";"):
                if r.get("akce") == "vyloucit" and not r.get("nasazeno"):
                    queued.append((r["text"].lower().split(), r["shoda"]))
    keywords = {" ".join(k.lower().split()) for r in rows for k in r["kws"]}
    decisions = _decisions(acc)

    skip = {"decided": 0, "negated": 0, "queued": 0, "keyword": 0, "conv": 0, "low": 0, "pii": 0}
    pool, cands, adds = [], [], {}
    guard_pii = privacy.enabled()
    for r in rows:
        if guard_pii and privacy.has_pii(r["query"]):
            skip["pii"] += 1
            continue
        lt = r["query"].lower()
        words = lt.split()
        prev = decisions.get(lt)
        resurf = (prev is not None and prev.get("rozhodnuti") == "ponechat" and r["conv"] == 0
                  and r["cost"] >= 5 * thr and prev.get("datum", "") < start.isoformat())
        if prev and not resurf:
            skip["decided"] += 1
            continue
        if _covered(words, negs_by_group.get(str(r["group_id"]), []) + negs_by_camp.get(str(r["campaign_id"]), [])):
            skip["negated"] += 1
            continue
        if queued and _covered(words, queued):
            skip["queued"] += 1
            continue
        if " ".join(words) in keywords:
            skip["keyword"] += 1
            continue
        if r["conv"] > 0:
            skip["conv"] += 1
            if not prev:
                a = adds.setdefault(lt, {"r": r, "conv": 0.0, "cost": 0.0, "clicks": 0})
                a["conv"] += r["conv"]
                a["cost"] += r["cost"]
                a["clicks"] += r["clicks"]
            continue
        pool.append(r)
        if r["clicks"] < min_clicks and r["cost"] < thr:
            skip["low"] += 1
            continue
        cands.append((r, bool(prev)))
    cands.sort(key=lambda x: (x[0]["cost"], x[0]["clicks"]), reverse=True)
    shown = cands[:max_rows]
    shown_ids = {id(r) for r, _ in shown}
    noclick = sorted((r for r in pool if id(r) not in shown_ids and r["impr"] >= 3),
                     key=lambda r: (r["impr"], r["clicks"]), reverse=True)[:max(0, no_click_rows)]
    vocab = {_fold(w) for k in keywords for w in _tokens(k)} | {_fold(w) for w in _tokens(acc.name.replace(".", " "))}
    words: dict[str, dict[str, Any]] = {}
    for r in pool:
        for w in set(_tokens(r["query"])):
            if _fold(w) in vocab:
                continue
            a = words.setdefault(w, {"n": 0, "impr": 0, "clicks": 0, "cost": 0.0, "ex": ("", -1)})
            a["n"] += 1
            a["impr"] += r["impr"]
            a["clicks"] += r["clicks"]
            a["cost"] += r["cost"]
            if r["impr"] > a["ex"][1]:
                a["ex"] = (r["query"], r["impr"])
    top_words = sorted(((w, a) for w, a in words.items() if a["n"] >= 2),
                       key=lambda x: (x[1]["impr"], x[1]["n"]), reverse=True)[:max(0, word_rows)]
    watch_hits = []
    for wt in _watchlist(acc):
        hits = [r for r in pool if wt in r["query"].lower()]
        if hits:
            watch_hits.append((wt, hits))
    add_list = sorted(adds.values(), key=lambda a: (a["conv"], -a["cost"]), reverse=True)[:30]

    used = [r for r, _ in shown] + noclick + [h for _, hs in watch_hits for h in hs[:3]] + [a["r"] for a in add_list]
    cmap = {c: f"C{i + 1}" for i, c in enumerate(dict.fromkeys((r["campaign_id"], r["campaign"]) for r in used))}
    gmap = {g: f"A{i + 1}" for i, g in enumerate(dict.fromkeys((r["group_id"], r["group"]) for r in used if r["group_id"]))}

    def code(r: dict[str, Any]) -> str:
        c = cmap[(r["campaign_id"], r["campaign"])]
        return c + (f"/{gmap[(r['group_id'], r['group'])]}" if r["group_id"] else "")

    def money(x: float) -> str:
        return f"{x:,.0f}".replace(",", " ")

    total_cost = sum(r["cost"] for r in rows)
    d = state_dir(acc)
    export = d / f"{dt.date.today():%Y-%m-%d}_dotazy.csv"
    with export.open("w", encoding="utf-8-sig", newline="") as fh:
        w = core.SafeCsv(fh)
        w.writerow(["dotaz", "klicove_slovo", "kampan", "kampan_id", "sestava", "sestava_id", "kliky", "zobrazeni",
                    "utrata", "konverze"])
        for r in sorted(rows, key=lambda r: r["cost"], reverse=True):
            w.writerow([r["query"], ", ".join(r["kws"]), r["campaign"], r["campaign_id"], r["group"], r["group_id"],
                        r["clicks"], r["impr"], f"{r['cost']:.2f}".replace(".", ","), f"{r['conv']:.2f}".replace(".", ",")])

    out = [f"{acc.name} (Sklik {acc.user_id}) | {start:%d. %m.} - {end:%d. %m. %Y} | CZK | práh: {min_clicks} kliky "
           f"nebo {money(thr)} Kč",
           f"Dotazů {len(rows)}, útrata {money(total_cost)} Kč. K posouzení {len(cands)}"
           + (f", zobrazeno top {len(shown)}" if len(shown) < len(cands) else "") + ".",
           f"Vynecháno: posouzené dřív {skip['decided']} | už vyloučené {skip['negated']} | v zásobníku "
           f"{skip['queued']} | = klíčové slovo {skip['keyword']} | konvertující {skip['conv']} | pod prahem {skip['low']}"
           + (f" | s e-mailem nebo telefonem {skip['pii']} (režim bez DPA, jsou jen v lokálním CSV)"
              if skip["pii"] else "")]
    if neg_unknown:
        out.append("POZOR: negativa sestav nebo kampaní se nepodařilo načíst - filtr už vyloučených nemusí být úplný.")
    if cmap:
        out.append("Kampaně: " + " | ".join(f"{v} {k[1]} [{k[0]}]" for k, v in cmap.items()))
    if gmap:
        out.append("Sestavy: " + " | ".join(f"{v} {k[1]} [{k[0]}]" for k, v in gmap.items()))
    out.append("#\tdotaz\tkde\tkl\tútrata\tzobr")
    for i, (r, again) in enumerate(shown, 1):
        out.append(f"{i}\t{r['query']}{' (!dřív ponecháno)' if again else ''}\t{code(r)}\t{r['clicks']}\t"
                   f"{money(r['cost'])}\t{r['impr']}")
    if watch_hits:
        out.append("SLEDOVANÁ SLOVA (vždy, i bez prokliku):")
        for wt, hs in watch_hits:
            ex = ", ".join(f"{h['query']} [{code(h)}]" for h in sorted(hs, key=lambda h: -h["impr"])[:3])
            out.append(f"  {wt}: dotazů {len(hs)}, zobr {sum(h['impr'] for h in hs)}, kl "
                       f"{sum(h['clicks'] for h in hs)}, {money(sum(h['cost'] for h in hs))} | {ex}")
    if noclick:
        out.append(f"POD PRAHEM S NEJVÍC ZOBRAZENÍMI (top {len(noclick)}):")
        out.append("#\tdotaz\tkde\tkl\tútrata\tzobr")
        for i, r in enumerate(noclick, 1):
            out.append(f"N{i}\t{r['query']}\t{code(r)}\t{r['clicks']}\t{money(r['cost'])}\t{r['impr']}")
    if top_words:
        out.append("SLOVA MIMO KLÍČOVÁ SLOVA (napříč nekonvertujícími dotazy):")
        out.append("slovo\tdotazů\tzobr\tkl\tútrata\tpříklad")
        for w_, a in top_words:
            out.append(f"{w_}\t{a['n']}\t{a['impr']}\t{a['clicks']}\t{money(a['cost'])}\t{a['ex'][0]}")
    if add_list:
        out.append(f"KANDIDÁTI NA PŘIDÁNÍ (konvertují a nejsou klíčovým slovem): {len(adds)}")
        out.append("#\tdotaz\tkde\tkonv\tkl\tútrata")
        for i, a in enumerate(add_list, 1):
            conv = f"{a['conv']:.1f}".rstrip("0").rstrip(".")
            out.append(f"P{i}\t{a['r']['query']}\t{code(a['r'])}\t{conv}\t{a['clicks']}\t{money(a['cost'])}")
    out.append(f"Kompletní export: {export}")
    return "\n".join(out)


HEAD = ["Účet", "Sklik ID", "Akce", "Text", "Shoda", "Kampaň / sestava", "Důvod", "Priorita", "Útrata", "Zobrazení",
        "Pokryté dotazy", "ID položky", "Nasadit"]
SHEET = "Dávka ze zásobníku"
YES = {"ano", "a", "yes", "y", "x", "1", "true"}
MATCH = {"EXACT": "přesná", "PHRASE": "frázová", "BROAD": "volná"}


def preview(accounts: list[str] | None = None, per_account: int = 10, counts: dict[str, int] | None = None) -> str:
    counts = {str(k).lower(): int(v) for k, v in (counts or {}).items()}
    batch_rows, full_rows, summary = [], [], []
    for a in (active_accounts(accounts) if backlog is not None else []):
        n = counts.get(a.name.lower(), counts.get(str(a.user_id), per_account))
        op = sorted((r for r in backlog._load(a) if backlog._is_open(r)), key=backlog._key)
        cnames: dict[str, str] = {}
        gnames: dict[str, str] = {}
        if op:
            try:
                for c in core.campaigns(a):
                    cnames[str(c.get("id"))] = str(c.get("name"))
                for g in core.groups(a):
                    gnames[str(g.get("id"))] = f"{(g.get('campaign') or {}).get('name', '')} > {g.get('name')}"
            except SklikError:
                pass

        def row(r: dict[str, str], yes: bool) -> list[Any]:
            if (r.get("uroven") or "sestava") == "kampan":
                tgt = f"kampaň {cnames.get(r['cil_id'], r['cil_id'])} (všechny sestavy)"
            else:
                tgt = f"sestava {gnames.get(r['cil_id'], 'ID ' + r['cil_id'])}"
            base = [a.name, a.user_id, "Vyloučit" if r["akce"] == "vyloucit" else "Přidat KW", r["text"],
                    MATCH.get(r["shoda"], r["shoda"]), tgt, r["duvod"], int(r.get("priorita") or 2),
                    _num(r.get("utrata")) or "", _num(r.get("zobrazeni")) or "", r.get("dotazy", ""), r["id"]]
            return base + (["ano"] if yes else [])
        batch_rows += [row(r, True) for r in op[:n]]
        full_rows += [row(r, False) for r in op]
        summary.append([a.name, a.user_id, min(n, len(op)), max(0, len(op) - n)])
    plans = core.list_plans()
    plan_rows = [[p.account.name, p.account.user_id, p.id, ("[CHRÁNĚNÁ] " if p.guarded else "") + p.title,
                  "\n".join(p.lines), "ano"] for p in plans]
    d = core.clients_root().parent / "nahledy_zmen"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"sklik_nahled_{dt.date.today():%Y-%m-%d}_{dt.datetime.now():%H%M}.xlsx"
    plan_sheet = ("Další připravené změny", ["Účet", "Sklik ID", "Plán", "Změna", "Podrobnosti", "Nasadit"],
                  plan_rows, [22, 12, 10, 30, 60, 9], 5)
    if backlog is None:
        if not plan_rows:
            return "Žádné připravené plány, náhled nevznikl."
        write_xlsx(path, [plan_sheet])
        return "\n".join([f"Náhled uložen: {path}", f"Připravené plány: {len(plan_rows)}",
                          "Provedení až po souhlasu uživatele."])
    write_xlsx(path, [
        ("Souhrn", ["Účet", "Sklik ID", "V dávce", "Zůstane v zásobníku"], summary, [24, 12, 10, 18], None),
        (SHEET, HEAD, batch_rows, [22, 12, 10, 30, 10, 34, 28, 8, 9, 10, 40, 12, 9], 12),
        plan_sheet,
        ("Celý zásobník", HEAD[:-1], full_rows, [22, 12, 10, 30, 10, 34, 28, 8, 9, 10, 40, 12], None),
    ])
    return "\n".join([f"Náhled uložen: {path}",
                      f"Dávka: {len(batch_rows)} položek | další připravené plány: {len(plan_rows)}"]
                     + [f"  {s[0]}: {s[2]} (zbývá {s[3]})" for s in summary]
                     + ["Nasazení až po souhlasu uživatele přes sklik_release_preview."])


def release_preview(path: str | None = None) -> str:
    d = core.clients_root().parent / "nahledy_zmen"
    p = Path(path) if path else (sorted(d.glob("sklik_nahled_*.xlsx")) or [None])[-1]
    if not p or not Path(p).exists():
        raise SklikError("Žádný náhled Sklik zatím neexistuje. Nejdřív sklik_preview_changes.")
    rows = read_sheet(Path(p), SHEET) if backlog is not None else []
    out: list[str] = []
    if rows:
        out += _release_batch(Path(p), rows)
    prow = read_sheet(Path(p), "Další připravené změny")
    if len(prow) > 1:
        ph = prow[0]
        ok = [r[ph.index("Plán")] for r in prow[1:] if len(r) > ph.index("Nasadit")
              and r[ph.index("Nasadit")].strip().lower() in YES]
        no = [r[ph.index("Plán")] for r in prow[1:] if r and r[ph.index("Plán")] not in ok]
        if ok:
            out.append("Připravené plány schválené v náhledu: " + ", ".join(ok))
        if no:
            out.append("Plány vyřazené v náhledu (neprovádět): " + ", ".join(no))
    return "\n\n".join(out) or "V náhledu není nic ke schválení."


def _release_batch(p: Path, rows: list[list[str]]) -> list[str]:
    h = rows[0]
    i_acc, i_id, i_yes = h.index("Sklik ID"), h.index("ID položky"), h.index("Nasadit")
    per: dict[str, set[str]] = {}
    skipped = 0
    for r in rows[1:]:
        r = r + [""] * (len(h) - len(r))
        if r[i_yes].strip().lower() in YES:
            per.setdefault(str(r[i_acc]).split(".")[0], set()).add(r[i_id])
        elif r[i_id]:
            skipped += 1
    out = [f"Z náhledu {p.name}: k nasazení {sum(len(v) for v in per.values())}, vyřazeno {skipped}."]
    for uid, ids in per.items():
        acc = get_account(uid)
        allrows = backlog._load(acc)
        pick = [r for r in allrows if r["id"] in ids and backlog._is_open(r)]
        if pick:
            out += backlog._release(acc, pick, allrows)
    return out


try:
    import sklik_backlog as backlog
except ImportError:
    backlog = None
