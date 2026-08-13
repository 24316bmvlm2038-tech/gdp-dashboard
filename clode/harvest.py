"""Collect facts from the web into a reviewable database.

The corpus this model trains on is true by construction: capitals come from a
table, arithmetic is computed, spellings are derived from the word itself.
Nothing in it can be wrong. Pouring scraped prose into that would throw the
property away — the model would state whatever a page said, in its own voice,
with no way to tell where it came from.

So this harvester does not scrape prose. It reads *structured* endpoints
(Wikipedia's REST summary API, which returns a short factual extract per
topic), turns each into a question and answer pair in the same shape as the
rest of the corpus, and records where it came from and when. Every harvested
fact keeps its source URL, so any claim the model makes from this data can be
traced back to a page.

Being a well-behaved client is part of the job, not a nicety:

* ``robots.txt`` is fetched once per host and honoured.
* Requests to a host are spaced by ``MIN_INTERVAL`` seconds.
* Each cycle is bounded — this collects steadily, it does not hammer.

The database is ``data/harvested.json``. It is reviewable and diffable on
purpose: harvested facts are the one part of the corpus a human should be
able to read before the model learns it.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / 'data' / 'harvested.json'

USER_AGENT = 'ClodeMiniHarvester/1.0 (educational language model project)'
MIN_INTERVAL = 2.0        # seconds between requests to the same host
TIMEOUT = 15
SUMMARY_API = 'https://en.wikipedia.org/api/rest_v1/page/summary/'

# Topics worth knowing that the hand-written tables do not cover. The harvester
# walks this list; each entry becomes a "what is X" pair if the source has a
# usable extract.
SEED_TOPICS = [
    'Photosynthesis', 'Plate tectonics', 'Antibiotic', 'Vaccine', 'Democracy',
    'Renaissance', 'Industrial Revolution', 'Silk Road', 'Printing press',
    'Great Barrier Reef', 'Amazon rainforest', 'Sahara', 'Mount Everest',
    'Pacific Ocean', 'Nile', 'Volcano', 'Earthquake', 'Glacier', 'Monsoon',
    'Photosynthesis', 'Mitochondrion', 'Immune system', 'Antibody', 'Neuron',
    'Gravity', 'Electricity', 'Magnetism', 'Radioactivity', 'Periodic table',
    'Algebra', 'Geometry', 'Probability', 'Prime number', 'Pi',
    'Internet', 'World Wide Web', 'Encryption', 'Operating system', 'Database',
    'Machine learning', 'Neural network', 'Computer vision', 'Robotics',
    'Solar System', 'Galaxy', 'Black hole', 'Supernova', 'Comet', 'Telescope',
]


class HarvestError(RuntimeError):
    """A fetch could not be completed."""


@dataclass
class Fact:
    """One harvested question and answer, with where it came from."""

    question: str
    answer: str
    source: str
    topic: str
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec='seconds'))

    def key(self) -> str:
        return self.question.strip().lower()


class PoliteFetcher:
    """Fetches URLs while respecting robots.txt and a per-host rate limit."""

    def __init__(self, user_agent: str = USER_AGENT, min_interval: float = MIN_INTERVAL):
        self.user_agent = user_agent
        self.min_interval = min_interval
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last_request: dict[str, float] = {}

    def _robots_for(self, host_root: str):
        if host_root not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(urllib.parse.urljoin(host_root, '/robots.txt'))
            try:
                parser.read()
            except Exception:
                # A robots.txt we cannot read is not permission to ignore it,
                # but it is also not a reason to stop: treat it as unknown and
                # let the caller decide by keeping the rate limit.
                self._robots[host_root] = None
            else:
                self._robots[host_root] = parser
        return self._robots[host_root]

    def allowed(self, url: str) -> bool:
        parts = urllib.parse.urlparse(url)
        root = f'{parts.scheme}://{parts.netloc}'
        parser = self._robots_for(root)
        if parser is None:
            return True
        return parser.can_fetch(self.user_agent, url)

    def _wait_turn(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            remaining = self.min_interval - (time.monotonic() - last)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request[host] = time.monotonic()

    def get(self, url: str) -> str:
        if not self.allowed(url):
            raise HarvestError(f'robots.txt disallows {url}')
        host = urllib.parse.urlparse(url).netloc
        self._wait_turn(host)
        request = urllib.request.Request(url, headers={'User-Agent': self.user_agent,
                                                       'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                charset = response.headers.get_content_charset() or 'utf-8'
                return response.read().decode(charset, errors='replace')
        except urllib.error.HTTPError as exc:
            raise HarvestError(f'HTTP {exc.code} for {url}') from exc
        except urllib.error.URLError as exc:
            raise HarvestError(f'could not reach {url}: {exc.reason}') from exc
        except OSError as exc:
            raise HarvestError(f'network error for {url}: {exc}') from exc


def first_sentence(text: str, limit: int = 240) -> str:
    """The opening sentence, which is where these extracts state the fact."""
    text = ' '.join(text.split())
    for end in ('. ', '.\n'):
        index = text.find(end)
        if 0 < index < limit:
            return text[:index + 1]
    return text[:limit].rstrip() + ('.' if text and not text.endswith('.') else '')


def fact_from_summary(topic: str, payload: dict) -> Fact | None:
    """Turn one summary response into a question and answer pair."""
    extract = (payload.get('extract') or '').strip()
    if not extract:
        return None
    title = (payload.get('title') or topic).strip()
    source = ((payload.get('content_urls') or {}).get('desktop') or {}).get('page') \
        or f'{SUMMARY_API}{urllib.parse.quote(topic)}'
    answer = first_sentence(extract)
    if len(answer.split()) < 5:
        return None
    return Fact(question=f'what is {title.lower()}', answer=answer,
                source=source, topic=title)


def load_database(path: Path = DATABASE) -> list[Fact]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return []
    return [Fact(**entry) for entry in raw]


def save_database(facts: list[Fact], path: Path = DATABASE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(f) for f in facts], indent=1, ensure_ascii=False),
                    encoding='utf-8')


def harvest(topics: list[str], fetcher: PoliteFetcher | None = None,
            existing: list[Fact] | None = None, limit: int = 20):
    """Yield ``(topic, Fact | HarvestError)`` for topics not already collected.

    Topics already in the database are skipped rather than refetched — the
    point is to grow the database over many short cycles, not to re-read the
    same pages forever.
    """
    fetcher = fetcher or PoliteFetcher()
    seen = {f.key() for f in (existing or [])}
    collected = 0
    for topic in topics:
        if collected >= limit:
            return
        question = f'what is {topic.lower()}'
        if question in seen:
            continue
        url = f'{SUMMARY_API}{urllib.parse.quote(topic.replace(" ", "_"))}'
        try:
            payload = json.loads(fetcher.get(url))
        except HarvestError as exc:
            yield topic, exc
            continue
        except json.JSONDecodeError as exc:
            yield topic, HarvestError(f'malformed response for {topic}: {exc}')
            continue
        fact = fact_from_summary(topic, payload)
        if fact is None:
            yield topic, HarvestError(f'no usable extract for {topic}')
            continue
        seen.add(fact.key())
        collected += 1
        yield topic, fact


def merge(existing: list[Fact], new: list[Fact]) -> list[Fact]:
    """Add facts that are not already present, keeping the earlier version."""
    by_key = {f.key(): f for f in existing}
    for fact in new:
        by_key.setdefault(fact.key(), fact)
    return list(by_key.values())


def as_pairs(facts: list[Fact]) -> list[tuple[str, str]]:
    """Harvested facts in the same shape the corpus generators produce."""
    pairs: list[tuple[str, str]] = []
    for fact in facts:
        pairs.append((fact.question, fact.answer))
        pairs.append((f'tell me about {fact.topic.lower()}', fact.answer))
    return pairs
