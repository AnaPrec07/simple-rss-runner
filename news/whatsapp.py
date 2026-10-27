"""Chat with your news over WhatsApp (Twilio WhatsApp API).

Run:  uvicorn news.whatsapp:app --port 8080   and point the Twilio sandbox
"When a message comes in" webhook at  https://<public-host>/whatsapp
Commands: "digest" (today's briefing), "panama", "tech"; anything else is a question
answered from the latest headlines plus Google Search grounding.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from collections import defaultdict, deque

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import Response

from . import digest

app = FastAPI(title="news-whatsapp")
HISTORY: dict[str, deque] = defaultdict(lambda: deque(maxlen=8))
ALLOWED = {n.strip() for n in os.getenv("WHATSAPP_ALLOWED", "").split(",") if n.strip()}
MAX_LEN = 1500  # WhatsApp body limit via Twilio is 1600


def valid_signature(url: str, params: dict, signature: str, token: str) -> bool:
    """Twilio X-Twilio-Signature: base64(HMAC-SHA1(token, url + sorted key+value))."""
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    mac = hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(mac).decode(), signature)


def format_section(data: dict, key: str, limit: int = 5) -> str:
    rows = data["sections"].get(key, [])[:limit]
    return "\n\n".join(f"*{r['title']}*\n{r['blurb']}\n{r['url']}" for r in rows) or "Nothing new."


def _context(data: dict | None) -> str:
    if not data:
        return "No digest cached yet."
    return "\n".join(
        f"[{k}] {r['title']} ({r['source']}): {r['blurb']} {r['url']}"
        for k, rows in data["sections"].items() for r in rows
    )


def answer(sender: str, text: str) -> str:
    cmd = text.strip().lower()
    data = digest.load_cached() or digest.build()
    if cmd in {"digest", "hoy", "today"}:
        return (format_section(data, "panama", 3) + "\n\n" + format_section(data, "tech", 3))[:MAX_LEN]
    if cmd in {"panama", "panamá"}:
        return format_section(data, "panama")[:MAX_LEN]
    if cmd == "tech":
        return format_section(data, "tech")[:MAX_LEN]
    if cmd == "refresh":
        digest.build()
        return "Refreshed. Send 'digest'."
    if not os.getenv("GOOGLE_API_KEY"):
        return "Commands: digest, panama, tech, refresh. Set GOOGLE_API_KEY to enable free-form questions."
    from google import genai
    from google.genai import types

    history = HISTORY[sender]
    history.append(f"User: {text}")
    prompt = (
        "You are a concise news assistant replying on WhatsApp (plain text, under 1200 characters, "
        "answer in the user's language). Prefer the headlines below; use search for follow-ups and "
        "always name the source. If unsure, say so. Never invent facts.\n\nHEADLINES:\n"
        f"{_context(data)}\n\nCONVERSATION:\n" + "\n".join(history)
    )
    resp = genai.Client().models.generate_content(
        model=os.getenv("CHAT_MODEL", "gemini-2.5-flash"),
        contents=prompt,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
    )
    reply = (resp.text or "Sorry, I could not answer that.")[:MAX_LEN]
    history.append(f"Assistant: {reply}")
    return reply


def send_whatsapp(to: str, body: str) -> None:
    sid, tok = os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]
    httpx.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, tok),
        data={"From": os.environ["TWILIO_WHATSAPP_FROM"], "To": to, "Body": body},
        timeout=20,
    ).raise_for_status()


def _reply(sender: str, text: str) -> None:
    send_whatsapp(sender, answer(sender, text))


@app.post("/whatsapp")
async def whatsapp(request: Request, tasks: BackgroundTasks):
    form = dict((await request.form()).items())
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    public = os.getenv("PUBLIC_URL", str(request.url))
    if token and not valid_signature(public, form, request.headers.get("X-Twilio-Signature", ""), token):
        raise HTTPException(403, "bad signature")
    sender = form.get("From", "")
    if ALLOWED and sender not in ALLOWED:
        raise HTTPException(403, "not allowed")
    tasks.add_task(_reply, sender, form.get("Body", ""))  # reply async: avoids Twilio's 15s timeout
    return Response("<Response/>", media_type="application/xml")
