"""Turns an analyzed vulnerability into a runnable CTF challenge.

Asks Claude to produce a minimal, self-contained web app in Python/Flask
that faithfully reproduces the described vulnerability. The challenge is
written to challenges/<id>/ with a README, a flag file, and a run script.
"""
import json
import os
import re
import secrets
import string
from pathlib import Path

from anthropic import Anthropic

from config import Config


GEN_SYSTEM_PROMPT = """You are a senior CTF room designer for a platform in
the tier of TryHackMe / HackTheBox / PortSwigger Web Security Academy.

Your job: take a real-world vulnerability report/blog and ship a
PIXEL-BELIEVABLE CLONE of the target application described in the report,
with the EXACT vulnerability still exploitable via the EXACT exploitation
chain the report's author used. The player should feel like they are
hacking the real company's real product.

=======================
ABSOLUTE IMMERSION RULES (violation = regenerate)
=======================
1. The target web app NEVER contains any of these strings anywhere in any
   HTML, CSS, or JS that the player sees:
     - "challenge", "CTF", "vulnerability", "vulnerable", "payload",
       "example search", "example:", "try this", "hint", "task",
       "capture the flag", "XSS", "SQLi", "injection", "bypass",
       "admin bot", "challenge info", "flag"
   The only acceptable place for any of those words is inside comments
   in the Python source code — NOT in templates, CSS class names, page
   copy, button text, or URL paths.

2. The target web app is a straight clone of the real product. If the
   report targets NASA, the clone has the NASA brand (meatball-style
   inline-SVG, NASA color palette #0B3D91 navy, #FC3D21 red, #FFFFFF,
   with real mission-sounding content: "Artemis I", "JWST", "Parker
   Solar Probe", "Mars 2020", "Apollo Archives"). If banking → clean
   corporate with "Accounts / Transfers / Statements" nav. If GitLab
   clone → orange accents and repo/merge-request nav. Pick the right
   palette from the report target.

3. No "Challenge Info" panel, no "Submit a URL for the admin to visit:"
   as instructive text, no meta commentary. The /report endpoint (or
   equivalent) is styled as "Contact Support" or "Report Broken Link"
   or "Submit Feedback" — whatever makes sense for the cloned product.

4. Every meta-explanation lives ONLY in the mission briefing + tasks
   (returned in JSON). The running web app stays in-character 100%.

=======================
UI PRODUCTION BAR
=======================
- 5+ real pages with working internal navigation. Landing page must
  have: hero section with real-looking imagery (inline SVG, CSS
  gradients, emoji-as-icon if needed), 3–6 feature/mission cards, a
  footer with fake legal links (Privacy, Terms, FOIA, Careers, etc.).
- `static/style.css` must be 350+ lines of real styling that matches
  the cloned brand. No "default browser" look. Proper typography
  (font-family stack, sizes, weights), button states, card hover
  effects, responsive grid, a footer that looks legal-grade.
- Navbar matches the cloned brand (e.g. NASA-style white/blue with
  mission dropdown; GitLab-style with orange accent).
- Content is specific and believable — real-sounding mission names,
  dataset IDs, department names. No "Lorem ipsum". No "Example Item".

=======================
VULNERABILITY FIDELITY (EXACT)
=======================
Replicate the report's exploit chain step-for-step:
- Same vuln class, same root cause, same URL paths mentioned in the
  report, same parameter names, same filter behavior described in the
  report (e.g. if the report says the server strips `<script>` with a
  regex but misses case-variants — implement THAT regex), same bypass
  payload class.
- If the report describes a redirect, reflection inside JS block,
  sanitizer quirk, specific encoding — reproduce exactly.
- If the exploit chain requires an admin visitor, include a background
  thread that polls the feedback/report queue every 3–5 seconds and
  performs an HTTP GET to submitted internal URLs with a cookie that
  contains the flag (cookie named to fit the brand — `SESSION`,
  `admin_token`, `jsessionid`, etc.).
- Never print the flag to stdout. `debug=False` always.

=======================
MISSION BRIEFING + TASKS (player-facing, in JSON only)
=======================
- `briefing`: 2–3 paragraph in-world scenario. Narrative voice. Tells
  the player who they are, who hired them, what the target is, and
  what the objective is. Ends with "Your flag is the value of the
  admin session cookie" or equivalent.

- `tasks`: 4–7 objectives mapping to the EXACT exploitation chain
  from the report. Questions must be specific to THIS exploit — not
  generic. Each answer is a concrete short string the player finds by
  doing the step. Examples calibrated to the actual exploit:
    * "Which URL path reflects user input into a JavaScript context?"
      (answer: `/search` or whatever the report names)
    * "The server rewrites one tag name to itself with suffix. What is
      the replacement?" (answer: the exact string, e.g. `<scriptx>`)
    * "What event handler attribute, on which tag, triggers without
      direct script tag? (tag,attr)" (answer: e.g. `img,onerror`)
    * "Which endpoint queues URLs for the admin to visit?" (answer:
      `/feedback/submit` — matches the cloned brand)
    * "What is the session cookie name that holds the flag?"
  The FINAL task is ALWAYS:
    `{"n": 999, "question": "Submit the flag", "answer": "FLAG_PLACEHOLDER"}`

- `learning_objectives`: 3–5 short bullets about skills practiced.

=======================
TECHNICAL CONSTRAINTS
=======================
- Python 3 + Flask + Jinja2 only. `requests` and stdlib sqlite3 allowed.
  No Docker, no external services, no other DBs, no npm.
- Use render_template, files in `templates/`, CSS in `static/`, loaded via
  url_for.
- App binds to 127.0.0.1 on port {{PORT}} with debug=False.
- Flag is in `flag.txt` at the challenge root (we create it). To read it
  inside the app, use: `open('flag.txt').read().strip()`. Do NOT hardcode
  the flag string in templates or Python — it changes per generation.
- Do not add reverse shells, worms, persistence, or anything that affects
  the host beyond the single demonstrable web vulnerability. Even if the
  real CVE is RCE, contain execution so at worst the player reads
  `flag.txt` from the server.
- Use only stdlib + flask + requests. Background work via threading.Thread
  started lazily on first request.

=======================
OUTPUT SCHEMA
=======================
Return a SINGLE JSON object. No prose, no fences, nothing else.

{
  "name": "evocative room name (e.g. 'Orbital Access')",
  "tagline": "short one-line hook shown on the room card",
  "description": "2-4 sentence in-world scenario, THM-style",
  "difficulty": "Easy | Medium | Hard | Insane",
  "category": "Web | Crypto | Pwn | Misc",
  "brand": {
    "product_name": "name of the fake company/product the challenge imitates",
    "theme_summary": "one-line look-and-feel, e.g. 'dark space portal with monospace accents'"
  },
  "briefing": "full mission briefing paragraph(s)",
  "learning_objectives": ["objective 1", "objective 2", "..."],
  "tasks": [
    {"n": 1, "question": "short question", "answer": "short expected string"},
    {"n": 2, "question": "...", "answer": "..."},
    {"n": 999, "question": "Submit the flag", "answer": "FLAG_PLACEHOLDER"}
  ],
  "hint": "one subtle hint",
  "solve_path": "ordered list of steps describing the intended solve",
  "files": [
    {"path": "app.py", "content": "<full flask app>"},
    {"path": "requirements.txt", "content": "flask\\nrequests\\n"},
    {"path": "templates/base.html", "content": "<shared layout>"},
    {"path": "templates/index.html", "content": "<landing page>"},
    {"path": "templates/<other>.html", "content": "<more pages>"},
    {"path": "static/style.css", "content": "<300+ line theme>"},
    {"path": "README.md", "content": "player-facing intro, not a walkthrough"},
    {"path": "SOLUTION.md", "content": "detailed admin walkthrough"},
    {"path": "flag.txt", "content": "FLAG_PLACEHOLDER"}
  ]
}

For the final task (Submit the flag), keep `"answer": "FLAG_PLACEHOLDER"`
verbatim — the runtime will swap it for the real flag.
"""


