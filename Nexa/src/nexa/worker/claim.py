"""Worker-side claiming: safe batch claim + recovery of abandoned claims."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from nexa.contracts.scheduling import Reminder
from nexa.scheduling.queue import SqliteReminderQueue
from nexa.scheduling.retry import RetryPolicy
from nexa.scheduling.states import ReminderStatus as S

ABANDONED_ERROR = "ABANDONED_WHILE_SENDING"
ATTEMPTS_EXHAUSTED = "RETRIES_EXHAUSTED_AFTER_RESTART"


@dataclass
class AbandonedSummary:
    released: list[int] = field(default_factory=list)   # CLAIMED -> PENDING
    retried: list[int] = field(default_factory=list)    # SENDING -> RETRY_WAIT
    failed: list[int] = field(default_factory=list)     # SENDING -> FAILED


class ClaimCoordinator:
    def __init__(self, queue: SqliteReminderQueue, retry_policy: Optional[RetryPolicy] = None,
                 stale_after: timedelta = timedelta(minutes=5)):
        self.queue = queue
        self.retry = retry_policy or RetryPolicy()
        self.stale_after = stale_after

    def claim_batch(self, now: datetime, limit: int) -> list[Reminder]:
        return self.queue.claim_due(now, limit)

    def claim_one(self, reminder_id: int, now: datetime) -> bool:
        return self.queue.claim_one(reminder_id, now)

    def release(self, reminder_ids, now: datetime) -> int:
        return self.queue.release_claims(reminder_ids, now)

    def recover_abandoned(self, now: datetime) -> AbandonedSummary:
        """Claims left behind by a crashed/killed worker.
        CLAIMED never reached the sender -> back to PENDING.
        SENDING may have partly sent -> RETRY_WAIT (per-recipient delivery records
        stop already-sent recipients from receiving a second copy) or FAILED if exhausted."""
        out = AbandonedSummary()
        cutoff = now - self.stale_after
        for r in self.queue.find_stale(S.CLAIMED, cutoff):
            if self.queue.transition(r.id, [S.CLAIMED], S.PENDING, now, claimed_at=None):
                out.released.append(r.id)
        for r in self.queue.find_stale(S.SENDING, cutoff):
            nxt = self.retry.next_attempt(r.attempt_count, now)
            if nxt is None:
                if self.queue.transition(r.id, [S.SENDING], S.FAILED, now, last_error=ATTEMPTS_EXHAUSTED):
                    out.failed.append(r.id)
            elif self.queue.transition(r.id, [S.SENDING], S.RETRY_WAIT, now,
                                       next_attempt_at=now, last_error=ABANDONED_ERROR):
                out.retried.append(r.id)
        return out
