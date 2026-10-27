"""Curated feed list. Edit freely; any feed that fails is skipped, not fatal.

Feeds marked "unverified" were written from memory and could not be checked
from the build sandbox. Run `python -m news.check_feeds` from a networked
machine to see which ones respond.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    section: str  # "panama" | "latam" | "tech" | "science" | "business"
    weight: float = 1.0  # editorial trust / priority tie-breaker


SOURCES: list[Source] = [
    # --- Panama (Spanish + English) ---
    Source("La Prensa Panamá", "https://www.prensa.com/arc/outboundfeeds/rss/?outputType=xml", "panama", 1.3),
    Source("La Estrella de Panamá", "https://www.laestrella.com.pa/rss", "panama", 1.2),
    Source("Newsroom Panama", "https://newsroompanama.com/feed/", "panama", 1.2),
    Source("Panamá América", "https://www.panamaamerica.com.pa/rss.xml", "panama", 1.0),
    Source("TVN Noticias", "https://www.tvn-2.com/rss.xml", "panama", 1.0),
    Source("Telemetro", "https://www.telemetro.com/rss.xml", "panama", 1.0),
    Source("Metro Libre", "https://www.metrolibre.com/feed/", "panama", 0.9),
    Source("Autoridad del Canal de Panamá", "https://pancanal.com/feed/", "panama", 1.1),
    # --- Latin America business/tech ---
    Source("Rest of World", "https://restofworld.org/feed/latest", "latam", 1.2),
    Source("Reuters Latin America (via Google News)",
           "https://news.google.com/rss/search?q=Panama+when:2d&hl=en-US&gl=US&ceid=US:en", "panama", 0.8),
    # --- Tech beyond models: chips, robotics, security, space, energy, bio ---
    Source("Hacker News (100+ pts)", "https://hnrss.org/frontpage?points=100", "tech", 1.1),
    Source("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "tech", 1.2),
    Source("IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss", "tech", 1.3),
    Source("MIT Technology Review", "https://www.technologyreview.com/feed/", "tech", 1.2),
    Source("The Verge", "https://www.theverge.com/rss/index.xml", "tech", 1.0),
    Source("Krebs on Security", "https://krebsonsecurity.com/feed/", "tech", 1.1),
    Source("The Register", "https://www.theregister.com/headlines.atom", "tech", 0.9),
    Source("SpaceNews", "https://spacenews.com/feed/", "science", 1.0),
    Source("Quanta Magazine", "https://api.quantamagazine.org/feed/", "science", 1.1),
    Source("Canary Media (energy)", "https://www.canarymedia.com/rss.rss", "science", 0.9),
    Source("STAT News (biotech)", "https://www.statnews.com/feed/", "science", 0.9),
]

# Words that boost an item. Panama list is bilingual.
PANAMA_KEYWORDS = [
    "panamá", "panama", "canal", "colón", "zona libre", "asamblea nacional",
    "mulino", "copa airlines", "cobre panamá", "sbs", "hub", "ciudad del saber",
]
TECH_BEYOND_MODELS = [
    "chip", "semiconductor", "gpu", "quantum", "robot", "satellite", "starlink",
    "fusion", "battery", "grid", "crispr", "vulnerability", "ransomware",
    "datacenter", "data center", "fiber", "5g", "fintech", "blockchain",
]
# Demote pure model-release chatter so the digest goes beyond it.
LLM_NOISE = ["gpt-", "llm benchmark", "chatgpt", "gemini 3", "claude ", "openai releases"]
