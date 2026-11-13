"""Main window and custom Qt widgets."""
from __future__ import annotations

import ctypes
import math
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QPointF, QProcess, QRectF, QSettings, QSize, Qt, QTimer,
                            QUrl, QVariantAnimation, Signal)
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFont, QFontDatabase, QFontMetrics, QIcon,
                           QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

import core
from app_info import APP_NAME, VERSION_LABEL

# Fonts and stylesheet
TEXT = "#EAF1FF"

SANS_CANDIDATES = ("SF Pro Text", "Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", "Inter", "Roboto", "Ubuntu", "DejaVu Sans")
DISPLAY_CANDIDATES = ("SF Pro Display", "Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", "Helvetica Neue", "Inter", "Roboto", "Ubuntu", "DejaVu Sans")
MONO_CANDIDATES = ("Cascadia Mono", "Consolas", "SF Mono", "Menlo", "DejaVu Sans Mono", "Monospace")


def pick_family(candidates, fallback: str = "sans-serif") -> str:
    have = set(QFontDatabase.families())
    for name in candidates:
        if name in have:
            return name
    return fallback


STYLE_TEMPLATE = """
* { font-family: "@SANS@"; font-size: 13px; color: #EAF1FF; }
QLabel { background: transparent; }
QLabel#title { font-family: "@DISPLAY@"; font-size: 30px; font-weight: 700; }
QLabel#h2 { font-family: "@DISPLAY@"; font-size: 16px; font-weight: 600; }
QLabel#drop { font-family: "@DISPLAY@"; font-size: 20px; font-weight: 600; }
QLabel#muted { color: #8EA0C4; }
QLabel#count { color: #BFD6FF; background: rgba(47,107,255,0.30); border: 1px solid rgba(156,194,255,0.35);
               border-radius: 9px; padding: 1px 9px; font-size: 12px; font-weight: 600; }
QLabel#beta { color: #DCE9FF; font-size: 11px; font-weight: 700; padding: 3px 11px; border-radius: 11px;
              background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(90,146,255,0.55), stop:1 rgba(31,79,224,0.45));
              border: 1px solid rgba(190,215,255,0.55); }
QLabel#status[state="ok"] { color: #8FE3B0; }
QLabel#status[state="error"] { color: #FF9AA6; }
QLabel#status[state="busy"] { color: #BFD6FF; }
QLineEdit, QComboBox, QSpinBox { background: rgba(255,255,255,0.07); border: 1px solid rgba(160,190,255,0.20);
              border-radius: 12px; padding: 7px 12px; selection-background-color: #2F6BFF; }
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { background: rgba(255,255,255,0.10); }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #6B9BFF; background: rgba(255,255,255,0.11); }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: #5A6A8C; }
QComboBox { padding-right: 30px; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox::down-arrow { image: none; width: 0; height: 0; }
QComboBox QAbstractItemView { background: #0A1224; border: 1px solid rgba(160,190,255,0.28); border-radius: 10px;
              selection-background-color: #2F6BFF; outline: 0; padding: 4px; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }
QPushButton { background: rgba(255,255,255,0.10); border: 1px solid rgba(160,190,255,0.25);
              border-radius: 10px; padding: 7px 16px; }
QPushButton:hover { background: rgba(120,165,255,0.25); }
QPushButton:pressed { background: rgba(47,107,255,0.45); }
QPlainTextEdit { background: rgba(0,0,0,0.40); border: 1px solid rgba(160,190,255,0.16); border-radius: 14px;
              font-family: "@MONO@"; font-size: 12px; color: #B9C8E8; padding: 8px; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: rgba(160,190,255,0.30); border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: rgba(190,215,255,0.50); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { background: #0E1630; color: #EAF1FF; border: 1px solid rgba(160,190,255,0.35); padding: 6px 8px; }
QMessageBox, QDialog { background: #0A1020; }
"""


def build_style(sans: str, display: str, mono: str) -> str:
    return STYLE_TEMPLATE.replace("@SANS@", sans).replace("@DISPLAY@", display).replace("@MONO@", mono)


# Drawing and widget helpers
def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(c1: tuple, c2: tuple, t: float) -> QColor:
    """Blend two RGB or RGBA colors."""
    return QColor(*(int(lerp(a, b, t)) for a, b in zip(c1, c2)))


def no_drops(widget: QWidget) -> None:
    """Let the main window handle file drops."""
    widget.setAcceptDrops(False)
    for child in widget.findChildren(QWidget):
        child.setAcceptDrops(False)


def set_state(widget: QWidget, state: str) -> None:
    widget.setProperty("state", state)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def app_pixmap(size: int) -> QPixmap:
    """Create the application icon at the requested size."""
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(scale)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(1, 1, size - 2, size - 2)
    path = QPainterPath()
    path.addRoundedRect(r, size * 0.27, size * 0.27)
    bg = QLinearGradient(r.topLeft(), r.bottomRight())
    bg.setColorAt(0, QColor(96, 166, 255))
    bg.setColorAt(0.55, QColor(30, 84, 232))
    bg.setColorAt(1, QColor(8, 24, 98))
    p.fillPath(path, bg)
    p.save()
    p.setClipPath(path)
    gloss = QLinearGradient(QPointF(0, r.top()), QPointF(0, r.center().y()))
    gloss.setColorAt(0, QColor(255, 255, 255, 120))
    gloss.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillRect(QRectF(r.left(), r.top(), r.width(), r.height() * 0.55), gloss)
    p.restore()
    tri = QPainterPath()
    tri.moveTo(size * 0.38, size * 0.25)
    tri.lineTo(size * 0.38, size * 0.55)
    tri.lineTo(size * 0.66, size * 0.40)
    tri.closeSubpath()
    p.fillPath(tri, QColor(255, 255, 255, 240))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 215))
    p.drawRoundedRect(QRectF(size * 0.26, size * 0.64, size * 0.48, size * 0.07), size * 0.035, size * 0.035)
    p.setBrush(QColor(255, 255, 255, 140))
    p.drawRoundedRect(QRectF(size * 0.26, size * 0.76, size * 0.32, size * 0.07), size * 0.035, size * 0.035)
    rim = QLinearGradient(r.topLeft(), r.bottomRight())
    rim.setColorAt(0, QColor(220, 235, 255, 200))
    rim.setColorAt(1, QColor(120, 165, 255, 60))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QBrush(rim), 1.2))
    p.drawPath(path)
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(app_pixmap(size))
    return icon


