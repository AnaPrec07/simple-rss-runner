"""python -m news [build|email|print|push-whatsapp]   (schedule with cron / GitHub Actions)"""

import sys

from . import digest


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "email"
    data = digest.build()
    if cmd == "print":
        print(digest.to_text(data))
    elif cmd == "email":
        from .emailer import send_digest

        print(f"sent {send_digest(data)} email(s)")
    elif cmd == "push-whatsapp":
        import os

        from .whatsapp import format_section, send_whatsapp

        body = format_section(data, "panama", 3) + "\n\n" + format_section(data, "tech", 3)
        send_whatsapp(os.environ["WHATSAPP_TO"], body[:1500])
    elif cmd != "build":
        raise SystemExit(f"unknown command {cmd}")


main()
