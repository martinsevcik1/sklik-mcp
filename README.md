# Sklik MCP

**English** | [Čeština](README.cs.md)

A local MCP server that lets Claude (Claude Desktop) read and manage [Sklik](https://www.sklik.cz) accounts, the
ad platform of the Czech search engine Seznam. It covers both Sklik APIs: the whole Drak API (JSON v5, over 200
methods: campaigns, ad groups, ads, banners, keywords, negatives, budgets, retargeting, conversions, reports...)
and the newer Fénix REST API (smart campaigns and smart ads, image uploads, SEM conversions, Seznam Nákupy feeds).
Most of the work can be done from the conversation without the Sklik web interface.

- It runs on your computer with your own API key. Data from the accounts Claude works with does go through your
  conversation with Claude, though (see [Where your data goes](#where-your-data-goes)).
- It only touches accounts you allow in `sklik_accounts.yaml`. Anything else is refused, even reads.
- Every write takes two steps: Claude prepares the change (and validates it as a dry run wherever the API
  supports it), and it only goes live after you approve it.
- Sensitive changes (budgets, statuses, bids, removals, campaign settings, conversions, retargeting) are
  **guarded**: only a separate tool can apply them, and only after you explicitly approve that specific plan.
- Works on Windows and macOS. Needs nothing but Python.

> [!WARNING]
> **Vibe-coded.** I'm not a developer, I'm a marketer. I built this with Claude: most of the code was written by
> AI from my instructions, and I keep refining it in my own work. It works for me, but
> expect bugs, inefficient code and possibly security issues I haven't spotted. Before you point it at accounts
> that matter, read through the code (or have someone who understands it do that), start with one account and
> read every change before you approve it. Use it at your own risk.

The documentation and the tool descriptions are in Czech, as is Sklik itself. The step-by-step guide is
[docs/NAVOD.md](docs/NAVOD.md).

## What you need

- Claude Desktop (Windows or macOS)
- Python 3.10 or newer
- A Sklik (Seznam) account with access to your clients' accounts, and its API key
- Optionally a Fénix API token for smart campaigns, image uploads and SEM conversions

## Quick install

**Without git:** at the top of this page click **Code > Download ZIP**, unzip it (for example to
`Documents/mcp/sklik-mcp`) and double-click `instalovat-windows.bat` (Windows) or `instalovat-mac.command`
(macOS). The launcher finds Python, and offers to install it if it's missing.

**With git:**

```
git clone https://github.com/martinsevcik1/sklik-mcp.git
cd sklik-mcp
```

Windows: `py install.py`, macOS: `python3 install.py`

The installer creates a virtual environment, asks for the Drak API key, lists the accounts the key can access,
lets you pick the ones the MCP may work with, optionally sets up the Fénix token and adds the server to Claude
Desktop. Then quit Claude Desktop completely and start it again.

**Where to get the keys**
- **Drak API key:** in Sklik, your profile (top right) > Settings, at the bottom of the page click Copy.
  **If you already have a key, don't generate a new one**, that would invalidate the existing key and everything
  that uses it.
- **Fénix token:** in Sklik, Tools > API, create a new token with access level `rw` (read and write; admin
  rights aren't needed). You choose its validity; when it expires, create a new one and run
  `sklik_setup.py --fenix`. Creating a Fénix token doesn't affect the Drak key.

## Tools

**Reading and reports**
- `sklik_list_accounts` - allowed accounts
- `sklik_account_overview` - credit, budgets and performance of all campaigns
- `sklik_campaigns` - campaigns and ad groups with IDs
- `sklik_report` - any report (campaigns, groups, ads, banners, keywords, search terms...) with your choice of
  columns, period and granularity; the full result goes to a CSV in the client's folder
- `sklik_search_terms_review`, `sklik_mark_search_terms` - search term review, filtered locally to save context,
  remembers which terms you've already reviewed
- `sklik_call` - any read method of the API

**The whole Drak API**
- `sklik_api_methods` - catalogue of all methods
- `sklik_method_help` - parameters, allowed columns and notes from the official docs for one method
- `sklik_propose_call` - proposal for any write method (create, update, remove, set...); images and banners via
  `@soubor:PATH`
- `sklik_api_status` - API version in the MCP vs. the latest version in the Sklik changelog
- `sklik_reload_code` - reloads the code after you edit it, without restarting Claude Desktop (new tools still
  need a restart)

**Specialised proposals**
- `sklik_propose_negative_keywords` - negatives for one ad group, or for all groups in a campaign
- `sklik_propose_keywords` - keywords for an ad group

**Fénix API (smart campaigns, images, SEM)**
- `sklik_fenix_status` - checks the Fénix token and access to the allowed accounts (never prints the token)
- `sklik_fenix_endpoints`, `sklik_fenix_help` - endpoint catalogue and schemas from the Fénix OpenAPI spec
- `sklik_fenix_call` - reads (campaigns, images, SEM conversions, Nákupy feeds, smart ad copy suggestions)
- `sklik_fenix_propose` - write proposals, validated with `dryRun` where Fénix supports it; applied through
  `sklik_apply_change` / `sklik_apply_guarded_change` like every other plan
- `sklik_fenix_upload_images` - bulk image upload to the account library, returns the image IDs
- `sklik_fenix_import_token` - moves the token from a file to `~/.sklik/fenix.txt`

**Applying changes**
- `sklik_preview_changes`, `sklik_release_preview` - an Excel preview of prepared plans; tick what to apply in
  the Nasadit column
- `sklik_list_pending_changes`, `sklik_discard_change`
- `sklik_apply_change` - regular change
- `sklik_apply_guarded_change` - guarded change, only after explicit approval

## How to use it

Claude bundles related changes in one account into a single plan, so you approve few steps. Example prompts:

- **Search terms:** "Go through Sklik search terms for client X for the last 30 days, suggest negatives and new
  keywords as one plan."
- **Overview:** "How is Sklik doing for client X? Campaigns, spend, conversions, credit."
- **Audit:** "Check Sklik for client X: conversion tracking, structure, impression share, budgets, ads."
- **New campaign or ad group:** "Create a Sklik search campaign for service Y with 3 ad groups, keywords and
  ads." Everything is created paused, enabling it is a guarded change.
- **Reports:** "Export ad group performance by week for the last quarter to CSV."
- **Anything else from the interface:** describe what you want. Claude finds the method in the catalogue, reads
  its help and prepares a proposal.

## Account list and client folders

`sklik_accounts.yaml` (template in `sklik_accounts.example.yaml`, easiest to fill in with `sklik_setup.py`):

```yaml
clients_root: klienti          # relative to the folder with sklik_accounts.yaml
accounts:
  example-shop.cz: {user_id: 1234567, folder: example_shop}
```

The MCP saves reports, previews and search term review state in the client's folder.

## More than one computer

Put the account list in a synced folder (OneDrive, Google Drive, Dropbox, iCloud). Client folders and the change
log are resolved relative to it, so all computers share the same data. On each computer, clone the repo, run
`install.py` and point it to the same file. Keys in `~/.sklik/` are never synced, enter them on each computer
(the same key, not a new one).

## Extensions

You can add your own rules and tools without touching this repo: create a `sklik_extras.py` module in any folder
with an `INSTRUCTIONS` variable (text appended to Claude's instructions) and a `register(mcp, safe)` function
that registers extra tools. Pass the folder to the installer (`install_claude_config.py --extras PATH`), which
stores it in the `SKLIK_EXTRAS_DIR` variable.

## Updating

`git pull`, then run `install.py` again, or just reinstall the libraries:
`.venv/bin/python -m pip install -r requirements.txt` (Windows: `.venv\Scripts\python.exe -m pip install -r requirements.txt`).
Restart Claude Desktop afterwards.

Sklik releases new API versions often. The Drak method docs live in `sklik_docs.json`; `sklik_list_accounts`
and `sklik_api_status` warn you when Sklik has a newer version than the one the docs come from. The Fénix spec
refreshes itself once a week into `~/.sklik/`.

## Where your data goes

- **The server itself** runs on your computer and only talks to the Sklik API. There's no other server in
  between.
- **Tool results go into your conversation with Claude**, i.e. to Anthropic: campaign names, report numbers,
  search terms, ad copy and anything else Claude reads. They're handled like anything else you type into the
  conversation, under the terms of your Claude plan and your privacy settings (including whether conversations
  may be used for model training).
- **Credentials** (the keys in `~/.sklik`) stay on your computer. The server reads them locally and never
  returns them to the conversation.
- You're working with client data. If your contracts with clients or your agency cover this, check that
  processing through a third-party AI tool is fine.

### DPA mode

Personal data should only go into the conversation if you have a data processing agreement (DPA) with Anthropic.
It's part of the commercial terms for Claude Team, Enterprise and the API, but not for Free, Pro and Max.
That's why `sklik_accounts.yaml` has a switch:

```yaml
dpa: false   # default
```

- **`dpa: false` (default):** the MCP keeps personal data out of the conversation. It refuses to add or remove
  emails in email retargeting lists, masks email addresses in outputs (such as account login emails), and in
  search term reviews leaves out terms containing an email or phone number (they stay in the local CSV only) and
  masks them in other outputs.
- **`dpa: true`:** everything is allowed. Guarded changes and approval before every write work the same in both
  modes.

The current mode is shown in the account list. Limitation: names and addresses people type into search can't be
detected reliably, so the filter won't catch them. They're rare in search terms, but can't be ruled out.

## Security

- The Drak API key is in `~/.sklik/sklik.yaml`. Whoever has it can work in every account your Sklik account has
  access to. Don't copy it anywhere, don't share it, and keep it out of synced folders and git.
- **Never generate a new API key if you already use one.** The old one stops working, and so does everything
  connected to it (other tools, reporting, a second computer).
- The Fénix token is in `~/.sklik/fenix.txt` and the same applies. If it leaks, delete it in Sklik (Tools > API)
  and create a new one.
- Only images (jpg, png, gif, webp) up to 10 MB can be uploaded through the MCP. Any other file is refused.
- Changes made through the API show up in Sklik's change history under the account that owns the key.
- The change log is in the `logs` folder next to `sklik_accounts.yaml`.
- This MCP is meant to run on your own computer for accounts you have access to. Don't run it as a service for
  other people, let everyone install it themselves.

### How keys are stored

Keys and tokens are plain files in your home folder (`~/.sklik/`), readable only by your user. They're not
encrypted in the system keychain (Credential Manager on Windows, Keychain on macOS). Anyone with access to your
user account or its backups can read them, so don't back this folder up to the cloud, don't sync it and don't
send it to anyone. It's the same approach the official Google Ads client library and most command-line tools use.

### Prompt injection

Text written by other people goes into the conversation: search terms, campaign names, ad copy, error messages.
Someone could hide an "instruction" for Claude in there. No AI tool can fully prevent that, but the MCP limits
the risk:

- Claude's instructions say that text from the accounts is data, not commands.
- Nothing changes without a plan. Guarded changes need a separate tool and your explicit approval.
- The MCP only touches allowed accounts and has no tool that reads arbitrary files or sends data anywhere but
  the API.
- **Recommendation:** in Claude Desktop, keep the tools that apply changes (`sklik_apply_change`, `sklik_apply_guarded_change`) on
  approval every time, don't allow them permanently. Then nothing changes without your click, even if something
  confuses Claude.

CSV exports prefix values starting with `=`, `+`, `-` or `@` with an apostrophe so Excel doesn't run them as
formulas. Excel previews write everything as text.

## Found a problem?

Let me know and I'll fix it. Every report helps, since nobody but me and Claude has looked at this code.

- **Bugs, unclear docs, ideas:** open an [issue](https://github.com/martinsevcik1/sklik-mcp/issues).
- **Security issues** (a leaked key or token, a way around the safeguards, a write without approval, access to
  an account that isn't allowed): please don't open a public issue. Email me at
  [martin@sevcikmarketing.com](mailto:martin@sevcikmarketing.com).
- **Pull requests** are welcome. I read them after work, so it may take a while.

## Did it help?

The tool is free. If it saved you time and you'd like to give something back, a review on Google Maps or
Firmy.cz helps me the most. A couple of sentences about how it works for you is plenty.
A star here on GitHub is nice too.

<table>
  <tr>
    <td align="center"><a href="https://search.google.com/local/writereview?placeid=ChIJ-XMER96VEkcRXoq1r8WHRhk"><img src="docs/img/qr-google-review.png" width="160" alt="QR code: review on Google Maps"></a><br><a href="https://search.google.com/local/writereview?placeid=ChIJ-XMER96VEkcRXoq1r8WHRhk"><b>Review on Google</b></a></td>
    <td align="center"><a href="https://www.firmy.cz/detail/13441299-mgr-martin-sevcik-sevcikmarketing-com-brno-stare-brno.html"><img src="docs/img/qr-firmy-cz.png" width="160" alt="QR code: profile on Firmy.cz"></a><br><a href="https://www.firmy.cz/detail/13441299-mgr-martin-sevcik-sevcikmarketing-com-brno-stare-brno.html"><b>Review on Firmy.cz</b></a></td>
  </tr>
</table>

Thanks!

## Author and licence

[Martin Ševčík](https://sevcikmarketing.com). The code is under the [MIT](LICENSE) licence: you can use, modify
and redistribute it, commercially too, with no warranty.