def apply_windows_backdrop(hwnd: int) -> bool:
    """Apply the Windows backdrop and title-bar settings."""
    if sys.platform != "win32" or os.environ.get("MKVSTUDIO_NO_BLUR"):
        return False
    try:
        dwm = ctypes.windll.dwmapi
        handle = ctypes.c_void_p(hwnd)

        def set_attr(attr: int, value: int) -> int:
            val = ctypes.c_int(value)
            return dwm.DwmSetWindowAttribute(handle, attr, ctypes.byref(val), 4)

        if set_attr(20, 1) != 0:  # dark title bar (Windows 10 20H1+ and 11)
            set_attr(19, 1)       # older Windows 10 builds
        if set_attr(38, 3) != 0:  # acrylic backdrop, Windows 11 22H2+
            return False

        class Margins(ctypes.Structure):
            _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]

        dwm.DwmExtendFrameIntoClientArea(handle, ctypes.byref(Margins(-1, -1, -1, -1)))
        return True
    except Exception:
        return False


# Window background
class Backdrop(QWidget):
    """Paint the animated background."""

    # Center, radius, color, movement and phase for each light.
    ORBS = (
        (0.08, 0.04, 0.80, (47, 107, 255, 130), 0.05, 0.04, 0.16, 0.0),
        (0.98, 0.96, 0.78, (20, 66, 225, 115), 0.04, 0.05, 0.12, 2.1),
        (0.72, 0.26, 0.36, (88, 160, 255, 46), 0.08, 0.06, 0.22, 4.0),
        (0.22, 0.80, 0.42, (34, 96, 255, 44), 0.06, 0.05, 0.18, 1.2),
    )

    def __init__(self):
        super().__init__()
        self.base_alpha = 255
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(45)  # Update the background about 22 times per second.
        self._timer.timeout.connect(self._tick)
        if not os.environ.get("MKVSTUDIO_STATIC"):
            self._timer.start()

    def _tick(self):
        if self.isVisible() and not self.window().isMinimized():
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        t = time.monotonic() - self._t0
        p.fillRect(self.rect(), QColor(3, 5, 11, self.base_alpha))
        for cx, cy, radius, (r, g, b, a), ax, ay, speed, phase in self.ORBS:
            x = w * (cx + ax * math.sin(t * speed + phase))
            y = h * (cy + ay * math.cos(t * speed * 1.3 + phase))
            grad = QRadialGradient(QPointF(x, y), max(w, h) * radius)
            grad.setColorAt(0, QColor(r, g, b, a))
            grad.setColorAt(0.55, QColor(r, g, b, int(a * 0.35)))
            grad.setColorAt(1, QColor(r, g, b, 0))
            p.fillRect(self.rect(), grad)
        vignette = QLinearGradient(0, 0, 0, h)
        vignette.setColorAt(0, QColor(0, 0, 0, 0))
        vignette.setColorAt(1, QColor(0, 0, 0, 70))
        p.fillRect(self.rect(), vignette)


# Custom controls
class GlassCard(QFrame):
    """A panel with a translucent fill and a soft highlight."""

    def __init__(self, radius: int = 26, strength: float = 1.0):
        super().__init__()
        self.radius = radius
        self.strength = strength
        self.glow = 0.0  # 0..1, blue emphasis (used by the drop zone)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)
        s = self.strength

        fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
        fill.setColorAt(0, QColor(255, 255, 255, int(30 * s)))
        fill.setColorAt(1, QColor(110, 160, 255, int(12 * s)))
        p.fillPath(path, fill)

        p.save()
        p.setClipPath(path)
        # Top-left highlight
        spot = QRadialGradient(QPointF(rect.left() + rect.width() * 0.18, rect.top() - rect.height() * 0.10),
                               max(rect.width(), rect.height()) * 0.75)
        spot.setColorAt(0, QColor(190, 215, 255, int(46 * s)))
        spot.setColorAt(1, QColor(190, 215, 255, 0))
        p.fillRect(rect, spot)
        # Bottom edge glow
        bottom = QLinearGradient(QPointF(0, rect.bottom() - 46), QPointF(0, rect.bottom()))
        bottom.setColorAt(0, QColor(90, 150, 255, 0))
        bottom.setColorAt(1, QColor(90, 150, 255, int(26 * s)))
        p.fillRect(rect, bottom)
        if self.glow > 0:
            p.fillPath(path, QColor(47, 107, 255, int(46 * self.glow)))
        p.restore()

        rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
        rim.setColorAt(0, QColor(215, 232, 255, int(125 * s)))
        rim.setColorAt(0.45, QColor(120, 165, 255, int(26 * s)))
        rim.setColorAt(1, QColor(130, 175, 255, int(70 * s)))
        p.setPen(QPen(QBrush(rim), 1.2))
        p.drawPath(path)

        shine = QLinearGradient(rect.left() + self.radius, 0, rect.right() - self.radius, 0)
        shine.setColorAt(0, QColor(255, 255, 255, 0))
        shine.setColorAt(0.5, QColor(255, 255, 255, int(95 * s)))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(QPen(QBrush(shine), 1))
        p.drawLine(QPointF(rect.left() + self.radius, rect.top() + 1.2),
                   QPointF(rect.right() - self.radius, rect.top() + 1.2))


