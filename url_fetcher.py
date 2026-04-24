"""Fetches a blog post or vulnerability report URL and returns its text.

Handles:
- Generic blog posts (Medium, dev.to, personal security blogs)
- HackerOne public disclosed reports (incl. .json fallback)
- Bugcrowd crowdstream / disclosures
- YesWeHack public reports
- Intigriti public reports
- Google Bug Hunters writeups
- Anything else behind a plain-HTML fetch

Limitations:
- Login-gated content returns only what is publicly visible.
- Heavily JS-rendered SPAs may return very little — the analyzer
  will then have little to work with. We surface whatever we can.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "close",
}

# Free reader service used as fallback when the site blocks us.
# Returns plain markdown of the article. No API key required.
JINA_READER = "https://r.jina.ai/"

TIMEOUT = 25
MAX_BYTES = 4 * 1024 * 1024  # 4 MB
MIN_USEFUL_CHARS = 600

PLATFORMS = {
    "hackerone.com": "hackerone",
    "bugcrowd.com": "bugcrowd",
    "yeswehack.com": "yeswehack",
    "intigriti.com": "intigriti",
    "bughunters.google.com": "google_bbp",
    "medium.com": "medium",
    "dev.to": "devto",
}


@dataclass
class FetchResult:
    url: str
    final_url: str
    platform: str
    title: str
    text: str
    raw_html: str


def is_valid_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in {"http", "https"} and bool(p.netloc)
    except Exception:
        return False


def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().lstrip("www.")
    for key, name in PLATFORMS.items():
        if host == key or host.endswith("." + key):
            return name
    return "generic"


def fetch_url(url: str) -> FetchResult:
    if not is_valid_url(url):
        raise ValueError("Invalid URL. Must start with http:// or https://")

    platform = detect_platform(url)

    # Route-specific strategies
    if platform == "hackerone":
        try:
            return _fetch_hackerone(url)
        except Exception:
            pass

    # Try direct fetch first; fall back to reader service on blocks.
    try:
        result = _fetch_generic(url, platform)
        if result.text and len(result.text) >= MIN_USEFUL_CHARS:
            return result
        # content too thin — try reader
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", 0)
        if status not in (401, 403, 404, 406, 429, 451, 500, 502, 503, 520, 522, 525):
            raise
    except Exception:
        pass

    return _fetch_via_reader(url, platform)


def _http_get(url: str) -> requests.Response:
    r = requests.get(url, headers=DEFAULT_HEADERS, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    return r


def _truncate_bytes(r: requests.Response) -> str:
    # Avoid absurdly large pages
    content = r.content[:MAX_BYTES]
    enc = r.encoding or "utf-8"
    try:
        return content.decode(enc, errors="ignore")
    except LookupError:
        return content.decode("utf-8", errors="ignore")


def _fetch_generic(url: str, platform: str) -> FetchResult:
    r = _http_get(url)
    html = _truncate_bytes(r)
    title, text = _extract_main_text(html)
    return FetchResult(
        url=url,
        final_url=str(r.url),
        platform=platform,
        title=title,
        text=text,
        raw_html=html,
    )


def _fetch_via_reader(url: str, platform: str) -> FetchResult:
    """Fetch via r.jina.ai — a free reader that returns clean markdown text.

    Used when the direct fetch is blocked (403/429) or returns too little.
    Respects the original URL; the reader service fetches it and returns text.
    """
    reader_url = JINA_READER + url
    try:
        r = requests.get(
            reader_url,
            headers={
                "User-Agent": UA,
                "Accept": "text/plain, text/markdown, */*",
                # request clean content mode
                "X-Return-Format": "markdown",
            },
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        r.raise_for_status()
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", "?")
        raise RuntimeError(
            f"The site blocked the direct fetch, and the reader fallback also failed "
            f"({status}). Save the page as PDF or HTML and upload the file instead."
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"The site blocked the direct fetch, and the reader fallback is unreachable "
            f"({e}). Save the page as PDF or HTML and upload the file instead."
        ) from e

    text = r.text or ""
    title = ""
    # r.jina.ai returns a header block like "Title: ...\nURL Source: ...\nMarkdown Content:"
    m = re.search(r"^Title:\s*(.+)$", text, re.MULTILINE)
    if m:
        title = m.group(1).strip()

    if len(text.strip()) < MIN_USEFUL_CHARS:
        raise RuntimeError(
            "The reader returned too little content — the page may be paywalled "
            "or require login. Upload the report as a file instead."
        )

    return FetchResult(
        url=url,
        final_url=url,
        platform=platform,
        title=title,
        text=text.strip(),
        raw_html="",
    )


def _fetch_hackerone(url: str) -> FetchResult:
    """HackerOne public reports render via JS. Try the .json twin first."""
    # normalize e.g. https://hackerone.com/reports/123456
    m = re.match(r"^(https?://hackerone\.com/reports/\d+)", url, re.IGNORECASE)
    if m:
        base = m.group(1)
        try:
            r = requests.get(
                base + ".json",
                headers={**DEFAULT_HEADERS, "Accept": "application/json"},
                timeout=TIMEOUT,
            )
            if r.ok and r.headers.get("content-type", "").startswith("application/json"):
                data = r.json()
                title = data.get("title") or f"HackerOne Report"
                parts = [f"Title: {title}"]
                if data.get("severity_rating"):
                    parts.append(f"Severity: {data['severity_rating']}")
                if data.get("state"):
                    parts.append(f"State: {data['state']}")
                if data.get("disclosed_at"):
                    parts.append(f"Disclosed: {data['disclosed_at']}")
                if data.get("weakness", {}).get("name"):
                    parts.append(f"Weakness: {data['weakness']['name']}")
                body = data.get("vulnerability_information") or data.get("body") or ""
                parts.append("\n--- Report body ---\n")
                parts.append(body)
                return FetchResult(
                    url=url,
                    final_url=r.url,
                    platform="hackerone",
                    title=title,
                    text="\n".join(parts),
                    raw_html="",
                )
        except Exception:
            pass
    # fall through to generic HTML parse
    return _fetch_generic(url, "hackerone")


def _extract_main_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    # title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()

    # drop noise
    for tag in soup(["script", "style", "noscript", "iframe", "nav", "footer",
                     "header", "aside", "form", "svg"]):
        tag.decompose()

    # prefer main content containers
    candidates = []
    for sel in ["article", "main", '[role="main"]', ".post", ".content", ".markdown-body", "#content"]:
        for el in soup.select(sel):
            candidates.append(el.get_text("\n", strip=True))

    body_text = "\n\n".join(t for t in candidates if t)

    # fallback: full body text
    if len(body_text) < MIN_USEFUL_CHARS:
        body = soup.body or soup
        body_text = body.get_text("\n", strip=True)

    # collapse excessive blank lines
    body_text = re.sub(r"\n{3,}", "\n\n", body_text).strip()
    return title, body_text
