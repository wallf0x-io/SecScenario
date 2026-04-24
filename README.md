# SecScenario

Localhost tool that turns vulnerability reports/blogs into runnable CTF challenges.

**Pipeline:** Upload report → Claude analyzes the vulnerability → Claude generates a minimal, runnable Flask web app that faithfully reproduces it → you exploit it locally to retrieve the flag.

> **Scope:** Localhost-only, for personal security education and authorized research.
> Don't expose SecScenario (or its generated challenges) to the public internet.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up your API key
    # Copy .env.example → .env and fill in your key
    # (Get one at https://console.anthropic.com/settings/keys)
    # You must also have credits on that account:
    # https://console.anthropic.com/settings/billing

# 3. Run the app
python app.py

# 4. Open in browser
# http://127.0.0.1:5000
```

---

## Features

- **File & folder upload** — drag & drop single files or whole folders. Supports PDF, Markdown, HTML, TXT, JSON, RST, LOG, and ZIPs.
- **Automatic text extraction** from each format (PDF via `pypdf`, Markdown/HTML via BeautifulSoup, ZIP recursive walk).
- **Claude-powered analysis** — extracts vuln type, severity, CVE, root cause, exploitation steps into a structured record.
- **Auto-generated CTF** — Claude designs a self-contained Flask vulnerable web app that reproduces the report. Written to `challenges/<name>_<port>/`.
- **Per-challenge port allocation** (5100–5499) so multiple challenges can run side by side.
- **Source browser** for every generated challenge, right in the dashboard.

---

## Project layout

```
SecScenario/
├── app.py                 # Flask entrypoint + routes
├── config.py              # Env-driven configuration
├── database.py            # SQLite models/queries
├── extractor.py           # PDF/MD/HTML/ZIP → plain text
├── analyzer.py            # Claude call #1: vulnerability analysis
├── challenge_generator.py # Claude call #2: challenge materialization
├── templates/             # Jinja2 pages (dashboard/upload/report/challenge)
├── static/                # CSS + JS
├── uploads/               # (gitignored) your uploaded reports
├── challenges/            # (gitignored) generated CTF apps
└── instance/secscenario.db
```

---

## Running a generated challenge

Each generated challenge is self-contained. From its folder:

```bash
cd challenges/<name>_<port>
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:<port>`. Solve the vulnerability to retrieve the flag.

`SOLUTION.md` inside each challenge folder documents the intended solve.

---

## Troubleshooting

- **"credit balance is too low"** — add billing at console.anthropic.com.
- **"ANTHROPIC_API_KEY is missing"** — check `.env` has a real key (not the placeholder).
- **Upload fails (413)** — file exceeds 100 MB. Adjust `MAX_CONTENT_LENGTH` in `config.py`.
- **Port already in use** — another process is on 5000. Change `FLASK_PORT` in `.env`.

---

## Security notes

- The app binds only to `127.0.0.1`. Do not change this unless you know what you're doing.
- Generated challenges contain **intentionally vulnerable code**. Run them only on localhost.
- Uploaded files are saved unmodified under `uploads/`. Don't upload data you wouldn't otherwise trust on disk.
- The Anthropic API key lives in `.env` which is gitignored. Never commit `.env`.
