"""Seed a realistic demo roster so the tool can be tried in one command."""

from __future__ import annotations

from datetime import date, timedelta

from .core import OnboardingService

DEMO_PEOPLE = [
    # name, email, role, start offset (days from today), tz, buddy
    ("Amara Okafor", "amara@example.com", "Support Specialist", -10, "Africa/Lagos", "Daniel"),
    ("Mateo Silva", "mateo@example.com", "Backend Engineer", -3, "America/Sao_Paulo", "Priya"),
    ("Hana Sato", "hana@example.com", "Product Designer", 0, "Asia/Tokyo", "Leo"),
    ("Omar Haddad", "omar@example.com", "Frontend Developer", 4, "Europe/Berlin", None),
]


def seed_demo(service: OnboardingService, today: date | None = None) -> date:
    """Populate ``service`` with demo teammates in different stages. Returns the 'today' used."""
    today = today or date.today()
    iso = today.isoformat()
    for name, email, role, offset, tz, buddy in DEMO_PEOPLE:
        service.add_teammate(name, email, role, (today + timedelta(days=offset)).isoformat(), tz, buddy)

    # Amara (tm-001): well along, but two things are stuck.
    for tid in ("work_email", "tool_access", "helpdesk_access", "discord_invite", "setup_check", "welcome_post",
                "buddy_intro", "day_one_plan", "handbook", "first_task"):
        service.complete_task("tm-001", tid, iso)
    # day3_checkin (operator) and week1_feedback (agent) stay overdue/open.

    # Mateo (tm-002): accounts done, repo access blocked on a real blocker.
    for tid in ("work_email", "tool_access", "discord_invite", "welcome_post", "buddy_intro"):
        service.complete_task("tm-002", tid, iso)
    service.block_task("tm-002", "repo_access", "GitHub org invite needs an admin approval", iso)

    # Hana (tm-003): starts today, accounts done, setup check not confirmed by the teammate.
    for tid in ("work_email", "tool_access", "design_access", "discord_invite"):
        service.complete_task("tm-003", tid, iso)
    return today
