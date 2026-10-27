import base64, hashlib, hmac
from datetime import datetime, timezone

from news import digest, emailer, whatsapp
from news.fetch import Item, dedupe, score


def item(title, url, section="tech", summary=""):
    return Item(title, url, summary, "src", section, datetime.now(timezone.utc))


def test_dedupe_by_title_and_url():
    a, b, c = item("Same Title!", "u1"), item("same title", "u2"), item("Other", "u1")
    for i in (a, b, c):
        i.score = 1
    assert [i.title for i in dedupe([a, item("Other", "u3")])] == ["Same Title!", "Other"]


def test_scoring_prefers_panama_and_demotes_llm_noise():
    p = item("Canal de Panamá amplía", "p", "panama")
    n = item("OpenAI releases GPT-9, ChatGPT update", "n")
    assert score(p, 1.0) > score(n, 1.0)


def test_email_headers(monkeypatch):
    monkeypatch.setenv("MAIL_FROM", "Briefing <briefing@example.com>")
    monkeypatch.setenv("MAIL_UNSUBSCRIBE_URL", "https://example.com/u")
    data = {"date": "Mon", "sections": {"panama": [{"title": "T", "url": "http://x", "source": "s", "blurb": "b"}]}}
    m = emailer.build_message(data, "me@example.org")
    assert "example.com" in m["Message-ID"]
    assert "List-Unsubscribe" in m and m["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert m.get_body(("plain",)) and m.get_body(("html",))


def test_twilio_signature():
    params = {"Body": "hi", "From": "whatsapp:+507"}
    url = "https://h/whatsapp"
    sig = base64.b64encode(hmac.new(b"tok", (url + "Bodyhi" + "Fromwhatsapp:+507").encode(), hashlib.sha1).digest()).decode()
    assert whatsapp.valid_signature(url, params, sig, "tok")
    assert not whatsapp.valid_signature(url, params, "bad", "tok")
