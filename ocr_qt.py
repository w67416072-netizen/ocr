"""PySide6 interface for the OCR data classification tool.

Run with: ``python ocr_qt.py``

OCR API calls and ``ocr_data.json`` persistence are provided by the standalone
``qt_backend.py`` module.
"""

from __future__ import annotations

import os
import subprocess
import sys
import copy
import ctypes
import json
import shutil
import tempfile
import zipfile
import re
import time
from html import escape as html_escape
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from PySide6.QtCore import (
    Qt, Signal, QSize, QThreadPool, QUrl, QRect, QPoint, QTimer, QItemSelectionModel,
    QPropertyAnimation, QEvent, QObject,
)
from PySide6.QtGui import (
    QBrush, QColor, QDesktopServices, QFont, QPainter, QPen, QPixmap, QIcon, QImageReader,
    QKeySequence, QShortcut, QTextCursor, QTextTable, QCursor,
)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QFileDialog, QFormLayout, QFrame,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QAbstractItemView,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QRadioButton, QScrollArea,
    QCheckBox,
    QSizePolicy, QSpinBox, QDoubleSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget, QInputDialog, QComboBox,
    QListWidget, QListWidgetItem, QSplitter, QMenu, QDialogButtonBox, QColorDialog,
    QTabWidget, QStyledItemDelegate,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib import font_manager, rcParams
from matplotlib.path import Path as MplPath
from matplotlib.widgets import LassoSelector

from qt_backend import MODE_NAMES, OCRWorker, Repository, key_available, parse_line
import qt_backend


APP_DIR = qt_backend.APP_DIR
BLANK_LINE_MARKER = "~"
YELLOW = "#FFC400"
YELLOW_DARK = "#D49A00"
INK = "#17191C"
MUTED = "#6F747C"
SURFACE = "#FFFFFF"
BACKGROUND = "#F7F8FA"
BORDER = "#E8EAED"
GROUP_C_GREEN = "#16A269"
EXCEL_EXPORT_FORMAT_NAMES = {
    "standard": "标准格式（分类 | 名称 | 组值）",
    "grouped": "分组格式（辈分 | t1(A组) | t2(C组) | t3(B组) | d(D组)）",
}
EXCEL_EXPORT_FORMAT_SHORT_NAMES = {
    "standard": "标准格式",
    "grouped": "分组格式",
}
REPORT_FORMAT_NAMES = {
    "legacy": "仅名称",
    "columns": "三列",
    "grouped": "Markdown 分组表格",
}

for _font_path in (Path(r"C:\Windows\Fonts\msyh.ttc"), Path(r"C:\Windows\Fonts\msyh.ttf")):
    if _font_path.exists():
        font_manager.fontManager.addfont(str(_font_path))
        rcParams["font.sans-serif"] = [font_manager.FontProperties(fname=str(_font_path)).get_name()]
        break
rcParams["axes.unicode_minus"] = False


STYLE = f"""
* {{
    font-family: "Microsoft YaHei UI";
    font-size: 12px;
    color: {INK};
}}
QMainWindow, QWidget#appRoot {{ background: {BACKGROUND}; }}
QFrame#header {{ background: #FFFFFF; border-bottom: 1px solid {BORDER}; }}
QFrame#sidebar {{ background: #FCFCFC; border-right: 1px solid {BORDER}; }}
QFrame#card {{ background: #FFFFFF; border: 1px solid #EEF0F2; border-radius: 8px; }}
QFrame#card[panelRole="parameters"] {{
    background: #FFFFFF; border: 1px solid #E7E9EC; border-radius: 12px;
}}
QFrame#collapsibleSection {{
    background: #FFFFFF; border: 1px solid #E7E9EC; border-radius: 8px;
}}
QFrame#collapsibleHeader {{
    background: #FFFFFF; border: 0; border-radius: 8px;
}}
QFrame#collapsibleHeader:hover {{ background: #FFF9E9; }}
QLabel#collapsibleTitle {{ font-size: 12px; font-weight: 700; }}
QLabel#collapsibleArrow {{ color: #6F747C; font-size: 12px; font-weight: 700; }}
QLabel#appTitle {{ font-size: 15px; font-weight: 700; }}
QLabel#sectionTitle {{ font-size: 12px; font-weight: 700; }}
QLabel#muted {{ color: {MUTED}; font-size: 10px; }}
QPushButton {{
    min-height: 34px; padding: 0 14px; background: #F6F7F9;
    border: 1px solid #ECEEF1; border-radius: 8px;
}}
QPushButton:hover {{ background: #FFF8DF; border-color: #F4D66B; }}
QPushButton:pressed {{ background: #FFEDAD; }}
QPushButton:disabled {{ color: #A9ADB4; background: #F4F5F6; }}
QPushButton#primary {{ background: {YELLOW}; border-color: {YELLOW}; font-weight: 700; }}
QPushButton#primary:hover {{ background: #F2B900; border-color: #F2B900; }}
QPushButton#recognitionMode:checked {{
    background: {YELLOW}; border-color: {YELLOW}; color: {INK}; font-weight: 700;
}}
QPushButton#recognitionMode:checked:hover {{
    background: #F2B900; border-color: #F2B900;
}}
QPushButton#nav {{
    text-align: left; min-height: 52px; max-height: 52px; padding-left: 16px; border: 0;
    border-radius: 0; background: transparent; font-size: 13px;
}}
QPushButton#nav:hover {{ background: #FFF9E9; }}
QPushButton#nav:checked {{
    background: #FFF7E3; color: #30343A; border-left: 3px solid {YELLOW};
    padding-left: 13px;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QTableWidget {{
    background: #FFFFFF; border: 1px solid #E2E5E9; border-radius: 7px;
    selection-background-color: #FFE58A;
}}
QLineEdit, QSpinBox, QDoubleSpinBox {{ min-height: 34px; padding: 0 9px; }}
/* 数字框仅保留直接输入，彻底移除右侧的上下微调按钮。 */
QSpinBox, QDoubleSpinBox {{
    qproperty-buttonSymbols: NoButtons;
}}
QTableWidget {{ border-radius: 0; gridline-color: #ECEEF1; }}
QHeaderView::section {{
    background: #F7F8FA; border: 0; border-bottom: 1px solid #E3E5E8;
    padding: 8px; font-weight: 600;
}}
QScrollArea {{ border: 0; background: transparent; }}
QScrollArea#paramsScroll,
QScrollArea#paramsScroll > QWidget > QWidget,
QWidget#paramsContent {{ background: transparent; }}
"""


def add_shadow(widget: QWidget, blur: int = 14, opacity: int = 14) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, 2)
    effect.setColor(QColor(20, 25, 35, opacity))
    widget.setGraphicsEffect(effect)


def card(parent: QWidget | None = None) -> QFrame:
    frame = QFrame(parent)
    frame.setObjectName("card")
    add_shadow(frame)
    return frame


def sidebar_icon(kind: str) -> QIcon:
    """Create a state-aware vector icon without relying on icon fonts."""
    icon = QIcon()
    normal_color = "#B2B6BC" if kind == "menu" else "#747980"
    states = (
        (normal_color, QIcon.Mode.Normal, QIcon.State.Off),
        ("#4F545B", QIcon.Mode.Active, QIcon.State.Off),
        ("#25282C", QIcon.Mode.Normal, QIcon.State.On),
        ("#25282C", QIcon.Mode.Active, QIcon.State.On),
        ("#B2B6BC", QIcon.Mode.Disabled, QIcon.State.Off),
    )
    for color, mode, state in states:
        pixmap = QPixmap(28, 28)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if kind == "menu":
            painter.drawLine(7, 9, 21, 9)
            painter.drawLine(7, 14, 21, 14)
            painter.drawLine(7, 19, 21, 19)
        elif kind == "home":
            painter.drawLine(5, 13, 14, 5)
            painter.drawLine(14, 5, 23, 13)
            painter.drawRoundedRect(QRect(7, 12, 14, 11), 1.5, 1.5)
            painter.drawRect(QRect(12, 17, 4, 6))
        elif kind == "ocr":
            painter.drawRoundedRect(QRect(6, 5, 16, 18), 2, 2)
            painter.drawRect(QRect(10, 9, 8, 10))
            painter.drawLine(8, 7, 11, 7)
        elif kind == "image":
            painter.drawRoundedRect(QRect(5, 6, 18, 16), 2, 2)
            painter.drawEllipse(QRect(16, 9, 3, 3))
            painter.drawLine(7, 19, 12, 14)
            painter.drawLine(12, 14, 16, 18)
            painter.drawLine(16, 18, 19, 15)
            painter.drawLine(19, 15, 22, 19)
        elif kind == "history":
            painter.drawEllipse(QRect(6, 6, 16, 16))
            painter.drawLine(14, 9, 14, 15)
            painter.drawLine(14, 15, 18, 17)
            painter.drawLine(8, 5, 10, 3)
            painter.drawLine(18, 3, 20, 5)
        elif kind == "key":
            painter.drawEllipse(QRect(5, 5, 9, 9))
            painter.drawLine(12, 12, 22, 22)
            painter.drawLine(18, 18, 21, 15)
            painter.drawLine(20, 20, 23, 17)
        elif kind == "stats":
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRect(5, 14, 4, 9), 1, 1)
            painter.drawRoundedRect(QRect(12, 9, 4, 14), 1, 1)
            painter.drawRoundedRect(QRect(19, 5, 4, 18), 1, 1)
        elif kind == "rules":
            painter.drawRoundedRect(QRect(6, 5, 16, 18), 2, 2)
            painter.drawLine(10, 9, 14, 9)
            painter.drawLine(10, 13, 17, 13)
            painter.drawLine(10, 17, 14, 17)
            painter.drawLine(18, 16, 18, 20)
            painter.drawLine(16, 18, 20, 18)
        painter.end()
        icon.addPixmap(pixmap, mode, state)
    return icon


