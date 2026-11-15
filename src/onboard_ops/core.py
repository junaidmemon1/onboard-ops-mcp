"""Core onboarding logic: checklist template, state store, stuck-task detection.

Design note
-----------
This module is the *source of truth* for onboarding state. It deliberately does
not create accounts or send invites itself. An AI agent connects other MCP
servers / APIs (email, Discord, HR tools) to do the actions, then records the
result here with ``complete_task``. That keeps state auditable and the
agent's actions explicit.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

OWNERS = ("agent", "operator", "teammate", "manager")

# (key, title, owner, category, due offset in days from start date, automatable)
BASE_TEMPLATE: list[tuple[str, str, str, str, int, bool]] = [
    ("work_email", "Create work email and password-manager account", "agent", "accounts", -3, True),
    ("tool_access", "Invite to tracker, docs and shared drive", "agent", "accounts", -2, True),
    ("discord_invite", "Send Discord invite and assign starting role", "agent", "accounts", -1, True),
    ("setup_check", "Confirm laptop, internet and working hours", "teammate", "setup", -1, False),
    ("welcome_post", "Post welcome message in #introductions", "agent", "people", 0, True),
    ("buddy_intro", "Introduce onboarding buddy", "operator", "people", 0, False),
    ("day_one_plan", "Send day-one checklist and who-to-ask list", "agent", "people", 0, True),
    ("handbook", "Read the handbook and confirm", "teammate", "learning", 1, False),
    ("first_task", "Assign a small first task", "manager", "work", 2, False),
    ("day3_checkin", "Day-3 check-in: any blockers?", "operator", "people", 3, False),
    ("week1_feedback", "Collect week-one feedback", "agent", "people", 7, True),
    ("records_check", "Verify onboarding records are complete", "operator", "records", 7, False),
]

# Extra tasks added by role keyword.
ROLE_EXTRAS: dict[str, list[tuple[str, str, str, str, int, bool]]] = {
    "engineer": [("repo_access", "Grant repository access and dev environment", "agent", "accounts", -1, True)],
    "developer": [("repo_access", "Grant repository access and dev environment", "agent", "accounts", -1, True)],
    "design": [("design_access", "Grant design tool and brand asset access", "agent", "accounts", -1, True)],
    "support": [("helpdesk_access", "Grant helpdesk access and macros library", "agent", "accounts", -1, True)],
}

DONE, BLOCKED, OVERDUE, DUE, UPCOMING = "done", "blocked", "overdue", "due", "upcoming"


@dataclass
class Task:
    id: str
    title: str
    owner: str
    category: str
    due: str  # ISO date
    automatable: bool
    done_on: str | None = None
    blocked: str | None = None  # reason if blocked

    def state(self, today: date) -> str:
        if self.done_on:
            return DONE
        if self.blocked:
            return BLOCKED
        due = date.fromisoformat(self.due)
        if due < today:
            return OVERDUE
        if due == today:
            return DUE
        return UPCOMING

    def days_overdue(self, today: date) -> int:
        if self.done_on:
            return 0
        return max(0, (today - date.fromisoformat(self.due)).days)


@dataclass
class Teammate:
    id: str
    name: str
    email: str
    role: str
    start_date: str
    timezone: str = "UTC"
    buddy: str | None = None
    tasks: list[Task] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Teammate":
        tasks = [Task(**t) for t in data.get("tasks", [])]
        rest = {k: v for k, v in data.items() if k != "tasks"}
        return cls(tasks=tasks, **rest)

    def progress(self) -> float:
        if not self.tasks:
            return 0.0
        return round(sum(1 for t in self.tasks if t.done_on) / len(self.tasks), 3)

    def phase(self, today: date) -> str:
        start = date.fromisoformat(self.start_date)
        if today < start:
            return "pre-start"
        if self.progress() == 1.0:
            return "settled"
        if today <= start + timedelta(days=7):
            return "first-week"
        return "past-first-week"


def _parse_date(value: str | None) -> date:
    if value is None:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc


def build_checklist(role: str, start: date) -> list[Task]:
    """Build the task list for a new teammate, with due dates from the start date."""
    rows = list(BASE_TEMPLATE)
    seen = {r[0] for r in rows}
    lowered = role.lower()
    for keyword, extras in ROLE_EXTRAS.items():
        if keyword in lowered:
            for row in extras:
                if row[0] not in seen:
                    rows.append(row)
                    seen.add(row[0])
    rows.sort(key=lambda r: (r[4], r[0]))
    return [
        Task(
            id=key,
            title=title,
            owner=owner,
            category=category,
            due=(start + timedelta(days=offset)).isoformat(),
            automatable=automatable,
        )
        for key, title, owner, category, offset, automatable in rows
    ]


class OnboardingService:
    """JSON-file backed onboarding tracker."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        default = os.environ.get("ONBOARD_OPS_DATA", "onboarding-data.json")
        self.path = Path(path or default)

    # ---------- persistence ----------
    def _load(self) -> dict[str, Teammate]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        return {tid: Teammate.from_dict(d) for tid, d in raw.get("teammates", {}).items()}

    def _save(self, teammates: dict[str, Teammate]) -> None:
        payload = {"teammates": {tid: asdict(t) for tid, t in teammates.items()}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            os.replace(tmp, self.path)  # atomic on POSIX and Windows
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def _get(self, teammates: dict[str, Teammate], teammate_id: str) -> Teammate:
        try:
            return teammates[teammate_id]
        except KeyError:
            known = ", ".join(sorted(teammates)) or "none yet"
            raise KeyError(f"Unknown teammate '{teammate_id}'. Known ids: {known}.") from None

    # ---------- commands ----------
    def add_teammate(
        self,
        name: str,
        email: str,
        role: str,
        start_date: str,
        timezone: str = "UTC",
        buddy: str | None = None,
    ) -> dict[str, Any]:
        name, email, role = name.strip(), email.strip().lower(), role.strip()
        if not name or not role:
            raise ValueError("name and role are required.")
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError(f"'{email}' is not a valid email address.")
        start = _parse_date(start_date)
        teammates = self._load()
        if any(t.email == email for t in teammates.values()):
            raise ValueError(f"A teammate with email {email} already exists.")
        next_n = 1 + max((int(t.id.split("-")[1]) for t in teammates.values()), default=0)
        tm = Teammate(
            id=f"tm-{next_n:03d}",
            name=name,
            email=email,
            role=role,
            start_date=start.isoformat(),
            timezone=timezone,
            buddy=buddy,
            tasks=build_checklist(role, start),
        )
        teammates[tm.id] = tm
        self._save(teammates)
        return self._summary(tm, date.today())

    def complete_task(self, teammate_id: str, task_id: str, today: str | None = None) -> dict[str, Any]:
        day = _parse_date(today)
        teammates = self._load()
        tm = self._get(teammates, teammate_id)
        task = self._task(tm, task_id)
        if task.done_on:
            return self._summary(tm, day)  # idempotent
        task.done_on = day.isoformat()
        task.blocked = None
        self._save(teammates)
        return self._summary(tm, day)

    def block_task(self, teammate_id: str, task_id: str, reason: str, today: str | None = None) -> dict[str, Any]:
        if not reason.strip():
            raise ValueError("A reason is required so the next person knows what is stuck.")
        day = _parse_date(today)
        teammates = self._load()
        tm = self._get(teammates, teammate_id)
        task = self._task(tm, task_id)
        if task.done_on:
            raise ValueError(f"Task '{task_id}' is already done.")
        task.blocked = reason.strip()
        self._save(teammates)
        return self._summary(tm, day)

    def unblock_task(self, teammate_id: str, task_id: str, today: str | None = None) -> dict[str, Any]:
        day = _parse_date(today)
        teammates = self._load()
        tm = self._get(teammates, teammate_id)
        self._task(tm, task_id).blocked = None
        self._save(teammates)
        return self._summary(tm, day)

    # ---------- queries ----------
    def get_teammate(self, teammate_id: str) -> Teammate:
        return self._get(self._load(), teammate_id)

    def list_teammates(self, today: str | None = None) -> list[dict[str, Any]]:
        day = _parse_date(today)
        return [self._summary(t, day) for t in self._load().values()]

    def status(self, teammate_id: str, today: str | None = None) -> dict[str, Any]:
        day = _parse_date(today)
        tm = self._get(self._load(), teammate_id)
        out = self._summary(tm, day)
        out["tasks"] = [
            {**asdict(t), "state": t.state(day), "days_overdue": t.days_overdue(day)} for t in tm.tasks
        ]
        return out

    def agent_queue(self, today: str | None = None) -> list[dict[str, Any]]:
        """Automatable tasks that are due or overdue: the agent's to-do list."""
        day = _parse_date(today)
        items = []
        for tm in self._load().values():
            for t in tm.tasks:
                if t.automatable and t.state(day) in (DUE, OVERDUE):
                    items.append(
                        {
                            "teammate_id": tm.id,
                            "teammate": tm.name,
                            "task_id": t.id,
                            "title": t.title,
                            "due": t.due,
                            "days_overdue": t.days_overdue(day),
                        }
                    )
        items.sort(key=lambda i: (-i["days_overdue"], i["due"], i["teammate_id"]))
        return items

    def stuck(self, today: str | None = None, min_days_overdue: int = 1) -> list[dict[str, Any]]:
        """Tasks that are blocked, or overdue by at least ``min_days_overdue`` days."""
        day = _parse_date(today)
        out = []
        for tm in self._load().values():
            for t in tm.tasks:
                state = t.state(day)
                overdue = t.days_overdue(day)
                if state == BLOCKED or (state == OVERDUE and overdue >= min_days_overdue):
                    out.append(
                        {
                            "teammate_id": tm.id,
                            "teammate": tm.name,
                            "task_id": t.id,
                            "title": t.title,
                            "owner": t.owner,
                            "state": state,
                            "days_overdue": overdue,
                            "blocked_reason": t.blocked,
                            "suggested_followup": followup_text(tm, t, overdue),
                        }
                    )
        out.sort(key=lambda i: (-i["days_overdue"], i["teammate_id"]))
        return out

    def report(self, today: str | None = None) -> dict[str, Any]:
        day = _parse_date(today)
        teammates = list(self._load().values())
        summaries = [self._summary(t, day) for t in teammates]
        stuck = self.stuck(today)
        starting_soon = [s for s in summaries if s["phase"] == "pre-start"]
        avg = round(sum(s["progress"] for s in summaries) / len(summaries), 3) if summaries else 0.0
        return {
            "as_of": day.isoformat(),
            "teammates": len(summaries),
            "average_progress": avg,
            "starting_soon": [{"id": s["id"], "name": s["name"], "start_date": s["start_date"]} for s in starting_soon],
            "stuck_count": len(stuck),
            "stuck": stuck,
            "agent_queue_size": len(self.agent_queue(today)),
        }

    # ---------- helpers ----------
    @staticmethod
    def _task(tm: Teammate, task_id: str) -> Task:
        for t in tm.tasks:
            if t.id == task_id:
                return t
        raise KeyError(f"Unknown task '{task_id}' for {tm.id}. Tasks: {', '.join(t.id for t in tm.tasks)}.")

    @staticmethod
    def _summary(tm: Teammate, day: date) -> dict[str, Any]:
        states = [t.state(day) for t in tm.tasks]
        return {
            "id": tm.id,
            "name": tm.name,
            "email": tm.email,
            "role": tm.role,
            "start_date": tm.start_date,
            "timezone": tm.timezone,
            "buddy": tm.buddy,
            "phase": tm.phase(day),
            "progress": tm.progress(),
            "done": states.count(DONE),
            "total": len(states),
            "overdue": states.count(OVERDUE),
            "blocked": states.count(BLOCKED),
        }


def followup_text(tm: Teammate, task: Task, days_overdue: int) -> str:
    """A short, plain follow-up message for whoever owns a stuck task."""
    first = tm.name.split()[0]
    if task.blocked:
        return f"Blocked: '{task.title}' for {tm.name}. Reason: {task.blocked}. What would unblock it?"
    when = "today" if days_overdue == 0 else f"{days_overdue} day{'s' if days_overdue != 1 else ''} ago"
    if task.owner == "teammate":
        return f"Hi {first}, a quick nudge: '{task.title}' was due {when}. Anything in the way? Happy to help."
    if task.owner == "agent":
        return f"Agent task overdue ({when}): '{task.title}' for {tm.name}. Run it now or flag the blocker."
    return f"Reminder for the {task.owner}: '{task.title}' for {tm.name} was due {when}."


def render_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Onboarding report ({report['as_of']})",
        "",
        f"- Teammates in onboarding: **{report['teammates']}**",
        f"- Average progress: **{round(report['average_progress'] * 100)}%**",
        f"- Agent queue: **{report['agent_queue_size']}** task(s) due now",
        f"- Stuck: **{report['stuck_count']}**",
        "",
    ]
    if report["starting_soon"]:
        lines.append("## Starting soon")
        lines += [f"- {s['name']} starts {s['start_date']}" for s in report["starting_soon"]]
        lines.append("")
    if report["stuck"]:
        lines.append("## Stuck")
        for s in report["stuck"]:
            why = f" (blocked: {s['blocked_reason']})" if s["blocked_reason"] else f" ({s['days_overdue']}d overdue)"
            lines.append(f"- **{s['teammate']}**: {s['title']} [{s['owner']}]{why}")
        lines.append("")
    else:
        lines.append("Nothing is stuck.")
    return "\n".join(lines)
