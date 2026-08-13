"""Tests for the web-fact harvester.

The sandbox this was written in blocks outbound requests, so these cover
everything except the socket: robots.txt being honoured, the per-host rate
limit, extraction, provenance, de-duplication, and that a failure is reported
rather than silently producing an empty fact.
"""

import json
import sys
import time
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clode import harvest as H

SUMMARY = {
    'title': 'Photosynthesis',
    'extract': 'Photosynthesis is a process used by plants to convert light '
               'energy into chemical energy. It is vital for life on Earth.',
    'content_urls': {'desktop': {'page': 'https://en.wikipedia.org/wiki/Photosynthesis'}},
}


def test_extract_uses_the_first_sentence_and_keeps_the_source():
    fact = H.fact_from_summary('Photosynthesis', SUMMARY)
    assert fact.question == 'what is photosynthesis'
    assert fact.answer.endswith('chemical energy.')
    assert 'vital for life' not in fact.answer      # second sentence dropped
    assert fact.source == 'https://en.wikipedia.org/wiki/Photosynthesis'
    assert fact.fetched_at


def test_extract_rejects_empty_or_trivial_payloads():
    assert H.fact_from_summary('X', {'extract': ''}) is None
    assert H.fact_from_summary('X', {'extract': 'A short one.'}) is None


def test_first_sentence_handles_text_without_a_full_stop():
    assert H.first_sentence('no full stop here').endswith('.')


def test_robots_disallow_blocks_the_fetch(monkeypatch):
    class Blocking:
        def set_url(self, url): pass
        def read(self): pass
        def can_fetch(self, agent, url): return False

    monkeypatch.setattr(H.urllib.robotparser, 'RobotFileParser', Blocking)
    fetcher = H.PoliteFetcher()
    with pytest.raises(H.HarvestError) as exc:
        fetcher.get('https://example.com/page')
    assert 'robots.txt' in str(exc.value)


def test_rate_limit_spaces_requests_to_a_host(monkeypatch):
    monkeypatch.setattr(H.PoliteFetcher, 'allowed', lambda self, url: True)
    slept: list[float] = []
    monkeypatch.setattr(H.time, 'sleep', lambda s: slept.append(s))

    clock = {'t': 0.0}
    monkeypatch.setattr(H.time, 'monotonic', lambda: clock['t'])

    class Response:
        headers = type('H', (), {'get_content_charset': staticmethod(lambda: 'utf-8')})()
        def read(self): return b'{}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(H.urllib.request, 'urlopen', lambda *a, **k: Response())
    fetcher = H.PoliteFetcher(min_interval=2.0)
    fetcher.get('https://example.com/a')
    fetcher.get('https://example.com/b')          # immediately after
    assert slept and slept[0] == pytest.approx(2.0)


def test_network_failure_is_reported_per_topic(monkeypatch):
    class Failing(H.PoliteFetcher):
        def get(self, url):
            raise H.HarvestError('could not reach host')

    results = list(H.harvest(['Photosynthesis'], fetcher=Failing(), existing=[]))
    assert len(results) == 1
    topic, outcome = results[0]
    assert topic == 'Photosynthesis'
    assert isinstance(outcome, H.HarvestError)


def test_harvest_skips_topics_already_collected(monkeypatch):
    class Fetching(H.PoliteFetcher):
        def __init__(self):
            super().__init__()
            self.calls = []
        def get(self, url):
            self.calls.append(url)
            return json.dumps(SUMMARY)

    fetcher = Fetching()
    already = [H.Fact('what is photosynthesis', 'known', 'src', 'Photosynthesis')]
    results = list(H.harvest(['Photosynthesis'], fetcher=fetcher, existing=already))
    assert results == []
    assert fetcher.calls == []


def test_harvest_respects_the_per_cycle_limit():
    class Fetching(H.PoliteFetcher):
        def get(self, url):
            return json.dumps(SUMMARY)

    topics = [f'Topic{i}' for i in range(10)]
    results = list(H.harvest(topics, fetcher=Fetching(), existing=[], limit=3))
    assert len(results) == 3


def test_merge_keeps_existing_and_adds_new():
    old = [H.Fact('what is a', 'first answer', 's1', 'A')]
    new = [H.Fact('what is a', 'second answer', 's2', 'A'),
           H.Fact('what is b', 'b answer', 's3', 'B')]
    merged = H.merge(old, new)
    answers = {f.question: f.answer for f in merged}
    assert answers['what is a'] == 'first answer'   # not overwritten
    assert answers['what is b'] == 'b answer'


def test_database_round_trip(tmp_path):
    path = tmp_path / 'harvested.json'
    facts = [H.Fact('what is x', 'X is a thing.', 'https://example.com', 'X')]
    H.save_database(facts, path)
    back = H.load_database(path)
    assert back[0].question == 'what is x'
    assert back[0].source == 'https://example.com'


def test_corrupt_database_does_not_crash(tmp_path):
    path = tmp_path / 'harvested.json'
    path.write_text('{ not json')
    assert H.load_database(path) == []


def test_pairs_are_corpus_shaped():
    facts = [H.Fact('what is photosynthesis', 'It is a process.', 's', 'Photosynthesis')]
    pairs = H.as_pairs(facts)
    assert ('what is photosynthesis', 'It is a process.') in pairs
    assert ('tell me about photosynthesis', 'It is a process.') in pairs