def app_icon() -> QIcon:
    """Create the visible application icon used by the Windows taskbar."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#2F80ED"))
    painter.drawRoundedRect(QRect(6, 6, 52, 52), 12, 12)
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawRoundedRect(QRect(18, 14, 28, 36), 5, 5)
    painter.setBrush(QColor("#2F80ED"))
    painter.drawRoundedRect(QRect(23, 23, 18, 4), 2, 2)
    painter.drawRoundedRect(QRect(23, 32, 18, 4), 2, 2)
    painter.drawRoundedRect(QRect(23, 41, 12, 4), 2, 2)
    painter.end()
    return QIcon(pixmap)


def _ensure_windows_icon_files() -> tuple[str, str]:
    icon_dir = Path(tempfile.gettempdir()) / "ocr_qt_icons"
    icon_dir.mkdir(parents=True, exist_ok=True)
    app_path = icon_dir / "ocr_app.ico"
    transparent_path = icon_dir / "ocr_transparent.ico"
    if not app_path.exists():
        image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((24, 24, 232, 232), radius=48, fill=(47, 128, 237, 255))
        draw.rounded_rectangle((76, 56, 180, 200), radius=22, fill=(255, 255, 255, 255))
        draw.rounded_rectangle((96, 92, 160, 108), radius=8, fill=(47, 128, 237, 255))
        draw.rounded_rectangle((96, 128, 160, 144), radius=8, fill=(47, 128, 237, 255))
        draw.rounded_rectangle((96, 164, 140, 180), radius=8, fill=(47, 128, 237, 255))
        image.save(app_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
    if not transparent_path.exists():
        Image.new("RGBA", (16, 16), (0, 0, 0, 0)).save(transparent_path, sizes=[(16, 16)])
    return str(app_path), str(transparent_path)


def apply_windows_taskbar_icon(window: QWidget) -> None:
    if sys.platform != "win32":
        return
    app_path, _transparent_path = _ensure_windows_icon_files()
    user32 = ctypes.windll.user32
    load_image = user32.LoadImageW
    load_image.restype = ctypes.c_void_p
    image_icon = 1
    lr_loadfromfile = 0x00000010
    small_icon = load_image(None, app_path, image_icon, 16, 16, lr_loadfromfile)
    big_icon = load_image(None, app_path, image_icon, 0, 0, lr_loadfromfile)
    if not small_icon or not big_icon:
        return
    hwnd = int(window.winId())
    wm_seticon = 0x0080
    icon_small = 0
    icon_big = 1
    icon_small2 = 2
    user32.SendMessageW(hwnd, wm_seticon, icon_small, small_icon)
    user32.SendMessageW(hwnd, wm_seticon, icon_small2, small_icon)
    user32.SendMessageW(hwnd, wm_seticon, icon_big, big_icon)
    window._windows_hicons = (small_icon, big_icon)


def section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


def muted_label(text: str, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(wrap)
    return label


def record_day(value: Any) -> str:
    """Return a stable calendar-day key for a stored timestamp."""
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value or ""))
    return match.group(1) if match else "未标注日期"


def ordered_record_days(records: list[dict[str, Any]], timestamp_key: str) -> list[str]:
    """List record days newest first, putting legacy records without a date last."""
    days = {record_day(item.get(timestamp_key, "")) for item in records}
    dated_days = sorted((day for day in days if day != "未标注日期"), reverse=True)
    return dated_days + (["未标注日期"] if "未标注日期" in days else [])


class CollapsibleSection(QFrame):
    """A compact settings section whose full header toggles its contents."""

    def __init__(self, title: str, expanded: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("collapsibleSection")

        section_layout = QVBoxLayout(self)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(0)

        self.header = QFrame()
        self.header.setObjectName("collapsibleHeader")
        self.header.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.header.setMinimumHeight(34)
        self.header.mousePressEvent = self._toggle_from_event
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(14, 0, 14, 0)
        header_layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("collapsibleTitle")
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        self.arrow_label = QLabel()
        self.arrow_label.setObjectName("collapsibleArrow")
        self.arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.arrow_label.setFixedWidth(18)
        self.arrow_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_layout.addWidget(self.arrow_label)
        section_layout.addWidget(self.header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(14, 4, 14, 14)
        self.body_layout.setSpacing(8)
        section_layout.addWidget(self.body)
        self.set_expanded(expanded)

    def _toggle_from_event(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_expanded(not self.is_expanded())
        event.accept()

    def _update_state(self) -> None:
        expanded = self.is_expanded()
        self.body.setVisible(expanded)
        self.arrow_label.setText("▼" if expanded else "▶")

    def set_expanded(self, expanded: bool) -> None:
        self.body.setProperty("expanded", bool(expanded))
        self._update_state()

    def is_expanded(self) -> bool:
        return bool(self.body.property("expanded"))

    def add_widget(self, widget: QWidget) -> None:
        self.body_layout.addWidget(widget)

    def add_layout(self, child_layout) -> None:
        self.body_layout.addLayout(child_layout)


class StepButton(QPushButton):
    """Compact workflow step with an independently styled badge and labels."""

    def __init__(self, number: int, title: str, subtitle: str) -> None:
        super().__init__()
        self._x_scale = 1.0
        self._y_scale = 1.0
        self._ui_scale = 1.0
        self.setObjectName("step")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.content_layout = QHBoxLayout(self)

        self.badge = QLabel(str(number))
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.badge)

        labels = QVBoxLayout()
        labels.setContentsMargins(0, 0, 0, 0)
        labels.setSpacing(1)
        self.title_label = QLabel(title)
        self.subtitle_label = QLabel(subtitle)
        labels.addWidget(self.title_label)
        labels.addWidget(self.subtitle_label)
        self.content_layout.addLayout(labels, 1)

        for label in (self.badge, self.title_label, self.subtitle_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.toggled.connect(self._sync_style)
        self.apply_scale(1.0, 1.0, 1.0)

    def apply_scale(self, x_scale: float, y_scale: float, ui_scale: float) -> None:
        self._x_scale = x_scale
        self._y_scale = y_scale
        self._ui_scale = ui_scale
        badge_size = max(26, round(30 * ui_scale))
        self.setFixedHeight(max(50, round(56 * y_scale)))
        self.content_layout.setContentsMargins(
            round(10 * x_scale), round(4 * y_scale),
            round(10 * x_scale), round(4 * y_scale),
        )
        self.content_layout.setSpacing(max(8, round(10 * ui_scale)))
        self.badge.setFixedSize(badge_size, badge_size)
        self.title_label.setStyleSheet(
            "background:transparent;border:0;"
            f"font-size:{max(12, round(13 * ui_scale))}px;"
            "font-weight:600;color:#25282C;"
        )
        self.subtitle_label.setStyleSheet(
            "background:transparent;border:0;"
            f"font-size:{max(9, round(10 * ui_scale))}px;color:#777C84;"
        )
        self._sync_style(self.isChecked())

    def _sync_style(self, checked: bool) -> None:
        background = "#FFF9E8" if checked else "transparent"
        hover = "#FFF5D8" if checked else "#FAFAFA"
        button_radius = max(6, round(7 * self._ui_scale))
        self.setStyleSheet(
            f"QPushButton#step {{background:{background};border:0;"
            f"border-radius:{button_radius}px;padding:0;}}"
            f"QPushButton#step:hover {{background:{hover};border:0;}}"
        )
        badge_background = YELLOW if checked else "#ECEDEF"
        badge_color = INK if checked else "#4F545B"
        badge_radius = self.badge.width() // 2
        badge_font_size = max(11, round(12 * self._ui_scale))
        self.badge.setStyleSheet(
            f"background:{badge_background};color:{badge_color};border:0;"
            f"border-radius:{badge_radius}px;font-size:{badge_font_size}px;font-weight:600;"
        )


class DropZone(QFrame):
    filesDropped = Signal(list)
    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(132)
        self._set_active(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(3)
        icon = QLabel("▧")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size:28px;color:#B8BDC5;")
        icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.label = QLabel("拖拽图片到此处\n或点击选择图片")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("color:#5F646C;border:0;")
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(icon)
        layout.addWidget(self.label)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            self._set_active(True)
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_active(False)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802
        self._set_active(False)
        extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
        paths: list[str] = []
        for url in event.mimeData().urls():
            source = Path(url.toLocalFile())
            if source.is_dir():
                paths.extend(str(path) for path in source.rglob("*") if path.is_file() and path.suffix.lower() in extensions)
            elif source.is_file() and source.suffix.lower() in extensions:
                paths.append(str(source))
        # Preserve drag order and remove duplicate paths without breaking
        # Chinese, spaces, or brace characters in Windows filenames.
        paths = list(dict.fromkeys(paths))
        if paths:
            self.filesDropped.emit(paths)
        event.acceptProposedAction()

    def _set_active(self, active: bool) -> None:
        background = "#FFF8DF" if active else "#FFFFFF"
        border = "#E0AD00" if active else "#CCD1D8"
        self.setStyleSheet(
            f"QFrame {{background:{background}; border:2px dashed {border}; border-radius:10px;}}"
            "QLabel {border:0; background:transparent;}"
        )


class PlotCanvas(FigureCanvasQTAgg):
    thresholdsChanged = Signal(list, list)
    pointsLassoed = Signal(list)
    statusRequested = Signal(str, str)

    def __init__(self) -> None:
        self.figure = Figure(figsize=(7, 7), dpi=100, facecolor="white")
        self.axes = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.rows: list[dict[str, Any]] = []
        self.thresholds: list[float] = []
        self.lasso: LassoSelector | None = None
        self.lasso_enabled = False
        self.category_colors: dict[str, str] = {}
        self.scatter_artist = None
        self.annotation_artists: list[tuple[dict[str, Any], Any]] = []
        self.threshold_artists: list[Any] = []
        self._pending_threshold_previous: list[float] | None = None
        self._threshold_change_timer = QTimer(self)
        self._threshold_change_timer.setSingleShot(True)
        self._threshold_change_timer.setInterval(0)
        self._threshold_change_timer.timeout.connect(self._emit_threshold_change)
        self.mpl_connect("button_press_event", self._plot_clicked)
        self.mpl_connect("draw_event", self._plot_drawn)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.draw_rows([])

    def draw_rows(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        # LassoSelector owns matplotlib artists tied to the current axes
        # contents. Disconnect before clear and recreate after every redraw.
        if self.lasso is not None:
            self.lasso.disconnect_events()
            self.lasso = None
        ax = self.axes
        ax.clear()
        self.scatter_artist = None
        self.annotation_artists = []
        self.threshold_artists = []
        ax.set_facecolor("white")
        if rows:
            xs = [row["x"] for row in rows]
            ys = [row["y"] for row in rows]
            colors = [
                "#D14343" if row.get("marked", False)
                else self.category_colors.get(str(row.get("category", "")), "#2B78C5")
                for row in rows
            ]
            sizes = [70 if row.get("marked", False) else 38 for row in rows]
            self.scatter_artist = ax.scatter(xs, ys, s=sizes, color=colors, zorder=4)
            for row in rows:
                annotation = ax.annotate(
                    row["label"], (row["x"], row["y"]), xytext=(0, 5),
                    textcoords="offset points", ha="center", fontsize=8,
                    color="#D14343" if row.get("marked", False) else "#17191C",
                    fontweight="bold" if row.get("marked", False) else "normal",
                )
                self.annotation_artists.append((row, annotation))
            ax.margins(0.08)
            spine_color = "#CBD0D6"
        else:
            ticks = [index / 10 for index in range(11)]
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_xticks(ticks)
            ax.set_yticks(ticks)
            ax.scatter([0, .5, 1, 0, 1, 0, .5, 1], [0, 0, 0, .5, .5, 1, 1, 1],
                       marker="s", s=28, color=YELLOW, zorder=5, clip_on=False)
            spine_color = YELLOW
        ax.grid(True, color="#EAECF0", linewidth=.8)
        self._add_threshold_artists()
        ax.tick_params(colors="#6F747C", labelsize=9)
        for spine in ax.spines.values():
            spine.set_color(spine_color)
            spine.set_linewidth(1.1)
        self.figure.tight_layout(pad=2.2)
        self.draw_idle()
        self._reset_lasso()

    def _add_threshold_artists(self) -> None:
        self.threshold_artists = [
            self.axes.axhline(
                threshold, color="#D49A00", linestyle="--", linewidth=1.2, alpha=.75
            )
            for threshold in self.thresholds
        ]

    def _refresh_threshold_artists(self) -> None:
        for artist in self.threshold_artists:
            try:
                artist.remove()
            except ValueError:
                pass
        self._add_threshold_artists()
        # Match the classic UI: paint the line synchronously before the
        # deferred classification/table refresh is allowed to start.
        self.draw()
        self.repaint()

    def _show_added_threshold_immediately(self, threshold: float) -> None:
        artist = self.axes.axhline(
            threshold, color="#D49A00", linestyle="--", linewidth=1.2, alpha=.75
        )
        self.threshold_artists.append(artist)
        self.axes.draw_artist(artist)
        self.blit(self.axes.bbox)
        self.repaint()
        self._threshold_change_timer.start()

    def sync_row_styles(self, rows: list[dict[str, Any]],
                        category_colors: dict[str, str]) -> None:
        """Update classification colors without rebuilding the whole plot."""
        self.rows = rows
        self.category_colors = dict(category_colors)
        if self.scatter_artist is not None and self.annotation_artists:
            plotted_rows = [row for row, _annotation in self.annotation_artists]
            colors = [
                "#D14343" if row.get("marked", False)
                else self.category_colors.get(str(row.get("category", "")), "#2B78C5")
                for row in plotted_rows
            ]
            sizes = [70 if row.get("marked", False) else 38 for row in plotted_rows]
            self.scatter_artist.set_facecolors(colors)
            self.scatter_artist.set_sizes(sizes)
            for row, annotation in self.annotation_artists:
                marked = bool(row.get("marked", False))
                annotation.set_color("#D14343" if marked else "#17191C")
                annotation.set_fontweight("bold" if marked else "normal")
        self.draw_idle()

    def set_lasso_mode(self, enabled: bool) -> None:
        self.lasso_enabled = enabled
        self._reset_lasso()

    def cancel_lasso(self) -> bool:
        if not self.lasso_enabled or self.lasso is None:
            return False
        # Disconnect the selector that owns the in-progress mouse gesture and
        # create a fresh one.  Completed categories are data on OCRPage and are
        # therefore left untouched.
        self._reset_lasso()
        self.draw_idle()
        return True

    def _reset_lasso(self) -> None:
        if self.lasso is not None:
            self.lasso.disconnect_events()
            self.lasso = None
        if self.lasso_enabled:
            self.lasso = LassoSelector(self.axes, onselect=self._lasso_selected,
                                       props={"color": "#E04B3F", "linewidth": 1.5})

    def _plot_clicked(self, event) -> None:
        if self.lasso_enabled or event.inaxes != self.axes or event.ydata is None:
            return
        previous = list(self.thresholds)
        changed = False
        added_value: float | None = None
        removed_value: float | None = None
        if event.button == 1:
            value = round(float(event.ydata), 1)
            if value not in self.thresholds:
                self.thresholds.append(value)
                self.thresholds.sort()
                changed = True
                added_value = value
        elif event.button == 3 and self.thresholds:
            closest = min(self.thresholds, key=lambda value: abs(value - event.ydata))
            span = max(1.0, self.axes.get_ylim()[1] - self.axes.get_ylim()[0])
            if abs(closest - event.ydata) <= span * .05:
                self.thresholds.remove(closest)
                changed = True
                removed_value = closest
        else:
            return
        if not changed:
            return
        if self._pending_threshold_previous is None:
            self._pending_threshold_previous = previous
        if added_value is not None:
            self._show_added_threshold_immediately(added_value)
            self.statusRequested.emit("done", f"直线添加成功 · Y={added_value:g}")
        else:
            self._refresh_threshold_artists()
            if removed_value is not None:
                self.statusRequested.emit("done", f"直线已删除 · Y={removed_value:g}")

    def _plot_drawn(self, _event) -> None:
        if (
            self._pending_threshold_previous is not None
            and not self._threshold_change_timer.isActive()
        ):
            self._threshold_change_timer.start()

    def _emit_threshold_change(self) -> None:
        previous = self._pending_threshold_previous
        self._pending_threshold_previous = None
        if previous is not None and previous != self.thresholds:
            self.thresholdsChanged.emit(list(self.thresholds), previous)

    def _lasso_selected(self, vertices) -> None:
        if not self.rows:
            self.pointsLassoed.emit([])
            return
        path = MplPath(vertices)
        points = [(row["x"], row["y"]) for row in self.rows]
        indices = [index for index, inside in enumerate(path.contains_points(points)) if inside]
        self.pointsLassoed.emit(indices)


class CropCanvas(QWidget):
    """Crop viewer with zoom, pan, and draggable corner handles."""

    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__()
        self.pixmap = pixmap
        self.image_rect = QRect()
        self.selection = QRect()
        self.origin: QPoint | None = None
        self.zoom = 1.0
        self.pan = QPoint(0, 0)
        self.pan_origin: QPoint | None = None
        self.pan_start = QPoint(0, 0)
        self.resize_handle = ""
        self.handle_size = 9
        self.setMinimumSize(760, 520)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def _target_rect(self) -> QRect:
        size = self.pixmap.size()
        size.scale(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        size.setWidth(max(1, round(size.width() * self.zoom)))
        size.setHeight(max(1, round(size.height() * self.zoom)))
        return QRect((self.width() - size.width()) // 2 + self.pan.x(),
                     (self.height() - size.height()) // 2 + self.pan.y(),
                     size.width(), size.height())

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#202226"))
        self.image_rect = self._target_rect()
        painter.drawPixmap(self.image_rect, self.pixmap)
        if not self.selection.isNull():
            painter.setPen(QPen(QColor(YELLOW), 2))
            painter.drawRect(self.selection)
            painter.setBrush(QColor(YELLOW))
            for point in self._handle_points().values():
                painter.drawRect(QRect(point.x() - self.handle_size // 2,
                                       point.y() - self.handle_size // 2,
                                       self.handle_size, self.handle_size))

    def _handle_points(self) -> dict[str, QPoint]:
        return {
            "tl": self.selection.topLeft(), "tr": self.selection.topRight(),
            "bl": self.selection.bottomLeft(), "br": self.selection.bottomRight(),
        }

    def _hit_handle(self, point: QPoint) -> str:
        if self.selection.isNull():
            return ""
        tolerance = self.handle_size + 3
        for name, handle in self._handle_points().items():
            if abs(point.x() - handle.x()) <= tolerance and abs(point.y() - handle.y()) <= tolerance:
                return name
        return ""

    def mousePressEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        if event.button() in {Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton}:
            self.pan_origin = point
            self.pan_start = QPoint(self.pan)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if event.button() == Qt.MouseButton.LeftButton and self.image_rect.contains(point):
            self.resize_handle = self._hit_handle(point)
            if self.resize_handle:
                return
            self.origin = point
            self.selection = QRect(self.origin, self.origin)
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        if self.pan_origin is not None:
            self.pan = self.pan_start + point - self.pan_origin
            self.update()
            return
        point.setX(max(self.image_rect.left(), min(point.x(), self.image_rect.right())))
        point.setY(max(self.image_rect.top(), min(point.y(), self.image_rect.bottom())))
        if self.resize_handle:
            opposite = {
                "tl": self.selection.bottomRight(), "tr": self.selection.bottomLeft(),
                "bl": self.selection.topRight(), "br": self.selection.topLeft(),
            }[self.resize_handle]
            self.selection = QRect(opposite, point).normalized().intersected(self.image_rect)
        elif self.origin is not None:
            self.selection = QRect(self.origin, point).normalized().intersected(self.image_rect)
        self.update()

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802
        self.origin = None
        self.resize_handle = ""
        self.pan_origin = None
        self.setCursor(Qt.CursorShape.CrossCursor)

    def wheelEvent(self, event) -> None:  # noqa: N802
        old_zoom = self.zoom
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.zoom = max(.25, min(6.0, self.zoom * factor))
        if abs(self.zoom - old_zoom) > .001:
            self.selection = QRect()
            self.update()
        event.accept()

    def reset_view(self) -> None:
        self.zoom = 1.0
        self.pan = QPoint(0, 0)
        self.selection = QRect()
        self.update()

    def cropped(self) -> QPixmap:
        if self.selection.width() < 2 or self.selection.height() < 2:
            return QPixmap()
        sx = self.pixmap.width() / self.image_rect.width()
        sy = self.pixmap.height() / self.image_rect.height()
        source = QRect(
            round((self.selection.left() - self.image_rect.left()) * sx),
            round((self.selection.top() - self.image_rect.top()) * sy),
            round(self.selection.width() * sx),
            round(self.selection.height() * sy),
        ).intersected(self.pixmap.rect())
        return self.pixmap.copy(source)


class CropDialog(QDialog):
    def __init__(self, pixmap: QPixmap, default_name: str, parent: QWidget | None = None,
                 direct: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("裁剪图片")
        self.resize(980, 720)
        self.output_path = ""
        self.result_pixmap = QPixmap()
        self.default_name = default_name
        self.direct = direct
        layout = QVBoxLayout(self)
        hint_row = QHBoxLayout()
        hint_row.addWidget(muted_label("左键框选/拖动黄色角点 · 滚轮缩放 · 中键或右键平移"))
        reset = QPushButton("重置视图")
        reset.clicked.connect(lambda: self.canvas.reset_view())
        hint_row.addStretch()
        hint_row.addWidget(reset)
        layout.addLayout(hint_row)
        self.canvas = CropCanvas(pixmap)
        layout.addWidget(self.canvas, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("使用选区" if direct else "保存裁剪结果")
        save.setObjectName("primary")
        save.clicked.connect(self.save_crop)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def save_crop(self) -> None:
        cropped = self.canvas.cropped()
        if cropped.isNull():
            QMessageBox.warning(self, "提示", "请先框选裁剪区域")
            return
        self.result_pixmap = cropped
        if self.direct:
            self.accept()
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存裁剪图片", self.default_name, "PNG (*.png);;JPEG (*.jpg)"
        )
        if path and cropped.save(path):
            self.output_path = path
            self.accept()


class PixmapScrollViewer(QScrollArea):
    """Small reusable fit/zoom image preview used by all merge workflows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.source = QPixmap()
        self.highlight_rect = QRect()
        self.zoom = 1.0
        self.fit = True
        self._dragging = False
        self._drag_global_position = QPoint()
        self.label = QLabel("暂无预览")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("background:#F3F4F6;color:#8A9099;")
        self.label.setCursor(Qt.CursorShape.OpenHandCursor)
        self.label.installEventFilter(self)
        self.setWidget(self.label)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QScrollArea{background:#F3F4F6;border:1px solid #E3E6EA;border-radius:8px;}")
        self.setToolTip("滚轮缩放；放大后按住鼠标左键拖动画面")

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.label:
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self._dragging = True
                self._drag_global_position = event.globalPosition().toPoint()
                self.label.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return True
            if event.type() == QEvent.Type.MouseMove and self._dragging:
                current = event.globalPosition().toPoint()
                delta = current - self._drag_global_position
                self._drag_global_position = current
                self.horizontalScrollBar().setValue(
                    self.horizontalScrollBar().value() - delta.x()
                )
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() - delta.y()
                )
                event.accept()
                return True
            if (
                event.type() == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self._dragging = False
                self.label.setCursor(Qt.CursorShape.OpenHandCursor)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self.source = QPixmap(pixmap)
        self.highlight_rect = QRect()
        self.fit = True
        self.zoom = 1.0
        self._render()

    def set_highlight(self, rect: QRect | None) -> None:
        self.highlight_rect = QRect(rect) if rect is not None else QRect()
        self._render()

    def show_actual(self) -> None:
        self.fit = False
        self.zoom = 1.0
        self._render()

    def show_fit(self) -> None:
        self.fit = True
        self._render()

    def zoom_by(self, factor: float) -> None:
        if self.source.isNull():
            return
        if self.fit:
            available = QSize(max(1, self.viewport().width() - 18), max(1, self.viewport().height() - 18))
            self.zoom = min(available.width() / self.source.width(), available.height() / self.source.height())
        self.fit = False
        self.zoom = max(.05, min(8.0, self.zoom * factor))
        self._render()

    def _render(self) -> None:
        if self.source.isNull():
            self.label.setText("暂无预览")
            self.label.resize(max(320, self.viewport().width()), max(220, self.viewport().height()))
            return
        if self.fit:
            available = QSize(max(1, self.viewport().width() - 18), max(1, self.viewport().height() - 18))
            scale = min(available.width() / self.source.width(), available.height() / self.source.height(), 1.0)
        else:
            scale = self.zoom
        size = QSize(max(1, round(self.source.width() * scale)), max(1, round(self.source.height() * scale)))
        preview = self.source.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
        if self.highlight_rect.isValid() and not self.highlight_rect.isNull():
            sx = preview.width() / self.source.width()
            sy = preview.height() / self.source.height()
            highlight = QRect(
                round(self.highlight_rect.x() * sx),
                round(self.highlight_rect.y() * sy),
                max(2, round(self.highlight_rect.width() * sx)),
                max(2, round(self.highlight_rect.height() * sy)),
            ).intersected(preview.rect())
            if highlight.isValid():
                painter = QPainter(preview)
                painter.fillRect(highlight, QColor(255, 196, 0, 70))
                painter.setPen(QPen(QColor("#E53935"), 3))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(highlight.adjusted(1, 1, -1, -1))
                painter.end()
        self.label.setText("")
        self.label.resize(preview.size())
        self.label.setPixmap(preview)
        if self.highlight_rect.isValid() and not self.fit:
            center_x = round(self.highlight_rect.center().x() * scale)
            center_y = round(self.highlight_rect.center().y() * scale)
            QTimer.singleShot(
                0,
                lambda: self.ensureVisible(center_x, center_y, 80, 80),
            )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.fit:
            self._render()

    def wheelEvent(self, event) -> None:
        self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        event.accept()


def merge_pixmaps(images: list[QPixmap], reverse: bool = True, vertical: bool = False) -> QPixmap:
    images = [image for image in images if not image.isNull()]
    if not images:
        return QPixmap()
    ordered = list(reversed(images)) if reverse else list(images)
    if vertical:
        width = max(image.width() for image in ordered)
        height = sum(image.height() for image in ordered)
    else:
        width = sum(image.width() for image in ordered)
        height = max(image.height() for image in ordered)
    output = QPixmap(width, height)
    output.fill(QColor("white"))
    painter = QPainter(output)
    x = y = 0
    for image in ordered:
        if vertical:
            x = (width - image.width()) // 2
            painter.drawPixmap(x, y, image)
            y += image.height()
        else:
            y = (height - image.height()) // 2
            painter.drawPixmap(x, y, image)
            x += image.width()
    painter.end()
    return output


def stable_merged_path(repository: Repository, source_type: str, pixmap: QPixmap) -> str:
    configured = str(repository.get("merge_save_path", "") or "")
    directory = Path(configured) if configured else APP_DIR / "merged_images"
    directory.mkdir(parents=True, exist_ok=True)
    labels = {"file": "图片拼接", "screenshot": "截图拼接", "crop": "裁剪拼接"}
    suffix = ".png" if source_type == "screenshot" else ".jpg"
    stem = f"{labels.get(source_type, '图片拼接')}_{datetime.now():%Y%m%d_%H%M%S}"
    path = directory / f"{stem}{suffix}"
    counter = 1
    while path.exists():
        path = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    image_format = "PNG" if suffix == ".png" else "JPG"
    if not pixmap.save(str(path), image_format, 95):
        raise OSError(f"无法保存拼接图片：{path}")
    return str(path)


def add_merge_history(repository: Repository, source_type: str, output_path: str,
                      source_paths: list[str] | None = None) -> None:
    if not output_path or not Path(output_path).exists():
        return
    history = list(repository.get("merge_history", []) or [])
    labels = {"file": "文件拼接", "screenshot": "截图拼接", "crop": "裁剪拼接"}
    entry = {
        "type": source_type,
        "source_paths": list(source_paths or []),
        "output_path": output_path,
        "label": labels.get(source_type, source_type),
        "desc": Path(output_path).name,
        "time": datetime.now().strftime("%H:%M:%S"),
        "recognized": False,
        "recognized_type": "",
        "recognized_at": "",
    }
    history = [entry] + [item for item in history if item.get("output_path") != output_path]
    repository.set("merge_history", history[:20])


def mark_merge_recognized(repository: Repository, output_path: str, mode: str) -> None:
    if not output_path:
        return
    target = os.path.normcase(os.path.abspath(output_path))
    history = list(repository.get("merge_history", []) or [])
    changed = False
    for item in history:
        path = str(item.get("output_path", ""))
        if path and os.path.normcase(os.path.abspath(path)) == target:
            item["recognized"] = True
            item["recognized_type"] = mode
            item["recognized_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            changed = True
    if changed:
        repository.set("merge_history", history)


class MergePreviewDialog(QDialog):
    """Shared native preview for file, screenshot, and crop merge outputs."""

    def __init__(self, repository: Repository, images: list[QPixmap], source_type: str,
                 source_paths: list[str] | None = None, initial_mode: str = "accurate",
                 allow_vertical: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.images = [QPixmap(image) for image in images if not image.isNull()]
        self.source_type = source_type
        self.preview_key = {"file": "merge", "crop": "crop", "screenshot": "screenshot"}.get(
            source_type, source_type
        )
        self.source_paths = list(source_paths or [])
        self.reverse = True
        self.output_path = ""
        defaults = self.repository.get("preview_ocr_defaults", {}) or {}
        remembered_mode = str(defaults.get(self.preview_key, initial_mode))
        self.selected_mode = remembered_mode
        self.setWindowTitle({"file": "拼接预览", "screenshot": "截图拼接预览", "crop": "裁剪拼接预览"}.get(source_type, "拼接预览"))
        self.resize(1100, 780)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(section_label(self.windowTitle()))
        header.addStretch()
        header.addWidget(QLabel("识别模式"))
        self.mode = QComboBox()
        for key, name in MODE_NAMES.items():
            self.mode.addItem(name, key)
            item = self.mode.model().item(self.mode.count() - 1)
            if item is not None and not key_available(key):
                item.setEnabled(False)
                item.setToolTip("此模式的百度 OCR 密钥尚未配置")
        mode_index = self.mode.findData(remembered_mode)
        if mode_index < 0 or not key_available(remembered_mode):
            mode_index = self.mode.findData(initial_mode)
        if mode_index < 0 or not key_available(str(self.mode.itemData(mode_index))):
            mode_index = next(
                (index for index in range(self.mode.count()) if key_available(str(self.mode.itemData(index)))),
                0,
            )
        self.mode.setCurrentIndex(mode_index)
        self.mode.currentIndexChanged.connect(self.refresh_preview)
        header.addWidget(self.mode)
        self.direction = QComboBox()
        self.direction.addItem("横向拼接", False)
        if allow_vertical:
            self.direction.addItem("纵向拼接", True)
        self.direction.currentIndexChanged.connect(self.refresh_preview)
        header.addWidget(self.direction)
        self.order_button = QPushButton("切换为正向拼接")
        self.order_button.clicked.connect(self.toggle_order)
        header.addWidget(self.order_button)
        layout.addLayout(header)
        self.info = muted_label("")
        layout.addWidget(self.info)
        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("background:#FFF6DE;color:#9A6500;padding:8px;border-radius:7px;")
        layout.addWidget(self.warning)
        self.viewer = PixmapScrollViewer()
        layout.addWidget(self.viewer, 1)
        zoom = QHBoxLayout()
        zoom.addWidget(muted_label("滚轮缩放；默认后选择的内容在左侧／上方"))
        zoom.addStretch()
        for text_value, handler in [
            ("－", lambda: self.viewer.zoom_by(1 / 1.2)), ("＋", lambda: self.viewer.zoom_by(1.2)),
            ("100%", self.viewer.show_actual), ("适应窗口", self.viewer.show_fit),
        ]:
            button = QPushButton(text_value)
            button.clicked.connect(handler)
            zoom.addWidget(button)
        layout.addLayout(zoom)
        footer = QHBoxLayout()
        footer.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("另存图片")
        save.clicked.connect(self.save_copy)
        self.use_button = QPushButton("导入识别")
        self.use_button.setObjectName("primary")
        self.use_button.clicked.connect(self.use_result)
        footer.addWidget(cancel)
        footer.addWidget(save)
        footer.addWidget(self.use_button)
        layout.addLayout(footer)
        self.merged = QPixmap()
        self.refresh_preview()

    def toggle_order(self) -> None:
        self.reverse = not self.reverse
        self.order_button.setText("切换为反向拼接" if not self.reverse else "切换为正向拼接")
        self.refresh_preview()

    def refresh_preview(self, *_args) -> None:
        vertical = bool(self.direction.currentData()) if self.direction.count() else False
        self.merged = merge_pixmaps(self.images, self.reverse, vertical)
        self.viewer.set_pixmap(self.merged)
        order_text = "反向：后选择内容在前" if self.reverse else "正向：先选择内容在前"
        self.info.setText(
            f"{len(self.images)} 张／区域 · {self.merged.width()} × {self.merged.height()} px · {order_text}"
        )
        self.selected_mode = str(self.mode.currentData() or "accurate")
        if self.merged.isNull():
            self.warning.setText("没有可拼接的图片")
            return
        limits = self.repository.limits()
        mode = self.selected_mode
        width, height = self.merged.width(), self.merged.height()
        allowed, reason = self.repository.mode_allowed_for_size(width, height, mode)
        available = []
        for candidate in ("accurate", "general", "basic"):
            candidate_ok, _ = self.repository.mode_allowed_for_size(width, height, candidate)
            if key_available(candidate) and candidate_ok:
                available.append(candidate)
        recommended = available[0] if available else ""
        self.warning.setText(
            f"尺寸符合{MODE_NAMES.get(mode, mode)}规则；推荐：{MODE_NAMES.get(recommended, recommended)}"
            if allowed and key_available(mode) else
            f"⚠ {reason if key_available(mode) else '当前模式密钥未配置'}；"
            f"可用：{'、'.join(MODE_NAMES[item] for item in available) if available else '无，请调整方向或区域'}"
        )
        self.warning.setStyleSheet(
            "background:#ECFDF5;color:#137A4A;padding:8px;border-radius:7px;" if allowed and key_available(mode) else
            "background:#FFF3E0;color:#B45309;padding:8px;border-radius:7px;"
        )
        self.use_button.setEnabled(bool(allowed and key_available(mode)))

    def save_copy(self) -> None:
        if self.merged.isNull():
            return
        default = f"{self.windowTitle()}_{datetime.now():%Y%m%d_%H%M%S}.png"
        path, _ = QFileDialog.getSaveFileName(self, "保存拼接图片", default, "PNG (*.png);;JPEG (*.jpg)")
        if path and not self.merged.save(path):
            QMessageBox.warning(self, "保存失败", "无法写入所选文件")

    def use_result(self) -> None:
        if self.merged.isNull():
            QMessageBox.warning(self, "提示", "没有可导入的拼接结果")
            return
        self.selected_mode = str(self.mode.currentData() or "accurate")
        allowed, reason = self.repository.mode_allowed_for_size(
            self.merged.width(), self.merged.height(), self.selected_mode
        )
        if not key_available(self.selected_mode) or not allowed:
            QMessageBox.warning(self, "识别模式不可用", reason)
            return
        try:
            self.output_path = stable_merged_path(self.repository, self.source_type, self.merged)
            add_merge_history(self.repository, self.source_type, self.output_path, self.source_paths)
            defaults = dict(self.repository.get("preview_ocr_defaults", {}) or {})
            defaults[self.preview_key] = self.selected_mode
            self.repository.set("preview_ocr_defaults", defaults)
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))


class MultiCropCanvas(QWidget):
    """One-image-at-a-time editor retaining multiple source-space regions per image."""

    regionsChanged = Signal()

    def __init__(self, images: list[QPixmap]) -> None:
        super().__init__()
        self.images = images
        self.regions: list[list[QRect]] = [[] for _ in images]
        self.current_index = 0
        self.image_rect = QRect()
        self.zoom = 1.0
        self.pan = QPoint()
        self.origin: QPoint | None = None
        self.drag_rect = QRect()
        self.pan_origin: QPoint | None = None
        self.pan_start = QPoint()
        self.setMinimumSize(720, 500)
        self.setCursor(Qt.CursorShape.CrossCursor)

    @property
    def pixmap(self) -> QPixmap:
        return self.images[self.current_index] if self.images else QPixmap()

    def set_current_index(self, index: int) -> None:
        if not 0 <= index < len(self.images):
            return
        self.current_index = index
        self.reset_view()

    def _target_rect(self) -> QRect:
        if self.pixmap.isNull():
            return QRect()
        size = self.pixmap.size()
        size.scale(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        size = QSize(max(1, round(size.width() * self.zoom)), max(1, round(size.height() * self.zoom)))
        return QRect((self.width() - size.width()) // 2 + self.pan.x(),
                     (self.height() - size.height()) // 2 + self.pan.y(), size.width(), size.height())

    def _to_display(self, source: QRect) -> QRect:
        if self.image_rect.isNull() or self.pixmap.isNull():
            return QRect()
        sx = self.image_rect.width() / self.pixmap.width()
        sy = self.image_rect.height() / self.pixmap.height()
        return QRect(
            round(self.image_rect.left() + source.left() * sx),
            round(self.image_rect.top() + source.top() * sy),
            max(1, round(source.width() * sx)), max(1, round(source.height() * sy)),
        )

    def _to_source(self, display: QRect) -> QRect:
        sx = self.pixmap.width() / self.image_rect.width()
        sy = self.pixmap.height() / self.image_rect.height()
        return QRect(
            round((display.left() - self.image_rect.left()) * sx),
            round((display.top() - self.image_rect.top()) * sy),
            max(1, round(display.width() * sx)), max(1, round(display.height() * sy)),
        ).intersected(self.pixmap.rect())

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#202226"))
        if self.pixmap.isNull():
            return
        self.image_rect = self._target_rect()
        painter.drawPixmap(self.image_rect, self.pixmap)
        global_number = sum(len(items) for items in self.regions[:self.current_index])
        for offset, source_rect in enumerate(self.regions[self.current_index], start=1):
            rect = self._to_display(source_rect)
            painter.setPen(QPen(QColor("#F44336"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)
            badge = QRect(rect.left(), rect.top(), 30, 26)
            painter.fillRect(badge, QColor("#F44336"))
            painter.setPen(QColor("white"))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(global_number + offset))
        if not self.drag_rect.isNull():
            painter.setPen(QPen(QColor(YELLOW), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.drag_rect)

    def mousePressEvent(self, event) -> None:
        point = event.position().toPoint()
        if event.button() == Qt.MouseButton.RightButton:
            for index, source_rect in enumerate(self.regions[self.current_index]):
                if self._to_display(source_rect).contains(point):
                    self.regions[self.current_index].pop(index)
                    self.regionsChanged.emit()
                    self.update()
                    return
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.pan_origin = point
            self.pan_start = QPoint(self.pan)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.LeftButton and self.image_rect.contains(point):
            self.origin = point
            self.drag_rect = QRect(point, point)

    def mouseMoveEvent(self, event) -> None:
        point = event.position().toPoint()
        if self.pan_origin is not None:
            self.pan = self.pan_start + point - self.pan_origin
            self.update()
            return
        if self.origin is not None:
            point.setX(max(self.image_rect.left(), min(point.x(), self.image_rect.right())))
            point.setY(max(self.image_rect.top(), min(point.y(), self.image_rect.bottom())))
            self.drag_rect = QRect(self.origin, point).normalized().intersected(self.image_rect)
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.origin is not None:
            if self.drag_rect.width() >= 10 and self.drag_rect.height() >= 10:
                self.regions[self.current_index].append(self._to_source(self.drag_rect))
                self.regionsChanged.emit()
            self.origin = None
            self.drag_rect = QRect()
            self.update()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.pan_origin = None
            self.setCursor(Qt.CursorShape.CrossCursor)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.zoom = max(.1, min(10.0, self.zoom * factor))
        self.update()
        event.accept()

    def zoom_by(self, factor: float) -> None:
        self.zoom = max(.1, min(10.0, self.zoom * factor))
        self.update()

    def reset_view(self) -> None:
        self.zoom = 1.0
        self.pan = QPoint()
        self.drag_rect = QRect()
        self.update()

    def clear_current(self) -> None:
        if self.images:
            self.regions[self.current_index].clear()
            self.regionsChanged.emit()
            self.update()

    def cropped_images(self) -> list[QPixmap]:
        output = []
        for image, regions in zip(self.images, self.regions):
            for rect in regions:
                cropped = image.copy(rect.intersected(image.rect()))
                if not cropped.isNull():
                    output.append(cropped)
        return output


class MultiCropDialog(QDialog):
    def __init__(self, paths: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.paths = paths
        self.images: list[QPixmap] = []
        self.names: list[str] = []
        for path in paths:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            image = reader.read()
            if not image.isNull():
                self.images.append(QPixmap.fromImage(image))
                self.names.append(Path(path).name)
        self.result_images: list[QPixmap] = []
        self.setWindowTitle("裁剪并拼接 - 多图多区域")
        self.resize(1180, 820)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(section_label("裁剪并拼接"))
        header.addWidget(muted_label("左键框选多个区域 · 右键删除区域 · 中键平移 · 滚轮缩放"))
        header.addStretch()
        self.image_info = QLabel("")
        header.addWidget(self.image_info)
        layout.addLayout(header)
        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setFixedWidth(230)
        self.list.setIconSize(QSize(80, 60))
        self.list.currentRowChanged.connect(self.change_image)
        body.addWidget(self.list)
        self.canvas = MultiCropCanvas(self.images)
        self.canvas.regionsChanged.connect(self.refresh_list)
        body.addWidget(self.canvas, 1)
        layout.addLayout(body, 1)
        tools = QHBoxLayout()
        previous = QPushButton("◀ 上一张")
        previous.clicked.connect(lambda: self.change_image(self.canvas.current_index - 1))
        next_image = QPushButton("下一张 ▶")
        next_image.clicked.connect(lambda: self.change_image(self.canvas.current_index + 1))
        zoom_out = QPushButton("缩小")
        zoom_out.clicked.connect(lambda: self.canvas.zoom_by(1 / 1.2))
        zoom_in = QPushButton("放大")
        zoom_in.clicked.connect(lambda: self.canvas.zoom_by(1.2))
        reset = QPushButton("适应屏幕")
        reset.clicked.connect(self.canvas.reset_view)
        clear = QPushButton("清空本图区域")
        clear.clicked.connect(self.canvas.clear_current)
        for button in (previous, next_image, zoom_out, zoom_in, reset, clear):
            tools.addWidget(button)
        tools.addStretch()
        self.total = muted_label("")
        tools.addWidget(self.total)
        layout.addLayout(tools)
        footer = QHBoxLayout()
        footer.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("确认裁剪并进入拼接预览")
        confirm.setObjectName("primary")
        confirm.clicked.connect(self.confirm_crop)
        footer.addWidget(cancel)
        footer.addWidget(confirm)
        layout.addLayout(footer)
        QShortcut(QKeySequence("Left"), self, activated=lambda: self.change_image(self.canvas.current_index - 1))
        QShortcut(QKeySequence("Right"), self, activated=lambda: self.change_image(self.canvas.current_index + 1))
        QShortcut(QKeySequence("+"), self, activated=lambda: self.canvas.zoom_by(1.2))
        QShortcut(QKeySequence("-"), self, activated=lambda: self.canvas.zoom_by(1 / 1.2))
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self.canvas.reset_view)
        self.refresh_list()
        if self.images:
            self.list.setCurrentRow(0)

    def refresh_list(self) -> None:
        current = self.list.currentRow()
        self.list.blockSignals(True)
        self.list.clear()
        for index, (name, image) in enumerate(zip(self.names, self.images)):
            preview = image.scaled(80, 60, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            count = len(self.canvas.regions[index]) if hasattr(self, "canvas") else 0
            item = QListWidgetItem(QIcon(preview), f"{index + 1}. {name}\n已选 {count} 个区域")
            item.setSizeHint(QSize(210, 78))
            self.list.addItem(item)
        self.list.setCurrentRow(max(0, min(current, self.list.count() - 1)))
        self.list.blockSignals(False)
        count = sum(len(regions) for regions in self.canvas.regions) if hasattr(self, "canvas") else 0
        self.total.setText(f"共 {count} 个裁剪区域")
        self._update_info()

    def change_image(self, index: int) -> None:
        if not 0 <= index < len(self.images):
            return
        self.list.blockSignals(True)
        self.list.setCurrentRow(index)
        self.list.blockSignals(False)
        self.canvas.set_current_index(index)
        self._update_info()

    def _update_info(self) -> None:
        if not self.images:
            self.image_info.setText("没有可读取的图片")
            return
        index = self.canvas.current_index
        image = self.images[index]
        self.image_info.setText(
            f"图片 {index + 1}/{len(self.images)} · {self.names[index]} · {image.width()}×{image.height()} px"
        )

    def confirm_crop(self) -> None:
        self.result_images = self.canvas.cropped_images()
        if not self.result_images:
            QMessageBox.warning(self, "提示", "请至少框选一个裁剪区域")
            return
        self.accept()


def grab_virtual_desktop() -> QPixmap:
    """Capture every Qt screen into one logical-pixel virtual desktop image."""
    screens = QApplication.screens()
    if not screens:
        return QPixmap()
    virtual = screens[0].geometry()
    for screen in screens[1:]:
        virtual = virtual.united(screen.geometry())
    result = QPixmap(virtual.size())
    result.fill(QColor("black"))
    painter = QPainter(result)
    for screen in screens:
        shot = screen.grabWindow(0)
        geometry = screen.geometry()
        target = QRect(geometry.x() - virtual.x(), geometry.y() - virtual.y(),
                       geometry.width(), geometry.height())
        painter.drawPixmap(target, shot)
    painter.end()
    return result


def virtual_desktop_geometry() -> QRect:
    screens = QApplication.screens()
    if not screens:
        return QRect()
    geometry = screens[0].geometry()
    for screen in screens[1:]:
        geometry = geometry.united(screen.geometry())
    return geometry


class ContinuousScreenshotOverlay(QDialog):
    """Native repeated region capture overlay spanning the virtual desktop."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setModal(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.desktop = grab_virtual_desktop()
        self.captures: list[QPixmap] = []
        self.capture_rects: list[QRect] = []
        self.origin: QPoint | None = None
        self.current = QRect()
        self.middle_origin: QPoint | None = None
        geometry = virtual_desktop_geometry()
        if geometry.isValid():
            self.setGeometry(geometry)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.desktop)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 85))
        for index, rect in enumerate(self.capture_rects, start=1):
            painter.drawPixmap(rect, self.desktop, rect)
            painter.setPen(QPen(QColor("#36C275"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)
            painter.setBrush(QColor("#36C275"))
            painter.drawRect(QRect(rect.left(), rect.top(), 28, 24))
            painter.setPen(QColor("white"))
            painter.drawText(QRect(rect.left(), rect.top(), 28, 24), Qt.AlignmentFlag.AlignCenter, str(index))
        if not self.current.isNull():
            painter.drawPixmap(self.current, self.desktop, self.current)
            painter.setPen(QPen(QColor(YELLOW), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.current)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1976D2"))
        painter.drawRoundedRect(QRect(12, 12, 650, 42), 7, 7)
        painter.setPen(QColor("white"))
        total_width = sum(image.width() for image in self.captures)
        max_height = max((image.height() for image in self.captures), default=0)
        text_value = (
            f"已截 {len(self.captures)} 张 · 累计 {total_width}×{max_height}px   "
            "左键框选 | 中键拖动滚屏 | Space暂停 | Enter完成 | Backspace撤销 | Esc取消"
        )
        painter.drawText(QRect(24, 12, 630, 42), Qt.AlignmentFlag.AlignVCenter, text_value)

    def mousePressEvent(self, event) -> None:
        point = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = point
            self.current = QRect(point, point)
            self.update()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.middle_origin = point
            self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mouseMoveEvent(self, event) -> None:
        if self.origin is not None:
            point = event.position().toPoint()
            self.current = QRect(self.origin, point).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.origin is not None:
            rect = self.current.normalized().intersected(self.desktop.rect())
            self.origin = None
            self.current = QRect()
            if rect.width() >= 5 and rect.height() >= 5:
                self.capture_rects.append(rect)
                self.captures.append(self.desktop.copy(rect))
            self.update()
        elif event.button() == Qt.MouseButton.MiddleButton and self.middle_origin is not None:
            delta = event.position().toPoint() - self.middle_origin
            self.middle_origin = None
            self.setCursor(Qt.CursorShape.CrossCursor)
            self._scroll_underlay(delta, event.globalPosition().toPoint())

    def _scroll_underlay(self, delta: QPoint, global_point: QPoint) -> None:
        if abs(delta.y()) < 15 and abs(delta.x()) < 15:
            return
        try:
            import pyautogui
            self.hide()
            QApplication.processEvents()
            if abs(delta.y()) >= 15:
                pyautogui.scroll(-int(delta.y() / 20), x=global_point.x(), y=global_point.y())
            if abs(delta.x()) >= 15 and hasattr(pyautogui, "hscroll"):
                pyautogui.hscroll(-int(delta.x() / 20), x=global_point.x(), y=global_point.y())
            time.sleep(.15)
            self.desktop = grab_virtual_desktop()
            self.show()
            self.raise_()
            self.activateWindow()
            self.update()
        except Exception:
            self.show()
            self.raise_()

    def keyPressEvent(self, event) -> None:
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            if self.captures:
                self.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if event.key() in {Qt.Key.Key_Backspace, Qt.Key.Key_Delete}:
            if self.captures:
                self.captures.pop()
                self.capture_rects.pop()
                self.update()
            return
        if event.key() == Qt.Key.Key_Space:
            self.pause_capture()
            return
        super().keyPressEvent(event)

    def pause_capture(self) -> None:
        self.hide()
        dialog = QDialog(None)
        dialog.setWindowTitle("截图已暂停")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("截图覆盖层已隐藏，现在可以操作或滚动底层窗口。"))
        resume = QPushButton("继续截图（Space）")
        resume.setObjectName("primary")
        resume.clicked.connect(dialog.accept)
        layout.addWidget(resume)
        shortcut = QShortcut(QKeySequence("Space"), dialog)
        shortcut.activated.connect(dialog.accept)
        dialog.exec()
        time.sleep(.12)
        self.desktop = grab_virtual_desktop()
        self.show()
        self.raise_()
        self.activateWindow()
        self.update()


class ScreenshotSessionDialog(QDialog):
    """Review the regions collected by the continuous screenshot overlay."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("多区域截图")
        self.resize(760, 560)
        self.captures: list[QPixmap] = []
        self.output_path = ""
        layout = QVBoxLayout(self)
        layout.addWidget(section_label("截图列表"))
        layout.addWidget(muted_label("可跨显示器多次框选；确认后进入拼接预览。"))
        self.list = QListWidget()
        self.list.setIconSize(QSize(150, 100))
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setSpacing(8)
        layout.addWidget(self.list, 1)
        footer = QHBoxLayout()
        footer.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        finish = QPushButton("进入拼接预览")
        finish.setObjectName("primary")
        finish.clicked.connect(self.finish)
        footer.addWidget(cancel)
        footer.addWidget(finish)
        layout.addLayout(footer)

    def load_captures(self, captures: list[QPixmap]) -> None:
        self.captures = [QPixmap(image) for image in captures if not image.isNull()]
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        for index, pixmap in enumerate(self.captures, start=1):
            preview = pixmap.scaled(150, 100, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
            item = QListWidgetItem(QIcon(preview), f"截图 {index}\n{pixmap.width()}×{pixmap.height()}")
            item.setSizeHint(QSize(175, 135))
            self.list.addItem(item)

    def finish(self) -> None:
        if not self.captures:
            QMessageBox.warning(self, "提示", "请至少完成一次截图")
            return
        self.accept()


class TableFontDelegate(QStyledItemDelegate):
    """Keep the native cell editor visually identical to the displayed item."""

    def createEditor(self, parent, option, index):  # noqa: N802
        editor = super().createEditor(parent, option, index)
        if editor is not None:
            table = self.parent()
            configured_size = table.property("classifierFontSize") if table is not None else None
            font_size = int(configured_size or option.font.pointSize() or 11)
            editor_font = QFont(option.font)
            editor_font.setPointSize(font_size)
            editor.setFont(editor_font)
            editor.setStyleSheet(
                "padding: 0 5px; min-height: 0; border: 2px solid #F4C400; "
                "border-radius: 2px; background: #FFFFFF; "
                f"font-size: {font_size}pt;"
            )
        return editor


class DownwardComboBox(QComboBox):
    """Combo box whose popup always starts below the current cell."""

    groupShortcutPressed = Signal(str)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # +/- should trigger group shortcuts, not scroll through ABCD options.
        modifiers = event.modifiers()
        blocked = (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        )
        if not (modifiers & blocked) and not event.isAutoRepeat():
            nk = int(event.nativeVirtualKey())
            ns = int(event.nativeScanCode())
            key = event.key()
            text = event.text()
            if key in {Qt.Key.Key_Plus, Qt.Key.Key_Equal} or text in {"+", "＋", "="} or nk in {0x6B, 0xBB} or ns == 0x4E:
                self.groupShortcutPressed.emit("D")
                event.accept()
                return
            if key in {Qt.Key.Key_Minus, Qt.Key.Key_Underscore} or text in {"-", "－", "_"} or nk in {0x6D, 0xBD} or ns == 0x4A:
                self.groupShortcutPressed.emit("C")
                event.accept()
                return
        super().keyPressEvent(event)

    def showPopup(self) -> None:  # noqa: N802
        row_height = max(self.view().sizeHintForRow(0), self.fontMetrics().height() + 10)
        self.view().setMinimumHeight(row_height * self.count() + 2)
        self.view().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        super().showPopup()
        QTimer.singleShot(0, self._position_popup_below)

    def _position_popup_below(self) -> None:
        popup = self.view().window()
        popup.move(self.mapToGlobal(QPoint(0, self.height())))
        popup.resize(max(self.width(), popup.width()), popup.height())
        self.view().scrollToTop()


class GroupCellButton(QComboBox):
    """Native combo-style group cell whose arrow is the only popup trigger."""

    groupChanged = Signal(int, str)  # row_index, group
    rowClicked = Signal(int, object)  # row_index, keyboard modifiers

    def __init__(self, group: str, row_index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = row_index
        self.setObjectName("groupCell")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.addItems(list("ABCD"))
        self.setCurrentText(group if group in "ABCD" else "B")
        self.textActivated.connect(self._on_group_picked)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.rowClicked.emit(self._row, event.modifiers())
            # Keep the value area passive.  Only the 24 px drop-down section
            # behaves like a combo-box button.
            if event.position().x() < self.width() - 24:
                event.accept()
                return
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        # Scrolling the table must not accidentally change the group value.
        event.ignore()

    def showPopup(self) -> None:  # noqa: N802
        row_height = 24
        for row in range(self.count()):
            self.model().setData(
                self.model().index(row, 0),
                QSize(self.width(), row_height),
                Qt.ItemDataRole.SizeHintRole,
            )
        actual_row_height = max(row_height, self.view().sizeHintForRow(0))
        self.view().setFixedHeight(actual_row_height * self.count() + 2)
        self.view().setMinimumWidth(self.width())
        self.view().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        super().showPopup()
        QTimer.singleShot(0, self._position_popup_below)

    def _position_popup_below(self) -> None:
        popup = self.view().window()
        # The popup frame has its own margins.  Fixing its total height to the
        # raw item height clips rows, so constrain only the width and let the
        # popup layout include its frame around the four fixed-height items.
        popup.setMinimumHeight(0)
        popup.setMaximumHeight(16777215)
        popup.setFixedWidth(self.width())
        if popup.layout() is not None:
            popup.layout().activate()
        popup.adjustSize()
        popup.move(self.mapToGlobal(QPoint(0, self.height())))
        current = self.model().index(self.currentIndex(), 0)
        self.view().setCurrentIndex(current)
        selection = self.view().selectionModel()
        if selection is not None:
            selection.select(
                current,
                QItemSelectionModel.SelectionFlag.ClearAndSelect,
            )
        self.view().scrollTo(current)
        self.view().setFocus(Qt.FocusReason.PopupFocusReason)

    def _on_group_picked(self, group: str) -> None:
        if group in "ABCD":
            self.groupChanged.emit(self._row, group)


class ClassifierTable(QTableWidget):
    """Classification table that delegates native drag reordering to its data model."""

    rowsReordered = Signal(list, int)
    moveRequested = Signal(int)
    selectionMoveRequested = Signal(int)
    groupRequested = Signal(str)

    def __init__(self, rows: int, columns: int, parent: QWidget | None = None) -> None:
        super().__init__(rows, columns, parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    @staticmethod
    def _classification_key(event) -> tuple[str, Any] | None:
        modifiers = event.modifiers()
        key = event.key()
        if (
            modifiers == Qt.KeyboardModifier.ControlModifier
            and key in {Qt.Key.Key_Up, Qt.Key.Key_Down}
        ):
            return "cursor", -1 if key == Qt.Key.Key_Up else 1
        blocked = (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
            | Qt.KeyboardModifier.ShiftModifier
        )
        if modifiers & blocked:
            return None
        text_value = event.text()
        nk = int(event.nativeVirtualKey())
        ns = int(event.nativeScanCode())
        if key == Qt.Key.Key_Up:
            return "move", -1
        if key == Qt.Key.Key_Down:
            return "move", 1
        if key in {Qt.Key.Key_Plus, Qt.Key.Key_Equal} or text_value in {"+", "＋", "="} or nk in {0x6B, 0xBB} or ns == 0x4E:
            return "group", "D"
        if key in {Qt.Key.Key_Minus, Qt.Key.Key_Underscore} or text_value in {"-", "－", "_"} or nk in {0x6D, 0xBD} or ns == 0x4A:
            return "group", "C"
        return None

    def keyPressEvent(self, event) -> None:  # noqa: N802
        action = self._classification_key(event)
        if action:
            if event.isAutoRepeat():
                event.accept()
                return
            kind, value = action
            if kind == "move":
                self.moveRequested.emit(int(value))
            elif kind == "cursor":
                self.selectionMoveRequested.emit(int(value))
            else:
                self.groupRequested.emit(str(value))
            event.accept()
            return
        super().keyPressEvent(event)

    def dropEvent(self, event) -> None:
        selected = sorted({index.row() for index in self.selectionModel().selectedRows()})
        if not selected:
            event.ignore()
            return
        position = event.position().toPoint()
        target = self.rowAt(position.y())
        if target < 0:
            target = self.rowCount()
        else:
            rect = self.visualItemRect(self.item(target, 0))
            if position.y() > rect.center().y():
                target += 1
        self.rowsReordered.emit(selected, target)
        event.acceptProposedAction()


class ClassifierHistoryDialog(QDialog):
    """Browse editable classification-table snapshots without mixing OCR history."""

    def __init__(self, repository: Repository, restore_callback, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.restore_callback = restore_callback
        self.items: list[dict[str, Any]] = []
        self.setWindowTitle("分类表历史")
        self.resize(760, 480)
        layout = QVBoxLayout(self)
        layout.addWidget(section_label("已保存的分类表"))
        layout.addWidget(muted_label("恢复后可继续修改名称、分组和分类，再导出 Excel。", True))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["保存时间", "书名", "页码", "条目数"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.doubleClicked.connect(self.restore_selected)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh)
        delete = QPushButton("删除")
        delete.clicked.connect(self.delete_selected)
        clear = QPushButton("清空全部")
        clear.clicked.connect(self.clear_all)
        restore = QPushButton("恢复到分类表")
        restore.setObjectName("primary")
        restore.clicked.connect(self.restore_selected)
        close = QPushButton("关闭")
        close.clicked.connect(self.reject)
        buttons.addWidget(refresh)
        buttons.addWidget(delete)
        buttons.addWidget(clear)
        buttons.addStretch()
        buttons.addWidget(restore)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self) -> None:
        self.repository.reload()
        self.items = [
            item for item in (self.repository.get("classifier_history", []) or [])
            if isinstance(item, dict) and isinstance(item.get("snapshot"), dict)
        ]
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            values = (
                item.get("timestamp", ""), item.get("book_name", ""),
                item.get("page_no", ""), item.get("row_count", 0),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, cell)

    def _selected_item(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        return self.items[row] if 0 <= row < len(self.items) else None

    def restore_selected(self, *_args) -> None:
        item = self._selected_item()
        if item is None:
            QMessageBox.information(self, "提示", "请先选择一条分类表历史记录")
            return
        if QMessageBox.question(
            self, "恢复分类表",
            "恢复会替换当前分类表中的内容，是否继续？",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.restore_callback(item)
        self.accept()

    def delete_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            QMessageBox.information(self, "提示", "请先选择一条分类表历史记录")
            return
        if QMessageBox.question(
            self, "删除分类表历史", "确定删除选中的分类表历史记录吗？",
        ) != QMessageBox.StandardButton.Yes:
            return
        target_id = str(item.get("id", ""))
        history = list(self.repository.get("classifier_history", []) or [])
        if target_id:
            history = [entry for entry in history if str(entry.get("id", "")) != target_id]
        else:
            history = [entry for entry in history if entry is not item]
        self.repository.set("classifier_history", history)
        self.refresh()

    def clear_all(self) -> None:
        history = list(self.repository.get("classifier_history", []) or [])
        if not history:
            QMessageBox.information(self, "提示", "分类表历史记录已经为空")
            return
        if QMessageBox.question(
            self, "确认清空分类表历史",
            f"确定清空全部 {len(history)} 条分类表历史记录吗？",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.repository.set("classifier_history", [])
        self.refresh()


class OCRPage(QWidget):
    statusChanged = Signal(str, str)
    dataChanged = Signal()

    def __init__(self, repository: Repository) -> None:
        super().__init__()
        self.repository = repository
        self.thread_pool = QThreadPool.globalInstance()
        self.paths: list[str] = []
        self.results: list[dict[str, Any]] = []
        self.rows: list[dict[str, Any]] = []
        self.verification_path = ""
        self._selection_anchor_row: int | None = None
        self.undo_stack: list[dict[str, Any]] = []
        self.redo_stack: list[dict[str, Any]] = []
        self.parsed_snapshot: dict[str, Any] = {}
        self.lasso_count = 0
        self.lasso_categories: list[str] = []
        self.lasso_undo_history: list[dict[str, Any]] = []
        self.mode = "accurate"
        self.category_colors = dict(self.repository.get("qt_category_colors", {}) or {})
        self.notice_timer = QTimer(self)
        self.notice_timer.setSingleShot(True)
        self.notice_timer.timeout.connect(self._fade_top_notice)
        self._build()
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)
        self._refresh_key_states()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if (
            hasattr(self, "verification_viewer")
            and watched is self.verification_viewer.label
            and event.type() == QEvent.Type.MouseButtonDblClick
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._verification_image_double_clicked(event.position().toPoint())
            event.accept()
            return True
        if (
            event.type() == QEvent.Type.KeyPress
            and hasattr(self, "result_stack")
            and self.result_stack.currentIndex() == 1
            and self.isVisible()
            and self._classifier_table_has_focus()
        ):
            if not self._classifier_cell_editor_has_focus():
                action = ClassifierTable._classification_key(event)
                native_key = int(event.nativeVirtualKey())
                native_scan = int(event.nativeScanCode())
                group = None
                if action and action[0] == "group":
                    group = str(action[1])
                elif native_key in {0x6B, 0xBB} or native_scan == 0x4E:
                    # Windows VK_ADD / VK_OEM_PLUS / keypad-add scan code.
                    group = "D"
                elif native_key in {0x6D, 0xBD} or native_scan == 0x4A:
                    # Windows VK_SUBTRACT / VK_OEM_MINUS / keypad-minus scan code.
                    group = "C"
                if group is not None:
                    if not event.isAutoRepeat():
                        self.set_selected_group(group)
                        self._show_top_notice(
                            "done", f"快捷键已将选中记录修改为 {group} 组", 1800
                        )
                    event.accept()
                    return True
        return super().eventFilter(watched, event)

    def _classifier_table_has_focus(self) -> bool:
        """Return whether keyboard input currently belongs to the classifier table."""
        if not hasattr(self, "table"):
            return False
        focus = QApplication.focusWidget()
        return bool(
            focus is not None
            and (focus is self.table or self.table.isAncestorOf(focus))
        )

    def _classifier_cell_editor_has_focus(self) -> bool:
        """Detect a real in-cell editor instead of trusting the table's transient state."""
        if (
            not hasattr(self, "table")
            or self.table.state() != QAbstractItemView.State.EditingState
        ):
            return False
        focus = QApplication.focusWidget()
        if focus is None or focus in {self.table, self.table.viewport()}:
            return False
        if isinstance(focus, GroupCellButton):
            return False
        return self.table.isAncestorOf(focus)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        self.outer_layout = outer
        outer.setContentsMargins(16, 12, 16, 14)
        outer.setSpacing(10)

        step_card = card()
        self.step_card = step_card
        step_layout = QHBoxLayout(step_card)
        self.step_layout = step_layout
        step_layout.setContentsMargins(12, 7, 12, 7)
        step_layout.setSpacing(8)
        self.step_group = QButtonGroup(self)
        self.step_group.setExclusive(True)
        self.step_buttons: list[QPushButton] = []
        self.step_widths = (210, 170, 180, 180)
        self.step_arrows: list[QLabel] = []
        for index, (title, subtitle) in enumerate([
            ("交互绘图", "标注与区域选择"),
            ("分类表格", "生成结构化数据"),
            ("文本报告", "生成识别报告"),
            ("Excel 预览", "查看分组导出效果"),
        ], start=1):
            button = StepButton(index, title, subtitle)
            button.setFixedWidth(self.step_widths[index - 1])
            button.setProperty("pageIndex", index - 1)
            button.clicked.connect(lambda _checked=False, i=index - 1: self._switch_step(i))
            self.step_group.addButton(button)
            self.step_buttons.append(button)
            step_layout.addWidget(button)
            if index < 4:
                arrow = QLabel("›")
                arrow.setFixedWidth(12)
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow.setStyleSheet("font-size:18px;font-weight:300;color:#B8BDC4;")
                step_layout.addWidget(arrow)
                self.step_arrows.append(arrow)
        step_layout.addStretch(1)
        self.step_buttons[0].setChecked(True)
        outer.addWidget(step_card)

        self.top_notice_bar = QFrame()
        self.top_notice_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        notice_layout = QHBoxLayout(self.top_notice_bar)
        notice_layout.setContentsMargins(0, 0, 8, 0)
        notice_layout.setSpacing(8)
        self.top_notice = QLabel("")
        self.top_notice.setWordWrap(True)
        self.top_notice.setMinimumHeight(38)
        self.top_notice.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        notice_layout.addWidget(self.top_notice, 1)
        self.notice_undo_button = QPushButton("撤销本次圈选")
        self.notice_undo_button.setMinimumHeight(28)
        self.notice_undo_button.clicked.connect(self.undo_last_lasso)
        self.notice_undo_button.hide()
        notice_layout.addWidget(self.notice_undo_button)
        self.top_notice_bar.hide()
        self.notice_opacity = QGraphicsOpacityEffect(self.top_notice_bar)
        self.notice_opacity.setOpacity(1.0)
        self.top_notice_bar.setGraphicsEffect(self.notice_opacity)
        self.notice_animation = QPropertyAnimation(self.notice_opacity, b"opacity", self)
        self.notice_animation.setDuration(320)
        self.notice_animation.finished.connect(self.top_notice_bar.hide)

        workspace = QHBoxLayout()
        self.workspace_layout = workspace
        workspace.setSpacing(10)
        outer.addLayout(workspace, 1)

        params = card()
        self.params_card = params
        params.setProperty("panelRole", "parameters")
        params.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        add_shadow(params, blur=24, opacity=26)
        params.setFixedWidth(210)
        params_layout = QVBoxLayout(params)
        self.params_layout = params_layout
        params_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        self.params_scroll = scroll
        scroll.setObjectName("paramsScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setStyleSheet("background:transparent;")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_content = QWidget()
        scroll_content.setObjectName("paramsContent")
        scroll_content.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        scroll_layout = QVBoxLayout(scroll_content)
        self.params_content_layout = scroll_layout
        scroll_layout.setContentsMargins(14, 14, 14, 10)
        scroll_layout.setSpacing(9)

        scroll_layout.addWidget(section_label("1. 导入图片"))
        self.drop_zone = DropZone()
        self.drop_zone.clicked.connect(self.choose_files)
        self.drop_zone.filesDropped.connect(self.import_files)
        scroll_layout.addWidget(self.drop_zone)
        support = QHBoxLayout()
        support.addWidget(muted_label("支持 JPG / PNG / BMP / TIFF"))
        clear = QPushButton("清空")
        clear.setStyleSheet("border:0;background:transparent;color:#92979E;padding:0;min-height:24px;")
        clear.clicked.connect(self.clear_files)
        support.addWidget(clear)
        scroll_layout.addLayout(support)
        self.hint = muted_label("请选择图片后开始识别", True)
        self.hint.setStyleSheet("background:#FFF9E8;color:#8A6A00;padding:8px;border-radius:7px;")
        scroll_layout.addWidget(self.hint)

        scroll_layout.addWidget(section_label("2. 识别质量"))
        mode_row = QHBoxLayout()
        mode_row.setSpacing(5)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons: dict[str, QPushButton] = {}
        for mode, name in MODE_NAMES.items():
            button = QPushButton(name)
            button.setObjectName("recognitionMode")
            button.setProperty("compactParam", "true")
            button.setCheckable(True)
            button.setMinimumWidth(0)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            button.clicked.connect(lambda _checked=False, value=mode: self.select_mode(value))
            self.mode_group.addButton(button)
            self.mode_buttons[mode] = button
            mode_row.addWidget(button, 1)
        self.mode_buttons["accurate"].setChecked(True)
        scroll_layout.addLayout(mode_row)

        scroll_layout.addWidget(section_label("3. 图片处理"))
        process_row = QHBoxLayout()
        self.process_buttons: list[QPushButton] = []
        for title, handler in [
            ("拼接", self.merge_images),
            ("截图", self.capture_screen),
            ("裁剪", self.crop_image),
        ]:
            button = QPushButton(title)
            button.setProperty("compactParam", "true")
            button.setMinimumWidth(0)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            button.clicked.connect(handler)
            process_row.addWidget(button, 1)
            self.process_buttons.append(button)
        scroll_layout.addLayout(process_row)

        scroll_layout.addWidget(section_label("4. 坐标模式"))
        self.coordinate_layout = QVBoxLayout()
        self.coordinate_layout.setContentsMargins(0, 0, 0, 0)
        self.coordinate_layout.setSpacing(3)
        self.line_radio = QRadioButton("直线模式")
        self.lasso_radio = QRadioButton("圈选模式")
        self.line_radio.setChecked(True)
        self.line_radio.toggled.connect(lambda checked: self.plot.set_lasso_mode(not checked) if hasattr(self, "plot") else None)
        self.lasso_radio.toggled.connect(self._lasso_mode_changed)
        self.coordinate_layout.addWidget(self.line_radio)
        self.coordinate_layout.addWidget(self.lasso_radio)
        self.clear_classification_button = QPushButton("清理直线和圈选分类")
        self.clear_classification_button.setFixedHeight(30)
        self.clear_classification_button.clicked.connect(
            self.clear_line_and_lasso_classification
        )
        self.coordinate_layout.addWidget(self.clear_classification_button)
        scroll_layout.addLayout(self.coordinate_layout)

        scroll_layout.addWidget(section_label("5. 书籍信息"))
        form = QFormLayout()
        self.book_name = QLineEdit(str(self.repository.get("book_name", "")))
        self.book_name.setProperty("compactParamInput", "true")
        self.book_name.setMinimumWidth(0)
        self.book_name.editingFinished.connect(
            lambda: self.repository.set("book_name", self.book_name.text().strip())
        )
        self.book_page = QSpinBox()
        self.book_page.setProperty("compactParamInput", "true")
        self.book_page.setMinimumWidth(0)
        self.book_page.setRange(1, 999999)
        self.book_page.setValue(int(self.repository.get("book_page", 1) or 1))
        self.book_page.valueChanged.connect(
            lambda page: self.repository.set("book_page", int(page))
        )
        form.addRow("书名", self.book_name)
        form.addRow("当前页", self.book_page)
        scroll_layout.addLayout(form)
        scroll_layout.addStretch(1)
        scroll.setWidget(scroll_content)
        params_layout.addWidget(scroll, 1)
        self.start_button = QPushButton("开始识别")
        self.start_button.setObjectName("primary")
        self.start_button.setFixedHeight(48)
        self.start_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.start_button.setStyleSheet(
            f"QPushButton#primary {{background:{YELLOW};border:0;border-radius:0;"
            "border-bottom-left-radius:7px;border-bottom-right-radius:7px;"
            "font-weight:700;padding:0;}"
            "QPushButton#primary:hover {background:#F2B900;border:0;}"
            "QPushButton#primary:pressed {background:#E8AE00;border:0;}"
        )
        self.start_button.clicked.connect(self.start_ocr)
        params_layout.addWidget(self.start_button)
        params_layout.setContentsMargins(1, 1, 1, 1)
        params_layout.setSpacing(0)
        workspace.addWidget(params)

        result_card = card()
        self.result_card = result_card
        result_layout = QVBoxLayout(result_card)
        self.result_layout = result_layout
        result_layout.setContentsMargins(10, 10, 10, 10)
        self.result_stack = QStackedWidget()
        self.plot = PlotCanvas()
        self.plot.thresholdsChanged.connect(self.classify_thresholds)
        self.plot.pointsLassoed.connect(self.classify_lasso)
        self.plot.statusRequested.connect(self._plot_status_requested)
        self.result_stack.addWidget(self.plot)
        self.table_page, self.table = self._build_table_page()
        self.result_stack.addWidget(self.table_page)
        self.report_page, self.report = self._build_report_page()
        self.result_stack.addWidget(self.report_page)
        self.excel_preview_page, self.excel_preview_table = self._build_excel_preview_page()
        self.result_stack.addWidget(self.excel_preview_page)
        result_layout.addWidget(self.result_stack)
        workspace.addWidget(result_card, 1)
        self.page_undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self.page_undo_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.page_undo_shortcut.activated.connect(self.undo)
        self.cancel_lasso_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.cancel_lasso_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.cancel_lasso_shortcut.activated.connect(self.cancel_lasso_selection)
        self.apply_layout_scale(1.0, 1.0, 1.0)

    def apply_layout_scale(self, x_scale: float, y_scale: float,
                           ui_scale: float) -> None:
        """Keep the OCR workspace proportional to the 1050 x 730 design."""
        self.outer_layout.setContentsMargins(
            round(16 * x_scale), round(12 * y_scale),
            round(16 * x_scale), round(14 * y_scale),
        )
        self.outer_layout.setSpacing(max(8, round(10 * ui_scale)))
        self.step_layout.setContentsMargins(
            round(12 * x_scale), round(7 * y_scale),
            round(12 * x_scale), round(7 * y_scale),
        )
        self.step_layout.setSpacing(max(6, round(8 * ui_scale)))
        step_button_height = max(50, round(56 * y_scale))
        step_vertical_margin = round(7 * y_scale)
        self.step_card.setFixedHeight(
            step_button_height + step_vertical_margin * 2 + 2
        )
        for width, button in zip(self.step_widths, self.step_buttons):
            button.setFixedWidth(round(width * x_scale))
            if isinstance(button, StepButton):
                button.apply_scale(x_scale, y_scale, ui_scale)
        for arrow in self.step_arrows:
            arrow.setFixedWidth(max(10, round(12 * x_scale)))
            arrow.setStyleSheet(
                f"font-size:{max(16, round(18 * ui_scale))}px;"
                "font-weight:300;color:#B8BDC4;"
            )
        self.workspace_layout.setSpacing(max(8, round(10 * x_scale)))
        self.params_card.setFixedWidth(round(210 * x_scale))
        self.params_content_layout.setContentsMargins(
            round(14 * x_scale), round(12 * y_scale),
            round(14 * x_scale), round(8 * y_scale),
        )
        self.params_content_layout.setSpacing(max(6, round(7 * ui_scale)))
        self.coordinate_layout.setSpacing(max(2, round(3 * ui_scale)))
        compact_button_height = max(27, round(28 * y_scale))
        compact_padding = max(6, round(8 * x_scale))
        for button in self.mode_buttons.values():
            button.setStyleSheet(
                f"QPushButton#recognitionMode {{min-height:0;"
                f"max-height:{compact_button_height}px;padding:0 {compact_padding}px;"
                "background:#F6F7F9;border:1px solid #ECEEF1;border-radius:6px;}"
                f"QPushButton#recognitionMode:checked {{background:{YELLOW};"
                f"border-color:{YELLOW};color:{INK};font-weight:700;}}"
                "QPushButton#recognitionMode:hover {background:#FFF8DF;"
                "border-color:#F4D66B;}"
            )
            button.setFixedHeight(compact_button_height)
        for button in self.process_buttons:
            button.setStyleSheet(
                f"min-height:0;max-height:{compact_button_height}px;"
                f"padding:0 {compact_padding}px;background:#F6F7F9;"
                "border:1px solid #ECEEF1;border-radius:6px;"
            )
            button.setFixedHeight(compact_button_height)
        compact_input_height = max(29, round(30 * y_scale))
        for field in (self.book_name, self.book_page):
            field.setStyleSheet(
                f"min-height:0;max-height:{compact_input_height}px;"
                f"padding:0 {max(6, round(8 * x_scale))}px;"
            )
            field.setFixedHeight(compact_input_height)
        clear_height = max(27, round(28 * y_scale))
        self.clear_classification_button.setStyleSheet(
            f"min-height:0;max-height:{clear_height}px;"
            f"padding:0 {max(7, round(9 * x_scale))}px;"
            f"font-size:{max(10, round(11 * ui_scale))}px;"
            "background:#F8F9FA;border:1px solid #E9EBEE;border-radius:6px;"
        )
        self.clear_classification_button.setFixedHeight(clear_height)
        self.drop_zone.setMinimumHeight(max(104, round(112 * y_scale)))
        self.start_button.setFixedHeight(max(40, round(48 * y_scale)))
        params_radius = max(10, round(12 * ui_scale))
        self.start_button.setStyleSheet(
            f"QPushButton#primary {{background:{YELLOW};border:0;border-radius:0;"
            f"border-bottom-left-radius:{params_radius - 1}px;"
            f"border-bottom-right-radius:{params_radius - 1}px;"
            "font-weight:700;padding:0;}"
            "QPushButton#primary:hover {background:#F2B900;border:0;}"
            "QPushButton#primary:pressed {background:#E8AE00;border:0;}"
        )
        self.result_layout.setContentsMargins(
            round(10 * x_scale), round(10 * y_scale),
            round(10 * x_scale), round(10 * y_scale),
        )

    def _build_table_page(self) -> tuple[QWidget, QTableWidget]:
        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        toolbar.addWidget(section_label("分类结果"))
        font_config = self.repository.get("font_config", {}) or {}
        verify = QPushButton("原图核对")
        verify.clicked.connect(self.open_verification_dialog)
        advanced = QPushButton("高级分类操作")
        advanced.setMenu(self._build_advanced_menu())
        layout.addLayout(toolbar)
        undo = QPushButton("撤销")
        undo.clicked.connect(self.undo)
        add = QPushButton("添加")
        add.clicked.connect(self.add_row)
        delete = QPushButton("删除")
        delete.clicked.connect(self.delete_rows)
        up = QPushButton("上移")
        up.clicked.connect(lambda: self.move_row(-1))
        down = QPushButton("下移")
        down.clicked.connect(lambda: self.move_row(1))
        merge = QPushButton("合并")
        merge.clicked.connect(self.merge_rows)
        split_a = QPushButton("拆分A组")
        split_a.clicked.connect(self.split_group_a)
        cleanup = QPushButton("批量整理")
        cleanup.clicked.connect(self.batch_cleanup)
        classifier_history = QPushButton("分类表历史")
        classifier_history.clicked.connect(self.show_classifier_history)
        toolbar.addWidget(undo)
        toolbar.addWidget(add)
        toolbar.addWidget(delete)
        toolbar.addWidget(up)
        toolbar.addWidget(down)
        toolbar.addWidget(merge)
        toolbar.addWidget(split_a)
        toolbar.addWidget(cleanup)
        toolbar.addWidget(classifier_history)
        toolbar.addStretch()
        toolbar.addWidget(verify)
        toolbar.addWidget(advanced)
        table = ClassifierTable(0, 7)
        self.table_font_delegate = TableFontDelegate(table)
        table.setItemDelegate(self.table_font_delegate)
        table.setHorizontalHeaderLabels(["名称", "Y", "X", "高度", "置信度", "分组", "分类"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (4, 5, 6):
            table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        for column in (1, 2, 3):
            table.setColumnHidden(column, True)
        initial_size = int(font_config.get("font_size", 11) or 11)
        table.setProperty("classifierFontSize", initial_size)
        table.setFont(QFont("Microsoft YaHei UI", initial_size, QFont.Weight.Bold))
        table.setStyleSheet(self._classifier_table_font_style(initial_size))
        header_font = table.horizontalHeader().font()
        header_font.setPointSize(max(8, initial_size - 1))
        header_font.setBold(True)
        table.horizontalHeader().setFont(header_font)
        table.verticalHeader().setDefaultSectionSize(max(initial_size * 2 + 12, 34))
        table.itemChanged.connect(self._table_changed)
        table.clicked.connect(self._activate_group_cell_for_record)
        table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self.show_table_context_menu)
        table.rowsReordered.connect(self.reorder_rows)
        table.moveRequested.connect(self.move_row)
        table.selectionMoveRequested.connect(self.move_selection_cursor)
        table.groupRequested.connect(self.set_selected_group)
        table.itemSelectionChanged.connect(self._sync_verification_from_table)
        for sequence, handler in [
            ("Insert", self.add_row), ("Delete", self.delete_rows),
            ("Ctrl+Y", self.redo),
            ("Alt+Up", lambda: self.move_row(-1)), ("Alt+Down", lambda: self.move_row(1)),
            ("Space", self.toggle_mark_selected),
        ]:
            shortcut = QShortcut(QKeySequence(sequence), table)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)
        self.keypad_group_shortcuts = []
        for sequence, group in (("Num++", "D"), ("Num+-", "C")):
            shortcut = QShortcut(QKeySequence(sequence), table)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(
                lambda value=group: self._activate_group_shortcut(value)
            )
            self.keypad_group_shortcuts.append(shortcut)
        layout.addWidget(table, 1)
        return page, table

    def open_verification_dialog(self) -> None:
        if not hasattr(self, "verification_dialog"):
            dialog = QDialog(self)
            dialog.setWindowTitle("原图核对")
            dialog.resize(920, 680)
            dialog.setModal(False)
            self.verification_dialog = dialog
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(8)

            header = QHBoxLayout()
            self.verification_previous = QPushButton("上一张")
            self.verification_previous.clicked.connect(
                lambda: self._shift_verification_image(-1)
            )
            self.verification_position = QLabel("暂无原图")
            self.verification_position.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.verification_next = QPushButton("下一张")
            self.verification_next.clicked.connect(
                lambda: self._shift_verification_image(1)
            )
            header.addWidget(self.verification_previous)
            header.addWidget(self.verification_position, 1)
            header.addWidget(self.verification_next)
            layout.addLayout(header)

            self.verification_viewer = PixmapScrollViewer()
            self.verification_viewer.setMinimumSize(600, 420)
            layout.addWidget(self.verification_viewer, 1)

            tools = QHBoxLayout()
            self.verification_source_name = muted_label("尚未选择表格内容")
            self.verification_source_name.setWordWrap(True)
            tools.addWidget(self.verification_source_name, 1)
            for text_value, handler in (
                ("－", lambda: self.verification_viewer.zoom_by(1 / 1.2)),
                ("＋", lambda: self.verification_viewer.zoom_by(1.2)),
                ("100%", self.verification_viewer.show_actual),
                ("适应窗口", self.verification_viewer.show_fit),
            ):
                button = QPushButton(text_value)
                button.clicked.connect(handler)
                tools.addWidget(button)
            layout.addLayout(tools)

            self.verification_line = QLabel("当前行：—")
            self.verification_line.setWordWrap(True)
            self.verification_line.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.verification_line.setStyleSheet(
                "background:#FFFFFF;border:1px solid #E5E7EB;border-radius:6px;"
                "padding:7px;color:#374151;"
            )
            layout.addWidget(self.verification_line)
            footer = QHBoxLayout()
            footer.addStretch()
            close = QPushButton("关闭")
            close.clicked.connect(dialog.close)
            footer.addWidget(close)
            layout.addLayout(footer)

        self.verification_dialog.show()
        self.verification_dialog.raise_()
        self.verification_dialog.activateWindow()
        if self.rows and not 0 <= self.table.currentRow() < len(self.rows):
            self.table.selectRow(0)
            self.table.setCurrentCell(0, 0)
        self._sync_verification_from_table()
        if not self.rows:
            paths = self._verification_paths()
            if paths:
                self._show_verification_path(paths[0])

    def _verification_paths(self) -> list[str]:
        candidates = [str(result.get("path", "") or "") for result in self.results]
        candidates.extend(self.paths)
        paths: list[str] = []
        seen: set[str] = set()
        for path in candidates:
            if not path or not Path(path).is_file():
                continue
            key = os.path.normcase(os.path.abspath(path))
            if key not in seen:
                seen.add(key)
                paths.append(path)
        return paths

    def _show_verification_path(self, path: str, row: dict[str, Any] | None = None) -> None:
        paths = self._verification_paths()
        if not path or not Path(path).is_file():
            self.verification_path = ""
            self.verification_viewer.set_pixmap(QPixmap())
            self.verification_position.setText("无可用原图")
            self.verification_source_name.setText("该内容没有关联的本地图片")
            self.verification_line.setText(
                f"当前行：{row.get('label', '—')}" if row is not None else "当前行：—"
            )
            self.verification_previous.setEnabled(False)
            self.verification_next.setEnabled(False)
            return
        normalized = os.path.normcase(os.path.abspath(path))
        index = next(
            (i for i, item in enumerate(paths)
             if os.path.normcase(os.path.abspath(item)) == normalized),
            0,
        )
        current_normalized = (
            os.path.normcase(os.path.abspath(self.verification_path))
            if self.verification_path else ""
        )
        if current_normalized != normalized:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            image = reader.read()
            pixmap = QPixmap.fromImage(image) if not image.isNull() else QPixmap()
            self.verification_viewer.set_pixmap(pixmap)
            self.verification_path = path if not pixmap.isNull() else ""
        rect = row.get("_source_rect") if row is not None else None
        if not isinstance(rect, QRect) and row is not None:
            rect = self._estimated_text_rect(row)
        self.verification_viewer.set_highlight(rect if isinstance(rect, QRect) else None)
        self.verification_position.setText(f"第 {index + 1}/{len(paths)} 张")
        self.verification_source_name.setText(Path(path).name)
        self.verification_line.setText(
            f"当前行：{row.get('label', '—')}" if row is not None else "当前行：—"
        )
        enabled = len(paths) > 1
        self.verification_previous.setEnabled(enabled)
        self.verification_next.setEnabled(enabled)

    def _sync_verification_from_table(self) -> None:
        if (
            not hasattr(self, "verification_dialog")
            or not self.verification_dialog.isVisible()
        ):
            return
        row_index = self.table.currentRow()
        if not 0 <= row_index < len(self.rows):
            return
        row = self.rows[row_index]
        self._show_verification_path(str(row.get("_source_path", "") or ""), row)

    def _shift_verification_image(self, delta: int) -> None:
        paths = self._verification_paths()
        if not paths:
            return
        normalized = (
            os.path.normcase(os.path.abspath(self.verification_path))
            if self.verification_path else ""
        )
        current = next(
            (i for i, item in enumerate(paths)
             if os.path.normcase(os.path.abspath(item)) == normalized),
            0,
        )
        target_path = paths[(current + delta) % len(paths)]
        target_key = os.path.normcase(os.path.abspath(target_path))
        row_index = next(
            (i for i, row in enumerate(self.rows)
             if row.get("_source_path")
             and os.path.normcase(os.path.abspath(str(row["_source_path"]))) == target_key),
            -1,
        )
        if row_index >= 0:
            self.table.selectRow(row_index)
            self.table.setCurrentCell(row_index, 0)
            item = self.table.item(row_index, 0)
            if item is not None:
                self.table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
        else:
            self._show_verification_path(target_path)

    def _verification_image_double_clicked(self, display_point: QPoint) -> None:
        source = self.verification_viewer.source
        label_pixmap = self.verification_viewer.label.pixmap()
        if source.isNull() or label_pixmap.isNull() or not self.verification_path:
            return
        source_point = QPoint(
            round(display_point.x() * source.width() / max(1, label_pixmap.width())),
            round(display_point.y() * source.height() / max(1, label_pixmap.height())),
        )
        target_path = os.path.normcase(os.path.abspath(self.verification_path))
        candidates: list[tuple[int, QRect]] = []
        for index, row in enumerate(self.rows):
            path = str(row.get("_source_path", "") or "")
            if not path or os.path.normcase(os.path.abspath(path)) != target_path:
                continue
            rect = row.get("_source_rect")
            if not isinstance(rect, QRect):
                rect = self._estimated_text_rect(row, source.width())
            candidates.append((index, rect))
        if not candidates:
            return
        containing = [item for item in candidates if item[1].contains(source_point)]
        pool = containing or candidates
        row_index, _rect = min(
            pool,
            key=lambda item: (
                item[1].center().x() - source_point.x()
            ) ** 2 + (
                item[1].center().y() - source_point.y()
            ) ** 2,
        )
        self.table.selectRow(row_index)
        self.table.setCurrentCell(row_index, 0)
        item = self.table.item(row_index, 0)
        if item is not None:
            self.table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _build_report_page(self) -> tuple[QWidget, QTextEdit]:
        page = QWidget()
        layout = QVBoxLayout(page)
        first_row = QHBoxLayout()
        first_row.setAlignment(Qt.AlignmentFlag.AlignTop)
        first_row.addWidget(section_label("文本报告"))
        first_row.addStretch()
        replace = QPushButton("执行替换")
        replace.clicked.connect(self.apply_report_replacements)
        replace_settings = QPushButton("替换设置")
        replace_settings.clicked.connect(self.edit_report_replacements)
        simplified = QPushButton("繁→简")
        simplified.clicked.connect(lambda: self.convert_report("t2s"))
        traditional = QPushButton("简→繁")
        traditional.clicked.connect(lambda: self.convert_report("s2t"))
        export = QPushButton("导出 TXT")
        export.clicked.connect(self.export_txt)
        excel = QPushButton("导出 Excel")
        excel.clicked.connect(self.export_report_excel)
        history = QPushButton("导出历史")
        history.clicked.connect(self.show_export_history)
        self.separator_button = QPushButton("")
        self.separator_button.clicked.connect(self.toggle_report_separator)
        self.report_format_button = QPushButton("")
        self.report_format_button.clicked.connect(self.toggle_report_format)
        first_row.addWidget(replace)
        first_row.addWidget(replace_settings)
        first_row.addWidget(simplified)
        first_row.addWidget(traditional)
        first_row.addWidget(export)
        first_row.addWidget(excel)
        first_row.addWidget(history)
        first_row.addWidget(self.separator_button)
        first_row.addWidget(self.report_format_button)
        layout.addLayout(first_row)

        font_config = self.repository.get("font_config", {}) or {}
        editor = QTextEdit()
        editor.setPlaceholderText("识别完成后将在这里生成报告")
        editor.setUndoRedoEnabled(True)
        editor.setFont(QFont(
            "Microsoft YaHei UI",
            int(font_config.get("font_size", 11) or 11),
            QFont.Weight.Bold,
        ))
        layout.addWidget(editor)
        self._report_config_state: tuple[str, str] | None = None
        self._sync_report_controls()
        return page, editor

    def _build_excel_preview_page(self) -> tuple[QWidget, QTableWidget]:
        page = QWidget()
        layout = QVBoxLayout(page)
        header = QHBoxLayout()
        header.addWidget(section_label("Excel 分组表格预览"))
        header.addStretch()
        refresh = QPushButton("刷新预览")
        refresh.clicked.connect(self._refresh_excel_preview)
        header.addWidget(refresh)
        layout.addLayout(header)
        layout.addWidget(muted_label("预览内容与分组 Excel 导出一致，仅供核对，不会修改文本报告。"))
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["辈分", "t1(A组)", "t2(C组)", "t3(B组)", "d(D组)"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(False)
        table.setWordWrap(True)
        table.setShowGrid(True)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((70, 180, 260, 260, 260)):
            table.setColumnWidth(column, width)
        layout.addWidget(table, 1)
        return page, table

    def _switch_step(self, index: int) -> None:
        self.result_stack.setCurrentIndex(index)
        if index == 3:
            self._refresh_excel_preview()

    def _refresh_excel_preview(self) -> None:
        if not hasattr(self, "excel_preview_table"):
            return
        table = self.excel_preview_table
        entries = self._parse_report_entries()
        grouped_rows = self._grouped_excel_rows(entries)
        table.setRowCount(len(grouped_rows))
        for row_index, row in enumerate(grouped_rows):
            line_count = 1
            for column, key in enumerate(("辈分", "t1(A组)", "t2(C组)", "t3(B组)", "d(D组)")):
                value = str(row.get(key, ""))
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                table.setItem(row_index, column, item)
                line_count = max(line_count, value.count("\n") + 1)
            table.setRowHeight(row_index, max(28, line_count * 22))

    def _show_top_notice(self, state: str, text: str, duration: int = 4200,
                         undo_available: bool = False) -> None:
        styles = {
            "success": ("#ECFDF5", "#137A4A", "#A7E8CC", "✓"),
            "warning": ("#FFF7E6", "#A35B00", "#F3D19C", "⚠"),
            "info": ("#EFF6FF", "#245FA8", "#BFDBFE", "ℹ"),
            "error": ("#FFF1F1", "#B42318", "#F4B8B5", "✕"),
        }
        background, foreground, border, icon = styles.get(state, styles["info"])
        self.notice_timer.stop()
        self.notice_animation.stop()
        self.notice_opacity.setOpacity(1.0)
        self.top_notice.setText(f"  {icon}  {text}")
        self.top_notice.setStyleSheet(
            f"background:transparent;color:{foreground};border:0;"
            "padding:7px 12px;font-weight:600;"
        )
        self.top_notice_bar.setStyleSheet(
            f"QFrame {{background:{background};border:1px solid {border};border-radius:8px;}}"
            f"QPushButton {{color:{foreground};background:#FFFFFF;border:1px solid {border};"
            "border-radius:6px;padding:0 12px;min-height:28px;font-weight:600;}"
        )
        self.notice_undo_button.setVisible(bool(undo_available))
        self.top_notice_bar.show()
        self.top_notice_bar.adjustSize()
        self.top_notice_bar.raise_()
        parent = self.top_notice_bar.parentWidget()
        positioner = getattr(parent, "_position_notice_toast", None)
        if callable(positioner):
            positioner()
            QTimer.singleShot(0, positioner)
        self.notice_timer.start(max(1000, int(duration)))

    def _fade_top_notice(self) -> None:
        if not self.top_notice_bar.isVisible():
            return
        self.notice_animation.stop()
        self.notice_animation.setStartValue(self.notice_opacity.opacity())
        self.notice_animation.setEndValue(0.0)
        self.notice_animation.start()

    def _lasso_mode_changed(self, checked: bool) -> None:
        if checked:
            self._show_top_notice(
                "info", "圈选模式已开启：按住鼠标左键围住文字点，松开后自动分类。", 5000
            )
        elif hasattr(self, "top_notice"):
            self._show_top_notice("info", "已切换为直线模式：左键添加分割线，右键删除。", 2800)

    def _plot_status_requested(self, state: str, text: str) -> None:
        self.statusChanged.emit(state, text)
        if text.startswith("直线添加成功"):
            self._show_top_notice("success", text, 2200)

    def cancel_lasso_selection(self) -> None:
        if hasattr(self, "plot") and self.plot.cancel_lasso():
            self._show_top_notice("info", "已取消当前未完成的圈选轨迹，已有分类不受影响。", 3200)
            self.statusChanged.emit("done", "已取消当前圈选轨迹")

    def clear_line_and_lasso_classification(self) -> None:
        line_count = len(self.plot.thresholds)
        lasso_keys = {
            str(row.get("category_key", ""))
            for row in self.rows
            if str(row.get("category_key", "")).startswith("圈选提取")
        }
        lasso_count = max(len(lasso_keys), len(self.lasso_categories))
        if not line_count and not lasso_count:
            self._show_top_notice("info", "当前没有可清理的直线或圈选分类。", 2600)
            return
        self._snapshot()
        self.plot._threshold_change_timer.stop()
        self.plot._pending_threshold_previous = None
        self.plot.thresholds.clear()
        self.lasso_categories.clear()
        self.lasso_undo_history.clear()
        self.lasso_count = 0
        for row in self.rows:
            row["category_key"] = "数据区"
        self._apply_classification_rules()
        self._populate_results()
        message = f"已清理 {line_count} 条直线和 {lasso_count} 个圈选分类。"
        self._show_top_notice("success", message, 3200)
        self.statusChanged.emit("done", message.rstrip("。"))

    def refresh(self) -> None:
        self.repository.reload()
        self._refresh_key_states()
        self._sync_report_controls(regenerate_on_change=True)
        font_config = self.repository.get("font_config", {}) or {}
        self._apply_shared_font_size(int(font_config.get("font_size", 11) or 11))

    def select_mode(self, mode: str) -> None:
        self.mode = mode
        self._refresh_key_states()

    def _mode_status_for_paths(self, mode: str) -> tuple[int, list[str]]:
        reasons: list[str] = []
        allowed = 0
        for path in self.paths:
            ok, reason = self.repository.mode_allowed_for_image(path, mode)
            if ok:
                allowed += 1
            else:
                reasons.append(f"{Path(path).name}：{reason}")
        return allowed, reasons

    def _recommended_mode(self) -> str:
        for mode in ("accurate", "general", "basic"):
            if not key_available(mode):
                continue
            allowed, _reasons = self._mode_status_for_paths(mode)
            if not self.paths or allowed == len(self.paths):
                return mode
        return ""

    def _range_text(self, mode: str) -> str:
        limits = self.repository.limits()
        return (
            f"{MODE_NAMES[mode]}：宽 {limits[f'{mode}_min_width']}~{limits[f'{mode}_max_width']}，"
            f"高 {limits[f'{mode}_min_height']}~{limits[f'{mode}_max_height']}"
        )

    def _refresh_key_states(self) -> None:
        for mode, button in self.mode_buttons.items():
            has_key = key_available(mode)
            allowed, reasons = self._mode_status_for_paths(mode)
            size_ok = not self.paths or allowed == len(self.paths)
            button.setEnabled(has_key and size_ok)
            if not has_key:
                button.setToolTip(f"{MODE_NAMES[mode]}密钥未配置")
            elif not size_ok:
                button.setToolTip("\n".join(reasons[:4]))
            else:
                button.setToolTip(self._range_text(mode))
        if not key_available(self.mode):
            available = next((m for m in MODE_NAMES if key_available(m)), None)
            if available:
                self.mode = available
                self.mode_buttons[available].setChecked(True)
        current_enabled = self.mode_buttons[self.mode].isEnabled()
        self.start_button.setEnabled(bool(self.paths) and current_enabled)
        self._update_hint()

    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", "", "图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)"
        )
        if paths:
            self.import_files(paths)

    def import_files(self, paths: list[str]) -> None:
        """Import one image directly, or merge multiple images before OCR."""
        valid_paths = [str(Path(path)) for path in paths if Path(path).is_file()]
        valid_paths = list(dict.fromkeys(valid_paths))
        if not valid_paths:
            return
        if len(valid_paths) == 1:
            self.set_files(valid_paths)
            return
        try:
            images: list[QPixmap] = []
            for path in valid_paths:
                reader = QImageReader(path)
                reader.setAutoTransform(True)
                image = reader.read()
                if image.isNull():
                    raise OSError(f"无法读取图片：{path}\n{reader.errorString()}")
                images.append(QPixmap.fromImage(image))
            preview = MergePreviewDialog(
                self.repository,
                images,
                "file",
                valid_paths,
                self.mode,
                False,
                self,
            )
            if preview.exec() == QDialog.DialogCode.Accepted and preview.output_path:
                self.mode = preview.selected_mode
                self.mode_buttons[self.mode].setChecked(True)
                self.set_files([preview.output_path])
                self._show_file_toast(preview.output_path, "图片拼接成功")
                self.statusChanged.emit(
                    "done",
                    f"{len(valid_paths)} 张图片已拼接并导入 · "
                    f"{preview.merged.width()}×{preview.merged.height()}",
                )
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))

    def set_files(self, paths: list[str]) -> None:
        self.paths = [str(Path(path)) for path in paths if Path(path).is_file()]
        self.drop_zone.label.setText(
            f"已选择 {len(self.paths)} 张图片\n{Path(self.paths[0]).name}" if self.paths else "拖拽图片到此处\n或点击选择图片"
        )
        if self.paths and hasattr(self, "verification_viewer"):
            self._show_verification_path(self.paths[0])
        self._refresh_key_states()

    def clear_files(self) -> None:
        self.paths.clear()
        self.results.clear()
        self.rows.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.parsed_snapshot = {}
        self.lasso_categories.clear()
        self.lasso_undo_history.clear()
        self.lasso_count = 0
        self.plot.thresholds.clear()
        self.drop_zone.label.setText("拖拽图片到此处\n或点击选择图片")
        self.hint.setText("请选择图片后开始识别")
        self.plot.draw_rows([])
        self.table.setRowCount(0)
        self.report.clear()
        self.verification_path = ""
        if hasattr(self, "verification_viewer"):
            self.verification_viewer.set_pixmap(QPixmap())
            self.verification_position.setText("暂无原图")
            self.verification_source_name.setText("尚未选择表格内容")
            self.verification_line.setText("当前行：—")
        self._refresh_key_states()

    def _update_hint(self) -> None:
        if not self.paths:
            self.hint.setText("请选择图片后开始识别")
            return
        allowed, reasons = self._mode_status_for_paths(self.mode)
        available_modes = []
        for mode in MODE_NAMES:
            count, _ = self._mode_status_for_paths(mode)
            if key_available(mode) and count == len(self.paths):
                available_modes.append(MODE_NAMES[mode])
        recommended = self._recommended_mode()
        current_text = (
            f"当前：{MODE_NAMES[self.mode]}，{allowed}/{len(self.paths)} 张符合规则"
            if allowed == len(self.paths) else
            f"当前模式不可用：{reasons[0] if reasons else '尺寸不符合规则'}"
        )
        recommendation = f"推荐：{MODE_NAMES[recommended]}" if recommended else "建议先裁剪或调整图片尺寸"
        available_text = "、".join(available_modes) if available_modes else "无"
        self.hint.setText(f"{current_text}\n{recommendation}；可用：{available_text}")

    def start_ocr(self) -> None:
        if not self.paths:
            QMessageBox.warning(self, "提示", "请先选择图片")
            return
        if not key_available(self.mode):
            QMessageBox.warning(self, "密钥未配置", f"尚未配置{MODE_NAMES[self.mode]}密钥")
            return
        allowed, reasons = self._mode_status_for_paths(self.mode)
        if allowed != len(self.paths):
            detail = "\n".join(reasons[:5])
            QMessageBox.warning(
                self, "当前识别质量不可用",
                f"有 {len(self.paths) - allowed} 张图片不符合{MODE_NAMES[self.mode]}尺寸规则。\n\n{detail}"
            )
            return
        self.start_button.setEnabled(False)
        self.statusChanged.emit("running", "识别中…")
        worker = OCRWorker(self.repository, self.paths, self.mode)
        worker.signals.progress.connect(lambda text: self.statusChanged.emit("running", text))
        worker.signals.failed.connect(self._ocr_failed)
        worker.signals.completed.connect(self._ocr_completed)
        self.thread_pool.start(worker)

    def _ocr_failed(self, message: str) -> None:
        self.start_button.setEnabled(True)
        self.statusChanged.emit("error", "识别失败")
        QMessageBox.critical(self, "识别失败", message)

    def _ocr_completed(self, results: list) -> None:
        self.results = results
        self.rows = self._rows_with_sources(results)
        for row in self.rows:
            row["group"] = self._group_for_label(row["label"])
            row["category_key"] = "数据区"
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.lasso_categories.clear()
        self.lasso_undo_history.clear()
        self.lasso_count = 0
        self.plot.thresholds.clear()
        self._apply_classification_rules()
        self.parsed_snapshot = self._capture_classifier_state()
        self.repository.set("book_name", self.book_name.text().strip())
        self.repository.save_history_and_stats(
            self.mode, results, self.book_name.text().strip(), self.book_page.value()
        )
        for result in results:
            mark_merge_recognized(self.repository, str(result.get("path", "")), self.mode)
        self.book_page.setValue(int(self.repository.get("book_page", self.book_page.value())))
        self._populate_results()
        if self.rows:
            self.table.selectRow(0)
            self.table.setCurrentCell(0, 0)
        self.start_button.setEnabled(True)
        failures = sum(bool(r.get("error") or r.get("skipped")) for r in results)
        self.statusChanged.emit("done", f"识别完成 · {len(self.rows)} 行")
        self.dataChanged.emit()
        if failures:
            QMessageBox.warning(self, "识别完成", f"已识别 {len(self.rows)} 行，{failures} 张图片失败或被跳过。")

    @staticmethod
    def _estimated_text_rect(row: dict[str, Any], image_width: int = 0) -> QRect:
        """Use the saved OCR width, falling back to a legacy text estimate."""
        height = max(2, round(float(row.get("height", 0) or 0)))
        width = round(float(row.get("width", 0) or 0))
        if width <= 0:
            label = str(row.get("label", ""))
            units = sum(1.0 if ord(char) > 255 else .55 for char in label) or 1.0
            width = max(height, round(height * (units + .5)))
        left = max(0, round(float(row.get("x", 0) or 0)))
        top = max(0, round(float(row.get("y", 0) or 0)))
        if image_width > 0:
            width = min(width, max(2, image_width - left))
        return QRect(left, top, width, height)

    def _rows_with_sources(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for source_index, result in enumerate(results):
            source_path = str(result.get("path", "") or "")
            source_file = str(result.get("file", "") or "")
            boxes = result.get("boxes", []) or []
            if not isinstance(boxes, (list, tuple)):
                boxes = []
            image_width = 0
            if source_path and Path(source_path).is_file():
                image_width = QImageReader(source_path).size().width()
            for source_line, line in enumerate(result.get("lines", []) or []):
                row = parse_line(line)
                box = boxes[source_line] if source_line < len(boxes) else None
                if isinstance(box, dict):
                    row["x"] = float(box.get("left", row.get("x", 0)) or 0)
                    row["y"] = float(box.get("top", row.get("y", 0)) or 0)
                    row["width"] = float(box.get("width", 0) or 0)
                    row["height"] = float(box.get("height", row.get("height", 0)) or 0)
                    row["_source_box_exact"] = row["width"] > 0 and row["height"] > 0
                row["_source_index"] = source_index
                row["_source_line"] = source_line
                row["_source_path"] = source_path
                row["_source_file"] = source_file
                row["_source_rect"] = self._estimated_text_rect(row, image_width)
                rows.append(row)
        return rows

    def load_text_for_parsing(
        self,
        text: str,
        source_name: str = "历史记录",
        source_results: list[dict[str, Any]] | None = None,
    ) -> int:
        """Load recognized text into the native plot/table/report workflow."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return 0
        self.results = copy.deepcopy(source_results) if source_results else [{
            "file": source_name, "path": "", "type": "history",
            "lines": lines, "count": len(lines), "cached": True,
        }]
        self.rows = self._rows_with_sources(self.results)
        for row in self.rows:
            row["group"] = self._group_for_label(row["label"])
            row["category_key"] = "数据区"
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.lasso_categories.clear()
        self.lasso_undo_history.clear()
        self.lasso_count = 0
        self.plot.thresholds.clear()
        self._apply_classification_rules()
        self.parsed_snapshot = self._capture_classifier_state()
        self._populate_results()
        if self.rows:
            self.table.selectRow(0)
            self.table.setCurrentCell(0, 0)
        self._switch_step(0)
        self.step_buttons[0].setChecked(True)
        self.statusChanged.emit("done", f"已复制并解析 · {len(self.rows)} 行")
        return len(self.rows)

    def _apply_classification_rules(self, reorder: bool = True) -> None:
        """Apply the legacy section ordering and dynamic 1–5 category labels."""
        if not self.rows:
            return

        active_lasso = []
        for name in self.lasso_categories:
            if any(str(row.get("category_key", "")) == name for row in self.rows):
                active_lasso.append(name)
        self.lasso_categories = active_lasso

        # New lasso names are inserted at the front.  Number them in creation
        # order so the first selection is always 5, then 4, 3, ...
        lasso_sections: list[tuple[str, list[int]]] = []
        lasso_indices: set[int] = set()
        for name in reversed(self.lasso_categories):
            indices = [
                index for index, row in enumerate(self.rows)
                if str(row.get("category_key", "")) == name
            ]
            if indices:
                lasso_sections.append((name, indices))
                lasso_indices.update(indices)

        remaining = [index for index in range(len(self.rows)) if index not in lasso_indices]
        thresholds = sorted(float(value) for value in self.plot.thresholds)
        line_sections: list[tuple[str, list[int]]] = []
        if remaining:
            if not thresholds:
                line_sections.append(("数据区", remaining))
            else:
                low = [index for index in remaining if float(self.rows[index].get("y", 0)) < thresholds[0]]
                if low:
                    line_sections.append((f"低于 {thresholds[0]:g}", low))
                for lower, upper in zip(thresholds, thresholds[1:]):
                    middle = [
                        index for index in remaining
                        if lower <= float(self.rows[index].get("y", 0)) < upper
                    ]
                    if middle:
                        line_sections.append((f"{lower:g} ~ {upper:g}", middle))
                high = [index for index in remaining if float(self.rows[index].get("y", 0)) >= thresholds[-1]]
                if high:
                    line_sections.append((f"高于 {thresholds[-1]:g}", high))

        numbered_sections: list[tuple[int, list[int]]] = []
        for offset, (key, indices) in enumerate(lasso_sections):
            match = re.search(r"(\d+)$", key)
            sequence = int(match.group(1)) if match else offset + 1
            display_number = 6 - sequence
            display = str(display_number)
            for index in indices:
                self.rows[index]["category"] = display
                self.rows[index]["category_key"] = key
            numbered_sections.append((display_number, indices))

        # Remaining straight-line regions use the numbers below the lasso
        # categories.  Their high-Y region still receives the largest number.
        line_start = 6 - self.lasso_count - len(line_sections)
        for offset, (key, indices) in enumerate(line_sections):
            display_number = line_start + offset
            display = str(display_number)
            for index in indices:
                self.rows[index]["category"] = display
                self.rows[index]["category_key"] = key
            numbered_sections.append((display_number, indices))

        # Every category is rendered as one continuous block and the table is
        # always ordered numerically from the smallest category to 5.
        grouped_indices = [
            index
            for _number, indices in sorted(numbered_sections, key=lambda item: item[0])
            for index in indices
        ]
        if reorder and len(grouped_indices) == len(self.rows):
            self.rows = [self.rows[index] for index in grouped_indices]

    def _classifier_history_snapshot(self) -> dict[str, Any]:
        """Return the JSON-safe, editable portion of the current classifier state."""
        row_keys = (
            "label", "y", "x", "width", "height", "confidence", "group",
            "category", "category_key", "marked", "_source_index", "_source_line",
            "_source_path", "_source_file", "_source_box_exact",
        )
        rows = []
        for row in self.rows:
            saved = {key: row[key] for key in row_keys if key in row}
            rows.append(saved)
        return {
            "rows": rows,
            "thresholds": [float(value) for value in self.plot.thresholds],
            "lasso_categories": list(self.lasso_categories),
            "lasso_count": int(self.lasso_count),
        }

    def save_classifier_history(self, notify: bool = True) -> bool:
        if not self.rows:
            return False
        self.repository.save_classifier_history(
            self._classifier_history_snapshot(),
            self.book_name.text().strip(),
            self.book_page.value(),
        )
        if notify:
            self.statusChanged.emit("done", f"分类表已保存到历史 · {len(self.rows)} 条")
            self.dataChanged.emit()
        return True

    def show_classifier_history(self) -> None:
        ClassifierHistoryDialog(self.repository, self.restore_classifier_history, self).exec()

    def restore_classifier_history(self, record: dict[str, Any]) -> None:
        snapshot = record.get("snapshot", {})
        saved_rows = snapshot.get("rows", []) if isinstance(snapshot, dict) else []
        if not isinstance(saved_rows, list) or not saved_rows:
            QMessageBox.warning(self, "恢复失败", "该分类表历史记录没有可恢复的数据")
            return

        def number(value: Any, default: float = 0.0) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        rows: list[dict[str, Any]] = []
        for saved in saved_rows:
            if not isinstance(saved, dict):
                continue
            row = {
                "label": str(saved.get("label", "")),
                "y": number(saved.get("y")),
                "x": number(saved.get("x")),
                "width": number(saved.get("width")),
                "height": number(saved.get("height")),
                "confidence": number(saved.get("confidence")),
                "group": str(saved.get("group", "B")),
                "category": str(saved.get("category", "未分类")),
                "category_key": str(saved.get("category_key", "数据区")),
                "marked": bool(saved.get("marked", False)),
                "_source_index": int(number(saved.get("_source_index"))),
                "_source_line": int(number(saved.get("_source_line"))),
                "_source_path": str(saved.get("_source_path", "")),
                "_source_file": str(saved.get("_source_file", "")),
                "_source_box_exact": bool(saved.get("_source_box_exact", False)),
            }
            image_width = (
                QImageReader(row["_source_path"]).size().width()
                if row["_source_path"] and Path(row["_source_path"]).is_file() else 0
            )
            row["_source_rect"] = self._estimated_text_rect(row, image_width)
            rows.append(row)
        if not rows:
            QMessageBox.warning(self, "恢复失败", "该分类表历史记录格式无效")
            return
        self.rows = rows
        self.results = []
        self.paths = list(dict.fromkeys(
            row["_source_path"] for row in rows if row["_source_path"]
        ))
        self.plot.thresholds = [
            number(value) for value in snapshot.get("thresholds", [])
            if isinstance(value, (int, float, str))
        ]
        self.lasso_categories = [
            str(value) for value in snapshot.get("lasso_categories", [])
        ]
        self.lasso_count = int(number(snapshot.get("lasso_count"), len(self.lasso_categories)))
        self.lasso_undo_history.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.book_name.setText(str(record.get("book_name", "")))
        self.book_page.setValue(max(1, int(number(record.get("page_no"), 1))))
        self.parsed_snapshot = self._capture_classifier_state()
        self._populate_results()
        self._switch_step(1)
        if self.rows:
            self.table.selectRow(0)
            self.table.setCurrentCell(0, 0)
        self.statusChanged.emit("done", f"已恢复分类表历史 · {len(self.rows)} 条")
        self.dataChanged.emit()

    def _capture_classifier_state(self, thresholds: list[float] | None = None,
                                  redraw_plot: bool = True) -> dict[str, Any]:
        return {
            "rows": copy.deepcopy(self.rows),
            "thresholds": list(self.plot.thresholds if thresholds is None else thresholds),
            "lasso_categories": list(self.lasso_categories),
            "lasso_count": self.lasso_count,
            "category_colors": copy.deepcopy(self.category_colors),
            "_redraw_plot": bool(redraw_plot),
        }

    def _restore_classifier_state(self, state: dict[str, Any]) -> None:
        self.rows = copy.deepcopy(state.get("rows", []))
        self.plot.thresholds = list(state.get("thresholds", []))
        self.lasso_categories = list(state.get("lasso_categories", []))
        self.lasso_count = int(state.get("lasso_count", len(self.lasso_categories)) or 0)
        if "category_colors" in state:
            self.category_colors = copy.deepcopy(state["category_colors"])
            self.repository.set("qt_category_colors", self.category_colors)
        self._populate_results(redraw_plot=bool(state.get("_redraw_plot", True)))

    @staticmethod
    def _classifier_table_font_style(font_size: int) -> str:
        return (
            "QTableWidget {"
            f"font-size:{font_size}pt;"
            "font-weight:bold;"
            "}"
            "QTableWidget::item {"
            f"font-size:{font_size}pt;"
            "}"
        )

    @staticmethod
    def _group_button_style(font_size: int) -> str:
        return (
            "QComboBox#groupCell {"
            f"  font-size: {font_size}pt;"
            "  font-weight: bold;"
            "  background: #FFFFFF;"
            "  color: #17191C;"
            "  border: 1px solid #8FA9BC;"
            "  border-radius: 0;"
            "  padding: 0 27px 0 7px;"
            "}"
            "QComboBox#groupCell::drop-down {"
            "  subcontrol-origin: padding;"
            "  subcontrol-position: top right;"
            "  width: 23px;"
            "  background: #D8ECFA;"
            "  border-left: 1px solid #5F9FC8;"
            "}"
            "QComboBox#groupCell::drop-down:hover { background: #C7E4F8; }"
            "QComboBox#groupCell QAbstractItemView {"
            f"  font-size: {font_size}pt;"
            "  font-weight: normal;"
            "  color: #17191C;"
            "  background: #FFFFFF;"
            "  border: 1px solid #8A8A8A;"
            "  outline: 0;"
            "  padding: 0;"
            "  selection-background-color: #0078D7;"
            "  selection-color: #FFFFFF;"
            "}"
            "QComboBox#groupCell QAbstractItemView::item {"
            "  min-height: 24px;"
            "  padding: 0 0 0 6px;"
            "}"
        )

    def _create_group_button(self, row_index: int, group: str) -> GroupCellButton:
        button = GroupCellButton(group, row_index)
        button.setMinimumWidth(52)
        font_size = int(self.table.property("classifierFontSize") or 11)
        button.setFont(QFont("Microsoft YaHei UI", font_size, QFont.Weight.Bold))
        button.setStyleSheet(self._group_button_style(font_size))
        button.groupChanged.connect(self._group_combo_changed)
        button.rowClicked.connect(self._group_cell_clicked)
        return button

    def _group_cell_clicked(self, row_index: int, modifiers) -> None:
        """Select a table row without opening the group drop-down."""
        if not 0 <= row_index < self.table.rowCount():
            return
        selection = self.table.selectionModel()
        if selection is None:
            return
        index = self.table.model().index(row_index, 5)
        if (
            modifiers & Qt.KeyboardModifier.ShiftModifier
            and self._selection_anchor_row is not None
        ):
            self._select_row_range(self._selection_anchor_row, row_index)
        else:
            flags = QItemSelectionModel.SelectionFlag.Rows
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                flags |= QItemSelectionModel.SelectionFlag.Toggle
                if self._selection_anchor_row is None:
                    self._selection_anchor_row = row_index
            else:
                flags |= QItemSelectionModel.SelectionFlag.ClearAndSelect
                self._selection_anchor_row = row_index
            selection.select(index, flags)
        selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.table.setFocus(Qt.FocusReason.MouseFocusReason)

    def _select_row_range(self, first_row: int, last_row: int) -> None:
        """Select every complete row between the saved anchor and target."""
        selection = self.table.selectionModel()
        if selection is None:
            return
        selection.clearSelection()
        flags = (
            QItemSelectionModel.SelectionFlag.Select
            | QItemSelectionModel.SelectionFlag.Rows
        )
        start, end = sorted((first_row, last_row))
        for row_index in range(start, end + 1):
            selection.select(self.table.model().index(row_index, 0), flags)

    def _activate_group_cell_for_record(self, clicked_index) -> None:
        """Make the selected row's group cell current after a normal cell click."""
        if not clicked_index.isValid() or clicked_index.column() == 5:
            return
        row_index = clicked_index.row()
        if not 0 <= row_index < self.table.rowCount():
            return
        selection = self.table.selectionModel()
        if selection is None:
            return
        modifiers = QApplication.keyboardModifiers()
        if (
            modifiers & Qt.KeyboardModifier.ShiftModifier
            and self._selection_anchor_row is not None
        ):
            self._select_row_range(self._selection_anchor_row, row_index)
        elif not (modifiers & Qt.KeyboardModifier.ControlModifier):
            self._selection_anchor_row = row_index
        elif self._selection_anchor_row is None:
            self._selection_anchor_row = row_index
        group_index = self.table.model().index(row_index, 5)
        selection.setCurrentIndex(
            group_index,
            QItemSelectionModel.SelectionFlag.NoUpdate,
        )
        self.table.setFocus(Qt.FocusReason.MouseFocusReason)

    def _group_combo_changed(self, row_index: int, group: str) -> None:
        if not 0 <= row_index < len(self.rows) or group not in "ABCD":
            return
        if str(self.rows[row_index].get("group", "")) == group:
            return
        self._snapshot(redraw_plot=False)
        selected_ids = {
            id(self.rows[index]) for index in self._selected_rows()
            if 0 <= index < len(self.rows)
        }
        self.rows[row_index]["group"] = group
        # Rebuild the report/table from the updated row model.  The grouped
        # report is a rich-text table, so updating only the combo-box cell can
        # leave its previous column layout visible until another refresh.
        self._populate_results(redraw_plot=False)
        selected_ids.add(id(self.rows[row_index]))
        self._select_rows(
            index for index, row in enumerate(self.rows) if id(row) in selected_ids
        )
        self.statusChanged.emit("done", f"第 {row_index + 1} 行已设置为 {group} 组")

    def _table_row_token(self, row_index: int) -> int | None:
        item = self.table.item(row_index, 0)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def _table_order_matches_rows(self) -> bool:
        if self.table.rowCount() != len(self.rows):
            return False
        return all(self._table_row_token(index) == id(row) for index, row in enumerate(self.rows))

    def _update_table_row(self, row_index: int, row: dict[str, Any], create: bool = False) -> None:
        values = [
            row["label"], row["y"], row["x"], row["height"], row["confidence"],
            row["group"], row.get("category", "未分类"),
        ]
        category_color = QColor(self.category_colors.get(str(row.get("category", "未分类")), ""))
        background = QColor("#FFF3B0") if row.get("marked", False) else (
            category_color.lighter(180) if category_color.isValid() else QColor()
        )
        confidence = float(row.get("confidence", 0) or 0)
        confidence_threshold = float(self.repository.get("conf_threshold", 0) or 0)
        low_confidence = confidence > 0 and confidence_threshold > 0 and confidence < confidence_threshold
        for column, value in enumerate(values):
            item = self.table.item(row_index, column)
            if create or item is None:
                item = QTableWidgetItem()
                self.table.setItem(row_index, column, item)
            item.setData(Qt.ItemDataRole.UserRole, id(row) if column == 0 else None)
            item.setText(str(value))
            item.setBackground(QBrush(QColor("#FFF4C2")) if low_confidence else (
                QBrush(background) if background.isValid() else QBrush()
            ))
            if column == 0:
                style = self._font_style_for_label(str(row.get("label", "")))
                if style:
                    item.setForeground(QColor(str(style.get("color", "#17191C"))))
                    font = QFont(
                        str(style.get("font_family", "Microsoft YaHei UI")),
                        int(style.get("font_size", 11) or 11),
                    )
                    font.setBold(str(style.get("font_weight", "normal")) == "bold")
                    item.setFont(font)
                elif str(row.get("group", "")) == "C":
                    item.setForeground(QColor(GROUP_C_GREEN))
                else:
                    item.setForeground(QColor("#17191C"))
            if column == 4:
                item.setText(f"● {confidence:g}" if low_confidence else str(value))
                if low_confidence:
                    item.setForeground(QColor("#C62828"))
            if column == 6:
                item.setToolTip(str(row.get("category_key", "数据区")))
            if column == 5:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        group_widget = self.table.cellWidget(row_index, 5)
        if not isinstance(group_widget, GroupCellButton) or create:
            self.table.setCellWidget(
                row_index, 5,
                self._create_group_button(row_index, str(row.get("group", "B"))),
            )
        else:
            group_widget._row = row_index
            group_widget.blockSignals(True)
            group_widget.setCurrentText(str(row.get("group", "B")))
            group_widget.blockSignals(False)

    def _refresh_table_after_row_change(self, changed_row_ids: set[int] | None = None) -> None:
        """Apply row insertions/removals without rebuilding every table widget."""
        old_ids = [self._table_row_token(index) for index in range(self.table.rowCount())]
        new_ids = [id(row) for row in self.rows]
        old_set = {value for value in old_ids if value is not None}
        new_set = set(new_ids)
        # A category recalculation may reorder the whole table; retain the
        # existing full-refresh path for that less common case.
        old_common = [value for value in old_ids if value in new_set]
        new_common = [value for value in new_ids if value in old_set]
        if old_common != new_common:
            self._populate_results(redraw_plot=False)
            return

        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        current_ids = list(old_ids)
        for row_index in range(len(current_ids) - 1, -1, -1):
            if current_ids[row_index] not in new_set:
                self.table.removeRow(row_index)
                current_ids.pop(row_index)
        for row_index, row in enumerate(self.rows):
            row_id = id(row)
            if row_index < len(current_ids) and current_ids[row_index] == row_id:
                if changed_row_ids is None or row_id in changed_row_ids:
                    self._update_table_row(row_index, row)
                continue
            if row_id in current_ids:
                self.table.blockSignals(False)
                self.table.setUpdatesEnabled(True)
                self._populate_results(redraw_plot=False)
                return
            self.table.insertRow(row_index)
            current_ids.insert(row_index, row_id)
            self._update_table_row(row_index, row, create=True)
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.table.viewport().update()
        self._update_report()

    def _populate_results(self, redraw_plot: bool = True) -> None:
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.rows))
        for row_index, row in enumerate(self.rows):
            self._update_table_row(row_index, row, create=True)
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.table.viewport().update()
        if redraw_plot:
            self.plot.category_colors = dict(self.category_colors)
            self.plot.draw_rows(self.rows)
        self._update_report()

    def _sync_table_classifications(self) -> None:
        """Update category values/styles without recreating table cells or widgets."""
        if self.table.rowCount() != len(self.rows):
            self._populate_results(redraw_plot=False)
            return
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        confidence_threshold = float(self.repository.get("conf_threshold", 0) or 0)
        for row_index, row in enumerate(self.rows):
            category = str(row.get("category", "未分类"))
            category_item = self.table.item(row_index, 6)
            if category_item is not None:
                category_item.setText(category)
                category_item.setToolTip(str(row.get("category_key", "数据区")))
            category_color = QColor(self.category_colors.get(category, ""))
            background = QColor("#FFF3B0") if row.get("marked", False) else (
                category_color.lighter(180) if category_color.isValid() else QColor()
            )
            confidence = float(row.get("confidence", 0) or 0)
            low_confidence = (
                confidence > 0
                and confidence_threshold > 0
                and confidence < confidence_threshold
            )
            for column in range(self.table.columnCount()):
                item = self.table.item(row_index, column)
                if item is None:
                    continue
                if low_confidence:
                    item.setBackground(QBrush(QColor("#FFF4C2")))
                elif background.isValid():
                    item.setBackground(QBrush(background))
                else:
                    item.setBackground(QBrush())
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.table.viewport().update()

    def _sort_table_by_category(self) -> None:
        """Sort existing table rows by numeric category without rebuilding cells."""
        if self.table.rowCount() != len(self.rows):
            return
        rows_by_token: dict[int, dict[str, Any]] = {}
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        for row_index, row in enumerate(self.rows):
            item = self.table.item(row_index, 6)
            if item is None:
                continue
            token = id(row)
            rows_by_token[token] = row
            item.setData(Qt.ItemDataRole.UserRole, token)
            category = str(row.get("category", ""))
            try:
                item.setData(Qt.ItemDataRole.DisplayRole, int(category))
            except ValueError:
                item.setData(Qt.ItemDataRole.DisplayRole, category)

        self.table.sortItems(6, Qt.SortOrder.AscendingOrder)
        sorted_rows: list[dict[str, Any]] = []
        for row_index in range(self.table.rowCount()):
            item = self.table.item(row_index, 6)
            token = int(item.data(Qt.ItemDataRole.UserRole) or 0) if item is not None else 0
            row = rows_by_token.get(token)
            if row is not None:
                sorted_rows.append(row)
            if item is not None:
                item.setData(Qt.ItemDataRole.UserRole, None)
            group_widget = self.table.cellWidget(row_index, 5)
            if isinstance(group_widget, GroupCellButton):
                group_widget._row = row_index
        if len(sorted_rows) == len(self.rows):
            self.rows = sorted_rows
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.table.viewport().update()
        self._update_report()
        self._sync_verification_from_table()

    def _font_style_for_label(self, label: str) -> dict[str, Any] | None:
        _marker_count, label = self._split_blank_line_markers(label)
        rules = self.repository.get("font_style_rules", {}) or {}
        for prefix, rule in rules.items():
            if not isinstance(rule, dict) or not rule.get("enabled", True):
                continue
            if label.lower().startswith(str(prefix).lower()):
                return rule
        return None

    def _table_changed(self, item: QTableWidgetItem) -> None:
        index = item.row()
        if index >= len(self.rows):
            return
        keys = ["label", "y", "x", "height", "confidence", "group", "category"]
        key = keys[item.column()]
        try:
            value = item.text() if key in {"label", "group", "category"} else float(item.text())
        except ValueError:
            return
        if self.rows[index].get(key) == value:
            return
        self._snapshot(redraw_plot=False)
        self.rows[index][key] = value
        if key in {"label", "y", "x", "height"} and self.rows[index].get("_source_path"):
            source_path = str(self.rows[index]["_source_path"])
            image_width = QImageReader(source_path).size().width() if Path(source_path).is_file() else 0
            self.rows[index]["_source_rect"] = self._estimated_text_rect(
                self.rows[index], image_width
            )
            self._sync_verification_from_table()
        self._update_report()

    def _update_report(self) -> None:
        report_format = str(self.repository.get("report_format", "legacy"))
        if report_format == "grouped":
            self.report.setHtml(self._grouped_report_html(self._grouped_report_text()))
            return
        separator = "----\n" if self.repository.get("report_separator", "line") == "line" else "\n"
        sections: list[tuple[str, list[dict[str, Any]]]] = []
        for row in self.rows:
            category = str(row.get("category", "5"))
            if not sections or sections[-1][0] != category:
                sections.append((category, []))
            sections[-1][1].append(row)

        output = ""
        for category, rows in sections:
            if report_format == "columns":
                output += f"【{category}】:\n"
            previous_group = None
            previous_red = None
            for index, row in enumerate(rows):
                marker_count, name = self._split_blank_line_markers(
                    str(row.get("label", ""))
                )
                group = str(row.get("group", "B"))
                is_red = self._is_red_color((self._font_style_for_label(name) or {}).get("color", ""))
                if index > 0 and (
                    (previous_group is not None and previous_group != group)
                    or (previous_red and is_red)
                ):
                    output += separator
                if marker_count:
                    output += "\n" * marker_count
                if report_format == "columns":
                    output += f"{category}\t{name}\t{group}\n"
                else:
                    output += f"{name}\n"
                previous_group = group
                previous_red = is_red
            output += separator
        self.report.setPlainText(output)

    def _grouped_report_text(self) -> str:
        """Build an editable Markdown table for the grouped report."""
        grouped_rows: list[dict[str, Any]] = []
        current = {
            "辈分": "", "A组": "", "B组": [], "C组": [], "D组": [],
        }
        for row in self.rows:
            _marker_count, name = self._split_blank_line_markers(str(row.get("label", "")))
            group = str(row.get("group", "B"))
            if group == "A":
                if current["A组"]:
                    grouped_rows.append(current)
                    current = {"辈分": "", "A组": "", "B组": [], "C组": [], "D组": []}
                current["辈分"] = str(row.get("category", ""))
                current["A组"] = name
            elif group in {"B", "C", "D"}:
                current[f"{group}组"].append(name)

        if current["A组"] or current["B组"] or current["C组"] or current["D组"]:
            grouped_rows.append(current)

        lines = [
            "| 辈分 | a组 | c组 | b组 | d组 |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for grouped_row in grouped_rows:
            line_count = max(
                1,
                len(grouped_row["C组"]),
                len(grouped_row["B组"]),
                len(grouped_row["D组"]),
            )
            for index in range(line_count):
                lines.append(self._format_markdown_row([
                    grouped_row["辈分"] if index == 0 else "",
                    grouped_row["A组"] if index == 0 else "",
                    grouped_row["C组"][index] if index < len(grouped_row["C组"]) else "",
                    grouped_row["B组"][index] if index < len(grouped_row["B组"]) else "",
                    grouped_row["D组"][index] if index < len(grouped_row["D组"]) else "",
                ]))
        return "\n".join(lines)

    def _report_source_text(self) -> str:
        """Read the editable Markdown source when the report is rendered."""
        if str(self.repository.get("report_format", "legacy")) == "grouped":
            for frame in self.report.document().rootFrame().childFrames():
                if not isinstance(frame, QTextTable) or frame.rows() < 1 or frame.columns() < 5:
                    continue
                lines = [
                    "| 辈分 | a组 | c组 | b组 | d组 |",
                    "| :--- | :--- | :--- | :--- | :--- |",
                ]
                for row in range(1, frame.rows()):
                    values: list[str] = []
                    column = 0
                    while column < 5:
                        cell = frame.cellAt(row, column)
                        start = cell.firstCursorPosition().position()
                        end = cell.lastCursorPosition().position()
                        if start == end:
                            value = ""
                        else:
                            block = self.report.document().findBlock(start)
                            block_text: list[str] = []
                            while block.isValid() and block.position() <= end:
                                block_text.append(block.text())
                                if block.position() + block.length() >= end:
                                    break
                                block = block.next()
                            value = "\n".join(block_text).replace("\u2028", "\n").replace("\u2029", "\n").strip()
                        value = re.sub(r"\s*\n\s*", "<br>", value)
                        values.append(value)
                        span = max(1, cell.columnSpan())
                        values.extend([""] * min(span - 1, 5 - len(values)))
                        column += span
                    lines.append(self._format_markdown_row(values))
                return "\n".join(lines)
            return self.report.toMarkdown()
        return self.report.toPlainText()

    @classmethod
    def _grouped_report_html(cls, markdown: str) -> str:
        """Render the Markdown source as a fixed five-column editable table."""
        rows: list[list[str]] = []
        for raw_line in str(markdown).splitlines():
            cells = cls._split_markdown_row(raw_line)
            if cells is None or len(cells) < 5:
                continue
            if cls._is_markdown_separator(cells):
                continue
            rows.append(cells[:5])
        if not rows:
            return ""
        # A record is one A-group row plus its following C/B/D rows.  Collapse
        # those source rows into one visual table row so no internal rules can
        # appear between names belonging to the same record.
        records: list[list[str]] = []
        current_record: list[str] | None = None
        for values in rows[1:]:
            starts_record = bool(values[0].strip() or values[1].strip())
            if starts_record or current_record is None:
                if current_record is not None:
                    records.append(current_record)
                current_record = list(values)
                continue
            for index, value in enumerate(values):
                if value.strip():
                    current_record[index] = (
                        f"{current_record[index]}<br>{value}"
                        if current_record[index].strip() else value
                    )
        if current_record is not None:
            records.append(current_record)
        output = [
            '<table border="0" cellspacing="0" cellpadding="4" '
            'style="border-collapse:collapse; width:100%; border:2px solid #69727D;">'
        ]
        header = rows[0]
        output.append("<tr>" + "".join(
            '<th align="center" valign="middle" style="text-align:center; '
            'vertical-align:middle; border-top:1px solid #69727D; '
            'border-right:1px solid #69727D; border-bottom:2px solid #4F5965; '
            'border-left:1px solid #69727D;">' + html_escape(value) + "</th>"
            for value in header
        ) + "</tr>")
        for values in records:
            cells_html: list[str] = []
            for column, value in enumerate(values):
                parts = cls._split_markdown_names(value)
                content = "<br>".join(html_escape(part) for part in parts)
                # B 组需要左上对齐；D 组只取消水平居中，继续保持垂直居中。
                if column == 3:
                    align = "left"
                    valign = "top"
                elif column == 4:
                    align = "left"
                    valign = "middle"
                else:
                    align = "center"
                    valign = "middle"
                cells_html.append(
                    f'<td align="{align}" valign="{valign}" style="text-align:{align}; '
                    f'vertical-align:{valign}; border-top:2px solid #4F5965; '
                    'border-right:1px solid #8A929C; border-bottom:0; '
                    'border-left:1px solid #8A929C;">'
                    + content + "</td>"
                )
            output.append("<tr>" + "".join(cells_html) + "</tr>")
        output.append("</table>")
        return "".join(output)

    @staticmethod
    def _markdown_escape_cell(value: Any) -> str:
        """Escape a cell value without introducing alignment whitespace."""
        return str(value or "").strip().replace("|", r"\|")

    @classmethod
    def _format_markdown_row(cls, values: list[Any]) -> str:
        return "| " + " | ".join(cls._markdown_escape_cell(value) for value in values) + " |"

    @staticmethod
    def _split_markdown_row(line: str) -> list[str] | None:
        """Split a pipe-delimited Markdown row while honoring escaped pipes."""
        stripped = str(line).strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            return None
        body = stripped[1:-1]
        cells: list[str] = []
        current: list[str] = []
        escaped = False
        for char in body:
            if char == "|" and not escaped:
                cells.append("".join(current).strip().replace(r"\|", "|"))
                current = []
                continue
            current.append(char)
            if char == "\\" and not escaped:
                escaped = True
            else:
                escaped = False
        cells.append("".join(current).strip().replace(r"\|", "|"))
        return cells

    @classmethod
    def _is_markdown_header(cls, cells: list[str]) -> bool:
        return [cell.strip().lower() for cell in cells] == ["辈分", "a组", "c组", "b组", "d组"]

    @staticmethod
    def _is_markdown_separator(cells: list[str]) -> bool:
        return len(cells) >= 5 and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells[:5])

    @staticmethod
    def _split_markdown_names(value: str) -> list[str]:
        return [part.strip() for part in re.split(r"<br\s*/?>", value, flags=re.IGNORECASE) if part.strip()]

    @staticmethod
    def _split_blank_line_markers(label: str) -> tuple[int, str]:
        marker_count = len(label) - len(label.lstrip(BLANK_LINE_MARKER))
        return marker_count, label[marker_count:]

    def _sync_report_controls(self, regenerate_on_change: bool = False) -> None:
        report_format = str(self.repository.get("report_format", "legacy"))
        separator = str(self.repository.get("report_separator", "line"))
        state = (report_format, separator)
        previous = getattr(self, "_report_config_state", None)
        self._report_config_state = state
        if hasattr(self, "separator_button"):
            self.separator_button.setText("分隔：----" if separator == "line" else "分隔：空行")
            self.separator_button.setEnabled(report_format != "grouped")
        if hasattr(self, "report_format_button"):
            self.report_format_button.setText(
                f"格式：{REPORT_FORMAT_NAMES.get(report_format, REPORT_FORMAT_NAMES['legacy'])}"
            )
        if regenerate_on_change and previous is not None and previous != state and hasattr(self, "report"):
            self._update_report()

    def toggle_report_separator(self) -> None:
        current = str(self.repository.get("report_separator", "line"))
        self.repository.set("report_separator", "blank" if current == "line" else "line")
        self._sync_report_controls()
        self._update_report()

    def toggle_report_format(self) -> None:
        current = str(self.repository.get("report_format", "legacy"))
        formats = list(REPORT_FORMAT_NAMES)
        current_index = formats.index(current) if current in formats else 0
        self.repository.set("report_format", formats[(current_index + 1) % len(formats)])
        self._sync_report_controls()
        self._update_report()

    def _apply_shared_font_size(self, size: int) -> None:
        size = max(8, min(30, int(size)))
        config = dict(self.repository.get("font_config", {}) or {})
        config["font_size"] = size
        self.repository.set("font_config", config)
        if hasattr(self, "table"):
            self.table.setProperty("classifierFontSize", size)
            self.table.setFont(QFont("Microsoft YaHei UI", size, QFont.Weight.Bold))
            self.table.setStyleSheet(self._classifier_table_font_style(size))
            header_font = self.table.horizontalHeader().font()
            header_font.setPointSize(max(8, size - 1))
            header_font.setBold(True)
            self.table.horizontalHeader().setFont(header_font)
            self.table.verticalHeader().setDefaultSectionSize(max(size * 2 + 12, 34))
            for row in range(self.table.rowCount()):
                for column in range(self.table.columnCount()):
                    item = self.table.item(row, column)
                    if item is not None:
                        item_font = item.font()
                        item_font.setPointSize(size)
                        item.setFont(item_font)
            for row in range(self.table.rowCount()):
                widget = self.table.cellWidget(row, 5)
                if isinstance(widget, GroupCellButton):
                    widget.setFont(QFont("Microsoft YaHei UI", size, QFont.Weight.Bold))
                    widget.setStyleSheet(self._group_button_style(size))
            self.table.viewport().update()
        if hasattr(self, "report"):
            self.report.setFont(QFont("Microsoft YaHei UI", size, QFont.Weight.Bold))
            self.report.setStyleSheet(
                f"QTextEdit {{font-size:{size}pt;font-weight:bold;}}"
            )

    def set_shared_font_size(self, size: int) -> None:
        self._apply_shared_font_size(size)

    def _replace_report_text(self, text: str) -> None:
        if str(self.repository.get("report_format", "legacy")) == "grouped":
            self.report.setHtml(self._grouped_report_html(text))
            return
        cursor = self.report.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(text)
        cursor.endEditBlock()

    def edit_report_replacements(self) -> None:
        rules = self.repository.get("replace_rules", []) or []
        rows = [[rule.get("find", ""), rule.get("replace", "")] for rule in rules if isinstance(rule, dict)]

        def save(new_rows: list[list[Any]]) -> None:
            self.repository.set("replace_rules", [
                {"find": str(find), "replace": str(replace)}
                for find, replace in new_rows if str(find)
            ])

        EditableRulesDialog(
            "报告替换设置", ["查找", "替换为"], rows, save, ["", ""], self
        ).exec()

    def apply_report_replacements(self) -> None:
        rules = [
            rule for rule in (self.repository.get("replace_rules", []) or [])
            if isinstance(rule, dict) and str(rule.get("find", ""))
        ]
        if not rules:
            QMessageBox.information(self, "替换规则", "尚未配置替换规则，请先打开“替换设置”。")
            return
        report_format = str(self.repository.get("report_format", "legacy"))
        separator = "----" if self.repository.get("report_separator", "line") == "line" else ""
        output: list[str] = []
        changed = 0
        source_text = self._report_source_text()
        for line in source_text.splitlines(keepends=True):
            body = line.rstrip("\r\n")
            ending = line[len(body):]
            stripped = body.strip()
            if (
                not stripped
                or (stripped.startswith("【") and stripped.endswith("】" + ":"))
                or (separator and stripped == separator)
                or (report_format == "grouped" and stripped == "辈分\tA组\tB组\tC组\tD组")
            ):
                output.append(line)
                continue
            if report_format == "columns":
                parts = body.split("\t")
                if len(parts) < 3:
                    output.append(line)
                    continue
                original = parts[1]
                for rule in rules:
                    parts[1] = parts[1].replace(str(rule["find"]), str(rule.get("replace", "")))
                changed += int(parts[1] != original)
                output.append("\t".join(parts) + ending)
            elif report_format == "grouped":
                markdown_parts = self._split_markdown_row(body)
                if markdown_parts is not None and len(markdown_parts) >= 5:
                    if self._is_markdown_header(markdown_parts) or self._is_markdown_separator(markdown_parts):
                        output.append(line)
                        continue
                    row_changed = False
                    for index in range(1, 5):
                        original = markdown_parts[index]
                        for rule in rules:
                            markdown_parts[index] = markdown_parts[index].replace(
                                str(rule["find"]), str(rule.get("replace", ""))
                            )
                        row_changed = row_changed or markdown_parts[index] != original
                    changed += int(row_changed)
                    output.append(self._format_markdown_row(markdown_parts[:5]) + ending)
                    continue
                # Keep accepting reports generated by older versions.
                parts = body.split("\t")
                if len(parts) < 5:
                    output.append(line)
                    continue
                row_changed = False
                for index in range(1, 5):
                    original = parts[index]
                    for rule in rules:
                        parts[index] = parts[index].replace(str(rule["find"]), str(rule.get("replace", "")))
                    row_changed = row_changed or parts[index] != original
                changed += int(row_changed)
                output.append("\t".join(parts) + ending)
            else:
                original = body
                for rule in rules:
                    body = body.replace(str(rule["find"]), str(rule.get("replace", "")))
                changed += int(body != original)
                output.append(body + ending)
        new_text = "".join(output)
        if new_text != source_text:
            self._replace_report_text(new_text)
        self.statusChanged.emit("done", f"报告替换完成 · 修改 {changed} 行")

    def _parse_report_entries(self) -> list[dict[str, Any]]:
        report_format = str(self.repository.get("report_format", "legacy"))
        if report_format == "grouped":
            return self._parse_grouped_report_entries()
        separator = "----" if self.repository.get("report_separator", "line") == "line" else ""
        entries: list[dict[str, Any]] = []
        current_category = ""
        source_index = 0
        pending_blank_lines = 0
        for raw_line in self._report_source_text().splitlines():
            line = raw_line.strip()
            if not line:
                pending_blank_lines += 1
                continue
            if separator and line == separator:
                pending_blank_lines = max(1, pending_blank_lines)
                continue
            if line.startswith("【") and line.endswith("】:"):
                current_category = line[1:-2]
                pending_blank_lines = 0
                continue
            source = self.rows[source_index] if source_index < len(self.rows) else {}
            marker_blank_lines, _display_name = self._split_blank_line_markers(
                str(source.get("label", ""))
            )
            blank_lines_before = max(pending_blank_lines, marker_blank_lines)
            if report_format == "columns":
                parts = raw_line.split("\t")
                if len(parts) < 3:
                    continue
                entries.append({
                    "category": parts[0].strip() or current_category,
                    "name": parts[1].strip(),
                    "group": parts[2].strip() or "B",
                    "blank_lines_before": blank_lines_before,
                })
            else:
                entries.append({
                    "category": str(source.get("category", current_category or "未分类")),
                    "name": line,
                    "group": str(source.get("group", "B")),
                    "blank_lines_before": blank_lines_before,
                })
            source_index += 1
            pending_blank_lines = 0
        return entries

    def _parse_grouped_report_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        current_category = ""
        for raw_line in self._report_source_text().splitlines():
            markdown_parts = self._split_markdown_row(raw_line)
            if markdown_parts is not None and len(markdown_parts) >= 5:
                if self._is_markdown_header(markdown_parts) or self._is_markdown_separator(markdown_parts):
                    continue
                parts = markdown_parts[:5]
                category = parts[0].strip()
                if category:
                    current_category = category
                for group, cell in zip(("A", "C", "B", "D"), parts[1:5]):
                    for name in self._split_markdown_names(cell):
                        entries.append({
                            "category": current_category or "未分类",
                            "name": name,
                            "group": group,
                            "blank_lines_before": 0,
                        })
                continue
            if raw_line.strip() == "辈分\tA组\tB组\tC组\tD组":
                continue
            parts = raw_line.split("\t")
            if len(parts) < 5:
                continue
            category = parts[0].strip()
            if category:
                current_category = category
            for group, name in zip(("A", "B", "C", "D"), parts[1:5]):
                for name in self._split_markdown_names(name.strip()):
                    if not name:
                        continue
                    entries.append({
                        "category": current_category or "未分类",
                        "name": name,
                        "group": group,
                        "blank_lines_before": 0,
                    })
        return entries

    def _group_for_label(self, label: str) -> str:
        _marker_count, label = self._split_blank_line_markers(label)
        rules = self.repository.get("font_style_rules", {}) or {}
        for prefix, rule in rules.items():
            if not isinstance(rule, dict) or not rule.get("enabled", True):
                continue
            if str(label).lower().startswith(str(prefix).lower()):
                target = rule.get("target_group", "auto")
                if target in {"A", "B", "C", "D"}:
                    return target
                if target == "none":
                    return "B"
                if self._is_red_color(rule.get("color", "")):
                    return "A"
        return "B"

    @staticmethod
    def _is_red_color(color: Any) -> bool:
        return str(color or "").strip().upper() in {
            "#FF0000", "#FF0000FF", "RED", "#F00", "#CC0000",
            "#DC143C", "#B22222", "#8B0000",
        }

    def _build_advanced_menu(self) -> QMenu:
        menu = QMenu(self)
        self._populate_advanced_menu(menu)
        menu.aboutToShow.connect(lambda: self._populate_advanced_menu(menu))
        return menu

    def _populate_advanced_menu(self, menu: QMenu) -> None:
        menu.clear()
        menu.addAction("新增条目…", self.add_row)
        menu.addAction("编辑选中条目…", self.edit_selected_row)
        menu.addAction("复制选中条目", self.copy_selected_rows)
        menu.addAction("复制一份", self.duplicate_selected_rows)
        menu.addAction("标记／取消标记    Space", self.toggle_mark_selected)
        menu.addAction("删除选中条目", self.delete_rows)
        menu.addSeparator()
        menu.addAction("上移", lambda: self.move_row(-1))
        menu.addAction("下移", lambda: self.move_row(1))
        menu.addAction("合并选中行", self.merge_rows)
        menu.addSeparator()
        group_menu = menu.addMenu("修改选中项组值")
        for group in "ABCD":
            group_menu.addAction(f"改为 {group} 组", lambda _checked=False, value=group: self.set_selected_group(value))
        category_menu = menu.addMenu("分类操作")
        category_menu.addAction("重命名当前分类…", self.rename_selected_category)
        category_menu.addAction("查看当前分类统计", self.show_selected_category_stats)
        category_menu.addAction("更改当前分类颜色…", self.change_selected_category_color)
        batch_menu = category_menu.addMenu("整类修改组值")
        for group in "ABCD":
            batch_menu.addAction(f"整类改为 {group} 组", lambda _checked=False, value=group: self.set_category_group(value))
        menu.addSeparator()
        menu.addAction("拆分全部 A 组", self.split_group_a)
        menu.addAction("应用空格／清理规则", self.batch_cleanup)
        menu.addAction("清理直线和圈选分类", self.clear_line_and_lasso_classification)
        menu.addAction("恢复到本次解析初始状态", self.reset_to_parsed)
        menu.addSeparator()
        undo_action = menu.addAction("撤销    Ctrl+Z", self.undo)
        redo_action = menu.addAction("重做    Ctrl+Y", self.redo)
        undo_action.setEnabled(bool(self.undo_stack))
        redo_action.setEnabled(bool(self.redo_stack))

    def show_table_context_menu(self, position: QPoint) -> None:
        item = self.table.itemAt(position)
        if item is not None and item.row() not in self._selected_rows():
            self.table.selectRow(item.row())
        menu = QMenu(self.table)
        self._populate_advanced_menu(menu)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _row_dialog(self, title: str, initial: dict[str, Any] | None = None,
                    include_position: bool = False) -> tuple[dict[str, Any] | None, str]:
        initial = initial or {}
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        layout.addWidget(QLabel("名称"))
        name = QLineEdit(str(initial.get("label", "")))
        name.setMinimumHeight(38)
        name.setPlaceholderText("请输入条目名称")
        layout.addWidget(name)

        layout.addWidget(QLabel("分组"))
        group_row = QHBoxLayout()
        group_row.setSpacing(8)
        group_choice = QButtonGroup(dialog)
        group_choice.setExclusive(True)
        group_buttons: dict[str, QPushButton] = {}
        current_group = str(initial.get("group", "B"))
        for group_value in "ABCD":
            button = QPushButton(group_value)
            button.setCheckable(True)
            button.setMinimumHeight(36)
            button.setStyleSheet(
                "QPushButton { background:#F6F7F9;border:1px solid #E2E5E9;"
                "border-radius:7px;font-weight:700; }"
                f"QPushButton:checked {{ background:{YELLOW};border-color:{YELLOW}; }}"
            )
            button.setChecked(group_value == current_group)
            group_choice.addButton(button)
            group_buttons[group_value] = button
            group_row.addWidget(button, 1)
        if current_group not in group_buttons:
            group_buttons["B"].setChecked(True)
        layout.addLayout(group_row)

        common_grid = QGridLayout()
        common_grid.setHorizontalSpacing(12)
        common_grid.setVerticalSpacing(6)
        common_grid.addWidget(QLabel("分类"), 0, 0)
        category = QComboBox()
        category.setEditable(True)
        categories = list(dict.fromkeys(
            str(row.get("category", "")).strip()
            for row in self.rows if str(row.get("category", "")).strip()
        ))
        category.addItems(categories)
        category.setCurrentText(str(initial.get("category", "手动添加")))
        common_grid.addWidget(category, 1, 0)

        position = QComboBox()
        if include_position:
            common_grid.addWidget(QLabel("插入位置"), 0, 1)
            position.addItem("选中项之后", "after")
            position.addItem("选中项之前", "before")
            position.addItem("列表末尾", "end")
            common_grid.addWidget(position, 1, 1)
            common_grid.setColumnStretch(1, 1)
        common_grid.setColumnStretch(0, 1)
        layout.addLayout(common_grid)

        def number_box(value: Any, minimum: float, maximum: float) -> QDoubleSpinBox:
            box = QDoubleSpinBox()
            box.setRange(minimum, maximum)
            box.setDecimals(3)
            box.setValue(float(value or 0))
            return box

        y_value = number_box(initial.get("y", 0), -999999999, 999999999)
        x_value = number_box(initial.get("x", 0), -999999999, 999999999)
        height = number_box(initial.get("height", 0), 0, 999999999)
        confidence = number_box(initial.get("confidence", 100), 0, 100)
        confidence.setDecimals(1)
        confidence.setSuffix(" %")

        advanced_toggle = QPushButton()
        advanced_toggle.setCheckable(True)
        advanced_toggle.setChecked(not include_position)
        advanced_toggle.setStyleSheet(
            "text-align:left;border:0;background:transparent;padding:0;"
            "font-weight:700;color:#4B5563;"
        )
        advanced_panel = QWidget()
        advanced_grid = QGridLayout(advanced_panel)
        advanced_grid.setContentsMargins(0, 0, 0, 0)
        advanced_grid.setHorizontalSpacing(12)
        advanced_grid.setVerticalSpacing(6)
        for column, (label, widget) in enumerate((
            ("Y 坐标", y_value), ("X 坐标", x_value),
            ("高度", height), ("置信度", confidence),
        )):
            grid_row = (column // 2) * 2
            grid_column = column % 2
            advanced_grid.addWidget(QLabel(label), grid_row, grid_column)
            advanced_grid.addWidget(widget, grid_row + 1, grid_column)
            advanced_grid.setColumnStretch(grid_column, 1)

        def toggle_advanced(checked: bool) -> None:
            advanced_toggle.setText(
                "▾ 坐标与识别信息" if checked else "▸ 坐标与识别信息"
            )
            advanced_panel.setVisible(checked)
            QTimer.singleShot(0, dialog.adjustSize)

        advanced_toggle.toggled.connect(toggle_advanced)
        layout.addWidget(advanced_toggle)
        layout.addWidget(advanced_panel)
        toggle_advanced(advanced_toggle.isChecked())

        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_button = QPushButton("取消")
        submit_button = QPushButton("添加条目" if include_position else "保存修改")
        submit_button.setObjectName("primary")
        submit_button.setStyleSheet(
            f"background:{YELLOW};border-color:{YELLOW};font-weight:700;"
        )
        submit_button.setDefault(True)
        cancel_button.clicked.connect(dialog.reject)

        def accept_dialog() -> None:
            if not name.text().strip():
                QMessageBox.warning(dialog, "输入无效", "名称不能为空")
                name.setFocus()
                return
            dialog.accept()

        submit_button.clicked.connect(accept_dialog)
        button_row.addWidget(cancel_button)
        button_row.addWidget(submit_button)
        layout.addLayout(button_row)
        name.setFocus()
        name.selectAll()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None, ""
        label = name.text().strip()
        selected_group = next(
            (value for value, button in group_buttons.items() if button.isChecked()), "B"
        )
        result = {
            "label": label,
            "y": y_value.value(),
            "x": x_value.value(),
            "height": height.value(),
            "confidence": confidence.value(),
            "group": selected_group,
            "category": category.currentText().strip() or "未分类",
        }
        result["category_key"] = str(initial.get("category_key", result["category"]))
        if initial.get("marked", False):
            result["marked"] = True
        return result, str(position.currentData() or "end") if include_position else ""

    def edit_selected_row(self, *_args) -> None:
        indices = self._selected_rows()
        if len(indices) != 1:
            QMessageBox.information(self, "编辑条目", "请选择一条数据进行编辑")
            return
        index = indices[0]
        updated, _ = self._row_dialog("编辑分类条目", self.rows[index])
        if updated is None:
            return
        self._snapshot(redraw_plot=False)
        self.rows[index] = updated
        self._populate_results(redraw_plot=False)
        self._select_rows([index])

    def copy_selected_rows(self) -> None:
        indices = self._selected_rows()
        if not indices:
            QMessageBox.information(self, "复制条目", "请先选择要复制的数据")
            return
        lines = []
        for index in indices:
            row = self.rows[index]
            lines.append(
                f"{row.get('label', '')}|{float(row.get('y', 0)):g}|"
                f"{float(row.get('x', 0)):g}|{float(row.get('height', 0)):g}"
            )
        QApplication.clipboard().setText("\n".join(lines))
        self.statusChanged.emit("done", f"已复制 {len(lines)} 条分类数据")

    def duplicate_selected_rows(self) -> None:
        indices = self._selected_rows()
        if not indices:
            QMessageBox.information(self, "复制一份", "请先选择要复制的数据")
            return
        self._snapshot(redraw_plot=False)
        insert_at = indices[-1] + 1
        copies = [copy.deepcopy(self.rows[index]) for index in indices]
        self.rows[insert_at:insert_at] = copies
        self._populate_results(redraw_plot=False)
        self._select_rows(range(insert_at, insert_at + len(copies)))

    def toggle_mark_selected(self) -> None:
        indices = self._selected_rows()
        if not indices:
            return
        self._snapshot(redraw_plot=False)
        mark = not all(bool(self.rows[index].get("marked", False)) for index in indices)
        for index in indices:
            self.rows[index]["marked"] = mark
        self._populate_results(redraw_plot=False)
        self._select_rows(indices)
        action = "标记" if mark else "取消标记"
        self.statusChanged.emit("done", f"已{action} {len(indices)} 条数据")

    def _selected_category(self) -> str | None:
        indices = self._selected_rows()
        if not indices:
            QMessageBox.information(self, "分类操作", "请先选择分类中的一条数据")
            return None
        return str(self.rows[indices[0]].get("category", "未分类"))

    def rename_selected_category(self) -> None:
        old_name = self._selected_category()
        if old_name is None:
            return
        new_name, ok = QInputDialog.getText(self, "重命名分类", "新分类名称：", text=old_name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == old_name:
            return
        self._snapshot()
        changed = 0
        for row in self.rows:
            if str(row.get("category", "未分类")) == old_name:
                row["category"] = new_name
                changed += 1
        if old_name in self.category_colors:
            self.category_colors[new_name] = self.category_colors.pop(old_name)
            self.repository.set("qt_category_colors", self.category_colors)
        self._populate_results()
        self.statusChanged.emit("done", f"分类已重命名 · {changed} 条")

    def show_selected_category_stats(self) -> None:
        category = self._selected_category()
        if category is None:
            return
        rows = [row for row in self.rows if str(row.get("category", "未分类")) == category]
        groups = {group: sum(str(row.get("group", "")) == group for row in rows) for group in "ABCD"}
        confidences = [float(row.get("confidence", 0) or 0) for row in rows]
        average = sum(confidences) / len(confidences) if confidences else 0
        marked = sum(bool(row.get("marked", False)) for row in rows)
        QMessageBox.information(
            self, f"分类统计 · {category}",
            f"条目总数：{len(rows)}\n"
            f"A 组：{groups['A']}\nB 组：{groups['B']}\nC 组：{groups['C']}\nD 组：{groups['D']}\n"
            f"已标记：{marked}\n"
            f"平均置信度：{average:.1f}",
        )

    def change_selected_category_color(self) -> None:
        category = self._selected_category()
        if category is None:
            return
        current = QColor(self.category_colors.get(category, "#DDEBFF"))
        chosen = QColorDialog.getColor(current, self, f"分类颜色 · {category}")
        if not chosen.isValid():
            return
        self._snapshot()
        self.category_colors[category] = chosen.name()
        self.repository.set("qt_category_colors", self.category_colors)
        self._populate_results()
        self.statusChanged.emit("done", f"已更新分类“{category}”的颜色")

    def set_category_group(self, group: str) -> None:
        category = self._selected_category()
        if category is None:
            return
        targets = [row for row in self.rows if str(row.get("category", "未分类")) == category]
        changed = sum(str(row.get("group", "")) != group for row in targets)
        if not changed:
            self.statusChanged.emit("done", f"“{category}”已全部是 {group} 组")
            return
        if QMessageBox.question(
            self, "整类修改组值", f"将分类“{category}”中的 {len(targets)} 条数据全部改为 {group} 组吗？"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._snapshot(redraw_plot=False)
        for row in targets:
            row["group"] = group
        self._populate_results(redraw_plot=False)
        self.statusChanged.emit("done", f"整类改组完成 · {changed} 条 → {group} 组")

    def reset_to_parsed(self) -> None:
        if not self.parsed_snapshot:
            QMessageBox.information(self, "恢复初始状态", "当前没有可恢复的解析初始状态")
            return
        if self._capture_classifier_state() == self.parsed_snapshot:
            self.statusChanged.emit("done", "当前已经是解析初始状态")
            return
        if QMessageBox.question(
            self, "恢复初始状态", "确定放弃当前分类修改，恢复到本次 OCR／历史解析后的初始状态吗？"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._snapshot()
        self._restore_classifier_state(self.parsed_snapshot)
        self.statusChanged.emit("done", f"已恢复解析初始状态 · {len(self.rows)} 行")

    def _snapshot(self, thresholds: list[float] | None = None,
                  redraw_plot: bool = True) -> None:
        if (
            hasattr(self, "notice_undo_button")
            and self.notice_undo_button.isVisible()
            and self.lasso_undo_history
        ):
            self.notice_undo_button.hide()
        self.undo_stack.append(self._capture_classifier_state(thresholds, redraw_plot))
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self) -> None:
        if not self.undo_stack:
            self._show_top_notice("warning", "当前没有可撤销的分类操作。", 2600)
            return
        target_state = self.undo_stack[-1]
        current_state = self._capture_classifier_state(
            redraw_plot=bool(target_state.get("_redraw_plot", True))
        )
        lasso_record_index = next(
            (
                index for index in range(len(self.lasso_undo_history) - 1, -1, -1)
                if self.lasso_undo_history[index].get("after_state") == current_state
            ),
            -1,
        )
        lasso_record = self.lasso_undo_history[lasso_record_index] if lasso_record_index >= 0 else None
        self.redo_stack.append(current_state)
        self._restore_classifier_state(self.undo_stack.pop())
        if lasso_record is not None:
            self.lasso_undo_history.pop(lasso_record_index)
            message = (
                f"已撤销{lasso_record['category']}，恢复 {lasso_record['count']} 条数据。"
            )
            self._show_top_notice("success", message, 3800)
            self.statusChanged.emit("done", message.rstrip("。"))
        else:
            self._show_top_notice("info", "已撤销上一步分类操作。", 2600)

    def undo_last_lasso(self) -> None:
        if not self.lasso_undo_history:
            self._show_top_notice("warning", "当前没有可撤销的圈选操作。", 2600)
            return
        record = self.lasso_undo_history[-1]
        current_state = self._capture_classifier_state()
        if record.get("after_state") != current_state:
            self.notice_undo_button.hide()
            self._show_top_notice(
                "warning", "圈选后已有其他分类操作，请使用普通撤销逐步返回。", 3200
            )
            return
        self.undo()

    def redo(self) -> None:
        if not self.redo_stack:
            return
        target_state = self.redo_stack[-1]
        self.undo_stack.append(self._capture_classifier_state(
            redraw_plot=bool(target_state.get("_redraw_plot", True))
        ))
        self._restore_classifier_state(self.redo_stack.pop())

    def _select_rows(self, indices) -> None:
        self.table.clearSelection()
        selection = self.table.selectionModel()
        if selection is None:
            return
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        for index in indices:
            if 0 <= int(index) < self.table.rowCount():
                selection.select(self.table.model().index(int(index), 0), flags)

    def _selected_rows(self) -> list[int]:
        model = self.table.selectionModel()
        selected = sorted({index.row() for index in model.selectedRows()}) if model else []
        if not selected and 0 <= self.table.currentRow() < len(self.rows):
            selected = [self.table.currentRow()]
        return selected

    def _activate_group_shortcut(self, group: str) -> None:
        if self.result_stack.currentIndex() != 1:
            return
        if self._classifier_cell_editor_has_focus():
            return
        self.set_selected_group(group)

    def move_selection_cursor(self, direction: int) -> None:
        if self.result_stack.currentIndex() != 1:
            return
        if self._classifier_cell_editor_has_focus():
            return
        row_count = self.table.rowCount()
        if row_count <= 0:
            return
        selected = self._selected_rows()
        if selected:
            current = selected[0] if direction < 0 else selected[-1]
        else:
            current = self.table.currentRow()
        if current < 0:
            target = 0
        else:
            target = max(0, min(row_count - 1, current + direction))
        self._selection_anchor_row = target
        self._select_rows([target])
        self.table.setCurrentCell(target, 0)
        item = self.table.item(target, 0)
        if item is not None:
            self.table.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
        self._sync_verification_from_table()

    def add_row(self) -> None:
        selected = self._selected_rows()
        reference = self.rows[selected[-1]] if selected else {}
        initial = {
            "label": "",
            "y": reference.get("y", 0),
            "x": reference.get("x", 0),
            "height": reference.get("height", 0),
            "confidence": 100,
            "group": reference.get("group", "B"),
            "category": reference.get("category", "手动添加"),
            "category_key": reference.get("category_key", "数据区"),
        }
        new_row, position = self._row_dialog("新增分类条目", initial, include_position=True)
        if new_row is None:
            return
        for key in ("_source_index", "_source_line", "_source_path", "_source_file", "_source_rect"):
            if key in reference:
                new_row[key] = copy.deepcopy(reference[key])
        self._snapshot(redraw_plot=False)
        if not selected or position == "end":
            insert_at = len(self.rows)
        elif position == "before":
            insert_at = selected[0]
        else:
            insert_at = selected[-1] + 1
        self.rows.insert(insert_at, new_row)
        self._refresh_table_after_row_change()
        self._select_rows([insert_at])

    def delete_rows(self) -> None:
        indices = self._selected_rows()
        if not indices:
            return
        if QMessageBox.question(self, "确认删除", f"确定删除选中的 {len(indices)} 条数据吗？") != QMessageBox.StandardButton.Yes:
            return
        self._snapshot(redraw_plot=False)
        for index in reversed(indices):
            self.rows.pop(index)
        self._apply_classification_rules()
        self._refresh_table_after_row_change()

    def _swap_table_rows(self, first_row: int, second_row: int) -> None:
        first_items = [self.table.takeItem(first_row, column) for column in range(self.table.columnCount())]
        second_items = [self.table.takeItem(second_row, column) for column in range(self.table.columnCount())]
        for column, item in enumerate(second_items):
            if item is not None:
                self.table.setItem(first_row, column, item)
        for column, item in enumerate(first_items):
            if item is not None:
                self.table.setItem(second_row, column, item)

    def move_row(self, direction: int) -> None:
        indices = self._selected_rows()
        if not indices:
            QMessageBox.information(self, "提示", "请先选择要移动的数据")
            return
        if direction < 0 and indices[0] == 0:
            return
        if direction > 0 and indices[-1] == len(self.rows) - 1:
            return
        self._snapshot(redraw_plot=False)
        iteration = indices if direction < 0 else list(reversed(indices))
        affected_rows: set[int] = set()
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        for old in iteration:
            new = old + direction
            self.rows[old], self.rows[new] = self.rows[new], self.rows[old]
            self._swap_table_rows(old, new)
            affected_rows.update((old, new))
        for row_index in sorted(affected_rows):
            self.table.setCellWidget(
                row_index, 5,
                self._create_group_button(
                    row_index, str(self.rows[row_index].get("group", "B"))
                ),
            )
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.table.viewport().update()
        new_indices = [index + direction for index in indices]
        self._select_rows(new_indices)
        self._update_report()
        direction_text = "上移" if direction < 0 else "下移"
        self.statusChanged.emit("done", f"已{direction_text} {len(indices)} 条分类数据")

    def reorder_rows(self, indices: list[int], target: int) -> None:
        indices = sorted({index for index in indices if 0 <= index < len(self.rows)})
        if not indices:
            return
        moved = [self.rows[index] for index in indices]
        selected_set = set(indices)
        remainder = [row for index, row in enumerate(self.rows) if index not in selected_set]
        insert_at = max(0, min(len(remainder), target - sum(index < target for index in indices)))
        candidate = remainder[:insert_at] + moved + remainder[insert_at:]
        if candidate == self.rows:
            self._select_rows(indices)
            return
        self._snapshot(redraw_plot=False)
        self.rows = candidate
        self._populate_results(redraw_plot=False)
        self._select_rows(range(insert_at, insert_at + len(moved)))
        self.statusChanged.emit("done", f"已移动 {len(moved)} 条分类数据")

    def merge_rows(self) -> None:
        indices = self._selected_rows()
        if len(indices) < 2:
            QMessageBox.information(self, "提示", "请至少选择两行进行合并")
            return
        self._snapshot(redraw_plot=False)
        chosen = [self.rows[index] for index in indices]
        merged = copy.deepcopy(chosen[0])
        merged["label"] = "".join(str(row["label"]) for row in chosen)
        merged["confidence"] = round(sum(float(row["confidence"]) for row in chosen) / len(chosen))
        merged["category"] = chosen[0].get("category", "未分类")
        for index in reversed(indices):
            self.rows.pop(index)
        self.rows.insert(indices[0], merged)
        self._apply_classification_rules()
        self._refresh_table_after_row_change()
        self._select_rows([indices[0]])

    def set_selected_group(self, group: str) -> None:
        indices = self._selected_rows()
        if not indices:
            return
        changed_indices = [
            index for index in indices if str(self.rows[index].get("group", "")) != group
        ]
        if not changed_indices:
            self.statusChanged.emit("done", f"选中数据已经全部是 {group} 组")
            return
        self._snapshot(redraw_plot=False)
        self.table.blockSignals(True)
        for index in changed_indices:
            self.rows[index]["group"] = group
            group_item = self.table.item(index, 5)
            if group_item is not None:
                group_item.setText(group)
            group_widget = self.table.cellWidget(index, 5)
            if isinstance(group_widget, GroupCellButton):
                group_widget.blockSignals(True)
                group_widget.setCurrentText(group)
                group_widget.blockSignals(False)
            label_item = self.table.item(index, 0)
            if label_item is not None and not self._font_style_for_label(str(self.rows[index].get("label", ""))):
                label_item.setForeground(QColor(GROUP_C_GREEN if group == "C" else "#17191C"))
        self.table.blockSignals(False)
        self.table.viewport().update()
        self._select_rows(indices)
        self._update_report()
        self.statusChanged.emit("done", f"已将 {len(changed_indices)} 条数据设置为 {group} 组")

    def classify_thresholds(self, thresholds: list[float], previous: list[float] | None = None) -> None:
        if not self.rows:
            return
        self._snapshot(previous)
        self.plot.thresholds = sorted(float(value) for value in thresholds)
        # A threshold changes only category assignments.  Keep the existing
        # row/cell widgets intact and update the affected values in place.
        self._apply_classification_rules(reorder=False)
        self._sync_table_classifications()
        self._sort_table_by_category()
        self.plot.sync_row_styles(self.rows, self.category_colors)
        y_values = [float(row.get("y", 0) or 0) for row in self.rows]
        categories = list(dict.fromkeys(str(row.get("category", "5")) for row in self.rows))
        if len(set(y_values)) <= 1:
            coordinate = f"Y={y_values[0]:g}" if y_values else "无坐标"
            self.statusChanged.emit(
                "error", f"无法按线分区：全部文字坐标相同（{coordinate}）"
            )
        elif len(categories) <= 1 and thresholds:
            self.statusChanged.emit("done", "分割线未穿过文字坐标范围，当前仍为分类 5")
        else:
            self.statusChanged.emit(
                "done", f"已按 {len(thresholds)} 条分割线生成 {len(categories)} 个有效分类"
            )

    def classify_lasso(self, indices: list[int]) -> None:
        if not indices:
            self._show_top_notice("warning", "圈选区域内没有文字，请扩大圈选范围后重试。")
            self.statusChanged.emit("done", "圈选未命中文字")
            return
        self._snapshot()
        self.lasso_count += 1
        category = f"圈选提取 {self.lasso_count}"
        ordered = sorted(indices, key=lambda index: (-self.rows[index]["x"], self.rows[index]["y"]))
        for index in ordered:
            self.rows[index]["category_key"] = category
        self.lasso_categories.insert(0, category)
        # Keep the lasso selection order together at the front, matching the
        # legacy classifier's extraction behavior.
        selected = [self.rows[index] for index in ordered]
        selected_ids = set(indices)
        remainder = [row for index, row in enumerate(self.rows) if index not in selected_ids]
        self.rows = selected + remainder
        self._apply_classification_rules()
        self._populate_results()
        selected_rows = [
            index for index, row in enumerate(self.rows)
            if str(row.get("category_key", "")) == category
        ]
        self._select_rows(selected_rows)
        display_categories = list(dict.fromkeys(str(row.get("category", "")) for row in selected))
        display_text = "、".join(value for value in display_categories if value) or "未分类"
        self.lasso_undo_history.append({
            "category": category,
            "count": len(selected),
            "after_state": self._capture_classifier_state(),
        })
        if len(self.lasso_undo_history) > 30:
            self.lasso_undo_history.pop(0)
        message = f"圈选完成：{category}，共 {len(selected)} 条，已归入分类 {display_text}。"
        self._show_top_notice("success", message, undo_available=True)
        self.statusChanged.emit("done", f"{category} · {len(selected)} 条 · 分类 {display_text}")

    def split_group_a(self) -> None:
        targets = sum(row.get("group") == "A" and len(str(row.get("label", ""))) > 2 for row in self.rows)
        if not targets:
            QMessageBox.information(self, "拆分A组", "没有需要拆分的 A 组项目")
            return
        self._snapshot(redraw_plot=False)
        output: list[dict[str, Any]] = []
        for row in self.rows:
            label = str(row.get("label", ""))
            if row.get("group") == "A" and len(label) > 2:
                first = copy.deepcopy(row)
                second = copy.deepcopy(row)
                first["label"] = label[:2]
                first["group"] = "A"
                second["label"] = label[2:]
                second["group"] = "C"
                second["x"] = float(second.get("x", 0)) + 10
                output.extend([first, second])
            else:
                output.append(row)
        self.rows = output
        self._refresh_table_after_row_change()
        QMessageBox.information(self, "拆分完成", f"已拆分 {targets} 个 A 组项目")

    def batch_cleanup(self) -> None:
        if not self.rows:
            return
        self._snapshot(redraw_plot=False)
        filters = [str(value) for value in (self.repository.get("filter_rules", []) or []) if str(value)]
        replacements = self.repository.get("replace_rules", []) or []
        presets = self.repository.get("space_presets", {}) or {}
        tokens: list[str] = []
        for preset in presets.values():
            raw = str(preset.get("custom_chars", "")) if isinstance(preset, dict) else ""
            tokens.extend(value for value in re.split(r"[|,\s，]+", raw) if len(value.strip()) == 2)
        changed = 0
        changed_row_ids: set[int] = set()
        previous_classifications = {
            id(row): (str(row.get("category", "")), str(row.get("category_key", "")))
            for row in self.rows
        }
        output = []
        for row in self.rows:
            original = str(row.get("label", ""))
            label = original
            is_lasso = str(row.get("category_key", "")).startswith("圈选提取")
            for rule in replacements:
                if isinstance(rule, dict) and rule.get("find"):
                    label = label.replace(str(rule["find"]), str(rule.get("replace", "")))
            if not is_lasso:
                for token in tokens:
                    label = label.replace(token, f"{token[0]} {token[1]}")
                for value in filters:
                    label = label.replace(value, "")
                label = re.sub(r"\s+", " ", label).strip()
            if label != original:
                changed += 1
                changed_row_ids.add(id(row))
            if label:
                row["label"] = label
                row["group"] = self._group_for_label(label) if row.get("group") not in {"C", "D"} else row["group"]
                output.append(row)
        removed = len(self.rows) - len(output)
        self.rows = output
        # Cleanup does not move coordinates, so retain the existing row order.
        # This lets the table keep its cell widgets instead of recreating them.
        self._apply_classification_rules(reorder=False)
        for row in self.rows:
            if previous_classifications.get(id(row)) != (
                str(row.get("category", "")), str(row.get("category_key", ""))
            ):
                changed_row_ids.add(id(row))
        self._refresh_table_after_row_change(changed_row_ids)
        QMessageBox.information(self, "批量整理完成", f"已修改 {changed} 条，移除空白项 {removed} 条")

    def _report_export_filename(self, suffix: str) -> str:
        book_name = self.book_name.text().strip() or "未命名书籍"
        safe_book_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", book_name).rstrip(". ")
        safe_book_name = safe_book_name or "未命名书籍"
        return f"{safe_book_name}{self.book_page.value() - 1}{suffix}"

    def _direct_export_path(self, filename: str) -> Path | None:
        configured = str(self.repository.get("export_save_path", "") or "").strip()
        if not configured:
            QMessageBox.warning(
                self, "未设置导出目录", "请先在“设置”中配置导出文件目录。"
            )
            return None
        directory = Path(configured).expanduser()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.critical(self, "导出目录不可用", str(exc))
            return None
        return directory / filename

    def _show_file_toast(self, path: str | Path, title: str = "导出成功") -> None:
        previous = getattr(self, "_export_toast", None)
        if previous is not None:
            previous.close()
            previous.deleteLater()
        export_path = Path(path)
        host = self.window()
        toast = QFrame(host)
        toast.setObjectName("exportToast")
        toast.setFixedWidth(400)
        toast.setStyleSheet(
            "QFrame#exportToast { background:#ECFDF5;border:1px solid #A7E8CC;"
            "border-radius:12px; }"
            "QLabel { background:transparent;border:0; }"
            "QPushButton { background:#FFFFFF;color:#137A4A;border:1px solid #A7E8CC;"
            "min-height:30px;padding:0 10px; }"
        )
        toast_layout = QHBoxLayout(toast)
        toast_layout.setContentsMargins(14, 12, 12, 12)
        icon = QLabel("✓")
        icon.setStyleSheet("color:#16A269;font-size:24px;font-weight:700;")
        message = QLabel(
            f"<b>{title}</b><br>{export_path.name}<br>"
            f"<span style='color:#5F6B66'>{export_path.parent}</span>"
        )
        message.setWordWrap(True)
        open_button = QPushButton("打开目录")
        open_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(export_path.parent)))
        )
        toast_layout.addWidget(icon)
        toast_layout.addWidget(message, 1)
        toast_layout.addWidget(open_button)
        toast.adjustSize()
        toast.move(
            max(12, host.width() - toast.width() - 24),
            max(12, host.height() - toast.height() - 24),
        )
        toast.show()
        toast.raise_()
        timer = QTimer(toast)
        timer.setSingleShot(True)
        timer.timeout.connect(toast.close)
        timer.start(4200)
        toast._close_timer = timer
        self._export_toast = toast

    def export_txt(self) -> None:
        content = self._report_source_text()
        if not content.strip():
            QMessageBox.warning(self, "无法导出", "当前文本报告为空。")
            return
        path = self._direct_export_path(self._report_export_filename(".txt"))
        if path is None:
            return
        try:
            path.write_text(content, encoding="utf-8")
            self.repository.save_export_record(str(path), content)
            self.statusChanged.emit("done", f"文本报告已导出 · {path.name}")
            self._show_file_toast(path)
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    @staticmethod
    def _merge_adjacent_report_entries(
        entries: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Merge only consecutive entries with the same category and group.
        
        Exception: Group A entries are never merged - each A entry stays in its own row.
        """
        merged_entries: list[dict[str, str]] = []
        for entry in entries:
            category = str(entry.get("category", ""))
            name = str(entry.get("name", ""))
            group = str(entry.get("group", ""))
            blank_lines = max(0, int(entry.get("blank_lines_before", 0) or 0))
            
            # A组记录永远不合并，每条独占一行
            if group == "A":
                merged_entries.append({
                    "category": category,
                    "name": name,
                    "group": group,
                })
            elif (
                merged_entries
                and merged_entries[-1]["category"] == category
                and merged_entries[-1]["group"] == group
            ):
                merged_entries[-1]["name"] += "\n" * (blank_lines + 1) + name
            else:
                merged_entries.append({
                    "category": category,
                    "name": name,
                    "group": group,
                })
        return merged_entries

    def show_excel_export_menu(self) -> None:
        """显示Excel导出格式选择菜单"""
        menu = QMenu(self)

        default_format = self._default_excel_export_format()
        default_action = menu.addAction(
            f"按默认格式导出：{EXCEL_EXPORT_FORMAT_SHORT_NAMES[default_format]}"
        )
        default_action.triggered.connect(lambda: self.export_report_excel())
        menu.addSeparator()

        action1 = menu.addAction(EXCEL_EXPORT_FORMAT_NAMES["standard"])
        action1.triggered.connect(lambda: self.export_report_excel("standard"))

        action2 = menu.addAction(EXCEL_EXPORT_FORMAT_NAMES["grouped"])
        action2.triggered.connect(lambda: self.export_report_excel("grouped"))

        # 在按钮下方显示菜单
        button = self.sender()
        if isinstance(button, QPushButton):
            menu.exec(button.mapToGlobal(QPoint(0, button.height())))
        else:
            menu.exec(QCursor.pos())

    def _default_excel_export_format(self) -> str:
        configured = str(self.repository.get("excel_export_format", "grouped") or "grouped")
        return configured if configured in EXCEL_EXPORT_FORMAT_NAMES else "grouped"

    def export_report_excel(self, export_format: str | None = None) -> None:
        """导出Excel，支持多种格式

        Args:
            export_format: "standard" 或 "grouped"；省略时使用设置中的默认格式
        """
        if export_format not in EXCEL_EXPORT_FORMAT_NAMES:
            export_format = self._default_excel_export_format()
        entries = self._parse_report_entries()
        if not entries:
            QMessageBox.warning(self, "无法导出", "当前报告中没有可导出的条目。")
            return
        
        if export_format == "grouped":
            self._export_excel_grouped_format(entries)
        else:
            self._export_excel_standard_format(entries)

    def _export_excel_standard_format(self, entries: list[dict[str, Any]]) -> None:
        """标准格式：分类 | 名称 | 组值"""
        issues = []
        for index, entry in enumerate(entries, start=1):
            style = self._font_style_for_label(entry["name"]) or {}
            if self._is_red_color(style.get("color", "")) and entry["group"] != "A":
                issues.append(f"第 {index} 行：{entry['name']}（组 {entry['group']}）")
        if issues:
            preview = "\n".join(issues[:12])
            if len(issues) > 12:
                preview += f"\n……还有 {len(issues) - 12} 行"
            result = QMessageBox.question(
                self, "导出前检查",
                f"发现 {len(issues)} 行名称按规则显示为红色，但组值不是 A：\n\n{preview}\n\n是否继续导出？"
            )
            if result != QMessageBox.StandardButton.Yes:
                return
        path = self._direct_export_path(self._report_export_filename(".xlsx"))
        if path is None:
            return
        try:
            import pandas as pd

            # A later non-adjacent run with the same values remains a new row.
            merged_entries = self._merge_adjacent_report_entries(entries)

            frame = pd.DataFrame([
                {"分类": entry["category"], "名称": entry["name"], "组值": entry["group"]}
                for entry in merged_entries
            ])
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                frame.to_excel(writer, index=False)
                sheet = writer.sheets["Sheet1"]
                from openpyxl.styles import Alignment, Font

                for cell in sheet[1]:
                    cell.font = Font(bold=True)
                for row_cells in sheet.iter_rows():
                    for cell in row_cells:
                        cell.alignment = Alignment(wrap_text=True, vertical="top")
                for column, width in {"A": 14, "B": 60, "C": 10}.items():
                    sheet.column_dimensions[column].width = width
                for row_number, entry in enumerate(merged_entries, start=2):
                    line_count = max(1, entry["name"].count("\n") + 1)
                    sheet.row_dimensions[row_number].height = max(20, line_count * 18)
            self.repository.save_export_record(str(path), self._report_source_text())
            self.save_classifier_history(notify=False)
            self.statusChanged.emit(
                "done", f"报告 Excel 已导出（标准格式） · {len(entries)} 条合并为 {len(merged_entries)} 组"
            )
            self._show_file_toast(path)
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _grouped_excel_rows(self, entries: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Build the rows shared by the grouped Excel export and its preview."""
        grouped_rows: list[dict[str, str]] = []
        current_row = {
            "辈分": "", "t1(A组)": "", "t2(C组)": "", "t3(B组)": "", "d(D组)": "",
        }
        for entry in entries:
            group = str(entry.get("group", ""))
            name = str(entry.get("name", ""))
            category = str(entry.get("category", ""))
            if group == "A":
                # The first A group claims any preceding C/B/D values, matching the export layout.
                if current_row["t1(A组)"]:
                    grouped_rows.append(current_row.copy())
                    current_row = {
                        "辈分": "", "t1(A组)": "", "t2(C组)": "", "t3(B组)": "", "d(D组)": "",
                    }
                current_row["辈分"] = category
                current_row["t1(A组)"] = name
            elif group == "C":
                current_row["t2(C组)"] = "\n".join(
                    value for value in (current_row["t2(C组)"], name) if value
                )
            elif group == "B":
                current_row["t3(B组)"] = "\n".join(
                    value for value in (current_row["t3(B组)"], name) if value
                )
            elif group == "D":
                current_row["d(D组)"] = "\n".join(
                    value for value in (current_row["d(D组)"], name) if value
                )
        if any(current_row.values()):
            grouped_rows.append(current_row.copy())
        return grouped_rows

    def _export_excel_grouped_format(self, entries: list[dict[str, Any]]) -> None:
        """分组格式：辈分 | t1(A组) | t2(C组) | t3(B组) | d(D组)
        
        每遇到一个A组就新建一行，同一行的C、B、D组填入对应列
        辈分使用软件中的分类值；各组内容保持文本报告中的原始文本和换行。
        因此 D 组名称中已有的 | 会原样导出，导出过程不会自行添加 |。
        """
        path = self._direct_export_path(self._report_export_filename("_分组格式.xlsx"))
        if path is None:
            return
        
        try:
            import pandas as pd
            from openpyxl.styles import Alignment, Font, Border, Side
            
            grouped_rows = self._grouped_excel_rows(entries)
            
            if not grouped_rows:
                QMessageBox.warning(self, "导出失败", "没有可导出的数据（至少需要一个A组记录）")
                return
            
            # 创建DataFrame
            frame = pd.DataFrame(grouped_rows)
            
            # 写入Excel
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                frame.to_excel(writer, index=False)
                sheet = writer.sheets["Sheet1"]
                
                # 设置样式
                thin_border = Border(
                    left=Side(style='thin'),
                    right=Side(style='thin'),
                    top=Side(style='thin'),
                    bottom=Side(style='thin')
                )
                
                # 表头样式
                for cell in sheet[1]:
                    cell.font = Font(bold=True, size=11)
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                    cell.border = thin_border
                
                # 数据单元格样式和边框
                for row_cells in sheet.iter_rows(min_row=2):
                    for cell in row_cells:
                        cell.alignment = Alignment(wrap_text=True, vertical="top", horizontal="left")
                        cell.border = thin_border
                
                # 设置列宽
                sheet.column_dimensions["A"].width = 6   # 辈分
                sheet.column_dimensions["B"].width = 20  # t1(A组)
                sheet.column_dimensions["C"].width = 30  # t2(C组)
                sheet.column_dimensions["D"].width = 30  # t3(B组)
                sheet.column_dimensions["E"].width = 30  # d(D组)
                
                # 动态设置行高
                for row_number in range(2, len(grouped_rows) + 2):
                    max_lines = 1
                    for col in ["B", "C", "D", "E"]:
                        cell_value = str(sheet[f"{col}{row_number}"].value or "")
                        lines = max(1, cell_value.count("\n") + 1)
                        max_lines = max(max_lines, lines)
                    sheet.row_dimensions[row_number].height = max(20, max_lines * 18)
            
            self.repository.save_export_record(str(path), self._report_source_text())
            self.save_classifier_history(notify=False)
            self.statusChanged.emit(
                "done", f"报告 Excel 已导出（分组格式） · {len(entries)} 条 → {len(grouped_rows)} 行"
            )
            self._show_file_toast(path)
            
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def show_export_history(self) -> None:
        ExportHistoryDialog(self.repository, self).exec()

    def convert_report(self, mode: str) -> None:
        try:
            import opencc
            converter = opencc.OpenCC(mode)
            source_text = self._report_source_text()
            converted = converter.convert(source_text)
            if converted != source_text:
                self._replace_report_text(converted)
        except ImportError:
            QMessageBox.warning(self, "缺少组件", "请安装 opencc-python-reimplemented")

    def merge_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择要拼接的图片", "", "图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)")
        if len(paths) < 2:
            if paths:
                QMessageBox.warning(self, "提示", "请至少选择两张图片进行拼接")
            return
        try:
            images = []
            for path in paths:
                reader = QImageReader(path)
                reader.setAutoTransform(True)
                image = reader.read()
                if image.isNull():
                    raise OSError(f"无法读取图片：{path}\n{reader.errorString()}")
                images.append(QPixmap.fromImage(image))
            dialog = MergePreviewDialog(
                self.repository, images, "file", paths, self.mode, False, self
            )
            if dialog.exec() == QDialog.DialogCode.Accepted and dialog.output_path:
                self.mode = dialog.selected_mode
                self.mode_buttons[self.mode].setChecked(True)
                self.set_files([dialog.output_path])
                self._show_file_toast(dialog.output_path, "图片拼接成功")
                self.statusChanged.emit("done", f"拼接图片已导入 · {dialog.merged.width()}×{dialog.merged.height()}")
        except Exception as exc:
            QMessageBox.critical(self, "拼接失败", str(exc))

    def crop_image(self) -> None:
        start_dir = str(Path(self.paths[0]).parent) if self.paths else ""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择要裁剪的图片",
            start_dir,
            "图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)",
        )
        if not paths:
            return
        try:
            crop_dialog = MultiCropDialog(paths, self)
            if crop_dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if not crop_dialog.result_images:
                QMessageBox.warning(self, "无法裁剪", "请至少框选一个裁剪区域")
                return
            preview = MergePreviewDialog(
                self.repository,
                crop_dialog.result_images,
                "crop",
                paths,
                self.mode,
                False,
                self,
            )
            if preview.exec() == QDialog.DialogCode.Accepted and preview.output_path:
                self.mode = preview.selected_mode
                self.mode_buttons[self.mode].setChecked(True)
                self.set_files([preview.output_path])
                self._show_file_toast(preview.output_path, "裁剪拼接成功")
                self.statusChanged.emit(
                    "done",
                    f"裁剪拼接已导入 · {len(crop_dialog.result_images)} 个区域",
                )
        except Exception as exc:
            QMessageBox.critical(self, "裁剪失败", str(exc))

    def capture_screen(self) -> None:
        window = self.window()
        window.hide()

        def do_capture() -> None:
            overlay = ContinuousScreenshotOverlay()
            result = overlay.exec()
            captures = [QPixmap(image) for image in overlay.captures]
            window.show()
            window.raise_()
            window.activateWindow()
            if result != QDialog.DialogCode.Accepted or not captures:
                return
            session = ScreenshotSessionDialog(window)
            session.load_captures(captures)
            if session.exec() != QDialog.DialogCode.Accepted:
                return
            preview = MergePreviewDialog(
                self.repository, session.captures, "screenshot", [], self.mode, True, self
            )
            if preview.exec() == QDialog.DialogCode.Accepted and preview.output_path:
                self.mode = preview.selected_mode
                self.mode_buttons[self.mode].setChecked(True)
                self.set_files([preview.output_path])
                self._show_file_toast(preview.output_path, "截图拼接成功")
                self.statusChanged.emit("done", f"截图拼接已导入 · {len(session.captures)} 张")

        QTimer.singleShot(350, do_capture)


class HomeMonthlyChart(FigureCanvasQTAgg):
    """Current-month grouped stacked bars used by the home dashboard."""

    SERIES = [
        ("accurate_api", "高精度接口", "#0F5CC0"),
        ("accurate_cache", "高精度缓存", "#38BDF8"),
        ("general_api", "通用接口", "#7C3AED"),
        ("general_cache", "通用缓存", "#A78BFA"),
    ]

    def __init__(self) -> None:
        self.figure = Figure(figsize=(9, 3.3), dpi=100, facecolor="white")
        self.axes = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setMinimumHeight(280)
        self.rows: list[dict[str, Any]] = []
        self.annotation = None
        self.mpl_connect("motion_notify_event", self._hovered)

    def render(self, stats: dict[str, Any], month: str) -> None:
        self.axes.clear()
        today = datetime.now()
        # 当前月月初也保留 15 天的横轴空间，15 日后随日期逐日增加。
        day_count = max(15, today.day) if month == today.strftime("%Y-%m") else 31
        self.rows = []
        for day_number in range(1, day_count + 1):
            date_key = f"{month}-{day_number:02d}"
            day_data = stats.get(date_key, {}) or {}
            accurate = day_data.get("accurate", {}) or {}
            general = day_data.get("general", {}) or {}
            self.rows.append({
                "date": date_key,
                "label": str(day_number),
                "accurate_api": int(accurate.get("success", 0) or 0),
                "accurate_cache": int(accurate.get("cached", 0) or 0),
                "general_api": int(general.get("success", 0) or 0),
                "general_cache": int(general.get("cached", 0) or 0),
            })

        xs = list(range(len(self.rows)))
        bar_width = .34
        accurate_xs = [value - bar_width / 2 for value in xs]
        general_xs = [value + bar_width / 2 for value in xs]
        accurate_api = [row["accurate_api"] for row in self.rows]
        accurate_cache = [row["accurate_cache"] for row in self.rows]
        general_api = [row["general_api"] for row in self.rows]
        general_cache = [row["general_cache"] for row in self.rows]
        self.axes.bar(
            accurate_xs, accurate_api, bar_width, color="#0F5CC0",
            edgecolor="white", linewidth=.5,
            label=f"高精度接口（{sum(accurate_api)}）",
        )
        self.axes.bar(
            accurate_xs, accurate_cache, bar_width, bottom=accurate_api,
            color="#38BDF8", edgecolor="white", linewidth=.5,
            label=f"高精度缓存（{sum(accurate_cache)}）",
        )
        self.axes.bar(
            general_xs, general_api, bar_width, color="#7C3AED",
            edgecolor="white", linewidth=.5,
            label=f"通用接口（{sum(general_api)}）",
        )
        self.axes.bar(
            general_xs, general_cache, bar_width, bottom=general_api,
            color="#A78BFA", edgecolor="white", linewidth=.5,
            label=f"通用缓存（{sum(general_cache)}）",
        )

        self.axes.set_axis_on()
        self.axes.set_ylabel("次数", fontsize=9)
        self.axes.set_ylim(bottom=0)
        current_top = self.axes.get_ylim()[1]
        self.axes.set_ylim(0, max(1, current_top * 1.18))
        if self.rows:
            self.axes.set_xlim(-.7, len(self.rows) - .3)
        self.axes.yaxis.get_major_locator().set_params(integer=True)
        self.axes.grid(True, axis="y", linestyle="--", linewidth=.7, alpha=.22)
        self.axes.set_axisbelow(True)
        self.axes.spines[["top", "right"]].set_visible(False)
        self.axes.spines[["left", "bottom"]].set_color("#CBD5E1")
        tick_step = max(1, len(self.rows) // 10)
        tick_positions = list(range(0, len(self.rows), tick_step))
        if self.rows and tick_positions[-1] != len(self.rows) - 1:
            tick_positions.append(len(self.rows) - 1)
        self.axes.set_xticks(tick_positions)
        self.axes.set_xticklabels(
            [self.rows[index]["label"] for index in tick_positions], fontsize=8
        )
        self.axes.set_xlabel(f"{month}（日）", fontsize=9)
        self.axes.legend(loc="upper left", frameon=False, ncol=4, fontsize=8)
        if not any(
            row[key]
            for row in self.rows
            for key, _label, _color in self.SERIES
        ):
            self.axes.text(
                .5, .5, "本月暂无调用数据", ha="center", va="center",
                color="#9CA3AF", transform=self.axes.transAxes, fontsize=12,
            )
        self.annotation = self.axes.annotate(
            "", xy=(0, 0), xytext=(12, 14), textcoords="offset points",
            bbox={"boxstyle": "round,pad=.45", "fc": "white", "ec": "#CBD5E1"},
            fontsize=9, annotation_clip=False, zorder=20,
        )
        self.annotation.set_visible(False)
        self.figure.tight_layout(pad=1.2)
        self.draw_idle()

    def _hovered(self, event) -> None:
        if self.annotation is None:
            return
        if event.inaxes != self.axes or event.xdata is None or not self.rows:
            if self.annotation.get_visible():
                self.annotation.set_visible(False)
                self.draw_idle()
            return
        index = int(round(event.xdata))
        if not 0 <= index < len(self.rows) or abs(event.xdata - index) > .45:
            if self.annotation.get_visible():
                self.annotation.set_visible(False)
                self.draw_idle()
            return
        row = self.rows[index]
        accurate_total = row["accurate_api"] + row["accurate_cache"]
        general_total = row["general_api"] + row["general_cache"]
        bar_top = max(accurate_total, general_total)
        self.annotation.xy = (index, bar_top)
        y_min, y_max = self.axes.get_ylim()
        near_top = bar_top >= y_min + (y_max - y_min) * .68
        near_right = index >= len(self.rows) - 2
        self.annotation.set_position((
            -12 if near_right else 12,
            -14 if near_top else 14,
        ))
        self.annotation.set_horizontalalignment("right" if near_right else "left")
        self.annotation.set_verticalalignment("top" if near_top else "bottom")
        self.annotation.set_text(
            f"{row['date']}\n"
            f"高精度：接口 {row['accurate_api']} / 缓存 {row['accurate_cache']}\n"
            f"通用：接口 {row['general_api']} / 缓存 {row['general_cache']}"
        )
        self.annotation.set_visible(True)
        self.draw_idle()


class HomePage(QWidget):
    def __init__(self, repository: Repository) -> None:
        super().__init__()
        self.repository = repository
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 28)
        title_row = QHBoxLayout()
        title = QLabel("OCR 使用概览")
        title.setStyleSheet("font-size:26px;font-weight:700;")
        title_row.addWidget(title)
        title_row.addStretch()
        self.period_label = muted_label("")
        title_row.addWidget(self.period_label)
        layout.addLayout(title_row)
        layout.addWidget(muted_label("接口调用不包含缓存复用；缓存复用按高精度与通用分别统计。"))

        cards = QGridLayout()
        cards.setHorizontalSpacing(10)
        cards.setVerticalSpacing(10)
        self.stat_values: dict[str, QLabel] = {}
        definitions = [
            ("today_accurate", "今日高精度调用"),
            ("today_general", "今日通用调用"),
            ("today_accurate_cache", "今日高精度缓存"),
            ("today_general_cache", "今日通用缓存"),
            ("month_accurate", "本月高精度调用"),
            ("month_general", "本月通用调用"),
            ("month_accurate_cache", "本月高精度缓存"),
            ("month_general_cache", "本月通用缓存"),
            ("remaining_accurate", "今日高精度剩余"),
            ("remaining_general", "今日通用剩余"),
        ]
        for column in range(5):
            cards.setColumnStretch(column, 1)
        for index, (key, heading) in enumerate(definitions):
            frame = QFrame()
            frame.setStyleSheet(
                "QFrame { background:#FFFFFF; border:1px solid #E5E7EB; "
                "border-radius:12px; }"
            )
            frame.setMinimumHeight(68)
            frame.setMaximumHeight(76)
            add_shadow(frame, blur=18, opacity=16)
            box = QVBoxLayout(frame)
            box.setContentsMargins(12, 7, 12, 7)
            box.setSpacing(2)
            heading_label = QLabel(heading)
            heading_label.setStyleSheet("color:#667085;font-size:12px;border:0;")
            value = QLabel("0")
            value.setStyleSheet(
                "font-size:24px;font-weight:700;color:#101828;border:0;"
            )
            box.addWidget(heading_label)
            box.addWidget(value)
            self.stat_values[key] = value
            cards.addWidget(frame, index // 5, index % 5)
        layout.addLayout(cards)

        chart_card = card()
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(16, 14, 16, 12)
        chart_layout.addWidget(section_label("本月 OCR 调用分布"))
        chart_layout.addWidget(muted_label(
            "每天两根柱分别表示高精度和通用，深色为接口调用，浅色为缓存复用。"
        ))
        self.monthly_chart = HomeMonthlyChart()
        chart_layout.addWidget(self.monthly_chart, 1)
        layout.addWidget(chart_card, 1)
        self.refresh()

    def refresh(self) -> None:
        self.repository.reload()
        stats = self.repository.get("stats", {}) or {}
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")
        self.period_label.setText(f"{today} · {month}")

        today_data = stats.get(today, {}) or {}
        today_accurate = today_data.get("accurate", {}) or {}
        today_general = today_data.get("general", {}) or {}
        month_accurate_api = 0
        month_general_api = 0
        month_accurate_cache = 0
        month_general_cache = 0
        for date_key, day_data in stats.items():
            if not str(date_key).startswith(f"{month}-") or not isinstance(day_data, dict):
                continue
            accurate = day_data.get("accurate", {}) or {}
            general = day_data.get("general", {}) or {}
            month_accurate_api += int(accurate.get("success", 0) or 0)
            month_general_api += int(general.get("success", 0) or 0)
            month_accurate_cache += int(accurate.get("cached", 0) or 0)
            month_general_cache += int(general.get("cached", 0) or 0)

        today_accurate_api = int(today_accurate.get("success", 0) or 0)
        today_general_api = int(today_general.get("success", 0) or 0)
        today_accurate_cache = int(today_accurate.get("cached", 0) or 0)
        today_general_cache = int(today_general.get("cached", 0) or 0)
        values = {
            "today_accurate": today_accurate_api,
            "today_general": today_general_api,
            "today_accurate_cache": today_accurate_cache,
            "today_general_cache": today_general_cache,
            "month_accurate": month_accurate_api,
            "month_general": month_general_api,
            "month_accurate_cache": month_accurate_cache,
            "month_general_cache": month_general_cache,
        }
        for mode, key in (("accurate", "remaining_accurate"), ("general", "remaining_general")):
            config = self.repository.daily_ocr_limit_config(mode)
            if not config.get("enabled", False):
                values[key] = "不限额"
            else:
                _allowed, used, max_count = self.repository.daily_ocr_limit_status(mode)
                values[key] = f"{max(0, max_count - used)} 次"
        for key, value in values.items():
            self.stat_values[key].setText(str(value))
        self.monthly_chart.render(stats, month)


class HistoryPage(QWidget):
    parseRequested = Signal(str, str, list)

    def __init__(self, repository: Repository) -> None:
        super().__init__()
        self.repository = repository
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        top = QHBoxLayout()
        top.addWidget(section_label("识别历史记录"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索书名、类型、时间或内容")
        self.search.setMaximumWidth(310)
        self.search.textChanged.connect(self.apply_filter)
        top.addWidget(self.search)
        top.addStretch()
        self.history_newer_day = QPushButton("较新一天")
        self.history_newer_day.clicked.connect(lambda: self.change_day(-1))
        self.history_day_label = muted_label("")
        self.history_day_label.setMinimumWidth(172)
        self.history_day_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.history_older_day = QPushButton("较早一天")
        self.history_older_day.clicked.connect(lambda: self.change_day(1))
        top.addWidget(self.history_newer_day)
        top.addWidget(self.history_day_label)
        top.addWidget(self.history_older_day)
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh)
        detail_button = QPushButton("查看详情")
        detail_button.clicked.connect(self.show_detail)
        parse_button = QPushButton("复制解析")
        parse_button.setObjectName("primary")
        parse_button.clicked.connect(self.copy_parse_selected)
        export_button = QPushButton("导出")
        export_button.clicked.connect(self.export_selected)
        delete_button = QPushButton("删除")
        delete_button.clicked.connect(self.delete_selected)
        top.addWidget(refresh_button)
        top.addWidget(detail_button)
        top.addWidget(parse_button)
        top.addWidget(export_button)
        top.addWidget(delete_button)
        layout.addLayout(top)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["时间", "类型", "书名", "页码", "文件", "行数"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.doubleClicked.connect(self.show_detail)
        layout.addWidget(self.table)
        self.all_items: list[dict[str, Any]] = []
        self.items: list[dict[str, Any]] = []
        self.day_keys: list[str] = []
        self.current_day = ""
        self.refresh()

    def refresh(self) -> None:
        self.repository.reload()
        self.all_items = list(self.repository.get("history", []) or [])
        self.apply_filter()

    def apply_filter(self, *_args) -> None:
        query = self.search.text().strip().lower()
        if not query:
            filtered_items = list(self.all_items)
        else:
            filtered_items = []
            for item in self.all_items:
                content = " ".join(
                    str(value)
                    for file_data in item.get("files", [])
                    for value in (file_data.get("content", []) if isinstance(file_data.get("content", []), list) else [])
                )
                haystack = " ".join(str(item.get(key, "")) for key in ("timestamp", "type", "book_name", "page_no")) + " " + content
                if query in haystack.lower():
                    filtered_items.append(item)
        self.day_keys = ordered_record_days(filtered_items, "timestamp")
        if self.current_day not in self.day_keys:
            self.current_day = self.day_keys[0] if self.day_keys else ""
        self.items = [
            item for item in filtered_items
            if record_day(item.get("timestamp", "")) == self.current_day
        ]
        self._sync_day_navigation()
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            values = [
                item.get("timestamp", ""), item.get("type", ""), item.get("book_name", ""),
                item.get("page_no", ""), item.get("file_count", ""), item.get("total_lines", ""),
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, cell)

    def _sync_day_navigation(self) -> None:
        if not self.day_keys:
            self.history_day_label.setText("暂无记录")
            self.history_newer_day.setEnabled(False)
            self.history_older_day.setEnabled(False)
            return
        index = self.day_keys.index(self.current_day)
        self.history_day_label.setText(
            f"{self.current_day} · {index + 1}/{len(self.day_keys)} 页 · {len(self.items)} 条"
        )
        self.history_newer_day.setEnabled(index > 0)
        self.history_older_day.setEnabled(index < len(self.day_keys) - 1)

    def change_day(self, offset: int) -> None:
        if not self.day_keys or self.current_day not in self.day_keys:
            return
        index = max(0, min(len(self.day_keys) - 1, self.day_keys.index(self.current_day) + offset))
        if self.current_day != self.day_keys[index]:
            self.current_day = self.day_keys[index]
            self.apply_filter()

    def _item_text(self, item: dict[str, Any]) -> str:
        lines = [
            f"时间：{item.get('timestamp', '')}", f"类型：{item.get('type', '')}",
            f"书名：{item.get('book_name', '')}", f"页码：{item.get('page_no', '')}", "",
        ]
        for file_data in item.get("files", []):
            lines.append(f"【{file_data.get('name', '')}】")
            content = file_data.get("content", [])
            if isinstance(content, list):
                lines.extend(str(value) for value in content)
            lines.append("")
        return "\n".join(lines)

    def _item_content_text(self, item: dict[str, Any]) -> str:
        """Return only OCR lines, matching the legacy Copy & Parse action."""
        lines: list[str] = []
        for file_data in item.get("files", []):
            content = file_data.get("content", [])
            if isinstance(content, str):
                content = content.splitlines()
            if isinstance(content, (list, tuple)):
                lines.extend(str(value).strip() for value in content if str(value).strip())
        return "\n".join(lines)

    def _item_source_results(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        """Reconnect history text to the original images kept by the OCR cache."""
        cache_records = [
            value for value in (self.repository.get("ocr_cache", {}) or {}).values()
            if isinstance(value, dict)
        ]
        results: list[dict[str, Any]] = []
        for file_data in item.get("files", []) or []:
            content = file_data.get("content", [])
            if isinstance(content, str):
                content = content.splitlines()
            lines = [str(value).strip() for value in content if str(value).strip()]
            digest = str(file_data.get("image_hash", "") or "")
            file_name = str(file_data.get("name", "") or "")
            cached = next(
                (record for record in cache_records
                 if digest and str(record.get("hash", "")) == digest),
                None,
            )
            if cached is None:
                cached = next(
                    (record for record in cache_records
                     if file_name and str(record.get("file", "")) == file_name
                     and Path(str(record.get("path", ""))).is_file()),
                    None,
                )
            path = str((cached or {}).get("path", "") or "")
            if path and not Path(path).is_file():
                path = ""
            results.append({
                "file": file_name,
                "path": path,
                "type": "history",
                "lines": lines,
                "boxes": copy.deepcopy(
                    file_data.get("boxes", []) or (cached or {}).get("boxes", []) or []
                ),
                "count": len(lines),
                "cached": True,
                "image_hash": digest,
            })
        return results

    def copy_parse_selected(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self.items):
            QMessageBox.information(self, "提示", "请先选择一条历史记录")
            return
        item = self.items[row]
        text = self._item_content_text(item)
        if not text:
            QMessageBox.warning(self, "提示", "该记录没有可复制和解析的文字内容")
            return
        QApplication.clipboard().setText(text)
        source_name = str(item.get("book_name", "") or "历史记录")
        page_no = item.get("page_no", "")
        if page_no != "":
            source_name = f"{source_name} · 第 {page_no} 页"
        self.parseRequested.emit(text, source_name, self._item_source_results(item))

    def show_detail(self, *_args) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.items):
            return
        item = self.items[row]
        dialog = QDialog(self)
        dialog.setWindowTitle("历史记录详情")
        dialog.resize(760, 600)
        layout = QVBoxLayout(dialog)
        layout.addWidget(section_label(f"{item.get('book_name', '')} · 第 {item.get('page_no', '')} 页"))
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(self._item_text(item))
        layout.addWidget(editor)
        buttons = QHBoxLayout()
        parse = QPushButton("复制解析")
        parse.setObjectName("primary")
        parse.clicked.connect(lambda: self._copy_parse_item(item, dialog))
        close = QPushButton("关闭")
        close.clicked.connect(dialog.accept)
        buttons.addStretch()
        buttons.addWidget(parse)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        dialog.exec()

    def _copy_parse_item(self, item: dict[str, Any], dialog: QDialog | None = None) -> None:
        text = self._item_content_text(item)
        if not text:
            QMessageBox.warning(self, "提示", "该记录没有可复制和解析的文字内容")
            return
        QApplication.clipboard().setText(text)
        source_name = str(item.get("book_name", "") or "历史记录")
        page_no = item.get("page_no", "")
        if page_no != "":
            source_name = f"{source_name} · 第 {page_no} 页"
        if dialog is not None:
            dialog.accept()
        self.parseRequested.emit(text, source_name, self._item_source_results(item))

    def export_selected(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self.items):
            QMessageBox.information(self, "提示", "请先选择一条历史记录")
            return
        item = self.items[row]
        default = f"历史记录_{item.get('page_no', row + 1)}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "导出历史记录", default, "文本 (*.txt)")
        if path:
            content = self._item_text(item)
            Path(path).write_text(content, encoding="utf-8")
            self.repository.save_export_record(path, content)

    def delete_selected(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self.items):
            QMessageBox.information(self, "提示", "请先选择一条历史记录")
            return
        password, ok = QInputDialog.getText(self, "密码验证", "请输入管理员密码：", QLineEdit.EchoMode.Password)
        if not ok:
            return
        if password != str(self.repository.get("unlock_password", "000")):
            QMessageBox.warning(self, "验证失败", "密码错误")
            return
        if QMessageBox.question(self, "确认删除", "确定删除选中的历史记录吗？") != QMessageBox.StandardButton.Yes:
            return
        target = self.items[row]
        for index, item in enumerate(self.all_items):
            if item is target or item == target:
                self.all_items.pop(index)
                break
        self.repository.set("history", self.all_items)
        self.apply_filter()


class StatsCanvas(FigureCanvasQTAgg):
    hourRequested = Signal(int)
    detailChanged = Signal(str)

    def __init__(self) -> None:
        self.figure = Figure(figsize=(9, 4.2), dpi=100, facecolor="white")
        self.axes = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setMinimumHeight(260)
        self.full_rows: list[dict[str, Any]] = []
        self.display_rows: list[dict[str, Any]] = []
        self.display_start = 0
        self.all_day = True
        self.selected_date = ""
        self.mpl_connect("button_press_event", self._clicked)

    @staticmethod
    def minute_rows(stats: dict[str, Any], date: str) -> list[dict[str, Any]]:
        day_data = stats.get(date, {}) or {}
        start = datetime.strptime(date, "%Y-%m-%d")
        rows = [{
            "minute": (start + timedelta(minutes=index)).strftime("%Y-%m-%d %H:%M"),
            "label": (start + timedelta(minutes=index)).strftime("%H:%M"),
            "accurate_api": 0, "accurate_cache": 0,
            "general_api": 0, "general_cache": 0,
        } for index in range(24 * 60)]
        by_minute = {row["minute"]: row for row in rows}
        for record in day_data.get("minute_records", []) or []:
            mode = str(record.get("type", ""))
            if mode not in {"accurate", "general"}:
                continue
            minute = str(record.get("time", ""))[:16]
            row = by_minute.get(minute)
            if row is None:
                continue
            row[f"{mode}_api"] += int(record.get("api_success", 0) or 0)
            row[f"{mode}_cache"] += int(record.get("cached", 0) or 0)
        if not day_data.get("minute_records"):
            for mode in ("accurate", "general"):
                values = day_data.get(mode, {}) or {}
                rows[0][f"{mode}_api"] = int(values.get("success", 0) or 0)
                rows[0][f"{mode}_cache"] = int(values.get("cached", 0) or 0)
        return rows

    @staticmethod
    def latest_active_hour(rows: list[dict[str, Any]]) -> int:
        for index in range(len(rows) - 1, -1, -1):
            row = rows[index]
            if any(row[key] for key in ("accurate_api", "accurate_cache", "general_api", "general_cache")):
                return index // 60
        return 0

    @staticmethod
    def hour_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output = []
        for hour in range(24):
            chunk = rows[hour * 60:(hour + 1) * 60]
            output.append({
                "hour": hour, "label": f"{hour:02d}:00",
                **{key: sum(row[key] for row in chunk) for key in (
                    "accurate_api", "accurate_cache", "general_api", "general_cache"
                )},
            })
        return output

    def render(self, stats: dict[str, Any], date: str = "", all_day: bool = True,
               hour: int | None = None) -> tuple[str, int]:
        self.axes.clear()
        if not stats or not date or date not in stats:
            self.axes.text(.5, .5, "暂无统计数据", ha="center", va="center", color="#9CA3AF",
                           transform=self.axes.transAxes, fontsize=12)
            self.axes.set_axis_off()
            self.draw_idle()
            return "暂无统计数据", 0

        self.axes.set_axis_on()
        self.selected_date = date
        self.all_day = all_day
        self.full_rows = self.minute_rows(stats, date)
        if hour is None:
            hour = self.latest_active_hour(self.full_rows)
        hour = max(0, min(23, int(hour)))
        if all_day:
            self.display_start = 0
            self.display_rows = self.hour_rows(self.full_rows)
        else:
            self.display_start = hour * 60
            self.display_rows = self.full_rows[self.display_start:self.display_start + 60]

        series = [
            ("accurate_api", 3.0, -0.24, "#0F5CC0", "o", "高精度-接口成功"),
            ("accurate_cache", 2.0, -0.08, "#38BDF8", "s", "高精度-缓存复用"),
            ("general_api", 1.0, 0.08, "#7C3AED", "^", "通用-接口成功"),
            ("general_cache", 0.0, 0.24, "#F97316", "D", "通用-缓存复用"),
        ]
        for key, y_position, offset, color, marker, label in series:
            xs, ys, sizes, labels = [], [], [], []
            for index, row in enumerate(self.display_rows):
                value = int(row[key] or 0)
                if value <= 0:
                    continue
                xs.append(index + offset)
                ys.append(y_position)
                sizes.append(46 + min(value, 10) * 7 if all_day else 36 + min(value, 8) * 8)
                labels.append(str(value) if all_day else row["label"])
            self.axes.scatter(xs, ys, s=sizes, color=color, marker=marker, alpha=.92,
                              edgecolors="#111827", linewidths=.8, label=label)
            for x_value, y_value, text_value in zip(xs, ys, labels):
                self.axes.text(x_value + .06, y_value + .16, text_value, fontsize=8,
                               color="#111827", ha="left", va="bottom")

        self.axes.set_xlabel("时间（按小时聚合）" if all_day else "时间（精确到分钟）", fontsize=9)
        self.axes.set_yticks([])
        self.axes.grid(True, axis="x", linestyle="--", linewidth=.7, alpha=.22)
        self.axes.spines[["left", "top", "right"]].set_visible(False)
        self.axes.spines["bottom"].set_color("#CBD5E1")
        self.axes.legend(loc="upper left", frameon=False, ncol=4, fontsize=8)
        if all_day:
            positions = list(range(24))
            labels = [f"{value:02d}:00" for value in positions]
            self.axes.set_xlim(-.9, 23.9)
        else:
            positions = list(range(0, 60, 5)) + [59]
            labels = [f"{hour:02d}:{value:02d}" for value in positions]
            self.axes.set_xlim(-1.5, 60.5)
        self.axes.set_xticks(positions)
        self.axes.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        self.axes.set_ylim(-.7, 3.7)
        self.figure.tight_layout(pad=1.2)
        self.draw_idle()
        totals = {
            key: sum(int(row[key] or 0) for row in self.display_rows)
            for key in ("accurate_api", "accurate_cache", "general_api", "general_cache")
        }
        active = sum(any(row[key] for key in totals) for row in self.display_rows)
        range_text = "全天" if all_day else f"{hour:02d}:00-{hour:02d}:59"
        unit = "小时" if all_day else "分钟"
        summary = (
            f"{date}  {range_text} · 有调用 {active} 个{unit}    "
            f"高精度：接口 {totals['accurate_api']} / 缓存 {totals['accurate_cache']}    "
            f"通用：接口 {totals['general_api']} / 缓存 {totals['general_cache']}"
        )
        return summary, hour

    def _clicked(self, event) -> None:
        if event.inaxes != self.axes or event.xdata is None or not self.display_rows:
            return
        index = int(round(event.xdata))
        if self.all_day:
            if 0 <= index < 24:
                self.hourRequested.emit(index)
            return
        if not 0 <= index < 60:
            return
        row = self.full_rows[self.display_start + index]
        parts = []
        for label, key in (
            ("高精度接口成功", "accurate_api"), ("高精度缓存复用", "accurate_cache"),
            ("通用接口成功", "general_api"), ("通用缓存复用", "general_cache"),
        ):
            if row[key]:
                parts.append(f"{label} {row[key]} 次")
        self.detailChanged.emit(f"{row['minute']}  " + (" / ".join(parts) if parts else "无调用"))


class StatsPage(QWidget):
    statsCleared = Signal()

    def __init__(self, repository: Repository) -> None:
        super().__init__()
        self.repository = repository
        self.stats: dict[str, Any] = {}
        self.current_hour: int | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        top = QHBoxLayout()
        top.addWidget(section_label("识别统计"))
        top.addStretch()
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh)
        clear_button = QPushButton("清空统计")
        clear_button.setStyleSheet(
            "color:#B42318;background:#FFF1F1;border-color:#F4B8B5;"
        )
        clear_button.clicked.connect(self.clear_stats)
        top.addWidget(refresh_button)
        top.addWidget(clear_button)
        layout.addLayout(top)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        total_page = QWidget()
        total_layout = QVBoxLayout(total_page)
        total_controls = QHBoxLayout()
        total_controls.addWidget(QLabel("查看模式"))
        self.total_mode = "accurate"
        self.total_mode_group = QButtonGroup(self)
        self.total_mode_group.setExclusive(True)
        self.total_mode_buttons: dict[str, QPushButton] = {}
        for mode in ("accurate", "general"):
            button = QPushButton(MODE_NAMES[mode])
            button.setObjectName("statsViewMode")
            button.setCheckable(True)
            button.setChecked(mode == self.total_mode)
            button.setStyleSheet(
                "QPushButton#statsViewMode {min-height:30px;padding:0 14px;"
                "background:#FFFFFF;color:#0066FF;border:1px solid #D6E4FF;"
                "border-radius:6px;font-weight:600;}"
                "QPushButton#statsViewMode:hover {background:#FFFFFF;"
                "border-color:#0066FF;}"
                "QPushButton#statsViewMode:checked {background:#FFFFFF;"
                "color:#0066FF;border:2px solid #0066FF;font-weight:700;}"
            )
            button.clicked.connect(
                lambda checked=False, value=mode: self.select_total_mode(value)
                if checked else None
            )
            self.total_mode_group.addButton(button)
            self.total_mode_buttons[mode] = button
            total_controls.addWidget(button)
        total_controls.addStretch()
        self.total_overall = muted_label("")
        total_controls.addWidget(self.total_overall)
        total_layout.addLayout(total_controls)
        summary = QHBoxLayout()
        self.summary_labels: list[QLabel] = []
        for title in ("本月使用天数", "本月接口调用", "本月缓存复用", "本月日均接口"):
            frame = card()
            box = QVBoxLayout(frame)
            box.setContentsMargins(14, 10, 14, 10)
            box.addWidget(muted_label(title))
            value = QLabel("0")
            value.setStyleSheet("font-size:22px;font-weight:700;")
            box.addWidget(value)
            self.summary_labels.append(value)
            summary.addWidget(frame)
        total_layout.addLayout(summary)
        self.total_table = self._make_table([
            "日期", "星期", "当月累计天数", "当日接口", "当日缓存",
            "月累计接口", "月累计缓存", "月日均接口", "月日均缓存",
        ])
        total_layout.addWidget(self.total_table, 1)
        self.tabs.addTab(total_page, "总计")

        chart_page = QWidget()
        chart_layout = QVBoxLayout(chart_page)
        chart_layout.setContentsMargins(12, 10, 12, 10)
        controls = QHBoxLayout()
        controls.addWidget(section_label("高精度／通用调用次数趋势"))
        controls.addStretch()
        controls.addWidget(QLabel("日期"))
        self.chart_date = QComboBox()
        self.chart_date.setMinimumWidth(125)
        self.chart_date.currentTextChanged.connect(self._date_changed)
        controls.addWidget(self.chart_date)
        controls.addWidget(QLabel("范围"))
        self.chart_range = QComboBox()
        self.chart_range.addItems(["全天", "最近有调用的小时"])
        self.chart_range.currentTextChanged.connect(self._range_changed)
        controls.addWidget(self.chart_range)
        previous = QPushButton("上一小时")
        previous.clicked.connect(lambda: self.shift_hour(-1))
        next_hour = QPushButton("下一小时")
        next_hour.clicked.connect(lambda: self.shift_hour(1))
        controls.addWidget(previous)
        controls.addWidget(next_hour)
        chart_layout.addLayout(controls)
        self.chart = StatsCanvas()
        self.chart.hourRequested.connect(self.show_hour)
        self.chart.detailChanged.connect(self._show_chart_detail)
        chart_layout.addWidget(self.chart, 1)
        self.chart_summary = muted_label("")
        self.chart_summary.setWordWrap(True)
        self.chart_detail = QLabel("点击全天图中的小时点，可查看该小时的分钟明细")
        self.chart_detail.setStyleSheet("color:#4B5563;font-size:12px;")
        chart_layout.addWidget(self.chart_summary)
        chart_layout.addWidget(self.chart_detail)
        self.tabs.addTab(chart_page, "折线图")
        self.refresh()

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        return table

    @staticmethod
    def _number(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def select_total_mode(self, mode: str) -> None:
        if mode not in self.total_mode_buttons:
            return
        self.total_mode = mode
        self.total_mode_buttons[mode].setChecked(True)
        self.refresh_total()

    def _set_table_rows(self, table: QTableWidget, rows: list[list[Any]]) -> None:
        table.setSortingEnabled(False)
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, column, cell)

    def refresh(self) -> None:
        self.repository.reload()
        value = self.repository.get("stats", {}) or {}
        self.stats = value if isinstance(value, dict) else {}
        self.refresh_total()
        current_date = self.chart_date.currentText()
        dates = sorted(self.stats, reverse=True)
        self.chart_date.blockSignals(True)
        self.chart_date.clear()
        self.chart_date.addItems(dates)
        if current_date in dates:
            self.chart_date.setCurrentText(current_date)
        elif dates:
            self.chart_date.setCurrentIndex(0)
        self.chart_date.blockSignals(False)
        self.refresh_chart()

    def clear_stats(self) -> None:
        if not self.stats and not (self.repository.get("stats", {}) or {}):
            QMessageBox.information(self, "清空统计", "当前没有可清空的统计数据。")
            return
        password, ok = QInputDialog.getText(
            self,
            "密码验证",
            "请输入管理员密码：",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        if password != str(self.repository.get("unlock_password", "000")):
            QMessageBox.warning(self, "验证失败", "密码错误，统计数据未清空。")
            return
        if QMessageBox.question(
            self,
            "确认清空统计",
            "确定清空全部 OCR 调用统计吗？\n\n"
            "此操作不会删除识别历史、OCR 缓存、图片和导出记录。",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.repository.set("stats", {})
        self.refresh()
        self.statsCleared.emit()
        QMessageBox.information(self, "清空完成", "OCR 调用统计已全部清空。")

    def refresh_total(self, *_args) -> None:
        mode = self.total_mode
        rows: list[dict[str, Any]] = []
        month_totals: dict[str, dict[str, int]] = {}
        for day in sorted(self.stats):
            month = day[:7]
            month_state = month_totals.setdefault(month, {"days": 0, "api": 0, "cache": 0})
            month_state["days"] += 1
            values = self.stats.get(day, {}).get(mode, {}) or {}
            api = self._number(values.get("success"))
            cache = self._number(values.get("cached"))
            month_state["api"] += api
            month_state["cache"] += cache
            try:
                weekday = "周" + "一二三四五六日"[datetime.strptime(day, "%Y-%m-%d").weekday()]
            except (ValueError, IndexError):
                weekday = ""
            rows.append({
                "day": day, "weekday": weekday, "days": month_state["days"],
                "api": api, "cache": cache, "cum_api": month_state["api"],
                "cum_cache": month_state["cache"],
                "avg_api": month_state["api"] / month_state["days"],
                "avg_cache": month_state["cache"] / month_state["days"],
            })
        display_rows = [[
            row["day"], row["weekday"], row["days"], f"{row['api']:,}", f"{row['cache']:,}",
            f"{row['cum_api']:,}", f"{row['cum_cache']:,}",
            f"{row['avg_api']:.1f}", f"{row['avg_cache']:.1f}",
        ] for row in reversed(rows)]
        self._set_table_rows(self.total_table, display_rows)
        current_month = datetime.now().strftime("%Y-%m")
        month = month_totals.get(current_month, {"days": 0, "api": 0, "cache": 0})
        days = month["days"]
        values = [days, month["api"], month["cache"], f"{month['api'] / days:.1f}" if days else "0.0"]
        for label, value in zip(self.summary_labels, values):
            label.setText(f"{value:,}" if isinstance(value, int) else str(value))
        self.total_overall.setText(
            f"全部 {len(self.stats)} 天 · 接口 {sum(row['api'] for row in rows):,} · "
            f"缓存 {sum(row['cache'] for row in rows):,}"
        )

    def refresh_chart(self) -> None:
        date = self.chart_date.currentText()
        all_day = self.chart_range.currentText() == "全天"
        summary, used_hour = self.chart.render(self.stats, date, all_day, self.current_hour)
        self.current_hour = used_hour
        self.chart_summary.setText(summary)
        self.chart_detail.setText(
            "点击全天图中的小时点，可查看该小时的分钟明细"
            if all_day else "点击图中的时间点查看该分钟明细"
        )

    def _date_changed(self, *_args) -> None:
        self.current_hour = None
        self.refresh_chart()

    def _range_changed(self, *_args) -> None:
        if self.chart_range.currentText() == "最近有调用的小时":
            self.current_hour = None
        self.refresh_chart()

    def show_hour(self, hour: int) -> None:
        self.current_hour = max(0, min(23, int(hour)))
        self.chart_range.blockSignals(True)
        self.chart_range.setCurrentText("最近有调用的小时")
        self.chart_range.blockSignals(False)
        self.refresh_chart()
        self._show_hour_detail(self.current_hour)

    def shift_hour(self, delta: int) -> None:
        if not self.stats:
            return
        if self.current_hour is None:
            date = self.chart_date.currentText()
            rows = self.chart.minute_rows(self.stats, date) if date else []
            self.current_hour = self.chart.latest_active_hour(rows) if rows else 0
        self.show_hour(max(0, min(23, self.current_hour + delta)))

    def _show_hour_detail(self, hour: int) -> None:
        rows = self.chart.full_rows
        chunk = rows[hour * 60:(hour + 1) * 60]
        details = []
        for label, key in (
            ("高精度接口成功", "accurate_api"), ("高精度缓存复用", "accurate_cache"),
            ("通用接口成功", "general_api"), ("通用缓存复用", "general_cache"),
        ):
            value = sum(int(row[key] or 0) for row in chunk)
            if value:
                details.append(f"{label} {value} 次")
        text = " / ".join(details) if details else "无调用"
        self.chart_detail.setText(
            f"{self.chart_date.currentText()} {hour:02d}:00-{hour:02d}:59  {text}"
        )

    def _show_chart_detail(self, text: str) -> None:
        self.chart_detail.setText(text)


class GalleryImageView(QScrollArea):
    """Embedded image viewer with fit-to-window and Ctrl+wheel zoom."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.source = QPixmap()
        self.zoom = 1.0
        self.fit_to_window = True
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidgetResizable(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QScrollArea { background:#F3F4F6; border-radius:10px; }")
        self.image_label = QLabel("选择左侧图片即可预览")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("color:#8A9099; background:#F3F4F6; padding:24px;")
        self.image_label.setMinimumSize(420, 360)
        self.setWidget(self.image_label)

    def load_image(self, path: str) -> tuple[bool, str]:
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            self.clear_image("图片读取失败")
            return False, reader.errorString() or "无法读取该图片"
        self.source = QPixmap.fromImage(image)
        self.zoom = 1.0
        self.fit_to_window = True
        self._render()
        return True, ""

    def clear_image(self, message: str = "暂无可预览图片") -> None:
        self.source = QPixmap()
        self.image_label.clear()
        self.image_label.setText(message)
        self.image_label.setMinimumSize(420, 360)
        self.image_label.resize(max(420, self.viewport().width()), max(360, self.viewport().height()))

    def show_fit(self) -> None:
        if not self.source.isNull():
            self.fit_to_window = True
            self._render()

    def show_actual(self) -> None:
        if not self.source.isNull():
            self.fit_to_window = False
            self.zoom = 1.0
            self._render()

    def zoom_by(self, factor: float) -> None:
        if self.source.isNull():
            return
        if self.fit_to_window:
            available = QSize(max(1, self.viewport().width() - 20), max(1, self.viewport().height() - 20))
            self.zoom = min(
                available.width() / self.source.width(),
                available.height() / self.source.height(),
            )
        self.fit_to_window = False
        self.zoom = max(0.1, min(8.0, self.zoom * factor))
        self._render()

    def _render(self) -> None:
        if self.source.isNull():
            return
        if self.fit_to_window:
            available = QSize(max(1, self.viewport().width() - 20), max(1, self.viewport().height() - 20))
            scale = min(
                available.width() / self.source.width(),
                available.height() / self.source.height(),
                1.0,
            )
        else:
            scale = self.zoom
        width = max(1, round(self.source.width() * scale))
        height = max(1, round(self.source.height() * scale))
        preview = self.source.scaled(
            width, height, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setText("")
        self.image_label.setMinimumSize(0, 0)
        self.image_label.resize(preview.size())
        self.image_label.setPixmap(preview)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.fit_to_window and not self.source.isNull():
            self._render()
        elif self.source.isNull():
            self.image_label.resize(max(420, self.viewport().width()), max(360, self.viewport().height()))

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and not self.source.isNull():
            self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
            return
        super().wheelEvent(event)


class GalleryPage(QWidget):
    def __init__(self, repository: Repository) -> None:
        super().__init__()
        self.repository = repository
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        top = QHBoxLayout()
        top.addWidget(section_label("图片预览"))
        top.addStretch()
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh)
        open_button = QPushButton("打开图片")
        open_button.clicked.connect(self.open_selected)
        locate_button = QPushButton("定位文件")
        locate_button.clicked.connect(self.locate_selected)
        remove_button = QPushButton("移出预览")
        remove_button.clicked.connect(self.remove_selected)
        top.addWidget(refresh_button)
        top.addWidget(open_button)
        top.addWidget(locate_button)
        top.addWidget(remove_button)
        layout.addLayout(top)
        self.summary = muted_label("")
        layout.addWidget(self.summary)
        day_navigation = QHBoxLayout()
        self.gallery_newer_day = QPushButton("较新一天")
        self.gallery_newer_day.clicked.connect(lambda: self.change_day(-1))
        self.gallery_day_label = muted_label("")
        self.gallery_day_label.setMinimumWidth(172)
        self.gallery_day_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gallery_older_day = QPushButton("较早一天")
        self.gallery_older_day.clicked.connect(lambda: self.change_day(1))
        day_navigation.addWidget(self.gallery_newer_day)
        day_navigation.addWidget(self.gallery_day_label)
        day_navigation.addWidget(self.gallery_older_day)
        day_navigation.addStretch()
        layout.addLayout(day_navigation)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["图片", "识别模式", "行数", "更新时间"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setIconSize(QSize(48, 48))
        self.table.verticalHeader().setDefaultSectionSize(58)
        self.table.itemSelectionChanged.connect(self.show_selected)
        self.table.doubleClicked.connect(self.open_selected)
        splitter.addWidget(self.table)

        preview_card = card()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_toolbar = QHBoxLayout()
        self.preview_title = QLabel("图片预览")
        self.preview_title.setStyleSheet("font-weight:700;")
        preview_toolbar.addWidget(self.preview_title)
        preview_toolbar.addStretch()
        zoom_out = QPushButton("－")
        zoom_out.setFixedWidth(38)
        zoom_out.clicked.connect(lambda: self.viewer.zoom_by(1 / 1.2))
        zoom_in = QPushButton("＋")
        zoom_in.setFixedWidth(38)
        zoom_in.clicked.connect(lambda: self.viewer.zoom_by(1.2))
        actual = QPushButton("100%")
        actual.clicked.connect(self._show_actual)
        fit = QPushButton("适应窗口")
        fit.clicked.connect(self._show_fit)
        preview_toolbar.addWidget(zoom_out)
        preview_toolbar.addWidget(zoom_in)
        preview_toolbar.addWidget(actual)
        preview_toolbar.addWidget(fit)
        preview_layout.addLayout(preview_toolbar)
        self.viewer = GalleryImageView()
        preview_layout.addWidget(self.viewer, 1)
        self.preview_info = muted_label("选择左侧记录查看图片；双击可用系统程序打开")
        self.preview_info.setWordWrap(True)
        preview_layout.addWidget(self.preview_info)
        splitter.addWidget(preview_card)
        splitter.setSizes([520, 780])
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)
        self.all_records: list[dict[str, Any]] = []
        self.records: list[dict[str, Any]] = []
        self.day_keys: list[str] = []
        self.current_day = ""
        self._stale_count = 0
        self._record_limit = 30
        self.refresh()

    def refresh(self) -> None:
        self.repository.reload()
        cache = self.repository.get("ocr_cache", {}) or {}
        self.all_records = []
        stale_count = 0
        seen_paths: set[str] = set()
        for cache_key, value in cache.items():
            if not isinstance(value, dict) or not value.get("path"):
                continue
            path = Path(str(value["path"]))
            if not path.exists():
                stale_count += 1
                continue
            path_key = os.path.normcase(os.path.abspath(str(path)))
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)
            record = dict(value)
            record["_cache_key"] = cache_key
            record["_record_kind"] = "ocr"
            self.all_records.append(record)
        source_labels = {"file": "文件拼接", "screenshot": "截图拼接", "crop": "裁剪拼接"}
        for index, value in enumerate(self.repository.get("merge_history", []) or []):
            if not isinstance(value, dict) or not value.get("output_path"):
                continue
            path = Path(str(value["output_path"]))
            if not path.exists():
                stale_count += 1
                continue
            path_key = os.path.normcase(os.path.abspath(str(path)))
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)
            source_type = str(value.get("type", "file"))
            recognized_type = str(value.get("recognized_type", ""))
            self.all_records.append({
                "file": value.get("desc") or path.name,
                "path": str(path),
                "type": recognized_type,
                "display_type": MODE_NAMES.get(recognized_type, "") or source_labels.get(source_type, source_type),
                "line_count": 0,
                "updated_at": value.get("recognized_at") or value.get("time", ""),
                "_record_kind": "merge",
                "_merge_index": index,
            })
        self.all_records.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        try:
            limit = max(0, int(self.repository.get("gallery_ocr_limit", 30) or 30))
        except (TypeError, ValueError):
            limit = 30
        if limit:
            self.all_records = self.all_records[:limit]
        self._stale_count = stale_count
        self._record_limit = limit
        self.apply_day_page()

    def apply_day_page(self) -> None:
        self.day_keys = ordered_record_days(self.all_records, "updated_at")
        if self.current_day not in self.day_keys:
            self.current_day = self.day_keys[0] if self.day_keys else ""
        self.records = [
            record for record in self.all_records
            if record_day(record.get("updated_at", "")) == self.current_day
        ]
        self._sync_day_navigation()
        stale_text = (
            f"；另有 {self._stale_count} 条旧记录的原图片已被移动或删除"
            if self._stale_count else ""
        )
        self.summary.setText(
            f"当前日期可预览 {len(self.records)} 张（记录上限 {self._record_limit or '不限'}）{stale_text}"
        )
        self.table.setRowCount(len(self.records))
        for row, item in enumerate(self.records):
            values = [item.get("file", ""), item.get("display_type") or MODE_NAMES.get(item.get("type"), item.get("type", "")),
                      item.get("line_count", len(item.get("lines", []))), item.get("updated_at", "")]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 0:
                    reader = QImageReader(str(item["path"]))
                    reader.setAutoTransform(True)
                    source_size = reader.size()
                    if source_size.isValid():
                        reader.setScaledSize(source_size.scaled(
                            QSize(48, 48), Qt.AspectRatioMode.KeepAspectRatio,
                        ))
                    thumb = reader.read()
                    if not thumb.isNull():
                        cell.setIcon(QIcon(QPixmap.fromImage(thumb)))
                self.table.setItem(row, column, cell)
        if self.records:
            self.table.selectRow(0)
        else:
            self.viewer.clear_image("暂无可预览图片\n请先导入图片并完成 OCR 识别")
            self.preview_title.setText("图片预览")
            self.preview_info.setText("识别后的原图片仍需保存在原位置，才能在这里预览。")

    def _sync_day_navigation(self) -> None:
        if not self.day_keys:
            self.gallery_day_label.setText("暂无图片")
            self.gallery_newer_day.setEnabled(False)
            self.gallery_older_day.setEnabled(False)
            return
        index = self.day_keys.index(self.current_day)
        self.gallery_day_label.setText(
            f"{self.current_day} · {index + 1}/{len(self.day_keys)} 页 · {len(self.records)} 张"
        )
        self.gallery_newer_day.setEnabled(index > 0)
        self.gallery_older_day.setEnabled(index < len(self.day_keys) - 1)

    def change_day(self, offset: int) -> None:
        if not self.day_keys or self.current_day not in self.day_keys:
            return
        index = max(0, min(len(self.day_keys) - 1, self.day_keys.index(self.current_day) + offset))
        if self.current_day != self.day_keys[index]:
            self.current_day = self.day_keys[index]
            self.apply_day_page()

    def show_selected(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self.records):
            return
        record = self.records[row]
        path = str(record.get("path", ""))
        ok, error = self.viewer.load_image(path)
        self.preview_title.setText(str(record.get("file") or Path(path).name))
        if not ok:
            self.preview_info.setText(f"无法预览：{error}\n{path}")
            return
        try:
            file_size = Path(path).stat().st_size
            size_text = f"{file_size / 1024:.1f} KB" if file_size < 1024 * 1024 else f"{file_size / 1024 / 1024:.1f} MB"
        except OSError:
            size_text = "未知大小"
        self.preview_info.setText(
            f"{self.viewer.source.width()} × {self.viewer.source.height()} px  ·  {size_text}  ·  "
            f"{record.get('display_type') or MODE_NAMES.get(record.get('type'), record.get('type', ''))}  ·  "
            f"{record.get('line_count', len(record.get('lines', [])))} 行\n"
            f"Ctrl + 鼠标滚轮可缩放；放大后可拖动滚动条查看"
        )

    def _show_fit(self) -> None:
        self.viewer.show_fit()

    def _show_actual(self) -> None:
        self.viewer.show_actual()

    def open_selected(self, *_args) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.records):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.records[row]["path"]))

    def locate_selected(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self.records):
            return
        path = Path(self.records[row]["path"])
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def remove_selected(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self.records):
            return
        if QMessageBox.question(self, "移出预览", "只移除预览与缓存记录，不删除图片文件。确定继续吗？") != QMessageBox.StandardButton.Yes:
            return
        record = self.records[row]
        if record.get("_record_kind") == "merge":
            target = os.path.normcase(os.path.abspath(str(record.get("path", ""))))
            history = list(self.repository.get("merge_history", []) or [])
            history = [
                item for item in history
                if os.path.normcase(os.path.abspath(str(item.get("output_path", "")))) != target
            ]
            self.repository.set("merge_history", history)
        else:
            cache = self.repository.get("ocr_cache", {}) or {}
            cache.pop(record.get("_cache_key", ""), None)
            self.repository.set("ocr_cache", cache)
        self.refresh()


class KeysPage(QWidget):
    keysChanged = Signal()

    def __init__(self, repository: Repository) -> None:
        super().__init__()
        self.repository = repository
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.addWidget(section_label("密钥管理"))
        layout.addWidget(muted_label("密钥继续从原有 .env 文件加载，新旧界面完全共用。"))
        self.grid = QGridLayout()
        self.state_labels: dict[str, QLabel] = {}
        for row, (mode, name) in enumerate(MODE_NAMES.items()):
            frame = card()
            box = QHBoxLayout(frame)
            box.setContentsMargins(18, 16, 18, 16)
            box.addWidget(QLabel(name))
            box.addStretch()
            state = QLabel("● 已配置" if key_available(mode) else "○ 未配置")
            state.setStyleSheet("color:#16A269;" if key_available(mode) else "color:#C24A3A;")
            self.state_labels[mode] = state
            box.addWidget(state)
            self.grid.addWidget(frame, row // 2, row % 2)
        layout.addLayout(self.grid)
        buttons = QHBoxLayout()
        env_button = QPushButton("编辑密钥")
        env_button.setObjectName("primary")
        env_button.clicked.connect(self.edit_keys)
        raw_button = QPushButton("打开 .env")
        raw_button.clicked.connect(self.open_env)
        buttons.addWidget(env_button)
        buttons.addWidget(raw_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()

    def open_env(self) -> None:
        password, ok = QInputDialog.getText(
            self, "密码验证", "请输入管理员密码：", QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        if password != str(self.repository.get("unlock_password", "000")):
            QMessageBox.warning(self, "验证失败", "密码错误，无法打开 .env 文件")
            return
        env_path = APP_DIR / ".env"
        if not env_path.exists():
            env_path.touch()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(env_path)))

    def edit_keys(self) -> None:
        dialog = KeyEditorDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.keysChanged.emit()

    def refresh(self) -> None:
        for mode, label in self.state_labels.items():
            configured = key_available(mode)
            label.setText("● 已配置" if configured else "○ 未配置")
            label.setStyleSheet("color:#16A269;" if configured else "color:#C24A3A;")


class KeyEditorDialog(QDialog):
    ENV_FIELDS = [
        ("accurate", "高精度", "BAIDU_API_KEY", "BAIDU_SECRET_KEY"),
        ("basic", "快速", "BAIDU_API_KEY_BASIC", "BAIDU_SECRET_KEY_BASIC"),
        ("general", "通用", "BAIDU_API_KEY_GENERAL", "BAIDU_SECRET_KEY_GENERAL"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑 OCR 密钥")
        self.resize(650, 480)
        self.env_path = APP_DIR / ".env"
        self.values = self._read_values()
        self.inputs: dict[str, QLineEdit] = {}
        layout = QVBoxLayout(self)
        layout.addWidget(section_label("百度 OCR 接口密钥"))
        layout.addWidget(muted_label("内容保存到原有 .env 文件，新旧界面同时生效。", True))
        form = QFormLayout()
        for _mode, name, api_field, secret_field in self.ENV_FIELDS:
            heading = QLabel(name)
            heading.setStyleSheet("font-weight:700;margin-top:8px;")
            form.addRow(heading)
            api_input = QLineEdit(self.values.get(api_field, ""))
            secret_input = QLineEdit(self.values.get(secret_field, ""))
            api_input.setEchoMode(QLineEdit.EchoMode.Password)
            secret_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.inputs[api_field] = api_input
            self.inputs[secret_field] = secret_input
            form.addRow("API Key", api_input)
            form.addRow("Secret Key", secret_input)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _read_values(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if self.env_path.exists():
            for raw in self.env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    result[key.strip()] = value.strip()
        return result

    def save(self) -> None:
        updates = {key: widget.text().strip() for key, widget in self.inputs.items()}
        original = self.env_path.read_text(encoding="utf-8").splitlines() if self.env_path.exists() else []
        output: list[str] = []
        handled: set[str] = set()
        for raw in original:
            stripped = raw.strip()
            key = stripped.split("=", 1)[0].strip() if "=" in stripped and not stripped.startswith("#") else ""
            if key in updates:
                output.append(f"{key}={updates[key]}")
                handled.add(key)
            else:
                output.append(raw)
        for key, value in updates.items():
            if key not in handled:
                output.append(f"{key}={value}")
        self.env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
        for key, value in updates.items():
            os.environ[key] = value
        qt_backend.update_credentials(updates)
        self.accept()


class EditableRulesDialog(QDialog):
    """Reusable native table editor for rule collections."""

    def __init__(self, title: str, headers: list[str], rows: list[list[Any]],
                 save_callback, default_row: list[Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(max(720, len(headers) * 145), 620)
        self.save_callback = save_callback
        self.default_row = [str(value) for value in default_row]
        layout = QVBoxLayout(self)
        layout.addWidget(section_label(title))
        toolbar = QHBoxLayout()
        add = QPushButton("添加")
        add.clicked.connect(self.add_row)
        delete = QPushButton("删除选中")
        delete.clicked.connect(self.delete_rows)
        up = QPushButton("上移")
        up.clicked.connect(lambda: self.move_row(-1))
        down = QPushButton("下移")
        down.clicked.connect(lambda: self.move_row(1))
        toolbar.addWidget(add)
        toolbar.addWidget(delete)
        toolbar.addWidget(up)
        toolbar.addWidget(down)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.table)
        for row in rows:
            self._append([str(value) for value in row])
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _append(self, values: list[str]) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column in range(self.table.columnCount()):
            self.table.setItem(row, column, QTableWidgetItem(values[column] if column < len(values) else ""))

    def add_row(self) -> None:
        self._append(self.default_row)
        self.table.selectRow(self.table.rowCount() - 1)

    def delete_rows(self) -> None:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def move_row(self, direction: int) -> None:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        if len(rows) != 1:
            return
        old = rows[0]
        new = old + direction
        if not 0 <= new < self.table.rowCount():
            return
        values = [self.table.item(old, column).text() if self.table.item(old, column) else ""
                  for column in range(self.table.columnCount())]
        self.table.removeRow(old)
        self.table.insertRow(new)
        for column, value in enumerate(values):
            self.table.setItem(new, column, QTableWidgetItem(value))
        self.table.selectRow(new)

    def save(self) -> None:
        rows = []
        for row in range(self.table.rowCount()):
            rows.append([
                self.table.item(row, column).text().strip() if self.table.item(row, column) else ""
                for column in range(self.table.columnCount())
            ])
        try:
            self.save_callback(rows)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "规则格式错误", str(exc))
            return
        self.accept()


class ReportSettingsDialog(QDialog):
    def __init__(self, repository: Repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.setWindowTitle("报告格式")
        self.resize(480, 280)
        layout = QVBoxLayout(self)
        layout.addWidget(section_label("报告格式设置"))
        form = QFormLayout()
        self.format_combo = QComboBox()
        for format_key, format_name in REPORT_FORMAT_NAMES.items():
            self.format_combo.addItem(format_name, format_key)
        current_format = str(repository.get("report_format", "legacy"))
        current_index = self.format_combo.findData(current_format)
        self.format_combo.setCurrentIndex(current_index if current_index >= 0 else 0)
        self.separator_combo = QComboBox()
        self.separator_combo.addItems(["line", "blank"])
        current_separator = str(repository.get("report_separator", "line"))
        if self.separator_combo.findText(current_separator) < 0:
            self.separator_combo.addItem(current_separator)
        self.separator_combo.setCurrentText(current_separator)
        form.addRow("报告格式", self.format_combo)
        form.addRow("分类分隔", self.separator_combo)
        layout.addLayout(form)
        layout.addWidget(muted_label("Markdown 分组表格列顺序为：辈分、a组、c组、b组、d组；同组多条名称使用 <br> 放在同一单元格内。", True))
        save = QPushButton("保存")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        layout.addWidget(save, 0, Qt.AlignmentFlag.AlignRight)

    def save(self) -> None:
        self.repository.set("report_format", str(self.format_combo.currentData() or "legacy"))
        self.repository.set("report_separator", self.separator_combo.currentText())
        self.accept()


class RulesPage(QWidget):
    def __init__(self, repository: Repository) -> None:
        super().__init__()
        self.repository = repository
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 28)
        top = QHBoxLayout()
        top.addWidget(section_label("规则尺寸"))
        top.addStretch()
        layout.addLayout(top)
        layout.addWidget(muted_label("尺寸、清理、替换、字体、空格和报告规则均与经典版共用。"))
        frame = card()
        form = QGridLayout(frame)
        form.setContentsMargins(22, 20, 22, 20)
        form.addWidget(QLabel("模式"), 0, 0)
        form.addWidget(QLabel("最小宽度"), 0, 1)
        form.addWidget(QLabel("最大宽度"), 0, 2)
        form.addWidget(QLabel("最小高度"), 0, 3)
        form.addWidget(QLabel("最大高度"), 0, 4)
        self.inputs: dict[str, QSpinBox] = {}
        limits = self.repository.limits()
        for row, (mode, name) in enumerate(MODE_NAMES.items(), start=1):
            form.addWidget(QLabel(name), row, 0)
            for column, suffix in enumerate(("min_width", "max_width", "min_height", "max_height"), start=1):
                key = f"{mode}_{suffix}"
                spin = QSpinBox()
                if "width" in suffix:
                    spin.setRange(0, 8192)
                else:
                    spin.setRange(0, 100000)
                spin.setValue(int(limits[key]))
                self.inputs[key] = spin
                form.addWidget(spin, row, column)
        layout.addWidget(frame)
        save = QPushButton("保存规则")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        layout.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(8)
        layout.addWidget(section_label("数据处理规则"))
        rule_grid = QGridLayout()
        rule_actions = [
            ("过滤清理规则", self.edit_filters, "设置需要从报告中排除的文字或符号"),
            ("文字替换规则", self.edit_replacements, "按顺序执行查找与替换"),
            ("字体样式规则", self.edit_font_styles, "按前缀设置颜色、字体和自动分组"),
            ("空格规则预设", self.edit_space_presets, "维护自定义字符与规则预设"),
            ("报告格式", self.edit_report_settings, "设置报告格式与分类分隔方式"),
        ]
        for index, (title, handler, description) in enumerate(rule_actions):
            frame = card()
            box = QVBoxLayout(frame)
            box.setContentsMargins(16, 14, 16, 14)
            box.addWidget(QLabel(title))
            box.addWidget(muted_label(description, True))
            button = QPushButton("编辑")
            button.clicked.connect(handler)
            box.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
            rule_grid.addWidget(frame, index // 3, index % 3)
        layout.addLayout(rule_grid)
        layout.addStretch()

    def save(self) -> None:
        password, ok = QInputDialog.getText(self, "密码验证", "请输入管理员密码：", QLineEdit.EchoMode.Password)
        if not ok:
            return
        if password != str(self.repository.get("unlock_password", "000")):
            QMessageBox.warning(self, "验证失败", "密码错误")
            return
        values = {key: spin.value() for key, spin in self.inputs.items()}
        for mode in MODE_NAMES:
            if values[f"{mode}_min_width"] > values[f"{mode}_max_width"] or values[f"{mode}_min_height"] > values[f"{mode}_max_height"]:
                QMessageBox.warning(self, "规则错误", f"{MODE_NAMES[mode]}的最小值不能大于最大值")
                return
        self.repository.set("size_limits", values)
        QMessageBox.information(self, "保存成功", "尺寸规则已保存，新旧界面同时生效。")

    def edit_filters(self) -> None:
        values = self.repository.get("filter_rules", []) or []

        def save(rows):
            self.repository.set("filter_rules", [row[0] for row in rows if row[0]])

        EditableRulesDialog("过滤清理规则", ["过滤文字或符号"], [[value] for value in values],
                            save, [""], self).exec()

    def edit_replacements(self) -> None:
        rules = self.repository.get("replace_rules", []) or []
        rows = [[rule.get("find", ""), rule.get("replace", "")] for rule in rules if isinstance(rule, dict)]

        def save(new_rows):
            self.repository.set("replace_rules", [
                {"find": find, "replace": replace} for find, replace in new_rows if find
            ])

        EditableRulesDialog("文字替换规则", ["查找", "替换为"], rows,
                            save, ["", ""], self).exec()

    def edit_font_styles(self) -> None:
        rules = self.repository.get("font_style_rules", {}) or {}
        rows = []
        for prefix, rule in rules.items():
            rows.append([
                prefix, rule.get("font_family", "Microsoft YaHei UI"), rule.get("font_size", 18),
                rule.get("font_weight", "normal"), rule.get("color", "#FF0000"),
                rule.get("target_group", "auto"), rule.get("description", ""),
                "是" if rule.get("enabled", True) else "否",
            ])

        def save(new_rows):
            output = {}
            for prefix, family, size, weight, color, target, description, enabled in new_rows:
                if not prefix:
                    continue
                size_value = int(size)
                if size_value < 6 or size_value > 96:
                    raise ValueError(f"规则“{prefix}”的字号必须在 6～96 之间")
                if target not in {"auto", "none", "A", "B", "C", "D"}:
                    raise ValueError(f"规则“{prefix}”的目标分组无效")
                output[prefix] = {
                    "font_family": family or "Microsoft YaHei UI", "font_size": size_value,
                    "font_weight": weight or "normal", "color": color or "#000000",
                    "target_group": target, "description": description,
                    "enabled": enabled.lower() not in {"否", "false", "0", "no"},
                }
            self.repository.set("font_style_rules", output)

        headers = ["前缀", "字体", "字号", "粗细", "颜色", "目标组", "描述", "启用"]
        defaults = ["", "Microsoft YaHei UI", "18", "normal", "#FF0000", "auto", "", "是"]
        EditableRulesDialog("字体样式规则", headers, rows, save, defaults, self).exec()

    def edit_space_presets(self) -> None:
        presets = self.repository.get("space_presets", {}) or {}
        rows = []
        for name, preset in presets.items():
            rows.append([
                name, preset.get("description", ""), preset.get("custom_chars", ""),
                json.dumps(preset.get("rules", []), ensure_ascii=False),
            ])

        def save(new_rows):
            output = {}
            for name, description, custom_chars, rules_json in new_rows:
                if not name:
                    continue
                rules = json.loads(rules_json or "[]")
                if not isinstance(rules, list):
                    raise ValueError(f"预设“{name}”的规则必须是 JSON 列表")
                output[name] = {"custom_chars": custom_chars, "rules": rules, "description": description}
            self.repository.set("space_presets", output)

        EditableRulesDialog("空格规则预设", ["名称", "描述", "自定义字符", "规则 JSON"], rows,
                            save, ["新预设", "", "", "[]"], self).exec()

    def edit_report_settings(self) -> None:
        ReportSettingsDialog(self.repository, self).exec()


class ExportHistoryDialog(QDialog):
    def __init__(self, repository: Repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.setWindowTitle("导出历史管理")
        self.resize(1040, 680)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(section_label("导出历史管理"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索文件名或内容")
        self.search.setMaximumWidth(300)
        self.search.textChanged.connect(self.apply_filter)
        top.addWidget(self.search)
        top.addStretch()
        self.limit = QSpinBox()
        self.limit.setRange(10, 10000)
        self.limit.setValue(int(repository.get("export_history_limit", 500) or 500))
        self.limit.valueChanged.connect(lambda value: repository.set("export_history_limit", value))
        top.addWidget(QLabel("记录上限"))
        top.addWidget(self.limit)
        layout.addLayout(top)

        body = QHBoxLayout()
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["时间", "文件", "行数", "字符", "大小", "备份"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self.show_preview)
        body.addWidget(self.table, 3)
        right = QVBoxLayout()
        right.addWidget(section_label("内容预览"))
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        right.addWidget(self.preview, 1)
        for title, handler in [
            ("打开文件", self.open_file), ("另存副本", self.save_copy),
            ("删除记录", self.delete_selected), ("打包全部备份", self.pack_backups),
            ("清空所有", self.clear_all),
        ]:
            button = QPushButton(title)
            button.clicked.connect(handler)
            right.addWidget(button)
        body.addLayout(right, 2)
        layout.addLayout(body, 1)
        self.all_records: list[dict[str, Any]] = []
        self.records: list[dict[str, Any]] = []
        self.refresh()

    def refresh(self) -> None:
        self.repository.reload()
        self.all_records = list(self.repository.get("export_history", []) or [])
        self.apply_filter()

    def apply_filter(self, *_args) -> None:
        query = self.search.text().strip().lower()
        self.records = [record for record in self.all_records
                        if not query or query in (str(record.get("file_name", "")) + " " + str(record.get("content", ""))).lower()]
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            size = int(record.get("size_bytes", 0) or 0)
            values = [
                str(record.get("timestamp", ""))[:19].replace("T", " "),
                record.get("file_name", ""), record.get("line_count", 0),
                record.get("char_count", 0), f"{size / 1024:.1f} KB",
                "是" if record.get("backup_path") else "否",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, cell)
        self.preview.clear()

    def selected_record(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        return self.records[row] if 0 <= row < len(self.records) else None

    def show_preview(self) -> None:
        record = self.selected_record()
        self.preview.setPlainText(str(record.get("content", "")) if record else "")

    def source_path(self, record: dict[str, Any]) -> Path | None:
        for key in ("file_path", "backup_path"):
            value = record.get(key)
            if value and Path(value).exists():
                return Path(value)
        return None

    def open_file(self) -> None:
        record = self.selected_record()
        source = self.source_path(record) if record else None
        if source:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(source)))
        else:
            QMessageBox.warning(self, "文件不存在", "原文件和备份文件均不存在")

    def save_copy(self) -> None:
        record = self.selected_record()
        if not record:
            return
        source = self.source_path(record)
        default = str(record.get("file_name", "导出记录.txt"))
        target, _ = QFileDialog.getSaveFileName(self, "另存副本", default)
        if not target:
            return
        if source:
            shutil.copy2(source, target)
        else:
            Path(target).write_text(str(record.get("content", "")), encoding="utf-8")

    def _verify_password(self) -> bool:
        password, ok = QInputDialog.getText(self, "密码验证", "请输入管理员密码：", QLineEdit.EchoMode.Password)
        return bool(ok and password == str(self.repository.get("unlock_password", "000")))

    def delete_selected(self) -> None:
        record = self.selected_record()
        if not record:
            return
        if not self._verify_password():
            QMessageBox.warning(self, "验证失败", "密码错误或操作已取消")
            return
        for index, item in enumerate(self.all_records):
            if item is record or item == record:
                self.all_records.pop(index)
                break
        self.repository.set("export_history", self.all_records)
        self.apply_filter()

    def clear_all(self) -> None:
        if not self.all_records or not self._verify_password():
            return
        if QMessageBox.question(self, "确认清空", f"确定清空全部 {len(self.all_records)} 条导出记录吗？") != QMessageBox.StandardButton.Yes:
            return
        self.all_records = []
        self.repository.set("export_history", [])
        self.apply_filter()

    def pack_backups(self) -> None:
        sources = [self.source_path(record) for record in self.all_records]
        sources = [source for source in sources if source]
        if not sources:
            QMessageBox.information(self, "提示", "没有可打包的导出文件")
            return
        target, _ = QFileDialog.getSaveFileName(self, "打包导出历史", "导出历史.zip", "ZIP (*.zip)")
        if not target:
            return
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            used: set[str] = set()
            for source in sources:
                name = source.name
                if name in used:
                    name = f"{source.stem}_{len(used)}{source.suffix}"
                used.add(name)
                archive.write(source, name)
        QMessageBox.information(self, "打包完成", f"已打包 {len(sources)} 个文件")


class SettingsDialog(QDialog):
    def __init__(self, repository: Repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.setWindowTitle("设置")
        self.resize(720, 780)
        self.setMinimumSize(620, 420)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 18, 20, 18)
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)
        app_section = CollapsibleSection("应用设置", expanded=True)
        layout.addWidget(app_section)
        form = QFormLayout()
        self.history_limit = QSpinBox()
        self.history_limit.setRange(10, 10000)
        self.history_limit.setValue(int(repository.get("history_limit", 100) or 100))
        self.gallery_limit = QSpinBox()
        self.gallery_limit.setRange(10, 1000)
        self.gallery_limit.setValue(int(repository.get("gallery_ocr_limit", 30) or 30))
        form.addRow("历史记录上限", self.history_limit)
        form.addRow("图片预览数量", self.gallery_limit)
        self.merge_path = QLineEdit(str(repository.get("merge_save_path", "") or ""))
        self.export_path = QLineEdit(str(repository.get("export_save_path", "") or ""))
        merge_row = QHBoxLayout()
        merge_row.addWidget(self.merge_path)
        merge_browse = QPushButton("浏览")
        merge_browse.clicked.connect(lambda: self.choose_dir(self.merge_path))
        merge_row.addWidget(merge_browse)
        export_row = QHBoxLayout()
        export_row.addWidget(self.export_path)
        export_browse = QPushButton("浏览")
        export_browse.clicked.connect(lambda: self.choose_dir(self.export_path))
        export_row.addWidget(export_browse)
        form.addRow("拼接图片目录", merge_row)
        form.addRow("导出文件目录", export_row)
        self.excel_export_format = QComboBox()
        for format_key, format_name in EXCEL_EXPORT_FORMAT_NAMES.items():
            self.excel_export_format.addItem(format_name, format_key)
        current_excel_format = str(repository.get("excel_export_format", "grouped") or "grouped")
        current_index = self.excel_export_format.findData(current_excel_format)
        self.excel_export_format.setCurrentIndex(
            current_index if current_index >= 0 else self.excel_export_format.findData("grouped")
        )
        form.addRow("Excel默认导出格式", self.excel_export_format)
        self.report_format = QComboBox()
        for format_key, format_name in REPORT_FORMAT_NAMES.items():
            self.report_format.addItem(format_name, format_key)
        current_report_format = str(repository.get("report_format", "legacy") or "legacy")
        report_format_index = self.report_format.findData(current_report_format)
        self.report_format.setCurrentIndex(report_format_index if report_format_index >= 0 else 0)
        form.addRow("文本报告展示格式", self.report_format)
        app_section.add_layout(form)
        limit_section = CollapsibleSection("每日识别限制", expanded=True)
        layout.addWidget(limit_section)
        limit_form = QFormLayout()
        self.daily_limit_enabled: dict[str, QCheckBox] = {}
        self.daily_limit_count: dict[str, QSpinBox] = {}
        self.daily_limit_status: dict[str, QLabel] = {}
        for mode in ("accurate", "general"):
            daily_limit = repository.daily_ocr_limit_config(mode)
            enabled = QCheckBox("启用")
            enabled.setChecked(bool(daily_limit.get("enabled", False)))
            count = QSpinBox()
            count.setRange(1, 100000)
            try:
                count.setValue(max(1, int(daily_limit.get("max_count", 10))))
            except (TypeError, ValueError):
                count.setValue(10)
            enabled.setEnabled(False)
            count.setEnabled(False)
            self.daily_limit_enabled[mode] = enabled
            self.daily_limit_count[mode] = count
            limit_form.addRow(f"{MODE_NAMES[mode]}识别开关", enabled)
            limit_form.addRow(f"{MODE_NAMES[mode]}每日最多接口调用", count)
            status = muted_label("")
            self.daily_limit_status[mode] = status
            limit_form.addRow("今日剩余", status)
        unlock_limit = QPushButton("解锁修改")
        unlock_limit.clicked.connect(self.unlock_daily_limit)
        limit_form.addRow("", unlock_limit)
        limit_section.add_layout(limit_form)
        limit_section.add_widget(muted_label("快速识别不受限制；修改高精度或通用的每日限额、开关前需输入管理员密码。当天次数会在次日自动归零。", True))
        self.refresh_daily_limit_status()
        maintenance_section = CollapsibleSection("数据维护", expanded=False)
        layout.addWidget(maintenance_section)
        maintenance = QGridLayout()
        data_info = QPushButton("数据文件信息")
        data_info.clicked.connect(self.show_data_info)
        backup = QPushButton("备份全部数据")
        backup.clicked.connect(self.backup_data)
        clear_cache = QPushButton("清空 OCR 缓存")
        clear_cache.clicked.connect(self.clear_cache)
        export_history = QPushButton("导出历史管理")
        export_history.clicked.connect(lambda: ExportHistoryDialog(self.repository, self).exec())
        maintenance.addWidget(data_info, 0, 0)
        maintenance.addWidget(backup, 0, 1)
        maintenance.addWidget(clear_cache, 1, 0)
        maintenance.addWidget(export_history, 1, 1)
        maintenance_section.add_layout(maintenance)
        maintenance_section.add_widget(muted_label("备份会保存完整 ocr_data.json；清空缓存不会删除图片和识别历史。", True))
        security_section = CollapsibleSection("安全设置", expanded=False)
        layout.addWidget(security_section)
        password_form = QFormLayout()
        self.old_password = QLineEdit()
        self.old_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.old_password.setPlaceholderText("请输入当前管理员密码")
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password.setPlaceholderText("请输入新密码")
        self.confirm_password = QLineEdit()
        self.confirm_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password.setPlaceholderText("再次输入新密码")
        password_form.addRow("旧密码", self.old_password)
        password_form.addRow("新密码", self.new_password)
        password_form.addRow("确认新密码", self.confirm_password)
        security_section.add_layout(password_form)
        password_actions = QHBoxLayout()
        change_password = QPushButton("修改密码")
        change_password.clicked.connect(self.change_password)
        password_actions.addWidget(change_password)
        self.password_status = muted_label("")
        password_actions.addWidget(self.password_status)
        password_actions.addStretch()
        security_section.add_layout(password_actions)
        buttons = QHBoxLayout()
        save = QPushButton("保存")
        save.setObjectName("primary")
        save.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(save)
        buttons.setContentsMargins(20, 0, 20, 12)
        outer_layout.addLayout(buttons)

    def accept(self) -> None:
        self.repository.set("history_limit", self.history_limit.value())
        self.repository.set("gallery_ocr_limit", self.gallery_limit.value())
        self.repository.set("merge_save_path", self.merge_path.text().strip())
        self.repository.set("export_save_path", self.export_path.text().strip())
        self.repository.set(
            "excel_export_format", str(self.excel_export_format.currentData() or "grouped")
        )
        self.repository.set("report_format", str(self.report_format.currentData() or "legacy"))
        if getattr(self, "daily_limit_unlocked", False):
            limits = self.repository.get("daily_ocr_limits", {}) or {}
            limits = dict(limits) if isinstance(limits, dict) else {}
            for mode in ("accurate", "general"):
                previous = self.repository.daily_ocr_limit_config(mode)
                limits[mode] = {
                    "enabled": self.daily_limit_enabled[mode].isChecked(),
                    "max_count": self.daily_limit_count[mode].value(),
                    "date": str(previous.get("date", "")),
                    "used": previous.get("used", 0),
                }
            self.repository.set("daily_ocr_limits", limits)
            status_lines = []
            for mode in ("accurate", "general"):
                if self.daily_limit_enabled[mode].isChecked():
                    status_lines.append(
                        f"{MODE_NAMES[mode]}识别：已启用，每日最多 {self.daily_limit_count[mode].value()} 次接口调用"
                    )
                else:
                    status_lines.append(f"{MODE_NAMES[mode]}识别：未启用")
            QMessageBox.information(self, "每日识别限制已保存", "\n".join(status_lines))
        super().accept()

    def refresh_daily_limit_status(self) -> None:
        for mode in ("accurate", "general"):
            allowed, used, max_count = self.repository.daily_ocr_limit_status(mode)
            config = self.repository.daily_ocr_limit_config(mode)
            if not config.get("enabled", False):
                text = "未启用，不限额"
            else:
                remaining = max(0, max_count - used)
                text = f"已用 {used}/{max_count}，剩余 {remaining} 次"
            self.daily_limit_status[mode].setText(text)

    def unlock_daily_limit(self) -> None:
        if not self._verify_password():
            QMessageBox.warning(self, "验证失败", "密码错误或操作已取消")
            return
        self.daily_limit_unlocked = True
        for mode in ("accurate", "general"):
            self.daily_limit_enabled[mode].setEnabled(True)
            self.daily_limit_count[mode].setEnabled(True)
        self.daily_limit_count["accurate"].setFocus()

    def change_password(self) -> None:
        old = self.old_password.text()
        new = self.new_password.text()
        confirm = self.confirm_password.text()
        if old != str(self.repository.get("unlock_password", "000")):
            self.password_status.setStyleSheet("color:#C24A3A;")
            self.password_status.setText("旧密码错误")
            return
        if not new:
            self.password_status.setStyleSheet("color:#C24A3A;")
            self.password_status.setText("新密码不能为空")
            return
        if new != confirm:
            self.password_status.setStyleSheet("color:#C24A3A;")
            self.password_status.setText("两次新密码不一致")
            return
        self.repository.set("unlock_password", new)
        self.old_password.clear()
        self.new_password.clear()
        self.confirm_password.clear()
        self.password_status.setStyleSheet("color:#16A269;")
        self.password_status.setText("密码已修改")

    def choose_dir(self, target: QLineEdit) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择目录", target.text() or str(APP_DIR))
        if directory:
            target.setText(directory)

    def _verify_password(self) -> bool:
        password, ok = QInputDialog.getText(self, "密码验证", "请输入管理员密码：", QLineEdit.EchoMode.Password)
        return bool(ok and password == str(self.repository.get("unlock_password", "000")))

    def backup_data(self) -> None:
        source = APP_DIR / "ocr_data.json"
        if not source.exists():
            QMessageBox.warning(self, "无法备份", "ocr_data.json 不存在")
            return
        default = f"ocr_data_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
        target, _ = QFileDialog.getSaveFileName(self, "备份全部数据", default, "JSON (*.json)")
        if target:
            shutil.copy2(source, target)
            QMessageBox.information(self, "备份完成", "全部配置、历史、统计和缓存索引已备份。")

    def clear_cache(self) -> None:
        cache = self.repository.get("ocr_cache", {}) or {}
        if not cache:
            QMessageBox.information(self, "提示", "OCR 缓存已经为空")
            return
        if not self._verify_password():
            QMessageBox.warning(self, "验证失败", "密码错误或操作已取消")
            return
        if QMessageBox.question(self, "确认清空", f"确定清空 {len(cache)} 条 OCR 缓存吗？") == QMessageBox.StandardButton.Yes:
            self.repository.set("ocr_cache", {})
            QMessageBox.information(self, "清理完成", "OCR 缓存索引已清空，图片和识别历史未删除。")

    def show_data_info(self) -> None:
        data_path = APP_DIR / "ocr_data.json"
        size = data_path.stat().st_size if data_path.exists() else 0
        history = len(self.repository.get("history", []) or [])
        exports = len(self.repository.get("export_history", []) or [])
        cache = len(self.repository.get("ocr_cache", {}) or {})
        QMessageBox.information(
            self, "数据文件信息",
            f"数据文件：{data_path}\n文件大小：{size / 1024 / 1024:.2f} MB\n\n"
            f"识别历史：{history} 条\n导出历史：{exports} 条\nOCR 缓存：{cache} 条",
        )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.repository = Repository()
        # Keep the native title bar controls and use the visible app icon for
        # the title bar and Windows taskbar entry.
        self.setWindowTitle("\u200b")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1000, 680)
        config = self.repository.get("qt_window_config", {}) or {}
        self.resize(int(config.get("width", 1050)), int(config.get("height", 730)))
        self._responsive_key: tuple[int, int] | None = None
        self._responsive_ui_scale = 1.0
        self._build()

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = QFrame()
        self.header = header
        header.setObjectName("header")
        header.setFixedHeight(48)
        header_layout = QHBoxLayout(header)
        self.header_layout = header_layout
        header_layout.setContentsMargins(18, 0, 14, 0)
        header_layout.setSpacing(8)
        menu = QLabel("☰")
        self.menu_label = menu
        menu.setFixedWidth(18)
        menu.setAlignment(Qt.AlignmentFlag.AlignCenter)
        menu.setStyleSheet("font-size:16px;color:#4F545B;")

        logo = QWidget()
        self.logo_widget = logo
        logo.setFixedSize(18, 20)
        logo_layout = QHBoxLayout(logo)
        logo_layout.setContentsMargins(1, 2, 1, 2)
        logo_layout.setSpacing(2)
        self.logo_bars: list[QFrame] = []
        for height in (7, 12, 16):
            bar = QFrame()
            bar.setFixedSize(4, height)
            bar.setStyleSheet(f"background:{YELLOW};border-radius:1px;")
            logo_layout.addWidget(bar, 0, Qt.AlignmentFlag.AlignBottom)
            self.logo_bars.append(bar)

        title = QLabel("OCR 数据分类工具")
        title.setObjectName("appTitle")
        header_layout.addWidget(menu)
        header_layout.addSpacing(2)
        header_layout.addWidget(logo)
        header_layout.addSpacing(1)
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.font_size_label = QLabel("字号")
        font_config = self.repository.get("font_config", {}) or {}
        initial_font_size = max(8, min(30, int(font_config.get("font_size", 11) or 11)))
        self.font_size = QComboBox()
        self.font_size.addItems([str(size) for size in range(8, 31)])
        self.font_size.setCurrentText(str(initial_font_size))
        self.font_size.setFixedSize(64, 30)
        self.font_size.setToolTip("调整分类表格和文本报告的字号")
        self.font_size.setStyleSheet(
            "QComboBox {min-height:0;max-height:28px;padding:0 7px;"
            "background:#FFFFFF;border:1px solid #E2E5E9;border-radius:6px;}"
        )

        settings = QPushButton("⚙  设置")
        self.settings_button = settings
        settings.setFixedHeight(30)
        settings.setStyleSheet(
            "border:0;background:transparent;padding:0 8px;"
            "font-size:12px;color:#4F545B;"
        )
        settings.clicked.connect(self.open_settings)
        help_button = QPushButton("ⓘ  帮助")
        self.help_button = help_button
        help_button.setFixedHeight(30)
        help_button.setStyleSheet(
            "border:0;background:transparent;padding:0 8px;"
            "font-size:12px;color:#4F545B;"
        )
        help_button.clicked.connect(self.show_help)
        header_layout.addWidget(self.font_size_label)
        header_layout.addWidget(self.font_size)
        header_layout.addSpacing(2)
        header_layout.addWidget(settings)
        header_layout.addWidget(help_button)
        root_layout.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root_layout.addLayout(body, 1)

        sidebar = QFrame()
        self.sidebar = sidebar
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(150)
        sidebar_layout = QVBoxLayout(sidebar)
        self.sidebar_layout = sidebar_layout
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        self.sidebar_menu = QWidget()
        self.sidebar_menu.setFixedHeight(32)
        self.sidebar_menu_layout = QHBoxLayout(self.sidebar_menu)
        self.sidebar_menu_layout.setContentsMargins(16, 0, 0, 0)
        self.sidebar_menu_layout.setSpacing(0)
        self.sidebar_menu_icon = QLabel()
        self.sidebar_menu_qicon = sidebar_icon("menu")
        self.sidebar_menu_icon.setPixmap(
            self.sidebar_menu_qicon.pixmap(QSize(14, 14))
        )
        self.sidebar_menu_layout.addWidget(self.sidebar_menu_icon)
        self.sidebar_menu_layout.addStretch()
        sidebar_layout.addWidget(self.sidebar_menu)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.stack = QStackedWidget()

        self.home_page = HomePage(self.repository)
        self.ocr_page = OCRPage(self.repository)
        self.ocr_page.top_notice_bar.setParent(self)
        self.ocr_page.top_notice_bar.setFixedWidth(380)
        self.ocr_page.top_notice_bar.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )
        self.ocr_page.top_notice_bar.hide()
        self.gallery_page = GalleryPage(self.repository)
        self.history_page = HistoryPage(self.repository)
        self.keys_page = KeysPage(self.repository)
        self.stats_page = StatsPage(self.repository)
        self.rules_page = RulesPage(self.repository)
        pages = [
            ("home", "首页", self.home_page),
            ("ocr", "OCR 识别", self.ocr_page),
            ("image", "图片预览", self.gallery_page),
            ("history", "历史记录", self.history_page),
            ("key", "密钥管理", self.keys_page),
            ("stats", "统计", self.stats_page),
            ("rules", "规则尺寸", self.rules_page),
        ]
        self.nav_buttons: list[QPushButton] = []
        for index, (icon, name, page) in enumerate(pages):
            self.stack.addWidget(page)
            button = QPushButton(f"  {name}")
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setIcon(sidebar_icon(icon))
            button.setIconSize(QSize(18, 18))
            button.clicked.connect(lambda _checked=False, i=index: self.open_page(i))
            self.nav_group.addButton(button)
            self.nav_buttons.append(button)
            sidebar_layout.addWidget(button)
        sidebar_layout.addStretch()

        self.status_frame = QFrame()
        self.status_frame.setStyleSheet("background:#FFFFFF;border-top:1px solid #E8EAED;")
        status_layout = QHBoxLayout(self.status_frame)
        self.status_layout = status_layout
        status_layout.setContentsMargins(16, 9, 10, 9)
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color:#3B82F6;")
        self.status_text = QLabel("就绪")
        self.status_text.setStyleSheet("color:#6F747C;font-size:12px;")
        status_layout.addWidget(self.status_dot)
        status_layout.addWidget(self.status_text)
        status_layout.addStretch()
        sidebar_layout.addWidget(self.status_frame)
        body.addWidget(sidebar)
        body.addWidget(self.stack, 1)

        self.ocr_page.statusChanged.connect(self.set_status)
        self.ocr_page.dataChanged.connect(self.refresh_data_pages)
        self.stats_page.statsCleared.connect(self.home_page.refresh)
        self.font_size.currentTextChanged.connect(
            lambda value: self.ocr_page.set_shared_font_size(int(value))
        )
        self.history_page.parseRequested.connect(self.parse_history_record)
        self.keys_page.keysChanged.connect(self.ocr_page._refresh_key_states)
        self.nav_buttons[1].setChecked(True)
        self.open_page(1)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        """Scale the shell and OCR workspace from the 1050 x 730 reference."""
        x_scale = max(0.90, min(1.60, self.width() / 1050.0))
        y_scale = max(0.90, min(1.45, self.height() / 730.0))
        ui_scale = min(x_scale, y_scale)
        key = (round(x_scale * 100), round(y_scale * 100))
        if key == self._responsive_key:
            return
        self._responsive_key = key
        self._responsive_ui_scale = ui_scale

        self.header.setFixedHeight(round(48 * y_scale))
        self.header_layout.setContentsMargins(
            round(18 * x_scale), 0, round(14 * x_scale), 0
        )
        self.header_layout.setSpacing(max(7, round(8 * ui_scale)))
        self.menu_label.setFixedWidth(round(18 * ui_scale))
        self.menu_label.setStyleSheet(
            f"font-size:{max(15, round(16 * ui_scale))}px;color:#4F545B;"
        )
        self.logo_widget.setFixedSize(
            round(18 * ui_scale), round(20 * ui_scale)
        )
        for bar, base_height in zip(self.logo_bars, (7, 12, 16)):
            bar.setFixedSize(
                max(3, round(4 * ui_scale)), max(6, round(base_height * ui_scale))
            )
        header_button_height = max(28, round(30 * y_scale))
        header_font_size = max(11, round(12 * ui_scale))
        header_padding = max(7, round(8 * x_scale))
        self.font_size_label.setStyleSheet(
            f"font-size:{header_font_size}px;color:#4F545B;background:transparent;"
        )
        self.font_size.setFixedSize(
            max(58, round(64 * x_scale)), header_button_height
        )
        self.font_size.setStyleSheet(
            f"QComboBox {{min-height:0;max-height:{max(26, header_button_height - 2)}px;"
            f"padding:0 {max(6, round(7 * x_scale))}px;"
            f"font-size:{max(10, round(11 * ui_scale))}px;background:#FFFFFF;"
            "border:1px solid #E2E5E9;border-radius:6px;}"
        )
        for button in (self.settings_button, self.help_button):
            button.setFixedHeight(header_button_height)
            button.setStyleSheet(
                f"border:0;background:transparent;padding:0 {header_padding}px;"
                f"font-size:{header_font_size}px;color:#4F545B;"
            )

        self.sidebar.setFixedWidth(round(150 * x_scale))
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_menu.setFixedHeight(max(28, round(32 * y_scale)))
        self.sidebar_menu_layout.setContentsMargins(
            round(16 * x_scale), 0, 0, 0
        )
        menu_icon_size = max(13, round(14 * ui_scale))
        self.sidebar_menu_icon.setPixmap(
            self.sidebar_menu_qicon.pixmap(QSize(menu_icon_size, menu_icon_size))
        )
        nav_height = max(46, round(52 * y_scale))
        nav_font_size = max(12, round(13 * ui_scale))
        nav_padding = max(14, round(16 * x_scale))
        checked_padding = max(11, nav_padding - round(3 * x_scale))
        nav_icon_size = max(17, round(18 * ui_scale))
        compact_button_height = max(24, round(26 * y_scale))
        compact_input_height = max(25, round(27 * y_scale))
        for button in self.nav_buttons:
            button.setIconSize(QSize(nav_icon_size, nav_icon_size))
        self.setStyleSheet(
            f"QLabel#appTitle {{font-size:{max(14, round(15 * ui_scale))}px;"
            "font-weight:700;}"
            f"QLabel#sectionTitle {{font-size:{max(11, round(12 * ui_scale))}px;"
            "font-weight:700;}"
            f"QLabel#muted {{font-size:{max(9, round(10 * ui_scale))}px;color:{MUTED};}}"
            f"QPushButton#nav {{min-height:{nav_height}px;max-height:{nav_height}px;"
            f"padding-left:{nav_padding}px;font-size:{nav_font_size}px;}}"
            f"QPushButton#nav:checked {{background:#FFF7E3;color:#30343A;"
            f"border-left:{max(3, round(3 * x_scale))}px solid {YELLOW};"
            f"padding-left:{checked_padding}px;}}"
            f"QFrame#card {{background:#FFFFFF;border:1px solid #EEF0F2;"
            f"border-radius:{max(7, round(8 * ui_scale))}px;}}"
            f"QFrame#card[panelRole=\"parameters\"] {{background:#FFFFFF;"
            f"border:1px solid #E7E9EC;border-radius:{max(10, round(12 * ui_scale))}px;}}"
            f"QLineEdit,QSpinBox,QDoubleSpinBox {{min-height:{max(31, round(34 * y_scale))}px;"
            f"font-size:{max(11, round(12 * ui_scale))}px;}}"
            f"QRadioButton {{font-size:{max(11, round(12 * ui_scale))}px;}}"
            f"QPushButton[compactParam=\"true\"] {{min-height:{compact_button_height}px;"
            f"max-height:{compact_button_height}px;padding:0 {max(6, round(8 * x_scale))}px;}}"
            f"QLineEdit[compactParamInput=\"true\"],"
            f"QSpinBox[compactParamInput=\"true\"] {{min-height:{compact_input_height}px;"
            f"max-height:{compact_input_height}px;padding:0 {max(6, round(8 * x_scale))}px;}}"
        )
        self.status_layout.setContentsMargins(
            round(16 * x_scale), round(9 * y_scale),
            round(10 * x_scale), round(9 * y_scale),
        )
        status_font_size = max(10, round(12 * ui_scale))
        self.status_text.setStyleSheet(
            f"color:#6F747C;font-size:{status_font_size}px;"
        )
        toast_width = min(
            max(320, round(380 * ui_scale)), max(320, self.width() - 40)
        )
        self.ocr_page.top_notice_bar.setFixedWidth(toast_width)
        self.ocr_page.apply_layout_scale(x_scale, y_scale, ui_scale)
        self._position_notice_toast()

    def _position_notice_toast(self) -> None:
        if not hasattr(self, "ocr_page"):
            return
        toast = self.ocr_page.top_notice_bar
        toast.adjustSize()
        margin = max(16, round(20 * self._responsive_ui_scale))
        x = max(margin, self.width() - toast.width() - margin)
        y = max(self.header.height() + margin, self.height() - toast.height() - margin)
        toast.move(x, y)
        if toast.isVisible():
            toast.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "ocr_page"):
            self._apply_responsive_layout()

    def open_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        page = self.stack.currentWidget()
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()

    def set_status(self, state: str, text: str) -> None:
        colors = {
            "running": ("#F59E0B", "#FFF7E8"),
            "done": ("#16A269", "#ECFDF5"),
            "error": ("#D14343", "#FFF1F1"),
        }
        foreground, background = colors.get(state, ("#3B82F6", "#FFFFFF"))
        self.status_frame.setStyleSheet(f"background:{background};border-top:1px solid #E8EAED;")
        self.status_dot.setStyleSheet(f"color:{foreground};")
        status_font_size = max(10, round(12 * self._responsive_ui_scale))
        self.status_text.setStyleSheet(
            f"color:{foreground};font-size:{status_font_size}px;"
        )
        self.status_text.setText(text)

    def parse_history_record(
        self, text: str, source_name: str, source_results: list[dict[str, Any]]
    ) -> None:
        count = self.ocr_page.load_text_for_parsing(text, source_name, source_results)
        if not count:
            QMessageBox.warning(self, "解析失败", "历史记录中没有可解析的有效内容")
            return
        self.open_page(1)

    def refresh_data_pages(self) -> None:
        self.home_page.refresh()
        self.history_page.refresh()
        self.stats_page.refresh()
        self.gallery_page.refresh()

    def open_settings(self) -> None:
        SettingsDialog(self.repository, self).exec()
        self.ocr_page._sync_report_controls(regenerate_on_change=True)
        self.home_page.refresh()

    def show_help(self) -> None:
        QMessageBox.information(
            self, "帮助",
            "通过左侧导航切换功能页面，设置和帮助入口位于窗口右上角。\n\n"
            "分类表的“批量整理”会一次性应用已设置的替换、空格和清理规则：\n"
            "• 替换规则：将名称中的指定文字替换为目标文字。\n"
            "• 空格规则：为已配置的两个字词加入空格。\n"
            "• 清理规则：删除名称中匹配的内容；清理后为空的条目会移除。\n"
            "• A/B 组会按当前字体规则重新判断；C/D 组不会被自动改动。\n\n"
            "批量整理不会修改文字坐标，操作后可使用“撤销”恢复。\n\n"
            "导出 Excel 时会自动保存当前已校对的分类表；通过“分类表历史”恢复后可继续修改，再导出 Excel。",
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        self.repository.set("qt_window_config", {
            "width": self.width(), "height": self.height(),
            "x": self.x(), "y": self.y(),
        })
        super().closeEvent(event)


def main() -> int:
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("local.ocr.classifier")
    app = QApplication(sys.argv)
    app.setApplicationName("OCR")
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    apply_windows_taskbar_icon(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
