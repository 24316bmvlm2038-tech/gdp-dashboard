"""Tests for the web-search layer.

The network is not available in CI (and is blocked in the sandbox this was
developed in), so these tests cover everything except the socket: result
parsing, DuckDuckGo's redirect wrapping, provider selection, and that a
failure surfaces as a clear SearchError rather than an empty answer.
"""

import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clode import search as S

# Trimmed from html.duckduckgo.com's response markup.
DDG_HTML = """
<div class="results">
  <div class="result results_links">
    <h2 class="result__title">
      <a rel="nofollow" class="result__a"
         href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FTokyo&amp;rut=abc">
         Tokyo - Wikipedia</a>
    </h2>
    <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FTokyo">
      Tokyo is the <b>capital</b> and most populous city of Japan.</a>
  </div>
  <div class="result results_links">
    <h2 class="result__title">
      <a rel="nofollow" class="result__a" href="https://www.britannica.com/place/Tokyo">
         Tokyo | Japan, Population, Map</a>
    </h2>
    <a class="result__snippet" href="https://www.britannica.com/place/Tokyo">
      Tokyo, city and capital of Tokyo prefecture.</a>
  </div>
</div>
"""


def test_parses_titles_urls_and_snippets():
    parser = S._DuckDuckGoParser()
    parser.feed(DDG_HTML)
    results = parser.results
    assert len(results) == 2
    assert results[0].title == 'Tokyo - Wikipedia'
    assert results[0].url == 'https://en.wikipedia.org/wiki/Tokyo'
    assert 'capital' in results[0].snippet
    # Markup inside the snippet must not leak into the text.
    assert '<b>' not in results[0].snippet
    assert results[1].url == 'https://www.britannica.com/place/Tokyo'


def test_unwraps_duckduckgo_redirects():
    wrapped = '//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa%20b&rut=x'
    assert S.unwrap_url(wrapped) == 'https://example.com/a b'
    assert S.unwrap_url('https://example.com/direct') == 'https://example.com/direct'
    assert S.unwrap_url('') == ''


def test_citation_is_the_bare_host():
    assert S.Result('t', 'https://www.bbc.co.uk/news/x', 's').cite() == 'bbc.co.uk'


def test_duckduckgo_uses_the_parser(monkeypatch):
    monkeypatch.setattr(S, '_fetch', lambda *a, **k: DDG_HTML)
    results = S.duckduckgo('capital of japan', limit=5)
    assert [r.title for r in results] == ['Tokyo - Wikipedia', 'Tokyo | Japan, Population, Map']


def test_limit_is_respected(monkeypatch):
    monkeypatch.setattr(S, '_fetch', lambda *a, **k: DDG_HTML)
    assert len(S.duckduckgo('q', limit=1)) == 1


