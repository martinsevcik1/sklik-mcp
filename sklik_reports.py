from __future__ import annotations

import csv
import datetime as dt
import json
from typing import Any

import sklik_core as core
import sklik_docs
import sklik_privacy as privacy
from sklik_api import SklikError
from sklik_core import Account, call, get_account

MONEY = {"totalMoney", "clickMoney", "impressionMoney", "avgCpc", "avgCpt", "cpc", "cpt", "maxCpc", "maxCpt",
         "price", "dayBudget", "totalBudget", "exhaustedTotalBudget", "exhaustedDayBudget",
         "avgCostPerView", "conversionAvgPrice", "transactionAvgPrice",
         "walletCredit", "walletCreditWithVat", "accountLimit", "dayBudgetSum"}
STATS = ["impressions", "clicks", "totalMoney", "conversions", "conversionValue", "transactions"]
ENTITY_BASE = {
    "campaigns": ["id", "name", "status", "type", "budget.dayBudget"],
    "groups": ["id", "name", "status", "campaign.name"],
    "ads": ["id", "adType", "status", "headline1", "group.name", "campaign.name"],
    "banners": ["id", "name", "status", "group.name", "campaign.name"],
    "keywords": ["id", "name", "matchType", "status", "cpc", "group.name", "campaign.name"],
    "queries": ["query", "keyword.name", "group.id", "group.name", "campaign.id", "campaign.name"],
}
PERIODS = {"total": lambda d: 1, "daily": lambda d: d, "weekly": lambda d: d // 7 + 2,
           "monthly": lambda d: d // 28 + 2, "quarterly": lambda d: d // 90 + 2, "yearly": lambda d: d // 365 + 2}


def report_entities() -> list[str]:
    out = []
    for m in sklik_docs.docs():
        if m.endswith(".createReport") and sklik_docs.known(m[:-len("createReport")] + "readReport"):
            out.append(m[:-len(".createReport")])
    return sorted(out)


def _flat(d: dict[str, Any], pre: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        if k == "stats":
            continue
        key = f"{pre}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, key + "."))
        elif isinstance(v, list):
            out[key] = json.dumps(v, ensure_ascii=False) if v and isinstance(v[0], (dict, list)) else \
                ", ".join(str(x) for x in v)
        else:
            out[key] = v
    return out


def _money(k: str, v: Any) -> Any:
    if k.rsplit(".", 1)[-1] in MONEY and isinstance(v, (int, float)) and not isinstance(v, bool):
        return round(v / core.MONEY_DIV, 2)
    return v


def run_report(acc: Account, entity: str, date_from: str | None, date_to: str | None, granularity: str = "total",
               restriction: dict[str, Any] | None = None, cols: list[str] | None = None,
               include_empty: bool = False, max_items: int = 20000) -> tuple[list[dict[str, Any]], list[str]]:
    cm, rm = f"{entity}.createReport", f"{entity}.readReport"
    if not (sklik_docs.known(cm) and sklik_docs.known(rm)):
        raise SklikError(f"Report {entity} neexistuje. Dostupné: {', '.join(report_entities())}")
    cdoc = sklik_docs.docs()[cm]["params"]
    allowed = sklik_docs.columns(rm)
    rf = dict(restriction or {})
    dated = "dateFrom" in cdoc
    days = 1
    if dated:
        end = dt.date.fromisoformat(date_to) if date_to else dt.date.today() - dt.timedelta(days=1)
        start = dt.date.fromisoformat(date_from) if date_from else end - dt.timedelta(days=29)
        rf.update(dateFrom=start.isoformat(), dateTo=end.isoformat())
        days = (end - start).days + 1
    args: list[Any] = [rf]
    if "statGranularity" in cdoc:
        args.append({"statGranularity": granularity})
    created = call(acc, cm, *args)
    rid, total = created.get("reportId"), int(created.get("totalCount") or 0)
    if not rid:
        raise SklikError(f"{cm} nevrátil reportId.")
    if not cols:
        base = [c for c in ENTITY_BASE.get(entity, ["id", "name", "status", "group.name", "campaign.name"])
                if c in allowed]
        cols = base + ([c for c in STATS if c in allowed] if dated else [])
        if not cols:
            cols = allowed[:15]
    bad = [c for c in cols if allowed and c not in allowed]
    if bad:
        raise SklikError(f"Neznámé sloupce pro {rm}: {', '.join(bad)}. Povolené: {', '.join(allowed)}")
    try:
        sdl = int(core.api_limits(acc).get("statsDataLimit") or 0)
    except SklikError:
        sdl = 0
    per = PERIODS.get(granularity, PERIODS["daily"])(days) if dated else 1
    limit = max(1, min(1000, (sdl // per) if sdl else 1000))
    raw: list[dict[str, Any]] = []
    offset = 0
    while offset < max(total, 1) and len(raw) < max_items:
        opts: dict[str, Any] = {"offset": offset, "limit": limit, "displayColumns": cols}
        if "allowEmptyStatistics" in sklik_docs.docs()[rm]["params"]:
            opts["allowEmptyStatistics"] = bool(include_empty)
        batch = call(acc, rm, rid, opts).get("report") or []
        raw += batch
        if len(batch) < limit:
            break
        offset += limit
    rows: list[dict[str, Any]] = []
    for it in raw:
        base = {k: _money(k, v) for k, v in _flat(it).items()}
        stats = it.get("stats")
        if isinstance(stats, dict):
            stats = [stats]
        if not stats:
            rows.append(base)
            continue
        if granularity == "total" and len(stats) > 1:
            agg: dict[str, Any] = {}
            for st in stats:
                for k, v in st.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and k in ("impressions", "clicks",
                            "totalMoney", "clickMoney", "impressionMoney", "conversions", "conversionValue",
                            "transactions"):
                        agg[k] = agg.get(k, 0) + v
            stats = [agg]
        for st in stats:
            r = dict(base)
            for k, v in st.items():
                r["date" if k == "date" else k] = _money(k, v)
            rows.append(r)
    for r in rows:
        if "clicks" in r and "impressions" in r:
            r["CTR %"] = round(100 * r["clicks"] / r["impressions"], 2) if r.get("impressions") else 0
        if "clicks" in r and "totalMoney" in r:
            r["CPC Kč"] = round(r["totalMoney"] / r["clicks"], 2) if r.get("clicks") else 0
        if "conversions" in r and "totalMoney" in r:
            r["cena konv. Kč"] = round(r["totalMoney"] / r["conversions"], 2) if r.get("conversions") else ""
        if "conversionValue" in r and "totalMoney" in r:
            r["PNO %"] = round(100 * r["totalMoney"] / r["conversionValue"], 1) if r.get("conversionValue") else ""
    keys = list(dict.fromkeys(k for r in rows for k in r))
    return rows, keys


def report(account: str, entity: str, date_from: str | None = None, date_to: str | None = None,
           granularity: str = "total", restriction_json: str = "{}", columns: list[str] | None = None,
           sort_by: str = "totalMoney", max_rows: int = 100, include_empty: bool = False) -> str:
    acc = get_account(account)
    restriction = json.loads(restriction_json or "{}")
    if not isinstance(restriction, dict):
        raise SklikError("restriction_json musí být JSON objekt (restrictionFilter bez dateFrom/dateTo).")
    rows, keys = run_report(acc, entity, date_from, date_to, granularity, restriction, columns, include_empty)
    if sort_by and any(sort_by in r for r in rows):
        rows.sort(key=lambda r: (r.get(sort_by) if isinstance(r.get(sort_by), (int, float)) else -1), reverse=True)
    d = core.state_dir(acc, "reporty_sklik")
    path = d / f"{dt.datetime.now():%Y-%m-%d_%H%M}_{entity}_{granularity}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = core.SafeCsv(fh)
        w.writerow(keys)
        for r in rows:
            w.writerow([str(r.get(k, "")).replace(".", ",") if isinstance(r.get(k), float) else r.get(k, "")
                        for k in keys])
    tot = {k: round(sum(r.get(k) or 0 for r in rows if isinstance(r.get(k), (int, float))), 2)
           for k in ("impressions", "clicks", "totalMoney", "conversions", "conversionValue") if k in keys}
    out = [f"{acc.name} | report {entity} | {granularity} | řádků {len(rows)} | peníze v Kč",
           "Součty: " + ", ".join(f"{k} {v}" for k, v in tot.items()) if tot else "",
           "\t".join(keys)]
    shown = [dict(r) for r in rows[:max(0, max_rows)]]
    privacy.clean_rows(shown)
    for r in shown:
        out.append("\t".join("" if r.get(k) is None else str(r.get(k)) for k in keys))
    if len(rows) > max_rows:
        out.append(f"... dalších {len(rows) - max_rows} řádků v CSV")
    out.append(f"CSV: {path}")
    return "\n".join(x for x in out if x != "")


def account_info(account: str) -> str:
    acc = get_account(account)
    data = call(acc, "client.get")
    me = next((f for f in data.get("foreignAccounts") or [] if int(f.get("userId", 0)) == acc.user_id), None)
    out = [f"{acc.name} (Sklik {acc.user_id})"]
    if me:
        out.append("Přístup: {access} | vztah {relationType}/{relationStatus} | kredit {c} Kč (s DPH {cv} Kč) | "
                   "součet denních rozpočtů {db} Kč | měsíční limit {lim}".format(
                       access=me.get("access"), relationType=me.get("relationType"),
                       relationStatus=me.get("relationStatus"), c=_money("walletCredit", me.get("walletCredit")),
                       cv=_money("walletCreditWithVat", me.get("walletCreditWithVat")),
                       db=_money("dayBudgetSum", me.get("dayBudgetSum")),
                       lim=_money("accountLimit", me.get("accountLimit")) if me.get("accountLimit") else "bez limitu"))
    try:
        cr = call(acc, "client.getCredit")
        cr.pop("session", None)
        extra = {k: v for k, v in cr.items() if k not in ("status", "statusMessage")}
        if extra:
            out.append("client.getCredit: " + json.dumps(extra, ensure_ascii=False))
    except SklikError as ex:
        out.append(f"client.getCredit: {ex}")
    return "\n".join(out)


def overview(account: str, days: int = 30) -> str:
    acc = get_account(account)
    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=max(1, int(days)) - 1)
    allowed = sklik_docs.columns("campaigns.readReport")
    cols = [c for c in ["id", "name", "type", "status", "budget.dayBudget", "budget.name"] + STATS if c in allowed]
    rows, _ = run_report(acc, "campaigns", start.isoformat(), end.isoformat(), "total", {"isDeleted": False}, cols,
                         include_empty=True)
    rows.sort(key=lambda r: r.get("totalMoney") or 0, reverse=True)
    tot = {k: round(sum(r.get(k) or 0 for r in rows), 2) for k in ("impressions", "clicks", "totalMoney", "conversions",
                                                                  "conversionValue")}
    out = [account_info(account), f"Období {start:%d. %m.} - {end:%d. %m. %Y}: zobr {tot['impressions']:.0f}, "
           f"kliky {tot['clicks']:.0f}, útrata {tot['totalMoney']:.0f} Kč, konverze {tot['conversions']:.0f}, "
           f"hodnota konv. {tot['conversionValue']:.0f} Kč",
           "ID\tkampaň\ttyp\tstav\tden. rozpočet Kč\tzobr\tkliky\tútrata Kč\tkonv\tCPC Kč\tPNO %"]
    for r in rows:
        cv = r.get("conversionValue") or 0
        pno = round(100 * r["totalMoney"] / cv, 1) if cv and cv >= 0.05 * (r.get("totalMoney") or 0) else ""
        out.append(f"{r.get('id')}\t{r.get('name')}\t{r.get('type')}\t{r.get('status')}\t{r.get('budget.dayBudget', '')}"
                   f"\t{r.get('impressions', 0)}\t{r.get('clicks', 0)}\t{r.get('totalMoney', 0)}\t"
                   f"{r.get('conversions', 0)}\t{r.get('CPC Kč', '')}\t{pno}")
    return "\n".join(out)
