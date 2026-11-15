"""Welcome message drafting and Discord webhook delivery (dry-run by default)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .core import Teammate

ALLOWED_WEBHOOK_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
)


def draft_welcome(tm: Teammate, team_name: str = "the team") -> str:
    """A short, warm welcome message. Plain text, safe to post as-is."""
    first = tm.name.split()[0]
    buddy_line = f" Your onboarding buddy is {tm.buddy}, ask them anything." if tm.buddy else ""
    return (
        f"Welcome to {team_name}, {first}! 🎉\n"
        f"{first} joins us as {tm.role}, starting {tm.start_date} ({tm.timezone}).{buddy_line}\n"
        f"Your day-one checklist is on its way. If anything is unclear or stuck, reply here and we will sort it out."
    )


def send_discord(content: str, webhook_url: str | None = None, timeout: float = 10.0) -> dict[str, Any]:
    """Post ``content`` to a Discord webhook.

    Without a webhook URL (argument or ``DISCORD_WEBHOOK_URL``) nothing is sent
    and the payload is returned with ``sent: False``: a safe dry run.
    """
    url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    payload = {"content": content[:2000], "allowed_mentions": {"parse": []}}
    if not url:
        return {"sent": False, "dry_run": True, "reason": "No DISCORD_WEBHOOK_URL set.", "payload": payload}
    if not url.startswith(ALLOWED_WEBHOOK_PREFIXES):
        raise ValueError("Webhook URL must start with https://discord.com/api/webhooks/.")
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "onboard-ops-mcp/0.1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (prefix checked above)
            return {"sent": True, "dry_run": False, "status": resp.status, "payload": payload}
    except urllib.error.HTTPError as exc:
        return {"sent": False, "dry_run": False, "status": exc.code, "reason": f"Discord returned HTTP {exc.code}."}
    except urllib.error.URLError as exc:
        return {"sent": False, "dry_run": False, "reason": f"Could not reach Discord: {exc.reason}."}
