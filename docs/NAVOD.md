# Návod: Sklik MCP od nuly

Počítej zhruba s 15 minutami.

---

## 1. Účet ve Skliku a přístup ke klientům

Sklik API pracuje pod účtem, kterému patří API klíč. Ten účet musí mít přístup do účtů klientů, se kterými chceš
pracovat. Používej vždy **svůj vlastní** účet a svůj klíč, ne cizí: všechny změny přes API se v historii
Skliku zapisují pod majitele klíče.

Možnosti:

- **Agenturní účet:** klienti jsou připojení ke tvému agenturnímu účtu, klíč agenturního účtu vidí všechny.
- **Sdílený přístup:** klient ti ve svém Skliku dá přístup na tvůj Seznam účet
  (v Skliku klienta Nastavení > Přístupy / Správa přístupů). Pro zápis je potřeba přístup s právem úprav.
- **Vlastní účet:** MCP pracuje i s vlastním účtem, ke kterému klíč patří.

Pokud ještě Seznam účet nemáš, založ ho na https://registrace.seznam.cz a přihlas se na https://www.sklik.cz.

---

## 2. API klíč

1. Přihlas se na https://www.sklik.cz.
2. Vpravo nahoře klikni na svůj profil > **Nastavení**.
3. Dole na stránce je sekce s API klíčem.
   - **Klíč už existuje:** klikni na **Zkopírovat**.
   - **Klíč ještě nemáš:** vygeneruj ho a zkopíruj.

**Pozor: když už klíč máš, NEGENERUJ nový.** Vygenerováním nového přestane platit ten stávající a s ním
všechno, co na něm běží (jiné nástroje, reporty, MCP na druhém počítači).

Klíč nikam neposílej a nikomu ho nedávej. Kdo ho má, může pracovat ve všech účtech, kam má tvůj účet přístup.

### Token pro API Fénix (nepovinné)

Sklik má dvě API. Na většinu práce stačí **Drak** s klíčem výše. Novější **Fénix** je potřeba na chytré
kampaně a chytré reklamy, nahrávání obrázků do knihovny, zapínání a vypínání kampaní a SEM konverze.
Fénix má vlastní token, klíč z Draku tam nefunguje.

1. Ve Skliku otevři **Nástroje > API** a vytvoř nový token.
2. **Úroveň přístupu:** `rw` (čtení a zápis). Admin práva (`rwa`) nejsou potřeba, `r` by nestačilo na změny.
3. **Platnost:** zvol si sám. Po vypršení vytvoříš nový a jen ho znovu zadáš (viz níž).
4. Token zkopíruj. Vložíš ho do instalátoru v kroku 4.

Vytvoření nového tokenu pro Fénix stávající klíč Draku nezneplatní, jsou na sobě nezávislé.

---

## 3. Python a Claude Desktop

**Claude Desktop:** https://claude.ai/download, nainstaluj, aspoň jednou spusť a přihlas se.

**Python 3.10 nebo novější:**

- **Windows:** https://www.python.org/downloads/ > instalátor, na první obrazovce zaškrtni
  **Add python.exe to PATH**. Ověř v PowerShellu: `py --version`
- **macOS:** https://www.python.org/downloads/ > instalátor pro macOS. Pak ve složce Aplikace > Python 3.x
  spusť **Install Certificates.command** (bez toho padá spojení s API na chybě SSL certifikátu).
  Ověř v Terminálu: `python3 --version`

**Git** (nepovinné): Windows https://git-scm.com/download/win, macOS nabídne instalaci sám po `git --version`.
Bez gitu stačí na stránce repozitáře **Code > Download ZIP** a rozbalit.

---

## 4. Stažení a instalace

Windows (PowerShell):

```
cd $HOME\Documents
mkdir mcp -ErrorAction SilentlyContinue; cd mcp
git clone https://github.com/martinsevcik1/sklik-mcp.git
cd sklik-mcp
py install.py
```

macOS (Terminál):

```
mkdir -p ~/Documents/mcp && cd ~/Documents/mcp
git clone https://github.com/martinsevcik1/sklik-mcp.git
cd sklik-mcp
python3 install.py
```

Instalátor se postupně ptá, každý krok jde přeskočit a `install.py` spustit znovu:

