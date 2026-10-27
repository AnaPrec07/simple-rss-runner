"""Fetch, normalise, dedupe and score feed items."""

from __future__ import annotations

import calendar
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import feedparser
import httpx
from bs4 import BeautifulSoup

from .sources import LLM_NOISE, PANAMA_KEYWORDS, SOURCES, TECH_BEYOND_MODELS, Source

USER_AGENT = "simple-rss-runner/1.0 (+personal news digest)"


@dataclass
class Item:
    title: str
    url: str
    summary: str
    source: str
    section: str
    published: datetime
    score: float = 0.0
    id: str = field(init=False)

    def __post_init__(self) -> None:
        self.id = hashlib.sha1(self.url.encode()).hexdigest()[:10]


def _clean(html: str, limit: int = 400) -> str:
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def _published(entry) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return datetime.now(timezone.utc)


def fetch_source(src: Source, max_age_hours: int, client: httpx.Client) -> list[Item]:
    try:
        r = client.get(src.url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=15)
        r.raise_for_status()
    except Exception:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    items = []
    for e in feedparser.parse(r.content).entries[:40]:
        link = e.get("link")
        title = _clean(e.get("title", ""), 200)
        if not link or not title:
            continue
        pub = _published(e)
        if pub < cutoff:
            continue
        items.append(Item(title, link, _clean(e.get("summary", "")), src.name, src.section, pub))
    return items


def score(item: Item, weight: float) -> float:
    text = f"{item.title} {item.summary}".lower()
    s = weight
    s += 0.6 * sum(k in text for k in PANAMA_KEYWORDS) if item.section == "panama" else 0
    s += 0.4 * sum(k in text for k in TECH_BEYOND_MODELS)
    s -= 0.7 * sum(k in text for k in LLM_NOISE)
    age_h = (datetime.now(timezone.utc) - item.published).total_seconds() / 3600
    return s + max(0.0, 1.0 - age_h / 48)  # recency bonus


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def dedupe(items: list[Item]) -> list[Item]:
    seen_url, seen_title, out = set(), set(), []
    for it in sorted(items, key=lambda i: -i.score):
        key = _norm_title(it.title)
        if it.url in seen_url or key in seen_title:
            continue
        seen_url.add(it.url)
        seen_title.add(key)
        out.append(it)
    return out


def gather(max_age_hours: int = 36, sources: list[Source] | None = None) -> list[Item]:
    sources = sources or SOURCES
    weights = {s.name: s.weight for s in sources}
    with httpx.Client() as client, ThreadPoolExecutor(8) as pool:
        batches = pool.map(lambda s: fetch_source(s, max_age_hours, client), sources)
    items = [i for b in batches for i in b]
    for i in items:
        i.score = score(i, weights[i.source])
    return dedupe(items)


def top_by_section(items: list[Item], limits: dict[str, int]) -> dict[str, list[Item]]:
    out: dict[str, list[Item]] = {}
    for section, n in limits.items():
        out[section] = [i for i in items if i.section == section][:n]
    return out
