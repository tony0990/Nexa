from datetime import date, datetime, time, timedelta, timezone

import pytest

from nexa.scheduling.calculator import CAIRO, UTC, calculate_reminders, from_db, to_db
from nexa.scheduling.recovery import DueClass, RecoveryPolicy
from nexa.scheduling.retry import RetryPolicy
from nexa.scheduling.rules import ReminderPolicy
from nexa.scheduling.snooze import SnoozeOption, resolve_snooze_time
from nexa.scheduling.states import (InvalidTransition, ReminderStatus as S, ReminderType,
                                    assert_transition, make_idempotency_key, reminder_type_from_key)

P = ReminderPolicy.default()


def local(plans):
    return [(p.local.date().isoformat(), p.local.strftime("%H:%M"), p.reminder_type) for p in plans]


def test_default_rules_previous_day_2000_and_event_day_0800():
    plans = calculate_reminders(date(2026, 9, 7), time(15, 0), None, P)
    assert local(plans) == [("2026-09-06", "20:00", ReminderType.PREVIOUS_DAY),
                            ("2026-09-07", "08:00", ReminderType.EVENT_DAY)]
    assert all(p.scheduled_at.tzinfo is not None for p in plans)


@pytest.mark.parametrize("event,expected", [
    (time(9, 0), "07:00"), (time(8, 0), "06:00"), (time(7, 0), "06:00"), (time(6, 30), "06:00"),
])
def test_early_event_rule(event, expected):
    plans = calculate_reminders(date(2026, 9, 7), event, None, P)
    day = [p for p in plans if p.reminder_type == ReminderType.EARLY_EVENT]
    assert day and day[0].local.strftime("%H:%M") == expected
    assert all(p.local < datetime.combine(date(2026, 9, 7), event, tzinfo=CAIRO) for p in plans)


def test_very_early_event_never_reminded_after_event():
    plans = calculate_reminders(date(2026, 9, 7), time(5, 0), None, P)
    ev = datetime(2026, 9, 7, 5, 0, tzinfo=CAIRO)
    assert plans and all(p.local < ev for p in plans)


def test_event_after_nine_uses_0800():
    plans = calculate_reminders(date(2026, 9, 7), time(9, 1), None, P)
    assert ("2026-09-07", "08:00", ReminderType.EVENT_DAY) in local(plans)


def test_date_only_and_no_date():
    assert [p.local.strftime("%H:%M") for p in calculate_reminders(date(2026, 9, 7), None, None, P)] == ["20:00", "08:00"]
    assert calculate_reminders(None, None, None, P) == []


def test_past_reminders_are_dropped():
    now = datetime(2026, 9, 7, 6, 0, tzinfo=timezone.utc)   # 09:00 Cairo
    assert calculate_reminders(date(2026, 9, 7), time(15, 0), None, P, now) == []


def test_settings_change_times():
    pol = ReminderPolicy.from_settings({"default_evening_reminder_time": "19:30", "default_morning_reminder_time": '"07:15"'})
    assert [p.local.strftime("%H:%M") for p in calculate_reminders(date(2026, 9, 7), time(15, 0), None, pol)] == ["19:30", "07:15"]


def test_db_roundtrip_utc():
    dt = datetime(2026, 9, 6, 20, 0, tzinfo=CAIRO)
    assert from_db(to_db(dt)) == dt and to_db(dt) == "2026-09-06 17:00:00"


def test_retry_policy_matches_spec():
    r, now = RetryPolicy(), datetime(2026, 1, 1, tzinfo=UTC)
    assert [r.next_attempt(n, now) - now for n in (1, 2, 3, 4)] == [timedelta(minutes=m) for m in (1, 5, 15, 30)]
    assert r.next_attempt(5, now) is None and r.max_attempts == 5


def test_recovery_classification():
    p, now = RecoveryPolicy(recovery_window=timedelta(hours=2)), datetime(2026, 1, 1, 12, tzinfo=UTC)
    assert p.classify(now + timedelta(minutes=1), now) == DueClass.NOT_DUE
    assert p.classify(now - timedelta(seconds=30), now) == DueClass.ON_TIME
    assert p.classify(now - timedelta(minutes=30), now) == DueClass.LATE_RECOVERY
    assert p.classify(now - timedelta(hours=3), now) == DueClass.EXPIRED


def test_state_machine():
    assert_transition(S.PENDING, S.CLAIMED)
    for bad in [(S.SENT, S.PENDING), (S.PENDING, S.SENT), (S.CANCELLED, S.CLAIMED)]:
        with pytest.raises(InvalidTransition):
            assert_transition(*bad)
    assert len(S) == 9


def test_idempotency_key_roundtrip():
    k = make_idempotency_key(7, ReminderType.SNOOZE, datetime(2026, 9, 6, 17, tzinfo=UTC), "from3")
    assert reminder_type_from_key(k) == ReminderType.SNOOZE


def test_snooze_options():
    now = datetime(2026, 9, 6, 17, 0, tzinfo=UTC)
    assert resolve_snooze_time(SnoozeOption.MINUTES_30, now) - now == timedelta(minutes=30)
    assert resolve_snooze_time(SnoozeOption.HOUR_1, now) - now == timedelta(hours=1)
    assert resolve_snooze_time(SnoozeOption.HOURS_3, now) - now == timedelta(hours=3)
    tm = resolve_snooze_time(SnoozeOption.TOMORROW_MORNING, now).astimezone(CAIRO)
    assert (tm.date().isoformat(), tm.strftime("%H:%M")) == ("2026-09-07", "08:00")
    c = datetime(2026, 9, 8, 10, 0, tzinfo=CAIRO)
    assert resolve_snooze_time(SnoozeOption.CUSTOM, now, custom=c) == c
