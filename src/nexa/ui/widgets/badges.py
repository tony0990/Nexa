from PySide6.QtWidgets import QLabel


class StatusBadge(QLabel):
    def __init__(self, text: str = "", kind: str = "neutral") -> None:
        super().__init__(text)
        self.set_kind(kind, text)

    def set_kind(self, kind: str, text: str | None = None) -> None:
        if text is not None:
            self.setText(text)
        colors = {
            "ok": ("#dcfce7", "#166534"),
            "warn": ("#fef3c7", "#92400e"),
            "bad": ("#fee2e2", "#991b1b"),
            "info": ("#dbeafe", "#1e3a8a"),
            "neutral": ("#e5e7eb", "#374151"),
        }
        bg, fg = colors.get(kind, colors["neutral"])
        self.setStyleSheet(f"background: {bg}; color: {fg}; border-radius: 8px; padding: 2px 8px;")