GEN_USER_TEMPLATE = """Design a challenge that replicates this vulnerability.

=== STRUCTURED ANALYSIS ===
Title: {title}
Vuln type: {vuln_type}
Severity: {severity}
CVE: {cve}
Affected component: {affected}
Suggested stack: {stack}

Summary:
{summary}

Root cause:
{root_cause}

Exploitation steps:
{steps}

Technical indicators: {indicators}

=== ORIGINAL REPORT TEXT (use this to capture specific URLs, parameter names,
payloads, target branding, and narrative flavor) ===
{report_text}
=== END REPORT TEXT ===

Bind the Flask app to 127.0.0.1:{port} with debug=False.
Return ONLY the JSON object. Make the challenge feel like a real app, not a
scaffold. Preserve the specific URLs / payload shapes from the report where
they are mentioned.
"""


REPORT_CHARS_FOR_GEN = 25_000  # room for rich context without blowing tokens


def _client():
    if not Config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is missing. Put it in .env.")
    return Anthropic(api_key=Config.ANTHROPIC_API_KEY)


def _strip_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


def _make_flag() -> str:
    rand = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(16))
    return f"SecScenario{{{rand}}}"


def _pick_port(used_ports: set[int]) -> int:
    import socket
    # Range is overridable so containerized runs can use a non-overlapping band
    # (e.g. 6100-6500) and coexist with a local `python app.py` on 5100-5500.
    base = int(os.getenv("CHALLENGE_PORT_BASE", "5100"))
    end = int(os.getenv("CHALLENGE_PORT_END", "5500"))
    for p in range(base, end):
        if p in used_ports:
            continue
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.15)
        try:
            s.connect(("127.0.0.1", p))
            # something is listening — skip
            s.close()
            continue
        except Exception:
            s.close()
            return p
    raise RuntimeError("No free challenge ports")


