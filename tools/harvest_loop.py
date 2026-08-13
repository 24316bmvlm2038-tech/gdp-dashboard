"""Keep collecting facts from the web, on a loop.

    python -m tools.harvest_loop                 # run continuously
    python -m tools.harvest_loop --once          # a single cycle
    python -m tools.harvest_loop --review        # print what has been collected

Each cycle fetches a bounded number of topics, merges what it found into
``data/harvested.json``, and sleeps. It is meant to run for a long time and
collect slowly, which is the difference between a harvester and a nuisance:
the per-host rate limit in :class:`clode.harvest.PoliteFetcher` and the sleep
between cycles mean this asks for a handful of pages a minute, not thousands.

Nothing here touches the model. Harvested facts reach training only when the
corpus is rebuilt, and reach the released model only if
``tools.daily_train`` measures an improvement — so a bad harvest cannot
quietly degrade what is published.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clode.harvest import (  # noqa: E402
    DATABASE,
    SEED_TOPICS,
    Fact,
    HarvestError,
    PoliteFetcher,
    harvest,
    load_database,
    merge,
    save_database,
)

_stopping = False


def _stop(signum, frame):  # pragma: no cover - signal path
    global _stopping
    _stopping = True
    print('\nfinishing the current cycle, then stopping…', flush=True)


def cycle(fetcher: PoliteFetcher, topics: list[str], limit: int) -> tuple[int, int]:
    """One pass. Returns (facts added, failures)."""
    existing = load_database()
    found: list[Fact] = []
    failures = 0
    for topic, result in harvest(topics, fetcher=fetcher, existing=existing, limit=limit):
        if isinstance(result, HarvestError):
            failures += 1
            print(f'  ✗ {topic}: {result}', flush=True)
            continue
        found.append(result)
        print(f'  ✓ {topic}: {result.answer[:88]}', flush=True)

    if found:
        merged = merge(existing, found)
        save_database(merged)
        print(f'  database now holds {len(merged)} facts', flush=True)
    return len(found), failures


def review() -> int:
    facts = load_database()
    if not facts:
        print(f'{DATABASE} is empty — nothing harvested yet.')
        return 0
    print(f'{len(facts)} facts in {DATABASE}\n')
    for fact in facts:
        print(f'Q {fact.question}\nA {fact.answer}\n  source: {fact.source}'
              f'  fetched: {fact.fetched_at}\n')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--once', action='store_true', help='one cycle, then exit')
    ap.add_argument('--review', action='store_true', help='print the database and exit')
    ap.add_argument('--interval', type=float, default=900,
                    help='seconds to sleep between cycles (default 15 minutes)')
    ap.add_argument('--limit', type=int, default=10,
                    help='topics fetched per cycle')
    args = ap.parse_args()

    if args.review:
        return review()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    fetcher = PoliteFetcher()
    topics = list(SEED_TOPICS)
    cycles = added_total = failed_total = 0

    while not _stopping:
        cycles += 1
        print(f'cycle {cycles} — {time.strftime("%H:%M:%S")}', flush=True)
        added, failed = cycle(fetcher, topics, args.limit)
        added_total += added
        failed_total += failed

        if args.once:
            break
        if added == 0 and failed == 0:
            print('  every seed topic is already collected; nothing left to fetch.',
                  flush=True)
            break
        # Sleep in short slices so a stop signal is noticed promptly.
        waited = 0.0
        while waited < args.interval and not _stopping:
            time.sleep(min(1.0, args.interval - waited))
            waited += 1.0

    print(f'\n{cycles} cycles: {added_total} facts added, {failed_total} failures')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
