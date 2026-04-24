"""Claude-powered vulnerability analyzer.

Takes raw text from a report/blog and returns a structured understanding
of the vulnerability: type, root cause, affected component, exploitation
steps, etc. The output feeds into the challenge generator.
"""
import json
import re
from anthropic import Anthropic

from config import Config


MAX_INPUT_CHARS = 120_000

ANALYSIS_SYSTEM_PROMPT = """You are a senior application security engineer.
Your job: read a vulnerability blog post or security report and extract a
precise technical understanding of the vulnerability so another engineer can
reproduce it as a CTF challenge.

Respond with a SINGLE JSON object and nothing else. No prose, no code fences.

Required JSON schema:
{
  "title": "short human-readable title",
  "vuln_type": "e.g. SQL Injection, Server-Side Template Injection, SSRF, XXE, Auth Bypass, Deserialization, Path Traversal, RCE, XSS, IDOR, etc.",
  "severity": "Critical | High | Medium | Low",
  "cve": "CVE id if present, else null",
  "affected_component": "software/library/version affected",
  "summary": "2-4 sentence plain-English explanation",
  "root_cause": "what specifically in the code/design causes it",
  "exploitation_steps": "numbered, concrete steps an attacker takes",
  "technical_indicators": ["keywords", "endpoints", "parameters", "payloads mentioned"],
  "language_stack": "likely language/framework to reproduce (python/flask, node/express, php, java/spring, etc.)",
  "challenge_feasibility": "yes | partial | no — can this be reproduced locally as a self-contained web challenge?",
  "feasibility_notes": "why / what's needed"
}
"""


ANALYSIS_USER_TEMPLATE = """Analyze the following vulnerability report and
return the JSON described in your system instructions.

===== REPORT BEGIN =====
{report}
===== REPORT END =====
"""


def _client():
    if not Config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is missing. Put it in .env.")
    return Anthropic(api_key=Config.ANTHROPIC_API_KEY)


def _strip_json(text: str) -> str:
    """Best-effort: pull the JSON object out of the model response."""
    text = text.strip()
    # strip ``` fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # grab the first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


def analyze_report(report_text: str) -> tuple[dict, str]:
    """Returns (parsed_dict, raw_response_text)."""
    if not report_text or not report_text.strip():
        raise ValueError("Empty report text")

    trimmed = report_text[:MAX_INPUT_CHARS]
    client = _client()

    response = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=4000,
        system=ANALYSIS_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": ANALYSIS_USER_TEMPLATE.format(report=trimmed)}
        ],
    )

    raw = "".join(block.text for block in response.content if block.type == "text")
    parsed_json = _strip_json(raw)

    try:
        data = json.loads(parsed_json)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude did not return valid JSON: {e}\n---\n{raw[:500]}")

    # normalize exploitation_steps if returned as list
    if isinstance(data.get("exploitation_steps"), list):
        data["exploitation_steps"] = "\n".join(
            f"{i+1}. {step}" for i, step in enumerate(data["exploitation_steps"])
        )
    if isinstance(data.get("technical_indicators"), list):
        data["technical_indicators"] = ", ".join(data["technical_indicators"])

    return data, raw