def test_network_failure_becomes_search_error(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.URLError('Tunnel connection failed: 403 Forbidden')
    monkeypatch.setattr(S.urllib.request, 'urlopen', boom)
    with pytest.raises(S.SearchError) as exc:
        S.search('anything')
    assert 'could not reach' in str(exc.value)


def test_http_error_becomes_search_error(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.HTTPError('u', 429, 'Too Many Requests', {}, None)
    monkeypatch.setattr(S.urllib.request, 'urlopen', boom)
    with pytest.raises(S.SearchError) as exc:
        S.search('anything')
    assert '429' in str(exc.value)


def test_empty_query_rejected():
    with pytest.raises(S.SearchError):
        S.search('   ')


def test_provider_follows_available_keys(monkeypatch):
    monkeypatch.delenv('BRAVE_API_KEY', raising=False)
    monkeypatch.delenv('SERPER_API_KEY', raising=False)
    assert S.provider_name() == 'DuckDuckGo'
    monkeypatch.setenv('SERPER_API_KEY', 'k')
    assert S.provider_name() == 'Serper'
    monkeypatch.setenv('BRAVE_API_KEY', 'k')
    assert S.provider_name() == 'Brave'


def test_brave_results_are_parsed(monkeypatch):
    payload = {'web': {'results': [
        {'title': 'Tokyo', 'url': 'https://example.com/tokyo',
         'description': 'The <strong>capital</strong> of Japan.'}]}}
    monkeypatch.setattr(S, '_fetch', lambda *a, **k: json.dumps(payload))
    [result] = S.brave('capital of japan', 5, 'key')
    assert result.url == 'https://example.com/tokyo'
    assert result.snippet == 'The capital of Japan.'


def test_serper_results_are_parsed(monkeypatch):
    payload = {'organic': [{'title': 'Tokyo', 'link': 'https://example.com/t',
                            'snippet': 'Capital of Japan.'}]}
    monkeypatch.setattr(S, '_fetch', lambda *a, **k: json.dumps(payload))
    [result] = S.serper('q', 5, 'key')
    assert result.title == 'Tokyo' and result.snippet == 'Capital of Japan.'


def test_context_is_numbered_and_bounded():
    results = [S.Result(f'Title {i}', f'https://example.com/{i}', 'x' * 300)
               for i in range(4)]
    context = S.as_context(results, budget=200)
    assert context.startswith('[1] Title 0 (example.com):')
    assert len(context) <= 200


# --- deep search ----------------------------------------------------------

def _result(title, url, snippet=''):
    return S.Result(title, url, snippet)


def test_follow_ups_use_terms_the_query_did_not_have():
    results = [
        _result('Mars rover Perseverance lands', 'https://a.com/1',
                'The Perseverance rover collected samples in Jezero crater.'),
        _result('Perseverance drills again', 'https://b.com/2',
                'NASA says Perseverance found organic samples.'),
    ]
    follow = S.follow_up_queries('mars rover', results)
    assert follow, 'expected at least one follow-up query'
    assert all(q.startswith('mars rover ') for q in follow)
    joined = ' '.join(follow)
    assert 'perseverance' in joined      # recurs across results
    assert 'rover' not in joined.replace('mars rover ', '')  # already asked


def test_follow_ups_ignore_one_off_and_stopword_terms():
    results = [_result('A', 'https://a.com', 'that which through unique')]
    assert S.follow_up_queries('topic', results) == []


def test_deep_search_runs_a_second_round_on_what_it_found(monkeypatch):
    calls = []

    def fake_search(q, limit=5):
        calls.append(q)
        if q == 'mars rover':
            return [_result('Perseverance one', 'https://a.com/1', 'Perseverance samples'),
                    _result('Perseverance two', 'https://b.com/2', 'Perseverance samples')]
        return [_result('Deeper', 'https://c.com/3', 'more detail')]

    monkeypatch.setattr(S, 'search', fake_search)
    rounds = list(S.deep_search('mars rover', rounds=2, per_round=1))
    assert calls[0] == 'mars rover'
    assert len(calls) > 1, 'second round never ran'
    assert calls[1].startswith('mars rover ')
    assert rounds[-1][1][0].url == 'https://c.com/3'


def test_deep_search_does_not_repeat_urls(monkeypatch):
    same = [_result('Same', 'https://a.com/1', 'Perseverance rover samples')]
    monkeypatch.setattr(S, 'search', lambda q, limit=5: same)
    seen = [r.url for _, results in S.deep_search('mars rover', rounds=2, per_round=1)
            if not isinstance(results, Exception) for r in results]
    assert seen == ['https://a.com/1']


def test_deep_search_surfaces_a_failed_round_without_losing_the_rest(monkeypatch):
    def flaky(q, limit=5):
        if q == 'seed':
            # Two results sharing a term, so a follow-up round is generated.
            return [_result('Alpha', 'https://a.com', 'beta gamma'),
                    _result('Alpha two', 'https://b.com', 'beta gamma')]
        raise S.SearchError('provider refused')

    monkeypatch.setattr(S, 'search', flaky)
    rounds = list(S.deep_search('seed', rounds=2, per_round=1))
    assert isinstance(rounds[0][1], list)
    assert isinstance(rounds[-1][1], S.SearchError)
