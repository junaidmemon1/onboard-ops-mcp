"""MCP server exposing the onboarding tracker to AI agents.

Run with:  onboard-ops-mcp          (stdio transport)
Config:    ONBOARD_OPS_DATA          path to the JSON store
           DISCORD_WEBHOOK_URL       optional, enables real Discord posts
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .core import OnboardingService, render_report_markdown
from .notifier import draft_welcome, send_discord

mcp = FastMCP(
    "onboard-ops",
    instructions=(
        "Tracks new-teammate onboarding. Use agent_queue to see what you should do now, perform each action "
        "with your other tools (email, Discord, HR), then call complete_task. Use stuck_tasks to find what "
        "needs a human follow-up. Dates are ISO (YYYY-MM-DD)."
    ),
)


def _svc() -> OnboardingService:
    return OnboardingService()


@mcp.tool()
def add_teammate(
    name: str, email: str, role: str, start_date: str, timezone: str = "UTC", buddy: str | None = None
) -> dict[str, Any]:
    """Register a new teammate and generate their onboarding checklist (role-aware, dated from start_date)."""
    return _svc().add_teammate(name, email, role, start_date, timezone, buddy)


@mcp.tool()
def list_teammates(today: str | None = None) -> list[dict[str, Any]]:
    """List everyone in onboarding with phase and progress."""
    return _svc().list_teammates(today)


@mcp.tool()
def onboarding_status(teammate_id: str, today: str | None = None) -> dict[str, Any]:
    """Full checklist for one teammate, with each task's state (done, due, overdue, blocked, upcoming)."""
    return _svc().status(teammate_id, today)


@mcp.tool()
def agent_queue(today: str | None = None) -> list[dict[str, Any]]:
    """Automatable tasks that are due or overdue. This is the agent's to-do list."""
    return _svc().agent_queue(today)


@mcp.tool()
def complete_task(teammate_id: str, task_id: str, today: str | None = None) -> dict[str, Any]:
    """Mark a task done after the action has actually been carried out. Safe to call twice."""
    return _svc().complete_task(teammate_id, task_id, today)


@mcp.tool()
def block_task(teammate_id: str, task_id: str, reason: str, today: str | None = None) -> dict[str, Any]:
    """Flag a task as blocked with a reason so a human can unblock it."""
    return _svc().block_task(teammate_id, task_id, reason, today)


@mcp.tool()
def unblock_task(teammate_id: str, task_id: str, today: str | None = None) -> dict[str, Any]:
    """Clear a blocked flag once the blocker is resolved."""
    return _svc().unblock_task(teammate_id, task_id, today)


@mcp.tool()
def stuck_tasks(today: str | None = None, min_days_overdue: int = 1) -> list[dict[str, Any]]:
    """Blocked or overdue tasks, most overdue first, each with a ready-to-send follow-up message."""
    return _svc().stuck(today, min_days_overdue)


@mcp.tool()
def weekly_report(today: str | None = None) -> str:
    """Markdown summary: progress, who starts soon, what is stuck."""
    return render_report_markdown(_svc().report(today))


@mcp.tool()
def draft_welcome_message(teammate_id: str, team_name: str = "the team") -> str:
    """Draft a welcome message for a teammate. Does not send anything."""
    return draft_welcome(_svc().get_teammate(teammate_id), team_name)


@mcp.tool()
def post_welcome_to_discord(teammate_id: str, team_name: str = "the team") -> dict[str, Any]:
    """Post the welcome message to Discord. Dry run unless DISCORD_WEBHOOK_URL is configured."""
    return send_discord(draft_welcome(_svc().get_teammate(teammate_id), team_name))


@mcp.resource("onboarding://teammates")
def teammates_resource() -> list[dict[str, Any]]:
    """Current onboarding roster as a readable resource."""
    return _svc().list_teammates()


@mcp.prompt()
def onboarding_operator() -> str:
    """Playbook for an agent acting as the onboarding operator."""
    return (
        "You are the onboarding operator. Each run: 1) call agent_queue and carry out each task with your other "
        "tools, then complete_task. 2) call stuck_tasks and send each suggested_followup to its owner. "
        "3) if a task cannot be done, call block_task with a clear reason. 4) end with weekly_report. "
        "Never mark a task done before the action has succeeded."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
