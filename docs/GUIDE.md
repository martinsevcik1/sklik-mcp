# Guide: Sklik MCP from scratch

Česky: [NAVOD.md](NAVOD.md)

Allow about 15 minutes. The Sklik interface is in Czech, so menu names below are given in Czech with an English
translation in brackets.

---

## 1. Sklik account and access to clients

The Sklik API works under the account the API key belongs to. That account needs access to the client accounts
you want to work with. Always use **your own** account and your own key, not someone else's: every change made
through the API is recorded in Sklik's history under the key's owner.

Your options:

- **Agency account:** clients are linked to your agency account, and the agency account's key sees all of them.
- **Shared access:** the client gives your Seznam account access in their Sklik
  (in the client's Sklik: Nastavení > Přístupy / Správa přístupů, i.e. Settings > Access). To make changes you
  need access with editing rights.
- **Your own account:** the MCP also works with your own account, the one the key belongs to.

If you don't have a Seznam account yet, create one at https://registrace.seznam.cz and sign in at
https://www.sklik.cz.

---

## 2. API key

1. Sign in at https://www.sklik.cz.
2. Click your profile in the top right corner > **Nastavení** (Settings).
3. The API key section is at the bottom of the page.
   - **You already have a key:** click **Zkopírovat** (Copy).
   - **You don't have a key yet:** generate one and copy it.

**Careful: if you already have a key, DON'T generate a new one.** Generating a new key invalidates the current
one, and with it everything that runs on it (other tools, reports, the MCP on your other computer).

Don't send the key anywhere or give it to anyone. Whoever has it can work in every account your account can
access.

### Token for the Fénix API (optional)

Sklik has two APIs. **Drak**, with the key above, covers most of the work. The newer **Fénix** is needed for
smart campaigns and smart ads, uploading images to the library, switching campaigns on and off, and SEM
conversions. Fénix has its own token; the Drak key doesn't work there.

1. In Sklik, open **Nástroje > API** (Tools > API) and create a new token.
2. **Access level:** `rw` (read and write). Admin rights (`rwa`) aren't needed, and `r` isn't enough for changes.
3. **Validity:** your choice. When it expires, create a new one and just enter it again (see below).
4. Copy the token. You'll paste it into the installer in step 4.

Creating a new Fénix token doesn't invalidate your Drak key; the two are independent.

---

## 3. Python and Claude Desktop

**Claude Desktop:** https://claude.ai/download, install it, start it at least once and sign in.

**Python 3.10 or newer:**

- **Windows:** https://www.python.org/downloads/ > installer. On the first screen, tick
  **Add python.exe to PATH**. Check in PowerShell: `py --version`
- **macOS:** https://www.python.org/downloads/ > macOS installer. Then in Applications > Python 3.x, run
  **Install Certificates.command** (without it, API connections fail with an SSL certificate error).
  Check in Terminal: `python3 --version`

**Git** (optional): Windows https://git-scm.com/download/win; on macOS, `git --version` offers to install it.
Without git, use **Code > Download ZIP** on the repository page and unzip it.

---

## 4. Download and install

Windows (PowerShell):

```
cd $HOME\Documents
mkdir mcp -ErrorAction SilentlyContinue; cd mcp
git clone https://github.com/martinsevcik1/sklik-mcp.git
cd sklik-mcp
py install.py
```

macOS (Terminal):

```
mkdir -p ~/Documents/mcp && cd ~/Documents/mcp
git clone https://github.com/martinsevcik1/sklik-mcp.git
cd sklik-mcp
python3 install.py
```

The installer asks step by step (in Czech for now). You can skip any step and run `install.py` again:

1. **Libraries:** creates `.venv` and installs the packages it needs.
2. **Where the account list should live:** Enter = in the repo folder. If you use more than one computer, enter
   a path to a folder on a cloud drive (see step 6).
3. **API key:** paste the key from step 2 (it isn't shown as you type) and press Enter. It's saved to
   `~/.sklik/sklik.yaml`.
4. **Choosing accounts:** lists every account the key can access, numbered. Type the numbers of the accounts the
   MCP should work with (for example `1,3,5-8` or `vse` for all). Confirm the name and client folder for each
   (Enter = the suggested one).
5. **Fénix API (optional):** paste the token from step 2 (Token for the Fénix API). The installer checks it and
   saves it to `~/.sklik/fenix.txt`. The MCP works without it, just without smart campaigns and the other Fénix
   features.
6. **Claude Desktop config:** adds the server to the configuration (after backing it up).

Then **quit Claude Desktop completely** (Windows: including the icon next to the clock; macOS: Cmd+Q) and start
it again. In a conversation, type something like "list my Sklik accounts".

You can add more accounts at any time: run `install.py` again (the key and account steps), or run
`sklik_setup.py` from the repo root (Windows: `.venv\Scripts\python.exe sklik_setup.py`, macOS:
`.venv/bin/python sklik_setup.py`). Enter a new Fénix token (after it expires, for example) with
`sklik_setup.py --fenix`.
You can also edit the list in a text editor; changes apply straight away without a restart. It also holds the
`dpa` switch (see the README, section DPA mode). Leave it `false` unless you have a data processing agreement
with both the client and the model provider (Claude Team, Enterprise or the API, or Claude through Google Cloud
or Amazon Bedrock).

---

## 5. First steps

- "How has Sklik done for client X over the last 30 days?"
- "Go through the Sklik search terms for client X and suggest negatives."
- "Which Sklik API methods are there for retargeting?"

Claude always shows you a plan of the change first. It makes ordinary changes after your "yes"; protected ones
(budgets, statuses, CPC, removals, settings...) need explicit approval of the specific plan.

---

## 6. A second computer

1. Put the account list in a folder on a cloud drive you have on both computers. The client folders and the
   change log are created next to it.
2. On the second computer, repeat steps 3 and 4, and enter the path to the same file for the account list.
3. Enter the **same** API key (Zkopírovat/Copy, not generate) and the Fénix token if you use it. Don't copy or
   sync the `~/.sklik` folder between computers.

---

## 7. Troubleshooting

| Problem | What to do |
|---|---|
| Sign-in failed (401) | The key was copied wrongly, or a new one has been generated since. Run `sklik_setup.py` and enter the current key. |
| Fénix: missing token or HTTP 401 | The Fénix token is missing or has expired. Create a new one (Nástroje > API, `rw`) and enter it with `sklik_setup.py --fenix`. |
| Account not in sklik_accounts.yaml | The MCP only works with allowed accounts. Add it with `sklik_setup.py`. |
| 403 / insufficient rights | Your account only has read access to the client's account. Ask the client for editing rights. |
| 429 / too many requests | Sklik limits the number of calls per minute. The MCP retries on its own; with big reports, wait a moment. |
| Claude doesn't see the tools | Quit Claude Desktop completely and start it again. Check that `install_claude_config.py` printed "Zapsáno" (written). |
| SSL / certificate error on macOS | Run Install Certificates.command from the Python folder in Applications. |
