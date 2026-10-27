"""Send the digest in a way mailbox providers trust.

What actually keeps mail out of spam (in order of impact):
  1. Send from a domain you own with SPF, DKIM and DMARC all passing.
  2. Use a transactional provider (Resend / Postmark / SES) or Gmail SMTP with an
     app password, never a raw home/cloud IP.
  3. multipart/alternative (text + HTML), one recipient per message, real
     Message-ID/Date, List-Unsubscribe (+ one-click), plain subject.
  4. Only mail people who opted in; keep complaint rate near zero.
See README "Email deliverability" for the DNS records.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import httpx

from . import digest


def _cfg(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def build_message(data: dict, to: str) -> EmailMessage:
    sender = _cfg("MAIL_FROM")  # e.g. "Daily Briefing <briefing@yourdomain.com>"
    domain = sender.rsplit("@", 1)[-1].strip("> ")
    unsub_mail = _cfg("MAIL_UNSUBSCRIBE", sender.split("<")[-1].strip("> "))
    unsub_url = _cfg("MAIL_UNSUBSCRIBE_URL")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = digest.subject(data)
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=domain)
    if _cfg("MAIL_REPLY_TO"):
        msg["Reply-To"] = _cfg("MAIL_REPLY_TO")
    links = [f"<mailto:{unsub_mail}?subject=unsubscribe>"] + ([f"<{unsub_url}>"] if unsub_url else [])
    msg["List-Unsubscribe"] = ", ".join(links)
    if unsub_url:  # RFC 8058 one-click requires an HTTPS endpoint
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    footer = f"You are receiving this because you subscribed. To stop, reply &quot;unsubscribe&quot; or write to {unsub_mail}."
    msg.set_content(digest.to_text(data) + f"\n--\nTo unsubscribe reply 'unsubscribe' or write to {unsub_mail}\n")
    msg.add_alternative(digest.to_html(data, footer), subtype="html")
    return msg


def _send_smtp(msg: EmailMessage) -> None:
    host, port = _cfg("SMTP_HOST", "smtp.gmail.com"), int(_cfg("SMTP_PORT", "465"))
    ctx = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.starttls(context=ctx)
    with server:
        server.login(_cfg("SMTP_USER"), _cfg("SMTP_PASSWORD"))
        server.send_message(msg)


def _send_resend(msg: EmailMessage) -> None:
    body = msg.get_body(("html",)).get_content()
    text = msg.get_body(("plain",)).get_content()
    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {_cfg('RESEND_API_KEY')}"},
        json={
            "from": msg["From"], "to": [msg["To"]], "subject": msg["Subject"], "html": body, "text": text,
            "reply_to": msg.get("Reply-To"),
            "headers": {k: msg[k] for k in ("List-Unsubscribe", "List-Unsubscribe-Post") if msg[k]},
        },
        timeout=30,
    )
    r.raise_for_status()


def recipients() -> list[str]:
    """Opted-in addresses: MAIL_TO (comma separated) plus data/unsubscribed.txt exclusions."""
    to = [a.strip().lower() for a in _cfg("MAIL_TO").split(",") if a.strip()]
    try:
        with open(_cfg("MAIL_UNSUBSCRIBED_FILE", "data/unsubscribed.txt")) as f:
            blocked = {l.strip().lower() for l in f if l.strip()}
    except OSError:
        blocked = set()
    return [a for a in to if a not in blocked]


def send_digest(data: dict) -> int:
    send = _send_resend if _cfg("MAIL_PROVIDER", "smtp") == "resend" else _send_smtp
    n = 0
    for addr in recipients():  # one message per recipient: no exposed lists, better reputation
        send(build_message(data, addr))
        n += 1
    return n
