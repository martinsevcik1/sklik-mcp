# Sklik MCP

[English](README.md) | **Čeština**

Lokální MCP server, přes který Claude (Claude Desktop) čte a spravuje účty Sklik. Pokrývá obě API Skliku:
celé API Drak (JSON v5, přes 200 metod: kampaně, sestavy, inzeráty, bannery, klíčová slova, negativa, rozpočty,
retargeting, konverze, reporty...) a novější API Fénix (chytré kampaně a reklamy, nahrávání obrázků,
SEM konverze, feedy Nákupů). Většinu práce tak uděláš z konverzace bez webového rozhraní Skliku.

- Běží na tvém počítači s tvým API klíčem. Data z účtů, se kterými Claude pracuje, ale procházejí konverzací
  s Claudem (viz [Kam tečou data](#kam-tečou-data)).
- Pracuje jen s účty, které mu povolíš v `sklik_accounts.yaml`. Jiné účty odmítne, i pro čtení.
- Každý zápis má dva kroky: Claude změnu nejdřív připraví (a kde to API umí, ověří nanečisto přes `*.check`),
  provede se až po tvém souhlasu.
- Citlivé změny (rozpočty, stavy, CPC, mazání, nastavení kampaní, konverze, retargeting) jsou **chráněné**:
  provede je jen samostatný nástroj a jen po výslovném souhlasu s konkrétním plánem.
- Funguje na Windows i macOS. Potřebuje jen Python, žádné další služby.

> [!WARNING]
> **Vibecoděné.** Nejsem programátor, jsem marketér. Sklik MCP jsem postavil s Claudem: kód z velké části
> napsala AI podle mých zadání a já ho ladím při vlastní práci. Mně funguje, ale můžou v něm
> být chyby, neefektivní řešení i bezpečnostní rizika, na která jsem nepřišel. Než ho pustíš na důležité účty,
> projdi si kód (nebo ho dej projít někomu, kdo mu rozumí), začni na jednom účtu a každou změnu před schválením
> čti. Používáš ho na vlastní odpovědnost.

Podrobný návod krok za krokem: **[docs/NAVOD.md](docs/NAVOD.md)**

## Co potřebuješ

- Claude Desktop (Windows nebo macOS)
- Python 3.10 nebo novější
- Účet ve Skliku (Seznam) s přístupem do účtů klientů a jeho API klíč
- Nepovinně token pro API Fénix (chytré kampaně, nahrávání obrázků, SEM konverze)

## Rychlá instalace

**Bez gitu:** nahoře na této stránce **Code > Download ZIP**, rozbal třeba do `Dokumenty/mcp/sklik-mcp`
a spusť `instalovat-windows.bat` (Windows), nebo `instalovat-mac.command` (macOS) dvojklikem.
Spouštěč si sám najde Python, a když chybí, nabídne jeho instalaci.

**S gitem:**

```
git clone https://github.com/martinsevcik1/sklik-mcp.git
cd sklik-mcp
```

Windows: `py install.py`, macOS: `python3 install.py`

Instalátor vytvoří virtuální prostředí, zeptá se na API klíč Draku, vypíše účty, ke kterým má klíč přístup,
nechá tě vybrat ty, se kterými má MCP pracovat, volitelně nastaví token pro API Fénix a zapíše server
do Claude Desktopu.
Pak Claude Desktop úplně ukonči a spusť znovu.

**Kde vzít klíče**
- **API klíč Draku:** ve Skliku vpravo nahoře profil > Nastavení, dole na stránce Zkopírovat.
  **Když už klíč máš, nový negeneruj**, starý by přestal platit i se vším, co na něm běží.
- **Token pro Fénix:** ve Skliku Nástroje > API, vytvoř nový token s úrovní přístupu `rw` (čtení a zápis, admin
  práva nejsou potřeba). Platnost si zvolíš, po vypršení vytvoř nový a spusť `sklik_setup.py --fenix`.
  Nový token pro Fénix klíč Draku neovlivní.

Podrobně i s výběrem účtů: [docs/NAVOD.md](docs/NAVOD.md).

## Nástroje

**Čtení a reporty**
- `sklik_list_accounts` - povolené účty
- `sklik_account_overview` - kredit, rozpočty a výkon všech kampaní
- `sklik_campaigns` - kampaně a sestavy s ID
- `sklik_report` - libovolný report (kampaně, sestavy, inzeráty, bannery, slova, dotazy...) s výběrem sloupců,
  obdobím a granularitou, celý výsledek do CSV ve složce klienta
- `sklik_search_terms_review`, `sklik_mark_search_terms` - rozbor vyhledávacích dotazů, filtruje lokálně
  a šetří kontext, posouzené dotazy si pamatuje
- `sklik_call` - libovolná čtecí metoda API

**Celé API**
- `sklik_api_methods` - katalog všech metod
- `sklik_method_help` - parametry, povolené sloupce a poznámky z oficiální dokumentace k jedné metodě
- `sklik_propose_call` - návrh libovolné zápisové metody (create, update, remove, set...), soubory
  (obrázky, bannery) přes `@soubor:CESTA`
- `sklik_api_status` - verze API v MCP vs. nejnovější verze podle changelogu Skliku
- `sklik_reload_code` - po úpravě kódu ho načte znovu bez restartu Claude Desktopu (nové nástroje restart
  potřebují)

**Specializované návrhy**
- `sklik_propose_negative_keywords` - vylučující slova na sestavu, nebo do všech sestav kampaně
- `sklik_propose_keywords` - klíčová slova do sestavy

**API Fénix (chytré kampaně, obrázky, SEM)**
- `sklik_fenix_status` - ověří token Fénixu a přístup do povolených účtů (token nevypisuje)
- `sklik_fenix_endpoints`, `sklik_fenix_help` - katalog a schéma endpointů z OpenAPI Fénixu
- `sklik_fenix_call` - čtení (kampaně, obrázky, SEM konverze, feedy Nákupů, návrhy textů chytré reklamy)
- `sklik_fenix_propose` - návrh zápisu, kde to Fénix umí, s kontrolou nanečisto (`dryRun`); provede se přes
  `sklik_apply_change` / `sklik_apply_guarded_change` jako ostatní plány
- `sklik_fenix_upload_images` - hromadné nahrání obrázků do knihovny účtu, vrátí jejich ID
- `sklik_fenix_import_token` - přenese refresh token ze souboru do `~/.sklik/fenix.txt`

Fénix potřebuje vlastní token: Sklik > Nástroje > API, úroveň **rw** (admin práva nejsou potřeba).
Zadáš ho v instalátoru, nebo kdykoli později přes `sklik_setup.py --fenix`. Do konverzace ho nevkládej.
Postup krok za krokem je v [docs/NAVOD.md](docs/NAVOD.md).

**Provedení**
- `sklik_preview_changes`, `sklik_release_preview` - Excel s náhledem připravených plánů, ve sloupci Nasadit
  označíš, co provést
- `sklik_list_pending_changes`, `sklik_discard_change`
- `sklik_apply_change` - běžná změna
- `sklik_apply_guarded_change` - chráněná změna, jen po výslovném souhlasu

## Doporučené postupy

MCP je stavěný na maximální efektivitu: Claude skládá související změny v jednom účtu do jednoho plánu,
takže schvaluješ málo kroků. Příklady zadání:

- **Rozbor dotazů:** „Projdi dotazy ve Skliku u klienta X za 30 dní, navrhni negativa a nová slova jako jeden
  plán."
- **Přehled účtu:** „Jak si vede Sklik u klienta X? Kampaně, útrata, konverze, kredit."
- **Audit:** „Zkontroluj Sklik u klienta X: měření konverzí, struktura, podíl zobrazení, rozpočty, inzeráty."
- **Nová kampaň nebo sestava:** „Založ ve Skliku vyhledávací kampaň pro službu Y se 3 sestavami, slovy
  a inzeráty." Vše vznikne pozastavené, zapnutí je chráněná změna.
- **Reporty:** „Vyexportuj výkon sestav po týdnech za poslední čtvrtletí do CSV."
- **Cokoli dalšího z rozhraní:** popiš, co chceš. Claude si najde metodu v katalogu, přečte její nápovědu
  a připraví návrh.

## Seznam účtů a složky klientů

`sklik_accounts.yaml` (vzor v `sklik_accounts.example.yaml`, nejjednodušší je vyplnit přes `sklik_setup.py`):

```yaml
clients_root: klienti          # relativně ke složce se sklik_accounts.yaml
accounts:
  vzorovy-eshop.cz: {user_id: 1234567, folder: vzorovy_eshop}
```

Do složky klienta MCP ukládá reporty, náhledy a stav rozboru dotazů.

## Víc počítačů

Seznam účtů dej do složky na cloudovém disku (OneDrive, Google Drive, Dropbox, iCloud). Složky klientů a log
změn se počítají relativně k němu, takže všechny počítače sdílí stejná data. Na každém počítači stačí
naklonovat repo, spustit `install.py` a zadat cestu k tomu samému souboru. API klíč (`~/.sklik/sklik.yaml`)
se nesynchronizuje, na každém počítači ho zadáš znovu (stejný klíč, ne nový).

## Rozšíření

Vlastní pravidla a nástroje jde přidat bez úprav tohoto repa: v libovolné složce vytvoř modul `sklik_extras.py`
s proměnnou `INSTRUCTIONS` (text připojený k pokynům pro Clauda) a funkcí `register(mcp, safe)`, která
zaregistruje další nástroje. Cestu ke složce předej instalátoru (`install_claude_config.py --extras CESTA`),
zapíše ji do proměnné `SKLIK_EXTRAS_DIR`.

## Aktualizace

`git pull`, pak znovu `install.py`, nebo jen doinstalovat knihovny:
`.venv/bin/python -m pip install -r requirements.txt` (Windows: `.venv\Scripts\python.exe -m pip install -r requirements.txt`).
Po aktualizaci Claude Desktop úplně ukonči a spusť znovu.

Sklik vydává nové verze API často. Dokumentace metod je v `sklik_docs.json`. `sklik_list_accounts`
a `sklik_api_status` upozorní, když je na webu Skliku novější verze, než ze které dokumentace v MCP pochází.
Dokumentace Fénixu se jednou týdně sama obnoví do `~/.sklik/`.

## Kam tečou data

- **Server sám** běží u tebe na počítači a komunikuje jen s API Skliku. Žádný další server mezi tím není.
- **Přihlašovací údaje** (API klíč v `~/.sklik`) zůstávají na tvém počítači. Server je čte lokálně a do konverzace
  je nikdy nevrací.
- **Výsledky nástrojů jdou do konverzace s Claudem**, tedy k Anthropicu: názvy kampaní, čísla z reportů,
  vyhledávací dotazy, texty reklam i všechno ostatní, co si Claude přečte. Anthropic je zpracovává v USA nebo jinde
  ve světě a pomáhají mu s tím subdodavatelé ([seznam](https://www.anthropic.com/subprocessors)). Co s nimi smí
  dělat, určují podmínky tvého plánu Claude.

### Než to pustíš na klientský účet

1. **Smí data klienta k Anthropicu?** Výkon kampaní, rozpočty nebo tržby nejsou osobní údaje, ale často je chrání
   NDA nebo smlouva s klientem. Ověř si v ní (a ve smlouvě s agenturou, pokud pracuješ přes ni), že data smíš
   předat poskytovateli AI v USA nebo jinde mimo EU, včetně jeho subdodavatelů. Když to smlouva neřeší nebo
   zakazuje, potřebuješ souhlas klienta.
2. **Pracuješ v plánu s obchodními podmínkami?** Claude Team (od dvou míst), Enterprise a API mají smlouvu o
   zpracování osobních údajů (DPA) a Anthropic na datech netrénuje. Free, Pro a Max jsou spotřebitelské plány bez
   DPA a trénování v nich vypíná jen přepínač v nastavení. Na klientská data je nepoužívej.
3. **Jsou v datech osobní údaje?** Nech výchozí `dpa: false` (viz níže). `dpa: true` zapni, jen když máš DPA s
   klientem i s poskytovatelem modelu.
4. **Musí data zůstat v EU?** Claude přímo od Anthropicu zpracování jen v EU nezaručí. Použij Claude Code s modelem
   z Google Cloudu (Agent Platform, region `eu`) nebo z Amazon Bedrocku (evropský inference profil). DPA pak máš s
   Googlem nebo Amazonem a platíš za skutečnou spotřebu. Nastavení přes Google Cloud krok za krokem: [Jak používat
   Claude Code pro práci s firemními a zákaznickými
   daty](https://www.measuredesign.cz/blog/jak-pouzivat-claude-code-pro-praci-s-firemnimi-a-zakaznickymi-daty)
   (MeasureDesign). MCP do Claude Code přidáš takhle:

   ```
   claude mcp add --scope user sklik -- <složka>/.venv/bin/python <složka>/sklik_server.py
   ```

   Na Windows je Python v `<složka>\.venv\Scripts\python.exe`. Pokud máš seznam účtů jinde než ve složce MCP,
   přidej za `--scope user` i `--env SKLIK_ACCOUNTS_FILE=<cesta k sklik_accounts.yaml>`.

Tohle není právní rada. Smlouvy si nech projít od toho, kdo ti je píše.

### Režim s DPA a bez DPA

Osobní údaje by do konverzace měly jít jen tehdy, když máš smlouvu o zpracování osobních údajů (DPA) s klientem i s
poskytovatelem modelu. U Anthropicu je DPA automaticky součástí obchodních podmínek plánů Claude Team, Enterprise a
API, u Clauda přes Google Cloud nebo Amazon Bedrock ji máš s nimi. Plány Free, Pro a Max DPA nemají. Proto má MCP
přepínač v `sklik_accounts.yaml`:

```yaml
dpa: false   # výchozí
```

- **`dpa: false` (výchozí):** MCP do konverzace osobní údaje nepouští. Odmítne
  - přidávání a odebírání e-mailů v seznamech pro e-mailový retargeting,
  - e-mailové adresy ve výstupech (např. přihlašovací e-maily účtů) zamaskuje,
  - vyhledávací dotazy s e-mailem nebo telefonním číslem v rozboru dotazů vynechá (zůstanou jen v lokálním CSV)
    a v ostatních výpisech je zamaskuje.
- **`dpa: true`:** vše povolené. Ochrana chráněných změn a souhlas před zápisem platí v obou režimech.

Aktuální režim ukáže výpis účtů. Omezení: jména a adresy, které lidé píšou do vyhledávání, strojově spolehlivě
poznat nejde, takže je filtr nezachytí. Sklik na rozdíl od Google Ads ukazuje i ojedinělé dotazy, takže se v nich
e-mail nebo telefon občas objeví, zhruba jednou na tisíc dotazů.

## Bezpečnost

- API klíč je v `~/.sklik/sklik.yaml`. Kdo ho má, může pracovat ve všech účtech, kam má tvůj účet přístup.
  Nikam ho nekopíruj, nesdílej a nedávej do synchronizovaných složek ani do gitu.
- **Nikdy negeneruj nový API klíč, pokud už nějaký používáš.** Starý tím přestane platit a s ním všechno,
  co je na něj napojené (jiné nástroje, reporting, druhý počítač).
- Token pro Fénix je v `~/.sklik/fenix.txt` a platí pro něj totéž. Když unikne, smaž ho ve Skliku
  (Nástroje > API) a vytvoř nový.
- Nahrát přes MCP jde jen obrázek (jpg, png, gif, webp) do 10 MB. Jiné soubory z disku MCP odmítne.
- Změny provedené přes API se v historii Skliku zapisují pod účet, kterému patří klíč.
- Log všech provedených změn je ve složce `logs` vedle `sklik_accounts.yaml`.
- MCP je určené k běhu na tvém počítači pro účty, ke kterým máš přístup. Neprovozuj ho jako službu
  pro ostatní, ať si ho každý nainstaluje sám se svým přístupem.

### Uložení klíčů

Klíče a tokeny leží jako obyčejné soubory ve tvé domovské složce (`~/.sklik/`), čitelné jen pro tvého uživatele.
Nejsou zašifrované v trezoru systému (Správce pověření ve Windows, Klíčenka na macOS). Kdo se dostane k tvému
uživatelskému účtu nebo k jeho zálohám, může je přečíst. Proto tuhle složku nezálohuj do cloudu, nesynchronizuj
a nikomu neposílej. Je to stejný přístup, jaký používá oficiální knihovna Google Ads i většina nástrojů
pro příkazovou řádku.

### Podstrčené pokyny (prompt injection)

Do konverzace jdou texty z účtů, které píšou cizí lidé: vyhledávací dotazy, názvy kampaní, texty reklam,
chybové hlášky. Někdo do nich může schovat „pokyn“ pro Clauda. Úplná ochrana proti tomu u AI nástrojů
neexistuje, MCP ale riziko omezuje:

- Claude má v pokynech, že texty z účtů jsou data, ne příkazy.
- Žádná změna se neprovede bez plánu. Chráněné změny jen samostatným nástrojem po výslovném souhlasu.
- MCP sahá jen na povolené účty a nemá nástroj, který by četl libovolné soubory nebo posílal data jinam
  než do API.
- **Doporučení:** v Claude Desktopu nech u nástrojů pro provedení změn (`sklik_apply_change`,
  `sklik_apply_guarded_change`) zapnuté schvalování pokaždé, nepovoluj je natrvalo. Pak se žádná změna
  neprovede bez tvého kliknutí, ani kdyby Clauda něco zmátlo.

Exporty do CSV mají hodnoty začínající `=`, `+`, `-` nebo `@` označené apostrofem, aby je Excel nespustil
jako vzorec. Náhledy v Excelu zapisují všechno jako text.

## Narazil jsi na problém?

Dej mi vědět, opravím to. Každé hlášení pomáhá, protože kód nikdo jiný než já a Claude nekontroloval.

- **Chyba, nesrozumitelný návod, nápad na vylepšení:** založ [issue](https://github.com/martinsevcik1/sklik-mcp/issues).
- **Bezpečnostní problém** (únik klíče nebo tokenu, obejití pojistek, zápis bez souhlasu, přístup k účtu,
  který není povolený): prosím ne do veřejného issue. Napiš mi na
  [martin@sevcikmarketing.com](mailto:martin@sevcikmarketing.com).
- **Pull requesty** beru rád. Jen počítej s tím, že je čtu po práci, takže odpověď může chvíli trvat.

## Pomohlo ti to?

Nástroj je zdarma. Pokud ti ušetřil čas a chceš mi to nějak vrátit, nejvíc mi pomůže
recenze na Google Mapách nebo na Firmy.cz. Stačí pár vět o tom, jak se ti s ním pracuje.
Hvězdička tady na GitHubu taky potěší.

<table>
  <tr>
    <td align="center"><a href="https://search.google.com/local/writereview?placeid=ChIJ-XMER96VEkcRXoq1r8WHRhk"><img src="docs/img/qr-google-review.png" width="160" alt="QR kód: recenze na Google Mapách"></a><br><a href="https://search.google.com/local/writereview?placeid=ChIJ-XMER96VEkcRXoq1r8WHRhk"><b>Recenze na Google</b></a></td>
    <td align="center"><a href="https://www.firmy.cz/detail/13441299-mgr-martin-sevcik-sevcikmarketing-com-brno-stare-brno.html"><img src="docs/img/qr-firmy-cz.png" width="160" alt="QR kód: profil na Firmy.cz"></a><br><a href="https://www.firmy.cz/detail/13441299-mgr-martin-sevcik-sevcikmarketing-com-brno-stare-brno.html"><b>Recenze na Firmy.cz</b></a></td>
  </tr>
</table>

Díky!

## Autor a licence

[Martin Ševčík](https://sevcikmarketing.com). Kód je pod licencí [MIT](LICENSE):
můžeš ho používat, upravovat i dál šířit, i komerčně, bez záruky.