1. **Knihovny:** vytvoří `.venv` a nainstaluje potřebné balíčky.
2. **Kde má ležet seznam účtů:** Enter = ve složce repa. Používáš-li víc počítačů, zadej cestu do složky
   na cloudovém disku (viz krok 6).
3. **API klíč:** vlož klíč z kroku 2 (při psaní se nezobrazuje) a Enter. Uloží se do `~/.sklik/sklik.yaml`.
4. **Výběr účtů:** vypíše všechny účty, ke kterým má klíč přístup, s čísly. Napiš čísla účtů, se kterými má
   MCP pracovat (např. `1,3,5-8` nebo `vse`). U každého potvrď název a složku klienta (Enter = navržená).
5. **API Fénix (nepovinné):** vlož token z kroku 2 (Token pro API Fénix). Instalátor ho ověří a uloží
   do `~/.sklik/fenix.txt`. Bez něj MCP funguje, jen bez chytrých kampaní a dalších věcí z Fénixu.
6. **Zápis do Claude Desktopu:** přidá server do konfigurace (předtím ji zazálohuje).

Pak **Claude Desktop úplně ukonči** (Windows: i ikonu u hodin, macOS: Cmd+Q) a spusť znovu. V konverzaci
napiš třeba „vypiš moje Sklik účty".

Další účty přidáš kdykoli: znovu `install.py` (krok s klíčem a výběrem účtů), nebo ručně z kořene repa
`sklik_setup.py` (Windows: `.venv\Scripts\python.exe sklik_setup.py`, macOS: `.venv/bin/python sklik_setup.py`).
Nový token pro Fénix (třeba po vypršení) zadáš přes `sklik_setup.py --fenix`.
Seznam jde upravit i v textovém editoru, změny platí hned bez restartu. Je v něm i přepínač `dpa`
(viz README.cs.md, část Režim s DPA a bez DPA). Bez plánu Claude Team, Enterprise nebo API nech `false`.

---

## 5. První kroky

- „Jak si vede Sklik u klienta X za posledních 30 dní?"
- „Projdi vyhledávací dotazy ve Skliku u klienta X a navrhni negativa."
- „Jaké metody má Sklik API pro retargeting?"

Claude nejdřív vždy ukáže plán změny. Běžné změny provede po tvém „ano", u chráněných (rozpočty, stavy, CPC,
mazání, nastavení...) chce výslovný souhlas s konkrétním plánem.

---

## 6. Druhý počítač

1. Seznam účtů dej do složky na cloudovém disku, který máš na obou počítačích. Složky klientů a log změn
   se vytvoří vedle něj.
2. Na druhém počítači zopakuj kroky 3 a 4, u seznamu účtů zadej cestu k tomu samému souboru.
3. Zadej **stejný** API klíč (Zkopírovat, ne Vygenerovat) a případně token pro Fénix. Složku `~/.sklik`
   mezi počítači nekopíruj a nesynchronizuj.

---

## 7. Řešení problémů

| Problém | Co s tím |
|---|---|
| Přihlášení selhalo (401) | Klíč je špatně zkopírovaný, nebo byl mezitím vygenerován nový. Spusť `sklik_setup.py` a zadej aktuální klíč. |
| Fénix: chybí token nebo HTTP 401 | Token pro Fénix chybí nebo vypršel. Vytvoř nový (Nástroje > API, `rw`) a zadej ho přes `sklik_setup.py --fenix`. |
| Účet není v sklik_accounts.yaml | MCP pracuje jen s povolenými účty. Přidej ho přes `sklik_setup.py`. |
| 403 / nedostatečná práva | Tvůj účet má do účtu klienta jen přístup pro čtení. Požádej klienta o práva úprav. |
| 429 / příliš mnoho požadavků | Sklik omezuje počet volání za minutu. MCP to zkouší znovu samo, u velkých reportů chvíli počkej. |
| Claude nevidí nástroje | Claude Desktop úplně ukonči a spusť znovu. Zkontroluj, že `install_claude_config.py` vypsal „Zapsáno". |
| SSL / certifikát na macOS | Spusť Install Certificates.command ze složky Python v Aplikacích. |
