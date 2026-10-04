"""The Nexa eye: closed while idle, open while listening.

One widget, four states, all drawn with QPainter (no image assets, so it scales
cleanly, follows the light/dark theme and costs nothing to ship):

    idle        eye CLOSED     a calm closed lid with lashes, breathing softly
    recording   eye OPEN       iris and pupil visible; the pupil swells with the
                               live audio level, and the iris drifts a little so
                               the eye looks alive rather than like a still image
    paused      eye HALF shut  lid lowered to a slit
    processing  eye OPEN       a ring spins around the iris while the model works

Clicking the eye (or pressing Space/Enter when focused) emits `clicked`; the page
decides what that means. The widget itself owns no recording logic.

The lid is one number, `openness` in 0..1, animated with a property animation. The
eye outline is two cubic curves whose control points move with it, so closing the
eye is a continuous morph rather than a swap between two pictures.
"""

from __future__ import annotations

import math

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

IDLE, RECORDING, PAUSED, PROCESSING = "idle", "recording", "paused", "processing"

#: Target lid opening per state.
_OPENNESS = {IDLE: 0.0, RECORDING: 1.0, PAUSED: 0.28, PROCESSING: 0.85}

_FRAME_MS = 33  # ~30 fps; the timer only runs while the widget is visible


class EyeWidget(QWidget):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = IDLE
        self._openness = 0.0
        self._level = 0.0          # smoothed 0..1 audio level
        self._level_target = 0.0
        self._phase = 0.0          # animation clock, radians
        self._hover = False
        self._ring = 0.0           # processing ring angle, degrees

        self.setMinimumSize(280, 170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Nexa eye")

        self._anim = QPropertyAnimation(self, b"openness", self)
        self._anim.setDuration(380)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------ public
    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        if state not in _OPENNESS:
            raise ValueError(f"unknown eye state: {state!r}")
        self._state = state
        self._anim.stop()
        self._anim.setStartValue(self._openness)
        self._anim.setEndValue(_OPENNESS[state])
        self._anim.start()
        self.setAccessibleDescription({
            IDLE: "Not recording. Click to start.",
            RECORDING: "Recording. Click to stop.",
            PAUSED: "Paused.",
            PROCESSING: "Processing the recording.",
        }[state])
        self.update()

    def set_level(self, level: float) -> None:
        """Feed the live audio level, 0..1. Smoothed, so jitter does not flicker."""
        self._level_target = max(0.0, min(1.0, float(level)))

    # ---------------------------------------------------------- Qt property
    def _get_openness(self) -> float:
        return self._openness

    def _set_openness(self, value: float) -> None:
        self._openness = max(0.0, min(1.0, float(value)))
        self.update()

    openness = Property(float, _get_openness, _set_openness)

    # --------------------------------------------------------------- lifecycle
    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.06) % (2 * math.pi)
        self._level += (self._level_target - self._level) * 0.35
        self._level_target *= 0.92  # decay, so a stalled meter relaxes instead of sticking
        if self._state == PROCESSING:
            self._ring = (self._ring + 7.0) % 360.0
        self.update()

    # ------------------------------------------------------------------- input
    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    # ----------------------------------------------------------------- drawing
    def _colors(self):
        palette = self.palette()
        ink = palette.color(QPalette.WindowText)
        accent = palette.color(QPalette.Highlight)
        # An accent that is too dark reads as a black hole in dark mode.
        if accent.lightness() < 90:
            accent = accent.lighter(170)
        base = palette.color(QPalette.Base)
        return ink, accent, base

    def _eye_path(self, cx: float, cy: float, half_w: float, half_h: float, openness: float) -> QPainterPath:
        """An almond: two cubic curves between the corners; openness lifts the lids."""
        up = half_h * openness
        down = half_h * 0.55 * openness
        path = QPainterPath(QPointF(cx - half_w, cy))
        path.cubicTo(cx - half_w * 0.45, cy - up * 1.55, cx + half_w * 0.45, cy - up * 1.55, cx + half_w, cy)
        path.cubicTo(cx + half_w * 0.45, cy + down * 1.55, cx - half_w * 0.45, cy + down * 1.55, cx - half_w, cy)
        path.closeSubpath()
        return path

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        ink, accent, base = self._colors()

        rect = QRectF(self.rect())
        half_w = min(rect.width() * 0.42, rect.height() * 0.80)
        half_h = half_w * 0.46
        cx, cy = rect.center().x(), rect.center().y()
        o = self._openness

        self._paint_glow(painter, cx, cy, half_w, half_h, accent, o)

        outline = QPen(ink, max(3.0, half_w * 0.035), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        if o < 0.04:
            self._paint_closed(painter, cx, cy, half_w, half_h, ink, accent, outline)
        else:
            path = self._eye_path(cx, cy, half_w, half_h, o)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(base.lighter(112) if base.lightness() > 128 else base.lighter(135)))
            painter.drawPath(path)
            painter.save()
            painter.setClipPath(path)
            self._paint_iris(painter, cx, cy, half_w, half_h, accent, o)
            painter.restore()
            painter.setPen(outline)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            if self._state == PROCESSING:
                self._paint_ring(painter, cx, cy, half_h, accent)
        painter.end()

    def _paint_glow(self, p: QPainter, cx, cy, half_w, half_h, accent: QColor, o: float) -> None:
        """A soft halo: stronger when listening or hovered, a slow breath when idle."""
        strength = 0.10 + 0.22 * o + (0.10 if self._hover else 0.0)
        strength += 0.04 * math.sin(self._phase) * (1.0 - o)
        strength += 0.18 * self._level * o
        # Never wider/taller than the widget, or the halo is sliced off flat.
        rx = min(half_w * 1.25, (self.width() / 2.0) - 2)
        ry = min(half_h * 2.1, (self.height() / 2.0) - 2)
        gradient = QRadialGradient(QPointF(cx, cy), rx)
        halo = QColor(accent)
        halo.setAlphaF(max(0.0, min(0.6, strength)))
        gradient.setColorAt(0.0, halo)
        halo.setAlphaF(0.0)
        gradient.setColorAt(1.0, halo)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(gradient))
        p.drawEllipse(QPointF(cx, cy), rx, ry)

    def _paint_closed(self, p: QPainter, cx, cy, half_w, half_h, ink: QColor, accent: QColor, pen: QPen) -> None:
        """A closed lid: one gentle downward curve with short lashes."""
        sag = half_h * 0.34
        curve = QPainterPath(QPointF(cx - half_w, cy))
        curve.cubicTo(cx - half_w * 0.4, cy + sag * 1.5, cx + half_w * 0.4, cy + sag * 1.5, cx + half_w, cy)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(curve)
        lash = QPen(ink, max(2.0, pen.widthF() * 0.7), Qt.SolidLine, Qt.RoundCap)
        p.setPen(lash)
        for i in range(7):
            t = (i + 0.5) / 7
            point = curve.pointAtPercent(t)
            spread = (t - 0.5) * 2.0
            length = half_h * (0.30 - 0.12 * abs(spread))
            p.drawLine(point, QPointF(point.x() + spread * length * 0.9, point.y() + length))
        # A tiny accent dot under the lid: "asleep, but present".
        dot = QColor(accent)
        dot.setAlphaF(0.55 + 0.25 * math.sin(self._phase))
        p.setPen(Qt.NoPen)
        p.setBrush(dot)
        p.drawEllipse(QPointF(cx, cy + half_h * 0.95), 3.2, 3.2)

    def _paint_iris(self, p: QPainter, cx, cy, half_w, half_h, accent: QColor, o: float) -> None:
        drift_x = math.sin(self._phase * 0.7) * half_w * 0.05 * o
        drift_y = math.cos(self._phase * 0.5) * half_h * 0.05 * o
        centre = QPointF(cx + drift_x, cy + drift_y)
        iris_r = half_h * 0.88
        gradient = QRadialGradient(centre, iris_r)
        gradient.setColorAt(0.0, accent.lighter(135))
        gradient.setColorAt(0.65, accent)
        gradient.setColorAt(1.0, accent.darker(170))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(gradient))
        p.drawEllipse(centre, iris_r, iris_r)
        # The pupil swells with the voice.
        pupil_r = iris_r * (0.36 + 0.20 * self._level)
        p.setBrush(QColor(12, 14, 20))
        p.drawEllipse(centre, pupil_r, pupil_r)
        shine = QColor(255, 255, 255, 215)
        p.setBrush(shine)
        p.drawEllipse(QPointF(centre.x() - iris_r * 0.30, centre.y() - iris_r * 0.34), iris_r * 0.14, iris_r * 0.14)
        p.setBrush(QColor(255, 255, 255, 120))
        p.drawEllipse(QPointF(centre.x() + iris_r * 0.22, centre.y() + iris_r * 0.26), iris_r * 0.07, iris_r * 0.07)

    def _paint_ring(self, p: QPainter, cx, cy, half_h, accent: QColor) -> None:
        radius = half_h * 1.12
        pen = QPen(accent, max(3.0, half_h * 0.12), Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        p.drawArc(rect, int(-self._ring * 16), 100 * 16)
        faint = QColor(accent)
        faint.setAlphaF(0.35)
        pen.setColor(faint)
        p.setPen(pen)
        p.drawArc(rect, int((-self._ring + 180) * 16), 60 * 16)
