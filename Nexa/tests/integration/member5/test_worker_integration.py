import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "unit", "member5"))
from conftest import Env, T0  # noqa: E402
from fakes import ScriptedEmailSender  # noqa: E402

from nexa.contracts.meetings import ActionItem  # noqa: E402
from nexa.scheduling.calculator import CAIRO, UTC, from_db  # noqa: E402
from nexa.scheduling.completion import CompletionService  # noqa: E402
from nexa.scheduling.service import ReminderService  # noqa: E402
from nexa.scheduling.snooze import InvalidSnoozeTime, ReminderNotSnoozable  # noqa: E402
from nexa.worker.claim import ClaimCoordinator  # noqa: E402
from nexa.worker.health import WorkerState, check_worker_health  # noqa: E402
from nexa.worker.heartbeat import Heartbeat  # noqa: E402
from nexa.worker.single_instance import SingleInstanceLock  # noqa: E402
from nexa.worker import windows_startup  # noqa: E402


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path / "n.db")


def seed_same_time(env, n=100):
    ids = []
    for i in range(1, n + 1):
        env.add_action(id=i, owner=(i % 5) + 1)
        ids.append(env.add_reminder(i, T0))
    return ids


def test_schedule_creates_independent_records(env):
    env.add_action(id=1)
    a = ActionItem(id=1, meeting_id=1, due_date=datetime(2026, 9, 7).date(), due_time=datetime(2026, 9, 7, 15).time())
    env.now = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)
    rs = ReminderService(env.queue).schedule_for_action(a)
    assert len(rs) == 2 and len({r.id for r in rs}) == 2 and len({r.idempotency_key for r in rs}) == 2
    assert len(ReminderService(env.queue).schedule_for_action(a)) == 2       # idempotent
    assert sum(env.queue.count_by_status().values()) == 2
    assert env.audit.types().count("reminder.create") == 2


def test_100_same_time_reminders_no_mix_no_duplicates(env):
    ids = seed_same_time(env, 100)
    s = env.worker(batch_size=30).run_once(T0)
    assert s.sent == 100 and len(env.sender.sent) == 100
    assert {env.row(i)["status"] for i in ids} == {"SENT"}
    # each email went to the right owner for its own task
    for i, m in zip(range(1, 101), sorted(env.sender.sent, key=lambda m: int(m.subject.split()[-1]))):
        assert m.subject.endswith(f"Task {i}") and m.to == [f"emp{(i % 5) + 1}@x.eg"]
    assert env.worker().run_once(T0).sent == 0                               # nothing re-sent


