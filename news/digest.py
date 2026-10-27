"""Build the daily digest (plain text + HTML) and cache it for the chat bot."""

from __future__ import annotations

import html
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .fetch import Item, gather, top_by_section

TZ = ZoneInfo(os.getenv("DIGEST_TZ", "America/Panama"))
CACHE = Path(os.getenv("DIGEST_CACHE", "data/latest_digest.json"))
SECTIONS = {
    "panama": ("Panamá hoy", 8),
    "latam": ("Latin America", 3),
    "tech": ("Tech beyond the models", 8),
    "science": ("Science, space & energy", 4),
}


def _llm_blurbs(items: list[Item]) -> dict[str, str]:
    """One-line 'why it matters' per item. Optional: returns {} without an API key."""
    if not os.getenv("GOOGLE_API_KEY"):
        return {}
    try:
        from google import genai

        client = genai.Client()
        listing = "\n".join(f"{i.id} | {i.source} | {i.title} | {i.summary[:200]}" for i in items)
        resp = client.models.generate_content(
            model=os.getenv("DIGEST_MODEL", "gemini-2.5-flash"),
            contents=(
                "For each line (id | source | title | snippet) write one factual sentence, max 25 words, "
                "in the language of the title, saying why it matters. Do not add facts beyond the snippet. "
                'Return JSON object {id: sentence}.\n' + listing
            ),
            config={"response_mime_type": "application/json"},
        )
        return json.loads(resp.text)
    except Exception:  # noqa: BLE001 - digest must still go out
        return {}


def build(max_age_hours: int = 36) -> dict:
    items = gather(max_age_hours)
    picked = top_by_section(items, {k: v[1] for k, v in SECTIONS.items()})
    flat = [i for lst in picked.values() for i in lst]
    blurbs = _llm_blurbs(flat)
    now = datetime.now(TZ)
    data = {
        "date": now.strftime("%A %d %B %Y"),
        "sections": {
            k: [
                {"title": i.title, "url": i.url, "source": i.source, "blurb": blurbs.get(i.id) or i.summary[:160]}
                for i in lst
            ]
            for k, lst in picked.items()
        },
    }
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def load_cached() -> dict | None:
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return None


def subject(data: dict) -> str:
    # Plain, specific subject. No emojis, ALL CAPS or "!!!": these feed spam scoring.
    return f"Panama & tech briefing: {data['date']}"


def to_text(data: dict) -> str:
    out = [f"Panama & tech briefing - {data['date']}", ""]
    for key, (label, _) in SECTIONS.items():
        rows = data["sections"].get(key) or []
        if not rows:
            continue
        out.append(label.upper())
        for r in rows:
            out += [f"- {r['title']} ({r['source']})", f"  {r['blurb']}", f"  {r['url']}"]
        out.append("")
    return "\n".join(out)


def to_html(data: dict, footer: str = "") -> str:
    e = html.escape
    parts = [
        '<div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:640px;margin:0 auto;'
        'color:#1a1a1a;line-height:1.5">',
        f'<h1 style="font-size:20px">Panama &amp; tech briefing</h1><p style="color:#666">{e(data["date"])}</p>',
    ]
    for key, (label, _) in SECTIONS.items():
        rows = data["sections"].get(key) or []
        if not rows:
            continue
        parts.append(f'<h2 style="font-size:16px;border-bottom:1px solid #ddd;padding-bottom:4px">{e(label)}</h2>')
        for r in rows:
            parts.append(
                f'<p style="margin:10px 0"><a href="{e(r["url"])}" style="color:#0b57d0;text-decoration:none;'
                f'font-weight:600">{e(r["title"])}</a><br><span style="color:#666;font-size:12px">{e(r["source"])}'
                f'</span><br>{e(r["blurb"])}</p>'
            )
    parts.append(f'<p style="color:#888;font-size:12px;margin-top:24px">{footer}</p></div>')
    return "".join(parts)
