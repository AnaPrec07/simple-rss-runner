"""Report which configured feeds respond: python -m news.check_feeds"""

import httpx
import feedparser

from .sources import SOURCES

with httpx.Client(follow_redirects=True, timeout=15) as c:
    for s in SOURCES:
        try:
            r = c.get(s.url, headers={"User-Agent": "simple-rss-runner/1.0"})
            n = len(feedparser.parse(r.content).entries)
            print(f"{'OK ' if r.status_code == 200 and n else 'BAD'} {s.name:45} {r.status_code} entries={n}")
        except Exception as e:  # noqa: BLE001
            print(f"BAD {s.name:45} {type(e).__name__}")