def test_parallel_claims_never_overlap(env):
    ids = seed_same_time(env, 100)
    got, lock = [], threading.Lock()

    def loop():
        while True:
            b = env.queue.claim_due(T0, 7)
            if not b:
                return
            with lock:
                got.extend(r.id for r in b)
    ts = [threading.Thread(target=loop) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert sorted(got) == sorted(ids)
    assert not env.queue.claim_one(ids[0], T0)                               # already claimed


def test_restart_mid_batch_no_double_send(env):
    ids = seed_same_time(env, 10)
    w = env.worker()
    first = env.queue.claim_due(T0, 10)                                       # worker "crashes" after claiming 10
    for r in first[:3]:                                                       # ...having fully processed 3
        w._process(r, T0, __import__("nexa.worker.service", fromlist=["RunSummary"]).RunSummary())
    assert len(env.sender.sent) == 3
    later = T0 + timedelta(minutes=10)
    env.now = later
    s = env.worker(stale_claim_after=timedelta(minutes=5)).run_once(later)
    assert s.abandoned_recovered == 7 and len(env.sender.sent) == 10
    assert {env.row(i)["status"] for i in ids} == {"SENT"}


def test_crash_while_sending_does_not_resend_to_delivered_recipient(env):
    env.add_action(id=1, owner=1); rid = env.add_reminder(1, T0)
    w = env.worker()
    r = env.queue.claim_due(T0, 1)[0]
    env.queue.transition(r.id, [__import__("nexa.scheduling.states", fromlist=["x"]).ReminderStatus.CLAIMED],
                         __import__("nexa.scheduling.states", fromlist=["x"]).ReminderStatus.SENDING, T0, increment_attempt=True)
    w.d.recorder.record(reminder=r, action=w.d.lookup.get_action(1), employee=env.employees[0], email=None,
                        result=__import__("nexa.contracts.email", fromlist=["x"]).SendResult(True, "m1"),
                        language="ENGLISH", attempted_at=T0, late_recovery=False)   # sent, then crash
    later = T0 + timedelta(minutes=10); env.now = later
    env.worker(stale_claim_after=timedelta(minutes=5)).run_once(later)
    assert env.sender.sent == [] and env.row(rid)["status"] == "SENT"


def test_device_offline_30_min_late_recovery(env):
    env.add_action(id=1); rid = env.add_reminder(1, T0)
    now = T0 + timedelta(minutes=30); env.now = now
    s = env.worker().run_once(now)
    assert s.sent == 1 and s.late_recovered == 1 and env.row(rid)["status"] == "SENT"
    assert "reminder.late_recovery" in env.audit.types()


def test_beyond_recovery_window_not_sent(env):
    env.add_action(id=1); rid = env.add_reminder(1, T0)
    now = T0 + timedelta(hours=30); env.now = now
    env.worker().run_once(now)
    assert env.sender.sent == [] and env.row(rid)["status"] == "FAILED"
    assert env.row(rid)["last_error"] == "MISSED_RECOVERY_WINDOW_EXPIRED"


def test_completed_task_reminder_never_sent(env):
    env.add_action(id=1); rid = env.add_reminder(1, T0)
    res = CompletionService(env.queue).mark_complete(1, "admin")
    assert res.skipped_reminder_ids == [rid]
    assert env.row(rid)["status"] == "SKIPPED_COMPLETED"
    env.worker().run_once(T0)
    assert env.sender.sent == []
    c = env.factory(); a = c.execute("SELECT status, completed_at FROM action_items WHERE id=1").fetchone(); c.close()
    assert a["status"] == "COMPLETED" and a["completed_at"]
    assert CompletionService(env.queue).mark_complete(1).already_completed
    assert "action.mark_complete" in env.audit.types()


def test_completed_after_claim_worker_double_checks(env):
    env.add_action(id=1); rid = env.add_reminder(1, T0)
    claimed = env.queue.claim_due(T0, 5)
    c = env.factory(); c.execute("UPDATE action_items SET status='COMPLETED' WHERE id=1"); c.close()
    from nexa.worker.service import RunSummary
    env.worker()._process(claimed[0], T0, RunSummary())
    assert env.sender.sent == [] and env.row(rid)["status"] == "SKIPPED_COMPLETED"


def test_completion_preserves_sent_history(env):
    env.add_action(id=1); sent = env.add_reminder(1, T0, "SENT"); pend = env.add_reminder(1, T0 + timedelta(days=1))
    CompletionService(env.queue).mark_complete(1)
    assert env.row(sent)["status"] == "SENT" and env.row(pend)["status"] == "SKIPPED_COMPLETED"


def test_snooze_moves_reminder_not_deadline(env):
    env.add_action(id=1); rid = env.add_reminder(1, T0)
    new_time = T0 + timedelta(hours=2)
    new = ReminderService(env.queue).snooze(rid, new_time)
    assert env.row(rid)["status"] == "SNOOZED" and new.status == "PENDING"
    env.worker().run_once(T0 + timedelta(minutes=1))
    assert env.sender.sent == []                                              # original time not sent
    env.worker().run_once(new_time)
    assert len(env.sender.sent) == 1
    c = env.factory(); a = c.execute("SELECT due_date, due_time FROM action_items WHERE id=1").fetchone(); c.close()
    assert (a["due_date"], a["due_time"]) == ("2026-09-07", "15:00")          # deadline untouched
    assert "reminder.snooze" in env.audit.types()


def test_snooze_validation(env):
    env.add_action(id=1); rid = env.add_reminder(1, T0)
    svc = ReminderService(env.queue)
    with pytest.raises(InvalidSnoozeTime):
        svc.snooze(rid, T0 - timedelta(minutes=1))
    sent = env.add_reminder(1, T0, "SENT", key="x")
    with pytest.raises(ReminderNotSnoozable):
        svc.snooze(sent, T0 + timedelta(hours=1))


def test_retry_schedule_then_success(env):
    env.add_action(id=1); rid = env.add_reminder(1, T0)
    sender = ScriptedEmailSender(fail_times=2)
    w = env.worker(sender)
    assert w.run_once(T0).retry_scheduled == 1
    r = env.row(rid)
    assert r["status"] == "RETRY_WAIT" and from_db(r["next_attempt_at"]) == T0 + timedelta(minutes=1)
    assert w.run_once(T0 + timedelta(seconds=30)).claimed == 0                # not yet
    t2 = T0 + timedelta(minutes=1); env.now = t2
    w.run_once(t2)
    assert from_db(env.row(rid)["next_attempt_at"]) == t2 + timedelta(minutes=5)
    t3 = t2 + timedelta(minutes=5); env.now = t3
    w.run_once(t3)
    assert env.row(rid)["status"] == "SENT" and env.row(rid)["attempt_count"] == 3 and len(sender.sent) == 1


def test_retries_exhausted_then_failed(env):
    env.add_action(id=1); rid = env.add_reminder(1, T0)
    w = env.worker(ScriptedEmailSender(fail_times=99)); now = T0
    for delay in (0, 1, 5, 15, 30):
        now = now + timedelta(minutes=delay); env.now = now
        w.run_once(now)
    r = env.row(rid)
    assert r["status"] == "FAILED" and r["attempt_count"] == 5 and "boom" in r["last_error"]


def test_permanent_error_fails_immediately(env):
    env.add_action(id=1); rid = env.add_reminder(1, T0)
    env.worker(ScriptedEmailSender(fail_times=9, permanent=True)).run_once(T0)
    assert env.row(rid)["status"] == "FAILED" and env.row(rid)["attempt_count"] == 1


def test_delivery_logged_with_gmail_id_and_no_recipient_fails(env):
    env.add_action(id=1, owner=1); env.add_action(id=2, owner=None)
    env.add_reminder(1, T0); r2 = env.add_reminder(2, T0)
    env.worker().run_once(T0)
    c = env.factory(); d = c.execute("SELECT * FROM email_deliveries").fetchall(); c.close()
    assert len(d) == 1 and d[0]["status"] == "SENT" and d[0]["gmail_message_id"] == "fake-1"
    assert env.row(r2)["last_error"] == "NO_RECIPIENTS"


def test_reschedule_invalidates_obsolete_and_recalculates(env):
    env.add_action(id=1)
    env.now = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)
    a = ActionItem(id=1, meeting_id=1, due_date=datetime(2026, 9, 7).date(), due_time=datetime(2026, 9, 7, 15).time())
    svc = ReminderService(env.queue)
    old = svc.schedule_for_action(a)
    new = svc.reschedule_action(1, datetime(2026, 9, 10, 14, 0, tzinfo=CAIRO))
    assert {env.row(r.id)["status"] for r in old} == {"CANCELLED"}
    assert [r.scheduled_at.astimezone(CAIRO).strftime("%m-%d %H:%M") for r in new] == ["09-09 20:00", "09-10 08:00"]
    c = env.factory(); a = c.execute("SELECT due_date,due_time FROM action_items WHERE id=1").fetchone(); c.close()
    assert (a["due_date"], a["due_time"]) == ("2026-09-10", "14:00")
    assert "action.reschedule" in env.audit.types()


