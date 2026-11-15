from datetime import date

import pytest

from onboard_ops.core import OnboardingService, build_checklist, render_report_markdown
from onboard_ops.demo import seed_demo


@pytest.fixture
def svc(tmp_path):
    return OnboardingService(tmp_path / "store.json")


def test_checklist_is_dated_from_start_and_role_aware():
    tasks = build_checklist("Backend Engineer", date(2026, 12, 1))
    ids = [t.id for t in tasks]
    assert "repo_access" in ids
    assert "design_access" not in ids
    assert tasks[0].due <= tasks[-1].due  # sorted by due date
    assert next(t for t in tasks if t.id == "welcome_post").due == "2026-12-01"
    assert next(t for t in tasks if t.id == "work_email").due == "2026-11-28"


def test_add_and_persist(svc):
    res = svc.add_teammate("Ada Lovelace", "Ada@Example.com", "Engineer", "2026-12-01")
    assert res["id"] == "tm-001"
    assert svc.get_teammate("tm-001").email == "ada@example.com"
    assert len(svc.list_teammates("2026-11-20")) == 1


def test_rejects_bad_input_and_duplicates(svc):
    svc.add_teammate("Ada", "ada@example.com", "Engineer", "2026-12-01")
    with pytest.raises(ValueError, match="already exists"):
        svc.add_teammate("Ada Two", "ADA@example.com", "Engineer", "2026-12-01")
    with pytest.raises(ValueError, match="valid email"):
        svc.add_teammate("Bob", "not-an-email", "Engineer", "2026-12-01")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        svc.add_teammate("Bob", "bob@example.com", "Engineer", "01/12/2026")


def test_ids_do_not_collide_after_multiple_adds(svc):
    for i in range(3):
        svc.add_teammate(f"P{i}", f"p{i}@example.com", "Support", "2026-12-01")
    assert [t["id"] for t in svc.list_teammates("2026-11-20")] == ["tm-001", "tm-002", "tm-003"]


def test_complete_is_idempotent_and_updates_progress(svc):
    svc.add_teammate("Ada", "ada@example.com", "Support", "2026-12-01")
    first = svc.complete_task("tm-001", "work_email", "2026-11-28")
    second = svc.complete_task("tm-001", "work_email", "2026-11-29")
    assert first["done"] == second["done"] == 1
    # first completion date is kept
    task = next(t for t in svc.get_teammate("tm-001").tasks if t.id == "work_email")
    assert task.done_on == "2026-11-28"


def test_unknown_ids_give_helpful_errors(svc):
    svc.add_teammate("Ada", "ada@example.com", "Support", "2026-12-01")
    with pytest.raises(KeyError, match="Known ids: tm-001"):
        svc.status("tm-999")
    with pytest.raises(KeyError, match="Unknown task"):
        svc.complete_task("tm-001", "nope")


def test_agent_queue_only_contains_due_automatable_tasks(svc):
    svc.add_teammate("Ada", "ada@example.com", "Support", "2026-12-01")
    queue = svc.agent_queue("2026-11-30")
    assert queue and all(q["task_id"] in {"work_email", "tool_access", "helpdesk_access", "discord_invite"} for q in queue)
    # operator/teammate tasks never appear in the agent queue
    assert not any(q["task_id"] in {"buddy_intro", "setup_check"} for q in queue)


def test_stuck_detects_overdue_and_blocked_with_followups(svc):
    svc.add_teammate("Ada Lovelace", "ada@example.com", "Engineer", "2026-12-01")
    svc.block_task("tm-001", "repo_access", "Admin approval pending", "2026-11-30")
    stuck = svc.stuck("2026-12-05")
    ids = {s["task_id"] for s in stuck}
    assert "repo_access" in ids  # blocked
    assert "setup_check" in ids  # teammate task overdue
    follow = next(s for s in stuck if s["task_id"] == "setup_check")["suggested_followup"]
    assert follow.startswith("Hi Ada")
    blocked = next(s for s in stuck if s["task_id"] == "repo_access")
    assert "Admin approval pending" in blocked["suggested_followup"]


def test_block_requires_reason_and_complete_clears_block(svc):
    svc.add_teammate("Ada", "ada@example.com", "Support", "2026-12-01")
    with pytest.raises(ValueError, match="reason"):
        svc.block_task("tm-001", "work_email", "  ")
    svc.block_task("tm-001", "work_email", "IT ticket open")
    svc.complete_task("tm-001", "work_email", "2026-11-29")
    task = next(t for t in svc.get_teammate("tm-001").tasks if t.id == "work_email")
    assert task.blocked is None and task.done_on == "2026-11-29"


def test_phase_transitions(svc):
    svc.add_teammate("Ada", "ada@example.com", "Support", "2026-12-01")
    assert svc.status("tm-001", "2026-11-20")["phase"] == "pre-start"
    assert svc.status("tm-001", "2026-12-03")["phase"] == "first-week"
    assert svc.status("tm-001", "2026-12-20")["phase"] == "past-first-week"
    for t in svc.get_teammate("tm-001").tasks:
        svc.complete_task("tm-001", t.id, "2026-12-02")
    assert svc.status("tm-001", "2026-12-20")["phase"] == "settled"


def test_demo_report_is_consistent(svc):
    today = seed_demo(svc, date(2026, 11, 16))
    report = svc.report(today.isoformat())
    assert report["teammates"] == 4
    assert report["stuck_count"] >= 2
    assert any(s["blocked_reason"] for s in report["stuck"])
    md = render_report_markdown(report)
    assert "Onboarding report (2026-11-16)" in md and "## Stuck" in md


def test_store_survives_corrupt_free_roundtrip(svc):
    svc.add_teammate("Ada", "ada@example.com", "Support", "2026-12-01")
    again = OnboardingService(svc.path)
    assert again.get_teammate("tm-001").name == "Ada"
