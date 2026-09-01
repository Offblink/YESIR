"""Web tools: fetch a page as text, and search via Brave Search HTML scraping.

The Brave choice (and its tradeoffs) is documented in README.md — it is the only
major engine that returns server-rendered results to bare HTTP requests.
"""

import html as html_mod
import re
import urllib.error
import urllib.request
from urllib.parse import quote

WEB_TIMEOUT = 15
SEARCH_TIMEOUT = 10
WEB_TRUNCATE = 12000
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _strip_html(markup: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>", "", markup)
    text = re.sub(r"(?is)<style.*?</style>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_mod.unescape(text)
    text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)
    text = re.sub(r"(?m)^[ \t]+", "", text)
    return text.strip()


def _truncate_middle(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n\n... [truncated {len(text) - limit} chars] ...\n\n{text[-half:]}"


def _fetch(url: str, timeout: int) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        raw = resp.read()
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def tool_web(url: str) -> str:
    if not re.match(r"^https?://", url):
        url = f"https://{url}"
    try:
        text = _strip_html(_fetch(url, WEB_TIMEOUT))
    except urllib.error.HTTPError as exc:
        return f"ERROR: Web fetch failed: HTTP {exc.code}"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        return f"ERROR: Web fetch failed: {reason}"
    return _truncate_middle(text, WEB_TRUNCATE)


def tool_web_search(query: str) -> str:
    url = f"https://search.brave.com/search?q={quote(query)}"
    try:
        text = _strip_html(_fetch(url, SEARCH_TIMEOUT))
    except urllib.error.HTTPError as exc:
        return f"ERROR: Search failed: HTTP {exc.code}"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        return f"ERROR: Search failed: {reason}"
    if len(text) < 50:
        return f"(no results for '{query}')"
    return _truncate_middle(text, WEB_TRUNCATE)