def test_graceful_shutdown_releases_unprocessed(env):
    seed_same_time(env, 5)
    w = env.worker()
    orig = w._process
    def once_then_stop(r, now, s):
        orig(r, now, s); w.stop()
    w._process = once_then_stop
    s = w.run_once(T0)
    assert s.sent == 1 and s.released == 4 and env.queue.count_by_status() == {"SENT": 1, "PENDING": 4}


def test_run_forever_heartbeat_and_health(env):
    env.add_action(id=1); env.add_reminder(1, T0)
    hb = Heartbeat(env.factory, lambda: env.now)
    w = env.worker(); w.heartbeat = hb; w.poll_interval = 0.01
    t = threading.Thread(target=w.run_forever); t.start()
    for _ in range(200):
        if env.sender.sent: break
        threading.Event().wait(0.01)
    w.stop(); t.join(5)
    assert len(env.sender.sent) == 1
    assert check_worker_health(env.factory, env.now).state == WorkerState.OFFLINE      # stopped cleanly
    hb.beat({"sent": 0})
    assert check_worker_health(env.factory, env.now + timedelta(seconds=30)).state == WorkerState.HEALTHY
    assert check_worker_health(env.factory, env.now + timedelta(minutes=2)).state == WorkerState.STALE
    assert check_worker_health(env.factory, env.now + timedelta(minutes=10)).state == WorkerState.OFFLINE


def test_health_without_heartbeat_is_offline(env):
    assert check_worker_health(env.factory, T0).state == WorkerState.OFFLINE


@pytest.mark.skipif(sys.platform == "win32", reason="file-lock path")
def test_single_instance(tmp_path):
    a, b = SingleInstanceLock("t", str(tmp_path)), SingleInstanceLock("t", str(tmp_path))
    assert a.acquire() and not b.acquire()
    a.release()
    assert b.acquire(); b.release()


def test_windows_startup_unsupported_off_windows():
    if sys.platform != "win32":
        with pytest.raises(windows_startup.UnsupportedPlatform):
            windows_startup.enable_startup("C:/Nexa/NexaWorker.exe")
    assert windows_startup.build_command("C:/N/W.exe", "--background") == '"C:/N/W.exe" --background'


def test_worker_app_cli_runs_without_gui(env, monkeypatch, tmp_path):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "apps"))
    import nexa_worker
    env.add_action(id=1); env.add_reminder(1, datetime.now(timezone.utc) - timedelta(seconds=5))
    rc = nexa_worker.main(["--db", env.path, "--once", "--log-dir", str(tmp_path / "logs")],
                          deps_builder=lambda cfg: env.deps(clock=None) if False else _live(env))
    assert rc == 0 and len(env.sender.sent) == 1


def _live(env):
    d = env.deps()
    d.clock = lambda: datetime.now(timezone.utc)
    d.queue.clock = d.clock
    return d
