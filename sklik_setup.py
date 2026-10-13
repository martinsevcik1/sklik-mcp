"""Nastavení Sklik MCP: API klíč a výběr účtů, se kterými smí MCP pracovat.

Spuštění přes install.py, nebo ručně pythonem z .venv:
    sklik_setup.py [--accounts CESTA] [--list]

1. Zeptá se na API klíč Drak (zadání se nezobrazuje) a uloží ho do ~/.sklik/sklik.yaml.
   Klíč zkopíruj v Skliku tlačítkem Zkopírovat. NEGENERUJ nový - zneplatnil by ten stávající.
2. Ověří přihlášení a vypíše účty, ke kterým má klíč přístup (vlastní i spravované).
3. Vybrané účty zapíše do seznamu povolených účtů (sklik_accounts.yaml). Existující záznamy ponechá.

--accounts  kde má seznam účtů ležet (výchozí sklik_accounts.yaml v této složce nebo SKLIK_ACCOUNTS_FILE)
--list      jen vypíše dostupné účty, nic nezapisuje
--fenix     nastaví refresh token pro API Fénix (chytré kampaně, nahrávání obrázků, SEM)
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import unicodedata
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sklik_api import TOKEN_FILE, Client, SklikError

HEADER = """\
# Seznam účtů, se kterými smí Sklik MCP pracovat. Cokoli mimo seznam odmítne - i čtení.
# Úpravy platí okamžitě, restart není potřeba.
#
# user_id = ID účtu ve Skliku (vypíše ho sklik_setup.py --list). Účet bez user_id je zablokovaný.
# folder  = složka klienta (relativně ke clients_root). Sem MCP ukládá reporty a náhledy.
# clients_root = kořen složek klientů. Relativní cesta se počítá od složky s tímto souborem,
#   takže když soubor leží na cloudovém disku, sdílí ho i se složkami klientů všechny počítače.
# dpa = máš s Anthropicem smlouvu o zpracování osobních údajů (DPA)? Platí pro plány Claude Team,
#   Enterprise a API. U Free, Pro a Max nech false: MCP pak do konverzace nepouští osobní údaje
#   (seznamy zákazníků, kontaktní údaje, vyhledávací dotazy s e-mailem nebo telefonem).
"""


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9.]+", "_", s).strip("_") or "klient"


def parse_pick(text: str, n: int) -> list[int]:
    text = text.strip().lower()
    if text in ("vse", "vše", "all", "*"):
        return list(range(1, n + 1))
    out: list[int] = []
    for part in re.split(r"[,\s]+", text):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [i for i in dict.fromkeys(out) if 1 <= i <= n]


def get_token() -> str:
    if TOKEN_FILE.exists():
        ans = input(f"Klíč už je uložený ({TOKEN_FILE}). Použít ho? [A/n] ").strip().lower()
        if ans in ("", "a", "ano", "y", "yes"):
            return (yaml.safe_load(TOKEN_FILE.read_text(encoding="utf-8")) or {}).get("token", "")
    print("API klíč najdeš ve Skliku: vpravo nahoře profil > Nastavení, dole na stránce Zkopírovat.")
    print("Nový klíč NEGENERUJ, pokud už nějaký máš - starý by přestal fungovat.")
    return getpass.getpass("Vlož API klíč Drak (nezobrazí se) a dej Enter: ").strip()


def save_token(token: str) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(yaml.safe_dump({"token": token}), encoding="utf-8")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    print(f"Klíč uložen do {TOKEN_FILE} (nikam se nevypisuje).")


def setup_fenix() -> None:
    import sklik_fenix as fenix
    print("API Fénix potřebuje vlastní token, API klíč Draku tu nefunguje.")
    print("Ve Skliku: Nástroje > API > vytvořit nový token. Úroveň přístupu rw (čtení a zápis),")
    print("admin práva (rwa) nejsou potřeba. Platnost si zvolíš, po vypršení stačí vytvořit nový a spustit tohle znovu.")
    if fenix.TOKEN_FILE.exists():
        ans = input(f"Token už je uložený ({fenix.TOKEN_FILE}). Nahradit ho? [a/N] ").strip().lower()
        if ans not in ("a", "ano", "y", "yes"):
            return
    tok = getpass.getpass("Vlož token pro Fénix (nezobrazí se) a dej Enter: ").strip()
    if not tok:
        print("Token je prázdný, Fénix přeskočen.")
        return
    fenix.save_token(tok)
    try:
        _, scope = fenix.access_token(None)
    except SklikError as ex:
        print(f"Token se nepodařilo ověřit: {ex}")
        return
    print(f"Token funguje a je uložený v {fenix.TOKEN_FILE} (nikam se nevypisuje).")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--accounts", help="cesta k sklik_accounts.yaml")
    ap.add_argument("--list", action="store_true", help="jen vypsat dostupné účty")
    ap.add_argument("--fenix", action="store_true", help="nastavit token pro API Fénix")
    args = ap.parse_args()
    if args.fenix:
        setup_fenix()
        return
    out_path = Path(args.accounts or os.environ.get("SKLIK_ACCOUNTS_FILE") or HERE / "sklik_accounts.yaml")
    out_path = out_path.expanduser()
    if out_path.is_dir():
        out_path = out_path / "sklik_accounts.yaml"

    token = get_token()
    if not token:
        sys.exit("Klíč je prázdný.")
    cl = Client(token)
    try:
        cl.login()
        info = cl.call("client.get")
    except SklikError as ex:
        sys.exit(f"Přihlášení nebo načtení účtu selhalo: {ex}")
    save_token(token)

    me = info.get("user") or {}
    print(f"\nPřihlášeno jako: {me.get('username')} (ID {me.get('userId')})")
    rows: list[dict] = []
    if me.get("userId"):
        rows.append({"userId": me["userId"], "username": me.get("username"), "relationName": "vlastní účet",
                     "access": "rwa"})
    rows += sorted(info.get("foreignAccounts") or [], key=lambda f: str(f.get("username", "")).lower())
    if not rows:
        sys.exit("Klíč nemá přístup k žádnému účtu.")
    print("\nÚčty, ke kterým má klíč přístup:")
    for i, f in enumerate(rows, 1):
        rel = f.get("relationName") or ""
        print(f"  {i:>3}. {f.get('username')}  | ID {f.get('userId')} | přístup {f.get('access')}"
              + (f" | {rel}" if rel else ""))
    if args.list:
        return

    data: dict = {}
    if out_path.exists():
        data = yaml.safe_load(out_path.read_text(encoding="utf-8")) or {}
        print(f"\nSeznam účtů už existuje ({out_path}), nové účty se do něj přidají.")
    accounts: dict = data.get("accounts") or {}
    known = {int(v["user_id"]) for v in accounts.values() if isinstance(v, dict) and v.get("user_id")}

    pick = input("\nKteré účty povolit? Čísla oddělená čárkou, rozsah 1-5, 'vse', Enter = žádný: ")
    try:
        chosen = parse_pick(pick, len(rows))
    except ValueError:
        sys.exit("Nerozumím výběru. Spusť znovu.")
    for i in chosen:
        f = rows[i - 1]
        uid = int(f["userId"])
        if uid in known:
            print(f"  {f.get('username')} už v seznamu je.")
            continue
        default_name = str(f.get("username") or uid).split("@")[0]
        name = input(f"  Název pro {f.get('username')} [{default_name}]: ").strip() or default_name
        folder = input(f"  Složka klienta [{slug(name)}]: ").strip() or slug(name)
        accounts[name] = {"user_id": uid, "folder": folder, "access": f.get("access")}
        known.add(uid)

    data.setdefault("dpa", False)
    data.setdefault("clients_root", "klienti")
    data["accounts"] = accounts
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(HEADER + "\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                        encoding="utf-8")
    print(f"\nZapsáno: {out_path} ({len(accounts)} účtů).")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nPřerušeno.")
