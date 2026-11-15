# onboard-ops-mcp

An MCP server and CLI that lets an AI agent run new-teammate onboarding: it generates a dated checklist for each person, tells the agent what to do now, flags what is stuck, and writes the follow-up message for whoever needs to act.

**Live demo:** https://junaidmemon1.github.io/onboard-ops-mcp/ (replays an agent run in your browser with sample people)

## Why this exists

Onboarding is a lot of small steps across many tools: accounts, Discord, a buddy, a first task, a check-in. Most of it repeats, and the failures are quiet: someone never confirmed their laptop, an admin approval is sitting unanswered.

This project splits the work the way I think an agent should handle it:

- **The agent does the repeatable steps** (invites, welcome post, day-one plan) using its other MCP tools, then records each result here.
- **This server is the source of truth.** It does not pretend to create accounts. It tracks what is done, due, overdue or blocked, so the agent's actions are explicit and auditable.
- **A person gets only what needs a person**, each with a ready message.

## Quick start

```bash
git clone https://github.com/junaidmemon1/onboard-ops-mcp.git
cd onboard-ops-mcp
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

onboard-ops demo          # a full run on sample data, no setup
pytest                    # 19 tests
```

Use it for real:

```bash
onboard-ops add "Ada Lovelace" ada@example.com "Backend Engineer" 2026-12-01 --buddy Priya
onboard-ops queue         # what the agent should do now
onboard-ops done tm-001 work_email
onboard-ops stuck         # blocked or overdue, with follow-up messages
onboard-ops report        # weekly markdown summary
```

## Connect it to an MCP client

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "onboard-ops": {
      "command": "onboard-ops-mcp",
      "env": { "ONBOARD_OPS_DATA": "/absolute/path/to/onboarding-data.json" }
    }
  }
}
```

If the command is not on your PATH, use the full path to the virtualenv's `onboard-ops-mcp`.

## Tools

| Tool | What it does |
| --- | --- |
| `add_teammate` | Registers a person and generates a role-aware checklist dated from their start date |
| `agent_queue` | Automatable tasks that are due or overdue: the agent's to-do list |
| `complete_task` | Marks a task done after the action succeeded (idempotent) |
| `block_task` / `unblock_task` | Flags a task with a reason so a human can clear it |
| `stuck_tasks` | Blocked or overdue tasks with a ready-to-send follow-up for the owner |
| `onboarding_status` / `list_teammates` | Checklist and progress for one person or everyone |
| `weekly_report` | Markdown summary: progress, who starts soon, what is stuck |
| `draft_welcome_message` | Drafts a welcome message, sends nothing |
| `post_welcome_to_discord` | Posts it to Discord. Dry run unless `DISCORD_WEBHOOK_URL` is set |

It also exposes a `onboarding://teammates` resource and an `onboarding_operator` prompt that describes the run loop for the agent.

## Design decisions

- **State, not side effects.** The server never creates accounts or sends invites on its own. The agent does that with other tools and reports back. A task is only marked done after the action worked.
- **Safe by default.** Discord posting is a dry run until a webhook is configured. Webhook URLs are checked against Discord's domains, and messages cannot ping `@everyone`.
- **Clear errors.** Unknown IDs, duplicate emails, bad dates and missing block reasons all return a message that says what to fix.
- **Testable time.** Every tool takes an optional `today`, so overdue logic is tested without waiting for real days to pass.
- **Atomic writes.** The JSON store is written to a temporary file and swapped in, so a crash cannot leave a half-written file.
- **Zero extra dependencies.** The only runtime dependency is the `mcp` SDK (pinned below 2.0, because 2.x renamed `FastMCP`).

## Verifying it works

- `pytest`: unit tests for checklist dates, role-specific tasks, stuck detection, idempotency and error messages, plus a test that boots the MCP server and calls its tools.
- `python examples/stdio_client_check.py`: connects over stdio as a real MCP client and runs a full session.

## Limits

- Storage is a single JSON file. That is right for a small team and a demo; a larger deployment would swap `OnboardingService` for a database.
- The live demo page simulates the agent in the browser with the same checklist rules. It is not connected to a server.
- The checklist template lives in `src/onboard_ops/core.py`. Edit `BASE_TEMPLATE` and `ROLE_EXTRAS` to match your own process.

## Project layout

```
src/onboard_ops/
  core.py       checklist template, state, stuck detection
  server.py     MCP tools, resource and prompt
  notifier.py   welcome drafting and Discord webhook
  cli.py        command-line interface
  demo.py       sample roster
docs/index.html live demo (GitHub Pages)
tests/          pytest suite
```

MIT licensed.
