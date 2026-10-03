from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class RenderedEmail:
    subject: str
    html_body: str = ""
    text_body: str = ""
    to: list[str] = field(default_factory=list)
    language: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class SendResult:
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    retryable: bool = True        # Member 4 maps retryable vs permanent errors


class EmailSender(Protocol):
    def send(self, message: RenderedEmail) -> SendResult: ...