class GlassButton(QPushButton):
    """A rounded button with several visual styles."""

    def __init__(self, text: str = "", variant: str = "secondary"):
        super().__init__(text)
        self.variant = variant
        self._hover = 0.0
        self._dot: QColor | None = None
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        if variant == "icon":
            self.setFixedSize(30, 30)

    def setDot(self, color: QColor | None):
        self._dot = color
        self.updateGeometry()
        self.update()

    def _set_hover(self, value):
        self._hover = float(value)
        self.update()

    def _go(self, target: float):
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event):
        self._go(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._go(0.0)
        super().leaveEvent(event)

    def _font(self) -> QFont:
        f = QFont(self.font())
        if self.variant == "primary":
            f.setPixelSize(16)
            f.setWeight(QFont.Weight.DemiBold)
        elif self.variant == "chip":
            f.setPixelSize(12)
            f.setWeight(QFont.Weight.Medium)
        elif self.variant == "secondary":
            f.setWeight(QFont.Weight.Medium)
        return f

    def sizeHint(self) -> QSize:
        if self.variant == "icon":
            return QSize(30, 30)
        text_w = QFontMetrics(self._font()).horizontalAdvance(self.text())
        pad, height = {"primary": (30, 54), "secondary": (20, 38), "chip": (14, 30), "ghost": (6, 28)}.get(self.variant, (16, 36))
        if self._dot is not None:
            text_w += 16
        return QSize(text_w + pad * 2, height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        enabled = self.isEnabled()
        down = self.isDown()
        h = self._hover
        v = self.variant
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        text_color = QColor(TEXT)

        if v == "primary":
            if enabled:
                top = mix((98, 166, 255), (130, 188, 255), h)
                bottom = mix((28, 88, 240), (44, 108, 255), h)
                if down:
                    top, bottom = top.darker(120), bottom.darker(125)
                grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
                grad.setColorAt(0, top)
                grad.setColorAt(1, bottom)
                p.fillPath(path, grad)
                p.save()
                p.setClipPath(path)
                gloss = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.center().y()))
                gloss.setColorAt(0, QColor(255, 255, 255, 105))
                gloss.setColorAt(1, QColor(255, 255, 255, 8))
                p.fillRect(QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.52), gloss)
                p.restore()
                rim = QLinearGradient(rect.topLeft(), rect.bottomLeft())
                rim.setColorAt(0, QColor(235, 245, 255, 200))
                rim.setColorAt(1, QColor(150, 195, 255, 90))
                p.setPen(QPen(QBrush(rim), 1.2))
                p.drawPath(path)
                text_color = QColor(255, 255, 255)
            else:
                p.fillPath(path, QColor(255, 255, 255, 14))
                p.setPen(QPen(QColor(160, 190, 255, 38), 1))
                p.drawPath(path)
                text_color = QColor(110, 128, 165)
        elif v in ("secondary", "chip", "icon"):
            alpha = 20 + int(22 * h) + (16 if down else 0)
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0, QColor(255, 255, 255, alpha + 10))
            grad.setColorAt(1, QColor(150, 190, 255, max(0, alpha - 6)))
            p.fillPath(path, grad)
            rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
            rim.setColorAt(0, QColor(215, 232, 255, 120 + int(60 * h)))
            rim.setColorAt(1, QColor(130, 175, 255, 50))
            p.setPen(QPen(QBrush(rim), 1))
            p.drawPath(path)
            if not enabled:
                text_color = QColor(110, 128, 165)
            elif v == "chip":
                text_color = QColor(207, 224, 255)
        else:  # ghost
            text_color = mix((156, 194, 255), (255, 255, 255), h)
            if not enabled:
                text_color = QColor(110, 128, 165)

        if self.hasFocus():
            p.setPen(QPen(QColor(130, 180, 255, 200), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        if v == "icon":
            c = rect.center()
            d = 5.0
            p.setPen(QPen(mix((150, 170, 205), (255, 255, 255), h), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(c.x() - d, c.y() - d), QPointF(c.x() + d, c.y() + d))
            p.drawLine(QPointF(c.x() - d, c.y() + d), QPointF(c.x() + d, c.y() - d))
            return

        font = self._font()
        p.setFont(font)
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(self.text())
        dot_w = 16 if self._dot is not None else 0
        x = rect.center().x() - (text_w + dot_w) / 2
        y = rect.center().y() + (fm.ascent() - fm.descent()) / 2
        if self._dot is not None:
            d = self._dot
            glow = QRadialGradient(QPointF(x + 4, rect.center().y()), 9)
            glow.setColorAt(0, QColor(d.red(), d.green(), d.blue(), 120))
            glow.setColorAt(1, QColor(d.red(), d.green(), d.blue(), 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QPointF(x + 4, rect.center().y()), 9.0, 9.0)
            p.setBrush(d)
            p.drawEllipse(QPointF(x + 4, rect.center().y()), 3.5, 3.5)
            x += dot_w
        p.setPen(text_color)
        p.drawText(QPointF(x, y), self.text())


class ToggleSwitch(QAbstractButton):
    """A custom animated switch."""

    def __init__(self, compact: bool = False):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedSize(*((42, 26) if compact else (52, 32)))
        self._pos = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(190)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_pos)
        self.toggled.connect(self._on_toggled)

    def _set_pos(self, value):
        self._pos = float(value)
        self.update()

    def _on_toggled(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        track = QRectF(1, 1, w - 2, h - 2)
        radius = track.height() / 2
        path = QPainterPath()
        path.addRoundedRect(track, radius, radius)
        t = self._pos

        grad = QLinearGradient(track.topLeft(), track.bottomLeft())
        grad.setColorAt(0, mix((255, 255, 255, 40), (112, 176, 255, 255), t))
        grad.setColorAt(1, mix((170, 195, 255, 26), (36, 96, 245, 255), t))
        p.fillPath(path, grad)
        p.setPen(QPen(mix((170, 195, 255, 70), (200, 225, 255, 160), t), 1))
        p.drawPath(path)

        d = h - 6.0
        x = 3 + t * (w - 6 - d)
        knob = QRectF(x, 3, d, d)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 55))
        p.drawEllipse(knob.translated(0, 1.4))
        kg = QLinearGradient(knob.topLeft(), knob.bottomLeft())
        kg.setColorAt(0, QColor(255, 255, 255))
        kg.setColorAt(1, QColor(212, 226, 255))
        p.setBrush(kg)
        p.drawEllipse(knob)
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(130, 180, 255, 200), 1.5))
            p.drawPath(path)


