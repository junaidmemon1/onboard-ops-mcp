import asyncio
import json

import pytest

from onboard_ops import cli, notifier
from onboard_ops.core import OnboardingService


def test_discord_is_dry_run_without_webhook(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    res = notifier.send_discord("hello")
    assert res["sent"] is False and res["dry_run"] is True


def test_discord_rejects_non_discord_urls():
    with pytest.raises(ValueError, match="discord.com"):
        notifier.send_discord("hello", "https://evil.example.com/hook")


def test_discord_never_pings_everyone(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    payload = notifier.send_discord("@everyone hi")["payload"]
    assert payload["allowed_mentions"] == {"parse": []}


def test_welcome_message_mentions_buddy(tmp_path):
    svc = OnboardingService(tmp_path / "s.json")
    svc.add_teammate("Hana Sato", "hana@example.com", "Designer", "2026-12-01", "Asia/Tokyo", "Leo")
    text = notifier.draft_welcome(svc.get_teammate("tm-001"), "Acme")
    assert "Hana" in text and "Leo" in text and "Acme" in text


def test_cli_flow(tmp_path, capsys):
    store = str(tmp_path / "s.json")
    assert cli.main(["--data", store, "add", "Ada Lovelace", "ada@example.com", "Engineer", "2026-12-01"]) == 0
    assert cli.main(["--data", store, "--today", "2026-12-05", "stuck"]) == 0
    out = capsys.readouterr().out
    assert "Added Ada Lovelace" in out and "Hi Ada" in out or "Agent task overdue" in out
    assert cli.main(["--data", store, "done", "tm-001", "nope"]) == 1  # clean error, no traceback


def test_cli_demo_runs(capsys):
    assert cli.main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "Agent queue" in out and "Weekly report" in out


def test_mcp_server_registers_tools_and_works(tmp_path, monkeypatch):
    monkeypatch.setenv("ONBOARD_OPS_DATA", str(tmp_path / "mcp.json"))
    from onboard_ops.server import mcp

    async def run():
        names = {t.name for t in await mcp.list_tools()}
        assert {"add_teammate", "agent_queue", "complete_task", "stuck_tasks", "weekly_report"} <= names
        await mcp.call_tool(
            "add_teammate",
            {"name": "Ada Lovelace", "email": "ada@example.com", "role": "Engineer", "start_date": "2026-12-01"},
        )
        queue = await mcp.call_tool("agent_queue", {"today": "2026-11-30"})
        return queue

    result = asyncio.run(run())
    flat = json.dumps(result, default=str)
    assert "work_email" in flat