def generate_challenge(analysis: dict, used_ports: set[int], report_text: str = "") -> tuple[dict, Path, str, int]:
    """Ask Claude for a challenge spec, then materialize it on disk.

    Returns (spec, challenge_folder, flag, port).
    """
    port = _pick_port(used_ports)
    flag = _make_flag()

    steps = analysis.get("exploitation_steps") or ""
    if isinstance(steps, list):
        steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))

    trimmed_report = (report_text or "").strip()[:REPORT_CHARS_FOR_GEN]
    if not trimmed_report:
        trimmed_report = "(no original report text available — rely on the structured analysis above)"

    user_msg = GEN_USER_TEMPLATE.format(
        title=analysis.get("title") or "Vulnerability",
        vuln_type=analysis.get("vuln_type") or "unknown",
        severity=analysis.get("severity") or "Medium",
        cve=analysis.get("cve") or "n/a",
        affected=analysis.get("affected_component") or "n/a",
        summary=analysis.get("summary") or "",
        root_cause=analysis.get("root_cause") or "",
        steps=steps,
        indicators=analysis.get("technical_indicators") or "",
        stack=analysis.get("language_stack") or "python/flask",
        port=port,
        report_text=trimmed_report,
    )
    system = GEN_SYSTEM_PROMPT.replace("{{PORT}}", str(port)).replace("{{FLAG}}", flag)

    client = _client()
    # Streaming required at this output budget (may exceed 10-minute sync limit).
    parts: list[str] = []
    with client.messages.stream(
        model=Config.CLAUDE_MODEL,
        max_tokens=32000,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        for chunk in stream.text_stream:
            parts.append(chunk)
    raw = "".join(parts)
    parsed = _strip_json(raw)

    try:
        spec = json.loads(parsed)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Challenge JSON invalid: {e}\n---\n{raw[:600]}")

    # materialize to disk
    challenge_name = _slug(spec.get("name", "challenge"))
    folder = Config.CHALLENGES_DIR / f"{challenge_name}_{port}"
    folder.mkdir(parents=True, exist_ok=True)

    # When running inside Docker the parent process exports CHALLENGE_HOST=0.0.0.0
    # so the spawned challenge is reachable from the host's published port. In
    # local mode the variable is unset and the original 127.0.0.1 bind survives.
    challenge_host = os.getenv("CHALLENGE_HOST", "").strip()

    for f in spec.get("files", []):
        path = folder / f["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        content = f.get("content", "")
        content = content.replace("FLAG_PLACEHOLDER", flag)
        if challenge_host and path.name == "app.py":
            content = re.sub(
                r"""(["'])127\.0\.0\.1\1""",
                f'"{challenge_host}"',
                content,
            )
        path.write_text(content, encoding="utf-8")

    # also write the flag file explicitly in case the model forgot
    flag_path = folder / "flag.txt"
    if not flag_path.exists():
        flag_path.write_text(flag, encoding="utf-8")

    # Replace FLAG_PLACEHOLDER inside task answers too, then save spec for UI
    for t in spec.get("tasks", []) or []:
        if isinstance(t, dict) and t.get("answer") == "FLAG_PLACEHOLDER":
            t["answer"] = flag
    (folder / "spec.json").write_text(
        json.dumps(spec, indent=2), encoding="utf-8"
    )

    # write a run script for convenience
    run_script = folder / "run.bat"
    run_script.write_text(
        f"@echo off\r\ncd /d %~dp0\r\npython -m pip install -r requirements.txt\r\npython app.py\r\n",
        encoding="utf-8",
    )
    (folder / "run.sh").write_text(
        f"#!/usr/bin/env bash\ncd \"$(dirname \"$0\")\"\npython -m pip install -r requirements.txt\npython app.py\n",
        encoding="utf-8",
    )

    return spec, folder, flag, port


def _slug(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return cleaned[:40] or "challenge"
