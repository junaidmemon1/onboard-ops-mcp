"""Command-line interface: use the tracker without an AI agent, or start the MCP server."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .core import OnboardingService, render_report_markdown
from .demo import seed_demo
from .notifier import draft_welcome, send_discord

ICON = {"done": "✔", "due": "●", "overdue": "!", "blocked": "✖", "upcoming": "·"}


def _bar(progress: float, width: int = 20) -> str:
    filled = round(progress * width)
    return "█" * filled + "░" * (width - filled)


def _print_status(data: dict) -> None:
    print(f"\n{data['name']} ({data['id']}) · {data['role']} · starts {data['start_date']} · {data['phase']}")
    print(f"  {_bar(data['progress'])} {round(data['progress'] * 100)}%  ({data['done']}/{data['total']})")
    for t in data["tasks"]:
        extra = ""
        if t["state"] == "overdue":
            extra = f"  ← {t['days_overdue']}d overdue"
        elif t["state"] == "blocked":
            extra = f"  ← blocked: {t['blocked']}"
        print(f"  {ICON[t['state']]} {t['title']} [{t['owner']}] due {t['due']}{extra}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="onboard-ops", description="Run new-teammate onboarding with agents.")
    p.add_argument("--data", help="Path to the JSON store (default: $ONBOARD_OPS_DATA or ./onboarding-data.json)")
    p.add_argument("--today", help="Override today's date (YYYY-MM-DD), useful for testing")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="Add a teammate and generate their checklist")
    a.add_argument("name")
    a.add_argument("email")
    a.add_argument("role")
    a.add_argument("start_date", help="YYYY-MM-DD")
    a.add_argument("--timezone", default="UTC")
    a.add_argument("--buddy")

    sub.add_parser("list", help="List teammates in onboarding")
    s = sub.add_parser("status", help="Show one teammate's checklist")
    s.add_argument("teammate_id")
    d = sub.add_parser("done", help="Mark a task done")
    d.add_argument("teammate_id")
    d.add_argument("task_id")
    b = sub.add_parser("block", help="Flag a task as blocked")
    b.add_argument("teammate_id")
    b.add_argument("task_id")
    b.add_argument("reason")
    sub.add_parser("queue", help="Tasks the agent should do now")
    st = sub.add_parser("stuck", help="Blocked or overdue tasks with follow-up messages")
    st.add_argument("--min-days", type=int, default=1)
    sub.add_parser("report", help="Weekly markdown report")
    w = sub.add_parser("welcome", help="Draft (and optionally post) a welcome message")
    w.add_argument("teammate_id")
    w.add_argument("--post", action="store_true", help="Post to Discord (needs DISCORD_WEBHOOK_URL)")
    sub.add_parser("demo", help="Run a self-contained demo in a temporary store")
    sub.add_parser("serve", help="Start the MCP server (stdio)")
    return p


def run_demo() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        svc = OnboardingService(Path(tmp) / "demo.json")
        today = seed_demo(svc)
        iso = today.isoformat()
        print(f"Demo roster seeded for {iso}.\n")
        print("1) Agent queue: what the agent should do right now")
        for item in svc.agent_queue(iso):
            print(f"   - {item['teammate']}: {item['title']} (due {item['due']})")
        print("\n2) Stuck: what needs a human, with a ready follow-up")
        for item in svc.stuck(iso):
            print(f"   - {item['teammate']} · {item['title']} [{item['owner']}]")
            print(f"     {item['suggested_followup']}")
        print("\n3) Weekly report\n")
        print(render_report_markdown(svc.report(iso)))
        print("\n4) Welcome message (dry run)\n")
        print(draft_welcome(svc.get_teammate("tm-003"), "Acme"))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "demo":
        return run_demo()
    if args.cmd == "serve":
        if args.data:
            os.environ["ONBOARD_OPS_DATA"] = args.data
        from .server import main as serve

        serve()
        return 0

    svc = OnboardingService(args.data)
    try:
        if args.cmd == "add":
            res = svc.add_teammate(args.name, args.email, args.role, args.start_date, args.timezone, args.buddy)
            print(f"Added {res['name']} as {res['id']} with {res['total']} onboarding tasks.")
        elif args.cmd == "list":
            rows = svc.list_teammates(args.today)
            if not rows:
                print("No teammates yet. Add one with: onboard-ops add NAME EMAIL ROLE YYYY-MM-DD")
            for r in rows:
                print(f"{r['id']}  {r['name']:<20} {r['phase']:<16} {_bar(r['progress'], 10)} {r['done']}/{r['total']}")
        elif args.cmd == "status":
            _print_status(svc.status(args.teammate_id, args.today))
        elif args.cmd == "done":
            r = svc.complete_task(args.teammate_id, args.task_id, args.today)
            print(f"Done. {r['name']} is at {round(r['progress'] * 100)}%.")
        elif args.cmd == "block":
            svc.block_task(args.teammate_id, args.task_id, args.reason, args.today)
            print("Blocked. It will show up in `onboard-ops stuck`.")
        elif args.cmd == "queue":
            items = svc.agent_queue(args.today)
            print(json.dumps(items, indent=2) if items else "Agent queue is empty.")
        elif args.cmd == "stuck":
            items = svc.stuck(args.today, args.min_days)
            if not items:
                print("Nothing is stuck.")
            for i in items:
                print(f"{i['teammate']} · {i['title']} [{i['owner']}]\n  {i['suggested_followup']}")
        elif args.cmd == "report":
            print(render_report_markdown(svc.report(args.today)))
        elif args.cmd == "welcome":
            text = draft_welcome(svc.get_teammate(args.teammate_id))
            print(text)
            if args.post:
                print(json.dumps(send_discord(text), indent=2))
    except (KeyError, ValueError) as exc:
        print(f"Error: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