class SwitchRow(QWidget):
    """A clickable row containing a label and switch."""

    toggled = Signal(bool)

    def __init__(self, text: str, checked: bool = False, compact: bool = False):
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.label = QLabel(text)
        self.switch = ToggleSwitch(compact)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.switch)
        self.switch.toggled.connect(self.toggled)
        self.switch.setChecked(checked)

    def isChecked(self) -> bool:
        return self.switch.isChecked()

    def setChecked(self, on: bool) -> None:
        self.switch.setChecked(on)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.switch.toggle()
        super().mouseReleaseEvent(event)


class GlassProgress(QWidget):
    """A progress bar with an animated busy state."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(14)
        self._target = 0.0
        self._shown = 0.0
        self._busy = False
        self._busy_pos = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_shown)
        self._slide = QVariantAnimation(self)
        self._slide.setStartValue(0.0)
        self._slide.setEndValue(1.0)
        self._slide.setDuration(1300)
        self._slide.setLoopCount(-1)
        self._slide.valueChanged.connect(self._set_slide)

    def _set_shown(self, value):
        self._shown = float(value)
        self.update()

    def _set_slide(self, value):
        self._busy_pos = float(value)
        self.update()

    def value(self) -> float:
        return self._target

    def setValue(self, fraction: float, animate: bool = True):
        fraction = max(0.0, min(1.0, float(fraction)))
        self._target = fraction
        self._anim.stop()
        if not animate:
            self._shown = fraction
            self.update()
            return
        self._anim.setStartValue(self._shown)
        self._anim.setEndValue(fraction)
        self._anim.start()

    def setBusy(self, on: bool):
        if on == self._busy:
            return
        self._busy = on
        if on:
            self._slide.start()
        else:
            self._slide.stop()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2
        track = QPainterPath()
        track.addRoundedRect(rect, radius, radius)
        p.fillPath(track, QColor(255, 255, 255, 22))
        p.setPen(QPen(QColor(170, 195, 255, 55), 1))
        p.drawPath(track)

        p.save()
        p.setClipPath(track)
        fill = None
        if self._busy:
            seg = rect.width() * 0.32
            x = rect.left() - seg + self._busy_pos * (rect.width() + seg)
            fill = QRectF(x, rect.top(), seg, rect.height())
        elif self._shown > 0:
            fill = QRectF(rect.left(), rect.top(), max(rect.height(), rect.width() * self._shown), rect.height())
        if fill is not None:
            grad = QLinearGradient(fill.topLeft(), fill.topRight())
            grad.setColorAt(0, QColor(47, 107, 255))
            grad.setColorAt(1, QColor(143, 192, 255))
            p.fillRect(fill, grad)
            gloss = QLinearGradient(fill.topLeft(), fill.bottomLeft())
            gloss.setColorAt(0, QColor(255, 255, 255, 120))
            gloss.setColorAt(0.5, QColor(255, 255, 255, 20))
            gloss.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillRect(fill, gloss)
        p.restore()


class GlassCombo(QComboBox):
    """A combo box with a custom arrow."""

    def __init__(self):
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() - 18, self.height() / 2)
        alpha = 230 if self.isEnabled() else 90
        p.setPen(QPen(QColor(156, 194, 255, alpha), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawLine(QPointF(c.x() - 4, c.y() - 2), QPointF(c.x(), c.y() + 2))
        p.drawLine(QPointF(c.x(), c.y() + 2), QPointF(c.x() + 4, c.y() - 2))


class ElidedLabel(QLabel):
    """A label that elides text when it does not fit."""

    def __init__(self, text: str = "", mode=Qt.TextElideMode.ElideMiddle):
        super().__init__()
        self._full = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(40)
        self._elide()

    def setFullText(self, text: str):
        self._full = text
        self.setToolTip(text)
        self._elide()

    def fullText(self) -> str:
        return self._full

    def _elide(self):
        if self.width() < 20:
            QLabel.setText(self, self._full)
        else:
            QLabel.setText(self, self.fontMetrics().elidedText(self._full, self._mode, self.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def showEvent(self, event):
        super().showEvent(event)
        self._elide()


class GlyphBadge(QWidget):
    """A small icon for a video, audio or subtitle track."""

    COLORS = {
        "video": ((104, 170, 255), (24, 76, 232)),
        "audio": ((92, 156, 255), (28, 70, 222)),
        "subtitle": ((88, 196, 255), (22, 100, 222)),
    }

    def __init__(self, kind: str, size: int = 40):
        super().__init__()
        self.kind = kind
        self.setFixedSize(size, size)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = float(self.width())
        r = QRectF(1, 1, s - 2, s - 2)
        top, bottom = self.COLORS.get(self.kind, self.COLORS["video"])
        grad = QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0, QColor(*top))
        grad.setColorAt(1, QColor(*bottom))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(r)
        gloss = QLinearGradient(r.topLeft(), QPointF(r.left(), r.center().y()))
        gloss.setColorAt(0, QColor(255, 255, 255, 110))
        gloss.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(gloss)
        p.drawEllipse(QRectF(r.left() + s * 0.06, r.top() + s * 0.03, r.width() - s * 0.12, r.height() * 0.5))
        rim = QLinearGradient(r.topLeft(), r.bottomRight())
        rim.setColorAt(0, QColor(230, 242, 255, 200))
        rim.setColorAt(1, QColor(130, 175, 255, 70))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QBrush(rim), 1.1))
        p.drawEllipse(r)

        white = QColor(255, 255, 255, 240)
        pen = QPen(white, max(1.5, s * 0.04), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

        def pt(x: float, y: float) -> QPointF:
            return QPointF(s * x, s * y)

        if self.kind == "video":
            p.setPen(pen)
            p.drawRoundedRect(QRectF(s * 0.27, s * 0.30, s * 0.46, s * 0.40), s * 0.08, s * 0.08)
            tri = QPainterPath()
            tri.moveTo(pt(0.44, 0.39))
            tri.lineTo(pt(0.44, 0.61))
            tri.lineTo(pt(0.62, 0.50))
            tri.closeSubpath()
            p.fillPath(tri, white)
        elif self.kind == "audio":
            spk = QPainterPath()
            spk.moveTo(pt(0.28, 0.43))
            spk.lineTo(pt(0.38, 0.43))
            spk.lineTo(pt(0.50, 0.32))
            spk.lineTo(pt(0.50, 0.68))
            spk.lineTo(pt(0.38, 0.57))
            spk.lineTo(pt(0.28, 0.57))
            spk.closeSubpath()
            p.fillPath(spk, white)
            p.setPen(pen)
            for radius in (0.11, 0.20):
                p.drawArc(QRectF(s * (0.50 - radius), s * (0.50 - radius), s * radius * 2, s * radius * 2),
                          -48 * 16, 96 * 16)
        else:  # subtitle
            p.setPen(pen)
            p.drawRoundedRect(QRectF(s * 0.26, s * 0.32, s * 0.48, s * 0.36), s * 0.08, s * 0.08)
            p.drawLine(pt(0.34, 0.45), pt(0.47, 0.45))
            p.drawLine(pt(0.53, 0.45), pt(0.66, 0.45))
            p.drawLine(pt(0.34, 0.56), pt(0.43, 0.56))
            p.drawLine(pt(0.49, 0.56), pt(0.66, 0.56))


# Main screen widgets
def muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


def card_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("h2")
    return label


class DropZone(GlassCard):
    """The video drop area."""

    def __init__(self):
        super().__init__(radius=28, strength=1.15)
        self.has_video = False
        self._highlight = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(18)
        self.badge = GlyphBadge("video", 64)
        lay.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(card_title("Video"))
        self.title = ElidedLabel("Drop a video here")
        self.title.setObjectName("drop")
        col.addWidget(self.title)
        self.info = muted("MP4, MKV, MOV, AVI, WebM and more")
        col.addWidget(self.info)
        lay.addLayout(col, 1)
        self.button = GlassButton("Choose video", "secondary")
        lay.addWidget(self.button, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_highlight(self, on: bool):
        self._highlight = on
        self.glow = 1.0 if on else 0.0
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._highlight:
            p.setPen(QPen(QColor(130, 185, 255, 235), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), self.radius - 1, self.radius - 1)
        elif not self.has_video:
            pen = QPen(QColor(160, 195, 255, 80), 1.2)
            pen.setStyle(Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([4.0, 5.0])
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(9, 9, -9, -9), self.radius - 9, self.radius - 9)


class TrackRow(GlassCard):
    removed = Signal(object)
    defaultToggled = Signal(object, bool)

    def __init__(self, kind: str, path: str):
        super().__init__(radius=20, strength=0.8)
        self.kind, self.path = kind, path
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(GlyphBadge(kind, 38))
        names = QVBoxLayout()
        names.setSpacing(0)
        self.name = ElidedLabel(Path(path).name)
        self.name.setToolTip(path)
        self.sub = ElidedLabel(("Audio" if kind == "audio" else "Subtitles") + "  ·  " + str(Path(path).parent),
                               Qt.TextElideMode.ElideLeft)
        self.sub.setObjectName("muted")
        names.addWidget(self.name)
        names.addWidget(self.sub)
        top.addLayout(names, 1)
        remove = GlassButton("", "icon")
        remove.setToolTip("Remove this track")
        remove.clicked.connect(lambda: self.removed.emit(self))
        top.addWidget(remove, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(top)

        fields = QHBoxLayout()
        fields.setSpacing(8)
        self.language = GlassCombo()
        for lang_name, code, _ in core.LANGUAGES:
            self.language.addItem(f"{lang_name} ({code})", code)
        guess = core.guess_language(path)
        self.language.setCurrentIndex(max(0, self.language.findData(guess)))
        self.language.setFixedWidth(200)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Track name (optional)")
        fields.addWidget(self.language)
        fields.addWidget(self.title, 1)
        outer.addLayout(fields)

        options = QHBoxLayout()
        options.setSpacing(12)
        self.delay = QSpinBox()
        self.delay.setRange(-600000, 600000)
        self.delay.setSingleStep(50)
        self.delay.setPrefix("Delay ")
        self.delay.setSuffix(" ms")
        self.delay.setFixedWidth(170)
        self.delay.setVisible(kind == "audio")
        options.addWidget(self.delay)
        options.addStretch(1)
        self.default = SwitchRow("Play by default", compact=True)
        self.default.toggled.connect(lambda on: self.defaultToggled.emit(self, on))
        options.addWidget(self.default)
        outer.addLayout(options)
        no_drops(self)

    def to_track(self) -> core.ExtraTrack:
        return core.ExtraTrack(self.kind, self.path, self.language.currentData(), self.title.text().strip(),
                               self.delay.value() if self.kind == "audio" else 0, self.default.isChecked())


# Main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION_LABEL}")
        self.setWindowIcon(app_icon())
        self.resize(1140, 780)
        self.setMinimumSize(960, 680)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.settings = QSettings("MKVStudio", "MKVStudio")
        self.video: core.ProbeResult | None = None
        self.rows: list[TrackRow] = []
        self.proc: QProcess | None = None
        self.cancelled = False
        self.auto_output = ""
        self.target = ""
        self.stdout_buffer = ""
        self.started_at = 0.0
        self._blur_applied = False
        self.backdrop = Backdrop()
        self.setCentralWidget(self.backdrop)
        self._build()
        self.resolve_tools()

    # Layout
    def _build(self):
        root = QVBoxLayout(self.backdrop)
        root.setContentsMargins(34, 26, 34, 24)
        root.setSpacing(20)

        # Header
        head = QHBoxLayout()
        head.setSpacing(16)
        logo = QLabel()
        logo.setPixmap(app_pixmap(58))
        logo.setFixedSize(58, 58)
        head.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        beta = QLabel(f"v{VERSION_LABEL}")
        beta.setObjectName("beta")
        title_row.addWidget(title)
        title_row.addWidget(beta, 0, Qt.AlignmentFlag.AlignBottom)
        title_row.addStretch(1)
        titles.addLayout(title_row)
        titles.addWidget(muted("Add dubbed audio and subtitles to a video. Nothing is re-encoded, so it's fast and lossless."))
        head.addLayout(titles, 1)
        self.tools_chip = GlassButton("FFmpeg", "chip")
        self.tools_chip.setToolTip("Click to choose the folder that contains ffmpeg and ffprobe")
        self.tools_chip.clicked.connect(self.choose_tools)
        head.addWidget(self.tools_chip, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)

        columns = QHBoxLayout()
        columns.setSpacing(20)
        root.addLayout(columns, 1)
        left = QVBoxLayout()
        left.setSpacing(20)
        columns.addLayout(left, 3)
        right = QVBoxLayout()
        right.setSpacing(20)
        columns.addLayout(right, 2)

        # Video
        self.drop_zone = DropZone()
        self.drop_zone.button.clicked.connect(self.choose_video)
        left.addWidget(self.drop_zone)

        # Tracks
        self.tracks_card = GlassCard()
        tl = QVBoxLayout(self.tracks_card)
        tl.setContentsMargins(24, 20, 24, 20)
        tl.setSpacing(12)
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(card_title("Added tracks"))
        self.count_label = QLabel("0")
        self.count_label.setObjectName("count")
        header.addWidget(self.count_label)
        header.addStretch(1)
        add_audio = GlassButton("Add audio", "secondary")
        add_audio.clicked.connect(lambda: self.choose_track("audio"))
        add_subs = GlassButton("Add subtitles", "secondary")
        add_subs.clicked.connect(lambda: self.choose_track("subtitle"))
        header.addWidget(add_audio)
        header.addWidget(add_subs)
        tl.addLayout(header)
        self.empty_label = muted("Drop audio or subtitle files anywhere in this window, or use the buttons above.")
        tl.addWidget(self.empty_label)
        self.rows_host = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setContentsMargins(0, 0, 6, 0)
        self.rows_layout.setSpacing(12)
        self.rows_layout.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.setWidget(self.rows_host)
        tl.addWidget(self.scroll, 1)
        left.addWidget(self.tracks_card, 1)

        # Output
        self.out_card = GlassCard()
        ol = QVBoxLayout(self.out_card)
        ol.setContentsMargins(24, 20, 24, 22)
        ol.setSpacing(8)
        ol.addWidget(card_title("Output"))
        ol.addSpacing(2)
        ol.addWidget(muted("Save as"))
        pick = QHBoxLayout()
        pick.setSpacing(8)
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Choose a video first")
        browse = GlassButton("Browse", "secondary")
        browse.clicked.connect(self.browse_output)
        pick.addWidget(self.out_edit, 1)
        pick.addWidget(browse)
        ol.addLayout(pick)
        ol.addSpacing(2)
        ol.addWidget(muted("Movie title (optional)"))
        self.title_edit = QLineEdit()
        ol.addWidget(self.title_edit)
        ol.addSpacing(8)
        self.keep_audio = SwitchRow("Keep the original audio", True)
        self.keep_subs = SwitchRow("Keep the original subtitles", True)
        ol.addWidget(self.keep_audio)
        ol.addSpacing(4)
        ol.addWidget(self.keep_subs)
        right.addWidget(self.out_card)

        # Actions
        run_card = GlassCard()
        rl = QVBoxLayout(run_card)
        rl.setContentsMargins(24, 22, 24, 18)
        rl.setSpacing(14)
        self.start_btn = GlassButton("Make MKV", "primary")
        self.start_btn.clicked.connect(self.toggle_run)
        self.start_btn.setEnabled(False)
        rl.addWidget(self.start_btn)
        self.progress = GlassProgress()
        rl.addWidget(self.progress)
        self.status = muted("Choose a video to begin.")
        self.status.setObjectName("status")
        rl.addWidget(self.status)
        self.reveal_btn = GlassButton("Show in folder", "ghost")
        self.reveal_btn.setVisible(False)
        self.reveal_btn.clicked.connect(self.reveal)
        rl.addWidget(self.reveal_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setVisible(False)
        self.log.setMinimumHeight(110)
        rl.addWidget(self.log, 1)
        rl.addStretch(1)
        foot = QHBoxLayout()
        details = GlassButton("Details", "ghost")
        details.clicked.connect(lambda: self.log.setVisible(not self.log.isVisible()))
        foot.addWidget(details)
        foot.addStretch(1)
        version = muted(f"{APP_NAME}  ·  {VERSION_LABEL}")
        version.setWordWrap(False)
        foot.addWidget(version)
        rl.addLayout(foot)
        right.addWidget(run_card, 1)

        for w in (self.drop_zone, self.tracks_card, self.out_card, run_card):
            no_drops(w)
        self.locked_cards = (self.drop_zone, self.tracks_card, self.out_card)
        self.refresh_tracks_header()

    # Window effects
    def showEvent(self, event):
        super().showEvent(event)
        if not self._blur_applied:
            self._blur_applied = True
            if apply_windows_backdrop(int(self.winId())):
                self.backdrop.base_alpha = 170
                self.backdrop.update()

    # UI helpers
    def set_status(self, text: str, state: str = "idle"):
        self.status.setText(text)
        set_state(self.status, state)

    def refresh_tracks_header(self):
        self.count_label.setText(str(len(self.rows)))
        self.empty_label.setVisible(not self.rows)

    def lock_ui(self, locked: bool):
        for card in self.locked_cards:
            card.setEnabled(not locked)

    # FFmpeg tools
    def resolve_tools(self):
        folder = str(self.settings.value("ffmpeg_dir", ""))
        self.ffmpeg = core.find_tool("ffmpeg", folder)
        self.ffprobe = core.find_tool("ffprobe", folder)
        ready = bool(self.ffmpeg and self.ffprobe)
        self.tools_chip.setText("FFmpeg ready" if ready else "FFmpeg not found")
        self.tools_chip.setDot(QColor(96, 220, 150) if ready else QColor(255, 176, 80))

    def choose_tools(self):
        folder = QFileDialog.getExistingDirectory(self, "Folder that contains ffmpeg and ffprobe")
        if folder:
            self.settings.setValue("ffmpeg_dir", folder)
            self.resolve_tools()

    def tools_ok(self) -> bool:
        if self.ffmpeg and self.ffprobe:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("FFmpeg needed")
        box.setText("MKV Studio uses FFmpeg to build the file.")
        box.setInformativeText("Install FFmpeg (ffmpeg and ffprobe), or pick the folder that contains ffmpeg.exe and ffprobe.exe.")
        choose = box.addButton("Choose folder", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is choose:
            self.choose_tools()
        return bool(self.ffmpeg and self.ffprobe)

    # File input
    def start_dir(self) -> str:
        return str(self.settings.value("last_dir", ""))

    def remember_dir(self, path: str):
        self.settings.setValue("last_dir", str(Path(path).parent))

    def choose_video(self):
        exts = " ".join(f"*{e}" for e in sorted(core.VIDEO_EXT))
        path, _ = QFileDialog.getOpenFileName(self, "Choose a video", self.start_dir(), f"Video ({exts});;All files (*)")
        if path:
            self.set_video(path)

    def choose_track(self, kind: str):
        exts = core.AUDIO_EXT if kind == "audio" else core.SUB_EXT
        label = "Audio" if kind == "audio" else "Subtitles"
        pattern = " ".join(f"*{e}" for e in sorted(exts))
        paths, _ = QFileDialog.getOpenFileNames(self, f"Add {label.lower()}", self.start_dir(), f"{label} ({pattern});;All files (*)")
        for p in paths:
            self.add_track(kind, p)

    def dragEnterEvent(self, event):
        if self.proc is None and any(core.kind_of(u.toLocalFile()) for u in event.mimeData().urls()):
            self.drop_zone.set_highlight(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drop_zone.set_highlight(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.drop_zone.set_highlight(False)
        if self.proc is not None:
            return
        skipped = 0
        video_taken = False
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            kind = core.kind_of(path)
            if kind == "video" and not video_taken:
                video_taken = True
                self.set_video(path)
            elif kind in ("audio", "subtitle"):
                self.add_track(kind, path)
            else:
                skipped += 1
        if skipped:
            self.set_status(f"Skipped {skipped} file(s) that aren't a video, audio or subtitle file.", "error")

    def set_video(self, path: str):
        if self.proc is not None or not self.tools_ok():
            return
        try:
            info = core.probe(self.ffprobe, path)
        except core.ProbeError as exc:
            QMessageBox.warning(self, "Can't read this video", str(exc))
            return
        self.remember_dir(path)
        self.video = info
        self.drop_zone.has_video = True
        self.drop_zone.title.setFullText(Path(path).name)
        lines = []
        first = next(iter(info.of_kind("video")), None)
        if first:
            lines.append(f"{first.codec}, {first.width}x{first.height}, {core.format_duration(info.duration)}")
        for s in info.of_kind("audio"):
            lines.append(f"Audio: {s.codec}, {s.language}" + (f", {s.title}" if s.title else ""))
        for s in info.of_kind("subtitle"):
            lines.append(f"Subtitles: {s.codec}, {s.language}" + (f", {s.title}" if s.title else ""))
        extra = len(lines) - 6
        shown = lines[:6] + ([f"+ {extra} more"] if extra > 0 else [])
        self.drop_zone.info.setText("\n".join(shown))
        self.drop_zone.button.setText("Change video")
        self.drop_zone.button.updateGeometry()
        self.drop_zone.update()
        current = self.out_edit.text().strip()
        if not current or current == self.auto_output:  # don't overwrite a path the user typed
            self.auto_output = core.default_output_path(path)
            self.out_edit.setText(self.auto_output)
        self.set_status("Ready when you are.")
        self.reveal_btn.setVisible(False)
        self.progress.setValue(0, animate=False)
        self.update_start()

    def add_track(self, kind: str, path: str):
        if self.proc is not None:
            return
        self.remember_dir(path)
        row = TrackRow(kind, path)
        row.removed.connect(self.remove_row)
        row.defaultToggled.connect(self.row_default)
        self.rows.append(row)
        self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
        self.refresh_tracks_header()

    def remove_row(self, row: TrackRow):
        if row in self.rows:
            self.rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self.refresh_tracks_header()

    def row_default(self, row: TrackRow, on: bool):
        if on:
            for other in self.rows:
                if other is not row and other.kind == row.kind:
                    other.default.setChecked(False)

    def browse_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save MKV as", self.out_edit.text(), "Matroska (*.mkv)")
        if path:
            self.out_edit.setText(path if path.lower().endswith(".mkv") else path + ".mkv")

    def update_start(self):
        self.start_btn.setEnabled(self.video is not None or self.proc is not None)

    # Remux job
    def toggle_run(self):
        if self.proc is not None:
            self.cancelled = True
            self.proc.kill()
            return
        if not self.video or not self.tools_ok():
            return
        job = core.Job(self.video, [r.to_track() for r in self.rows], self.out_edit.text().strip(),
                       self.keep_audio.isChecked(), self.keep_subs.isChecked(), self.title_edit.text().strip())
        errors = core.validate_job(job)
        if errors:
            QMessageBox.warning(self, "Check your settings", "\n".join(errors))
            return
        if Path(job.output).exists():
            ask = QMessageBox.question(self, "Replace file?", f"{Path(job.output).name} already exists. Replace it?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ask != QMessageBox.StandardButton.Yes:
                return
        self.target = job.output
        cmd = core.build_command(self.ffmpeg, replace(job, output=job.output + ".part"))
        self.log.clear()
        self.log.appendPlainText(" ".join(f'"{c}"' if " " in c else c for c in cmd))

        proc = QProcess(self)
        self.proc = proc
        self.cancelled = False
        self.stdout_buffer = ""
        try:  # Hide the console window on Windows.
            proc.setCreateProcessArgumentsModifier(lambda args: setattr(args, "flags", args.flags | core.NO_WINDOW))
        except (AttributeError, TypeError):
            pass
        proc.readyReadStandardOutput.connect(self.on_stdout)
        proc.readyReadStandardError.connect(self.on_stderr)
        proc.errorOccurred.connect(self.on_error)
        proc.finished.connect(self.on_finished)
        self.started_at = time.monotonic()
        proc.start(cmd[0], cmd[1:])
        self.start_btn.setText("Cancel")
        self.lock_ui(True)
        self.set_status("Working…", "busy")
        self.reveal_btn.setVisible(False)
        self.progress.setValue(0, animate=False)
        self.progress.setBusy(self.video.duration <= 0)

    def on_stdout(self):
        if self.proc is None:
            return
        self.stdout_buffer += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        *lines, self.stdout_buffer = self.stdout_buffer.split("\n")
        for line in lines:
            seconds = core.parse_progress_line(line)
            if seconds is not None and self.video and self.video.duration > 0:
                frac = min(1.0, seconds / self.video.duration)
                self.progress.setValue(frac)
                text = f"Working… {int(frac * 100)}%"
                elapsed = time.monotonic() - self.started_at
                if frac > 0.03 and elapsed > 3:
                    text += f"  ·  about {core.format_duration(elapsed * (1 - frac) / frac)} left"
                self.set_status(text, "busy")

    def on_stderr(self):
        if self.proc is None:
            return
        text = bytes(self.proc.readAllStandardError()).decode("utf-8", "replace").rstrip()
        if text:
            self.log.appendPlainText(text)

    def on_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            Path(self.target + ".part").unlink(missing_ok=True)
            self.set_status("FFmpeg couldn't start. Check the FFmpeg folder.", "error")
            self.finish_run()

    def on_finished(self, code, status):
        part = Path(self.target + ".part")
        crashed = status == QProcess.ExitStatus.CrashExit
        if self.cancelled:
            part.unlink(missing_ok=True)
            self.set_status("Cancelled.")
            self.progress.setValue(0, animate=False)
        elif code == 0 and not crashed:
            try:
                os.replace(part, self.target)
            except OSError as exc:
                part.unlink(missing_ok=True)
                self.set_status(f"Couldn't save the file: {exc.strerror or exc}. Is it open in another program?", "error")
            else:
                self.progress.setValue(1.0)
                size = core.human_size(Path(self.target).stat().st_size)
                self.set_status(f"Saved {Path(self.target).name}  ·  {size}", "ok")
                self.reveal_btn.setVisible(True)
        else:
            part.unlink(missing_ok=True)
            self.set_status("FFmpeg stopped with an error. Open Details to see why.", "error")
            self.log.setVisible(True)
        self.finish_run()

    def finish_run(self):
        if self.proc:
            self.proc.deleteLater()
        self.proc = None
        self.progress.setBusy(False)
        self.lock_ui(False)
        self.start_btn.setText("Make MKV")
        self.update_start()

    def reveal(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.target).parent)))

    def closeEvent(self, event):
        if self.proc is not None:
            self.cancelled = True
            self.proc.kill()
            self.proc.waitForFinished(2000)
        super().closeEvent(event)
