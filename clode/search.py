"""Live web search for the Clode app.

Two very different things are called "web search" here, because the two
backends have very different abilities:

* **Claude API backend** — Claude runs Anthropic's server-side web search tool
  itself. Nothing in this module is involved; see ``clode.backends``.
* **Local model backend** — Clode-mini cannot read the web (a 1,700 word
  vocabulary turns most pages into ``<|unk|>``), so the *app* does the
  searching through this module and shows what it found, attributed to its
  source, rather than pretending the model knew it.

Providers are tried in order of what the environment can actually reach:
Brave and Serper if their API keys are set, otherwise DuckDuckGo's keyless
HTML endpoint.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser

USER_AGENT = 'Mozilla/5.0 (compatible; Clode/1.0; +https://github.com/)'
TIMEOUT = 15


class SearchError(RuntimeError):
    """Raised when a search could not be completed."""


@dataclass
class Result:
    title: str
    url: str
    snippet: str

    def cite(self) -> str:
        host = urllib.parse.urlparse(self.url).netloc or self.url
        return host.removeprefix('www.')


# --------------------------------------------------------------------------
# DuckDuckGo (no API key)
# --------------------------------------------------------------------------

class _DuckDuckGoParser(HTMLParser):
    """Pulls results out of html.duckduckgo.com's markup."""

    def __init__(self):
        super().__init__()
        self.results: list[Result] = []
        self._mode: str | None = None
        self._href = ''
        self._title: list[str] = []
        self._snippet: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        attributes = dict(attrs)
        classes = (attributes.get('class') or '').split()
        if 'result__a' in classes:
            self._mode = 'title'
            self._href = attributes.get('href', '')
            self._title = []
        elif 'result__snippet' in classes:
            self._mode = 'snippet'
            self._snippet = []

    def handle_data(self, data):
        if self._mode == 'title':
            self._title.append(data)
        elif self._mode == 'snippet':
            self._snippet.append(data)

    def handle_endtag(self, tag):
        if tag != 'a' or self._mode is None:
            return
        if self._mode == 'snippet' and self.results:
            self.results[-1].snippet = ' '.join(''.join(self._snippet).split())
        elif self._mode == 'title':
            title = ' '.join(''.join(self._title).split())
            if title:
                self.results.append(Result(title, unwrap_url(self._href), ''))
        self._mode = None


def unwrap_url(href: str) -> str:
    """DuckDuckGo wraps outbound links in a redirect; recover the target."""
    if not href:
        return ''
    if href.startswith('//'):
        href = 'https:' + href
    parsed = urllib.parse.urlparse(href)
    if 'duckduckgo.com' in parsed.netloc and parsed.path.startswith('/l/'):
        target = urllib.parse.parse_qs(parsed.query).get('uddg')
        if target:
            return target[0]
    return href


def _fetch(url: str, data: bytes | None = None, headers: dict | None = None) -> str:
    request = urllib.request.Request(
        url, data=data, headers={'User-Agent': USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            charset = response.headers.get_content_charset() or 'utf-8'
            return response.read().decode(charset, errors='replace')
    except urllib.error.HTTPError as exc:
        raise SearchError(f'search provider returned HTTP {exc.code}') from exc
    except urllib.error.URLError as exc:
        raise SearchError(f'could not reach the search provider: {exc.reason}') from exc
    except OSError as exc:
        raise SearchError(f'network error during search: {exc}') from exc


def duckduckgo(query: str, limit: int) -> list[Result]:
    body = urllib.parse.urlencode({'q': query}).encode()
    html = _fetch('https://html.duckduckgo.com/html/', data=body)
    parser = _DuckDuckGoParser()
    parser.feed(html)
    return [r for r in parser.results if r.url][:limit]


def brave(query: str, limit: int, api_key: str) -> list[Result]:
    url = 'https://api.search.brave.com/res/v1/web/search?' + urllib.parse.urlencode(
        {'q': query, 'count': limit})
    payload = json.loads(_fetch(url, headers={'X-Subscription-Token': api_key,
                                              'Accept': 'application/json'}))
    out = []
    for item in payload.get('web', {}).get('results', [])[:limit]:
        out.append(Result(item.get('title', ''), item.get('url', ''),
                          strip_tags(item.get('description', ''))))
    return out


def serper(query: str, limit: int, api_key: str) -> list[Result]:
    body = json.dumps({'q': query, 'num': limit}).encode()
    payload = json.loads(_fetch('https://google.serper.dev/search', data=body,
                                headers={'X-API-KEY': api_key,
                                         'Content-Type': 'application/json'}))
    out = []
    for item in payload.get('organic', [])[:limit]:
        out.append(Result(item.get('title', ''), item.get('link', ''),
                          item.get('snippet', '')))
    return out


def strip_tags(text: str) -> str:
    return ' '.join(re.sub(r'<[^>]+>', '', text).split())


def provider_name() -> str:
    if os.environ.get('BRAVE_API_KEY'):
        return 'Brave'
    if os.environ.get('SERPER_API_KEY'):
        return 'Serper'
    return 'DuckDuckGo'


def search(query: str, limit: int = 5) -> list[Result]:
    """Run a live search, using whichever provider this machine can reach."""
    query = query.strip()
    if not query:
        raise SearchError('nothing to search for')

    brave_key = os.environ.get('BRAVE_API_KEY')
    serper_key = os.environ.get('SERPER_API_KEY')
    if brave_key:
        return brave(query, limit, brave_key)
    if serper_key:
        return serper(query, limit, serper_key)
    return duckduckgo(query, limit)


def as_context(results: list[Result], budget: int = 600) -> str:
    """Compact the results into something that can precede a prompt."""
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f'[{i}] {r.title} ({r.cite()}): {r.snippet}')
    text = '\n'.join(lines)
    return text[:budget]
