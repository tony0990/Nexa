"""Email error taxonomy and the retryable/permanent split.

This split is the contract Member 5's retry policy runs on, so it matters more
than it looks. Getting it backwards is expensive in both directions:

* A permanent error treated as retryable means Nexa retries a revoked token
  every few minutes forever and the admin is never told to reconnect.
* A transient error treated as permanent means one network blip silently
  cancels a reminder that was supposed to go out.

So the default for an *unrecognized* failure is `retryable`: a reminder that is
tried again is recoverable, a reminder dropped on a guess is not.
"""

from __future__ import annotations

from typing import Optional

from ..core.errors import NexaError

# HTTP statuses worth trying again. 429 is Gmail's rate limit, 5xx is Google's
# side. 408 is a request timeout.
RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})

# Statuses that will not change by trying again: the request or the credential
# is wrong, not the moment.
PERMANENT_STATUSES = frozenset({400, 401, 403, 404, 413, 422})

# Gmail's `reason` strings that mean "slow down", not "you may not".
_RETRYABLE_REASONS = frozenset(
    {
        "ratelimitexceeded",
        "userratelimitexceeded",
        "backenderror",
        "internalerror",
        "quotaexceeded",
        "servingratelimitexceeded",
    }
)

# 403 is ambiguous at Gmail: it is both "you are rate limited" and "this scope
# is not granted". The reason string is what distinguishes them.
_AMBIGUOUS_STATUSES = frozenset({403})


class EmailError(NexaError):
    """Base class for every failure in the email layer.

    `retryable` is what Member 5's worker branches on. `code` is a stable key
    the UI translates, matching the convention in `core.errors`.
    """

    retryable = False
    code = "email_error"

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        reason: Optional[str] = None,
        code: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status = status
        self.reason = reason
        if code:
            self.code = code

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.status:
            return f"{self.message} (HTTP {self.status})"
        return self.message


class TransientEmailError(EmailError):
    """A rate limit, a timeout, or a Google-side 5xx. Try again later."""

    retryable = True
    code = "email_transient"


class PermanentEmailError(EmailError):
    """The send will never succeed as submitted. Do not retry."""

    retryable = False
    code = "email_permanent"


class InvalidRecipientError(PermanentEmailError):
    """The address is malformed, so Gmail is never asked.

    A recipient Gmail rejects at submit time is permanent. Note that a *bounce*
    is not visible here at all: the Gmail API accepts the message and the
    bounce arrives later as a separate mail, so a SENT delivery row means
    "Gmail accepted it", not "it reached the inbox".
    """

    code = "email_invalid_recipient"


class GmailAuthError(PermanentEmailError):
    """Not connected, token revoked, or the granted scope is insufficient.

    Permanent on purpose: it needs an admin to reconnect in Settings, and
    Section 24.6 requires that invalid or revoked credentials produce a clear
    error rather than a silent retry loop.
    """

    code = "email_auth"


class GmailNotConfiguredError(GmailAuthError):
    """No OAuth client secrets are installed, so no flow can start."""

    code = "email_not_configured"


class EmailDependencyError(EmailError):
    """An optional dependency (`google-api-python-client`, `keyring`) is absent.

    Not retryable by the worker — retrying cannot install a package — but kept
    distinct from an auth error so the UI can say "this build is missing a
    component" rather than "reconnect your account".
    """

    retryable = False
    code = "email_dependency"


def classify_status(status: Optional[int], reason: Optional[str] = None) -> bool:
    """True when a failure with this status/reason is worth retrying."""
    normalized = (reason or "").strip().lower().replace(" ", "").replace("_", "")
    if status in _AMBIGUOUS_STATUSES:
        return normalized in _RETRYABLE_REASONS
    if status in PERMANENT_STATUSES:
        return False
    if status in RETRYABLE_STATUSES:
        return True
    if normalized in _RETRYABLE_REASONS:
        return True
    # Unknown or no status (a socket error never reaches an HTTP status):
    # retry, because the recoverable mistake is the cheaper one.
    return True


def from_http_error(exc: Exception) -> EmailError:
    """Map a `googleapiclient.errors.HttpError` to the taxonomy above.

    Duck-typed rather than isinstance-checked so this module imports without
    `googleapiclient` installed, and so a transport that raises a similar
    object still classifies correctly.
    """
    status = _status_of(exc)
    reason = _reason_of(exc)
    message = _message_of(exc) or str(exc)

    if status in (401,) or _looks_like_auth(reason, message):
        return GmailAuthError(message, status=status, reason=reason)
    if status == 403 and not classify_status(status, reason):
        return GmailAuthError(message, status=status, reason=reason)
    if classify_status(status, reason):
        return TransientEmailError(message, status=status, reason=reason)
    return PermanentEmailError(message, status=status, reason=reason)


def _looks_like_auth(reason: Optional[str], message: str) -> bool:
    text = f"{reason or ''} {message}".lower()
    return any(
        marker in text
        for marker in (
            "invalid_grant",
            "invalid credentials",
            "insufficient permission",
            "insufficientpermissions",
            "unauthorized",
            "token has been expired or revoked",
            "authError".lower(),
        )
    )


def _status_of(exc: Exception) -> Optional[int]:
    response = getattr(exc, "resp", None)
    for value in (getattr(response, "status", None), getattr(exc, "status_code", None)):
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None


def _reason_of(exc: Exception) -> Optional[str]:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, str) and reason:
        return reason
    for detail in _error_details(exc):
        value = detail.get("reason")
        if value:
            return str(value)
    return None


def _message_of(exc: Exception) -> Optional[str]:
    for detail in _error_details(exc):
        value = detail.get("message")
        if value:
            return str(value)
    return None


def _error_details(exc: Exception) -> list:
    """Pull `error.errors[]` out of a Google JSON error body, if present."""
    content = getattr(exc, "content", None)
    if not content:
        return []
    import json

    try:
        if isinstance(content, (bytes, bytearray)):
            content = content.decode("utf-8", "replace")
        body = json.loads(content)
    except (ValueError, UnicodeDecodeError):
        return []
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return []
    details = error.get("errors")
    out = [item for item in details or [] if isinstance(item, dict)]
    if not out and ("message" in error or "status" in error):
        out = [{"message": error.get("message"), "reason": error.get("status")}]
    return out
