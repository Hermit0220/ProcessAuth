"""
ui/dashboard.py
Main monitoring dashboard — frameless, glassmorphic, draggable.
Receives live stats updates via Qt signals from the session manager.
"""
import os
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal, QObject, Slot
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea,
    QSizePolicy, QProgressBar, QFileDialog,
    QMessageBox, QComboBox, QTabWidget, QSizeGrip,
)

from analysis.behavioral_engine import SessionStats
from utils.logger import get_logger
from ui.theme import theme_manager

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Signal bridge  (emits stats from worker thread → UI thread safely)
# ──────────────────────────────────────────────────────────────────────────────

class StatsSignal(QObject):
    updated = Signal(object)   # SessionStats


_stats_signal = StatsSignal()


def emit_stats(stats: SessionStats) -> None:
    """Called from worker threads; routes to the Qt signal system."""
    _stats_signal.updated.emit(stats)


# ──────────────────────────────────────────────────────────────────────────────
# Stat card widget
# ──────────────────────────────────────────────────────────────────────────────

class StatCard(QFrame):
    def __init__(self, label: str, value: str = "0", color: str = "#06b6d4") -> None:
        super().__init__()
        self._color = color
        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        self._lbl = QLabel(label.upper())
        self._lbl.setStyleSheet(
            "font-size:9px;font-weight:700;color:#334155;"
            "letter-spacing:1.8px;background:transparent;border:none;"
        )

        self._val = QLabel(value)
        self._val.setStyleSheet(
            f"font-size:26px;font-weight:800;color:{color};"
            "background:transparent;border:none;"
        )

        layout.addWidget(self._lbl)
        layout.addWidget(self._val)

    def set_value(self, v: str) -> None:
        self._val.setText(v)


# ──────────────────────────────────────────────────────────────────────────────
# Score arc widget
# ──────────────────────────────────────────────────────────────────────────────

class ScoreArc(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._score = 100.0
        self.setFixedSize(170, 170)

    def set_score(self, score: float) -> None:
        self._score = max(0.0, min(100.0, score))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        margin = 18
        rect = self.rect().adjusted(margin, margin, -margin, -margin)

        # Track ring
        pen = QPen(QColor(255, 255, 255, 14), 12, Qt.SolidLine, Qt.FlatCap)
        painter.setPen(pen)
        painter.drawArc(rect, 225 * 16, -270 * 16)

        # Score arc
        color_str = self._arc_color()
        pen2 = QPen(QColor(color_str), 12, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen2)
        span = int(-270 * 16 * self._score / 100)
        painter.drawArc(rect, 225 * 16, span)

        # Center number
        painter.setPen(QPen(QColor(color_str)))
        font = QFont("Segoe UI", 28, QFont.Bold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, f"{int(self._score)}")

    def _arc_color(self) -> str:
        if self._score >= 75:
            return "#22c55e"
        elif self._score >= 50:
            return "#eab308"
        return "#ef4444"


# ──────────────────────────────────────────────────────────────────────────────
# Main Dashboard Window
# ──────────────────────────────────────────────────────────────────────────────

class Dashboard(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ProcessAuth")
        self.setMinimumSize(980, 680)
        self.resize(1200, 760)          # sensible default size
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)

        self._session    = None
        self._timer      = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._start_time : float | None = None
        self._paused     = False
        self._log_lines  : list[str] = []
        self._drag_pos   = None
        self._last_susp  = 0   # track suspicious count to avoid log spam
        self._last_ext   = 0   # track external hits

        self._build_ui()
        _stats_signal.updated.connect(self._on_stats_update)

    # ── window painting ───────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        bg = theme_manager.get("window_bg")
        p.setBrush(QBrush(bg))
        p.drawRect(self.rect())

    # ── dragging ──────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("RootWidget")
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_title_bar())

        # Tab container
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane { border: none; background: transparent; }
            QTabBar::tab {
                background: rgba(255,255,255,0.03); color: #334155;
                border: 1px solid rgba(255,255,255,0.06); border-bottom: none;
                border-radius: 8px 8px 0 0; padding: 8px 22px;
                font-size: 12px; font-weight: 700; letter-spacing: 0.5px; margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: rgba(6,182,212,0.10); color: #06b6d4;
                border-color: rgba(6,182,212,0.25);
            }
            QTabBar::tab:hover:!selected { background: rgba(255,255,255,0.06); color: #94a3b8; }
        """)

        # Tab 1 - Monitor
        monitor_widget = QWidget()
        monitor_widget.setStyleSheet("background: transparent;")
        body = QHBoxLayout(monitor_widget)
        body.setContentsMargins(18, 18, 18, 18)
        body.setSpacing(14)
        body.addLayout(self._build_left_panel(), stretch=2)
        body.addLayout(self._build_right_panel(), stretch=3)
        self._tabs.addTab(monitor_widget, "Monitor")

        # Tab 2 - AI Humanizer
        from ui.humanizer_panel import HumanizerPanel
        self._humanizer_panel = HumanizerPanel()
        self._tabs.addTab(self._humanizer_panel, "AI Humanizer")

        root.addWidget(self._tabs)
        root.addWidget(self._build_status_bar())

        self.apply_theme()
        theme_manager.theme_changed.connect(self.apply_theme)

    # ── title bar ─────────────────────────────────────────────────────────────

    def _build_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(52)
        bar.setStyleSheet(
            "background: rgba(255,255,255,0.03);"
            "border-bottom: 1px solid rgba(255,255,255,0.06);"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 14, 0)
        lay.setSpacing(0)

        # Logo + title
        icon = QLabel("⬡")
        icon.setStyleSheet("font-size:18px; color:#06b6d4; background:transparent;")
        title = QLabel("  ProcessAuth")
        title.setStyleSheet("font-size:15px;font-weight:800;color:#06b6d4;background:transparent;letter-spacing:0.5px;")
        sub = QLabel("  ·  Behavioral Authentisizer by Hermit")
        sub.setStyleSheet("font-size:11px;color:#1e3a4a;background:transparent;")

        # Status pill
        self._status_pill = QLabel("● IDLE")
        self._status_pill.setStyleSheet(
            "font-size:10px;font-weight:700;letter-spacing:1.5px;"
            "padding:4px 14px;border-radius:20px;"
            "background:rgba(148,163,184,0.10);color:#475569;"
            "border:1px solid rgba(148,163,184,0.20);margin-right:10px;"
        )

        # Timer
        self._timer_label = QLabel("00:00:00")
        self._timer_label.setStyleSheet(
            "font-size:14px;font-weight:600;color:#334155;"
            "font-family:Consolas,monospace;background:transparent;margin-right:16px;"
        )

        # ── Window control buttons ─────────────────────────────────────────────
        #    Fully visible — light on dark, with hover states set via
        #    inline stylesheet (avoids cursor: pointer QSS warning)

        btn_min = QPushButton("—")
        btn_min.setFixedSize(30, 30)
        btn_min.setCursor(Qt.PointingHandCursor)
        btn_min.setStyleSheet("""
            QPushButton {
                background: rgba(30,30,40, 200);
                border: 1px solid rgba(255,255,255,10);
                padding: 10px;
                border-radius: 8px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.16);
                color: #e2e8f0;
                border-color: rgba(255,255,255,0.25);
            }
            QPushButton:pressed { background: rgba(255,255,255,0.05); }
        """)
        btn_min.clicked.connect(self.showMinimized)

        btn_close = QPushButton()
        btn_close.setFixedSize(30, 30)
        btn_close.setCursor(Qt.PointingHandCursor)
        target_path = os.path.abspath("assets/close.svg").replace("\\", "/")
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: rgba(239,68,68,0.12);
                border: 1px solid rgba(239,68,68,0.25);
                border-radius: 8px;
                image: url("{target_path}");
                padding: 8px;
            }}
            QPushButton:hover {{
                background: rgba(239,68,68,0.28);
                border-color: #ef4444;
            }}
            QPushButton:pressed {{ background: #dc2626; }}
        """)
        btn_close.clicked.connect(self._safe_close)

        # ── Theme toggle button ────────────────────────────────────────────────
        self._btn_theme = QPushButton("☀")
        self._btn_theme.setFixedSize(30, 30)
        self._btn_theme.setCursor(Qt.PointingHandCursor)
        self._btn_theme.setToolTip("Toggle Light / Dark mode")
        self._btn_theme.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 8px;
                font-size: 14px;
                color: #f1c40f;
            }
            QPushButton:hover { background: rgba(255,255,255,0.18); }
            QPushButton:pressed { background: rgba(255,255,255,0.05); }
        """)
        self._btn_theme.clicked.connect(self._on_theme_toggle)

        lay.addWidget(icon)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addStretch()
        lay.addWidget(self._status_pill)
        lay.addWidget(self._timer_label)
        lay.addSpacing(8)
        lay.addWidget(self._btn_theme)
        lay.addSpacing(4)
        lay.addWidget(btn_min)
        lay.addSpacing(6)
        lay.addWidget(btn_close)
        return bar

    # ── theme toggle ───────────────────────────────────────────────────────────

    def _on_theme_toggle(self) -> None:
        theme_manager.toggle()

    def apply_theme(self) -> None:
        is_dark = theme_manager.mode == "dark"
        self.update()  # repaint background

        if is_dark:
            self._btn_theme.setText("☀")
            self._btn_theme.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.08);
                    border: 1px solid rgba(255,255,255,0.15);
                    border-radius: 8px; font-size: 14px; color: #f1c40f;
                }
                QPushButton:hover { background: rgba(255,255,255,0.18); }
            """)
            tab_text = "#334155"; tab_sel_text = "#06b6d4"
            tab_bg   = "rgba(255,255,255,0.03)"
            tab_sel  = "rgba(6,182,212,0.10)"
            tab_bdr  = "rgba(255,255,255,0.06)"
            tab_sel_bdr = "rgba(6,182,212,0.25)"
            tab_hov  = "rgba(255,255,255,0.06)"; tab_hov_text = "#94a3b8"
            sbar_bg  = "rgba(255,255,255,0.015)"; sbar_bdr = "rgba(255,255,255,0.04)"
            sbar_col = "#1e3a4a"
        else:
            self._btn_theme.setText("🌙")
            self._btn_theme.setStyleSheet("""
                QPushButton {
                    background: rgba(0,0,0,0.08);
                    border: 1px solid rgba(0,0,0,0.15);
                    border-radius: 8px; font-size: 14px; color: #334155;
                }
                QPushButton:hover { background: rgba(0,0,0,0.14); }
            """)
            tab_text = "#475569"; tab_sel_text = "#0891b2"
            tab_bg   = "rgba(0,0,0,0.04)"
            tab_sel  = "rgba(6,182,212,0.12)"
            tab_bdr  = "rgba(0,0,0,0.08)"
            tab_sel_bdr = "rgba(8,145,178,0.35)"
            tab_hov  = "rgba(0,0,0,0.06)"; tab_hov_text = "#334155"
            sbar_bg  = "rgba(0,0,0,0.03)"; sbar_bdr = "rgba(0,0,0,0.08)"
            sbar_col = "#64748b"

        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: transparent; }}
            QTabBar::tab {{
                background: {tab_bg}; color: {tab_text};
                border: 1px solid {tab_bdr}; border-bottom: none;
                border-radius: 8px 8px 0 0; padding: 8px 22px;
                font-size: 12px; font-weight: 700; letter-spacing: 0.5px; margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background: {tab_sel}; color: {tab_sel_text};
                border-color: {tab_sel_bdr};
            }}
            QTabBar::tab:hover:!selected {{ background: {tab_hov}; color: {tab_hov_text}; }}
        """)
        self._status_text.setStyleSheet(
            f"font-size:10px;color:{sbar_col};background:transparent;"
        )

    # ── left panel ────────────────────────────────────────────────────────────

    def _build_left_panel(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(12)

        # ── Score arc card ─────────────────────────────────────────────────
        score_card = QFrame()
        score_card.setMinimumHeight(270)
        score_card.setStyleSheet("""
            QFrame {
                background: rgba(6,182,212,0.04);
                border: 1px solid rgba(6,182,212,0.14);
                border-radius: 16px;
            }
        """)
        sc = QVBoxLayout(score_card)
        sc.setContentsMargins(18, 16, 18, 16)
        sc.setSpacing(0)

        slbl = QLabel("AUTHENTICITY SCORE")
        slbl.setAlignment(Qt.AlignCenter)
        slbl.setStyleSheet(
            "font-size:9px;font-weight:700;color:#164e63;"
            "letter-spacing:2px;background:transparent;border:none;"
        )

        self._score_arc = ScoreArc()
        self._score_arc.setFixedSize(180, 180)

        self._score_label = QLabel("High Authenticity")
        self._score_label.setAlignment(Qt.AlignCenter)
        self._score_label.setStyleSheet(
            "font-size:12px;color:#22c55e;font-weight:700;"
            "letter-spacing:0.5px;"
            "background:transparent;border:none;"
        )

        sc.addWidget(slbl)
        sc.addSpacing(8)
        sc.addWidget(self._score_arc, alignment=Qt.AlignCenter)
        sc.addSpacing(8)
        sc.addWidget(self._score_label)
        col.addWidget(score_card)

        # ── Document label ─────────────────────────────────────────────────
        doc_card = self._glass_card()
        dc = QVBoxLayout(doc_card)
        dc.setContentsMargins(16, 12, 16, 12)
        dc.setSpacing(3)
        dc.addWidget(self._section_lbl("Document Monitored"))
        self._doc_label = QLabel("No document selected")
        self._doc_label.setWordWrap(True)
        self._doc_label.setStyleSheet(
            "font-size:12px;color:#334155;background:transparent;border:none;"
        )
        dc.addWidget(self._doc_label)
        col.addWidget(doc_card)

        # ── 3×2 stat-card grid ─────────────────────────────────────────────
        g1 = QHBoxLayout(); g1.setSpacing(10)
        self._card_keys  = StatCard("Keystrokes", "0", "#06b6d4")
        self._card_clip  = StatCard("Clipboard",  "0", "#8b5cf6")
        g1.addWidget(self._card_keys); g1.addWidget(self._card_clip)
        col.addLayout(g1)

        g2 = QHBoxLayout(); g2.setSpacing(10)
        self._card_susp  = StatCard("Suspicious", "0", "#ef4444")
        self._card_speed = StatCard("Speed (cpm)", "0", "#22c55e")
        g2.addWidget(self._card_susp); g2.addWidget(self._card_speed)
        col.addLayout(g2)

        g3 = QHBoxLayout(); g3.setSpacing(10)
        self._card_pasted = StatCard("Pasted Chars", "0", "#f59e0b")
        self._card_ext    = StatCard("Web Hits", "0", "#f472b6")
        g3.addWidget(self._card_pasted); g3.addWidget(self._card_ext)
        col.addLayout(g3)

        # ── Typing activity bar ────────────────────────────────────────────
        prog_card = self._glass_card()
        pc = QVBoxLayout(prog_card)
        pc.setContentsMargins(16, 12, 16, 14)
        pc.setSpacing(6)
        pc.addWidget(self._section_lbl("Typing Activity Intensity"))
        self._typing_bar = QProgressBar()
        self._typing_bar.setRange(0, 100)
        self._typing_bar.setValue(0)
        self._typing_bar.setTextVisible(False)
        self._typing_bar.setFixedHeight(6)
        self._typing_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255,255,255,0.05);
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                border-radius: 3px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #06b6d4, stop:1 #8b5cf6);
            }
        """)
        pc.addWidget(self._typing_bar)
        col.addWidget(prog_card)

        col.addStretch()
        return col

    # ── right panel ───────────────────────────────────────────────────────────

    def _build_right_panel(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(12)

        # ── Control buttons row ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        def mk_btn(text, color_bg, color_text, border_color):
            b = QPushButton(text)
            b.setFixedHeight(40)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {color_bg};
                    color: {color_text};
                    border: 1px solid {border_color};
                    border-radius: 10px;
                    font-size: 13px;
                    font-weight: 700;
                    padding: 0 18px;
                }}
                QPushButton:hover {{ filter: brightness(1.15); opacity: 0.9; }}
                QPushButton:disabled {{
                    background: rgba(255,255,255,0.04);
                    color: #1e293b;
                    border-color: rgba(255,255,255,0.06);
                }}
            """)
            return b

        self._btn_start = mk_btn("▶  Start Session",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0891b2,stop:1 #06b6d4)",
            "#ffffff", "#0891b2")
        self._btn_start.clicked.connect(self._on_start)

        self._btn_pause = mk_btn("⏸  Pause",
            "rgba(234,179,8,0.12)", "#eab308", "rgba(234,179,8,0.30)")
        self._btn_pause.setEnabled(False)
        self._btn_pause.clicked.connect(self._on_pause)

        self._btn_stop = mk_btn("⏹  Stop & Report",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #dc2626,stop:1 #ef4444)",
            "#ffffff", "#dc2626")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._on_stop)

        self._export_fmt = QComboBox()
        self._export_fmt.addItems(["HTML", "JSON"])
        self._export_fmt.setFixedHeight(40)
        self._export_fmt.setFixedWidth(90)
        self._export_fmt.setStyleSheet("""
            QComboBox {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px;
                padding: 0 12px;
                color: #94a3b8;
                font-size: 12px;
                font-weight: 600;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #0f172a;
                border: 1px solid rgba(255,255,255,0.1);
                selection-background-color: rgba(6,182,212,0.2);
                color: #e2e8f0;
            }
        """)

        btn_row.addWidget(self._btn_start)
        btn_row.addWidget(self._btn_pause)
        btn_row.addWidget(self._btn_stop)
        btn_row.addWidget(self._export_fmt)
        col.addLayout(btn_row)

        # ── Live metrics card ──────────────────────────────────────────────
        metrics_card = self._glass_card()
        ml = QVBoxLayout(metrics_card)
        ml.setContentsMargins(18, 16, 18, 16)
        ml.setSpacing(8)
        ml.addWidget(self._section_lbl("Live Session Metrics"))

        rows = [
            ("Total Keystrokes",       "_m_keys"),
            ("Total Chars Typed",      "_m_typed"),
            ("Pasted Chars (est.)",    "_m_pasted"),
            ("Backspaces",             "_m_back"),
            ("Avg Speed (cpm)",        "_m_speed"),
            ("Clipboard Events",       "_m_clip"),
            ("Suspicious Events",      "_m_susp"),
            ("External Web Hits",      "_m_ext"),
            ("Total Penalty pts",      "_m_pen"),
        ]
        for label, attr in rows:
            row = QHBoxLayout()
            lw = QLabel(label)
            lw.setStyleSheet("font-size:12px;color:#334155;background:transparent;")
            vw = QLabel("—")
            vw.setAlignment(Qt.AlignRight)
            vw.setStyleSheet("font-size:12px;color:#64748b;font-weight:600;background:transparent;")
            row.addWidget(lw)
            row.addStretch()
            row.addWidget(vw)
            setattr(self, attr, vw)
            ml.addLayout(row)

        col.addWidget(metrics_card)

        # ── Event log card ─────────────────────────────────────────────────
        log_card = self._glass_card()
        ll = QVBoxLayout(log_card)
        ll.setContentsMargins(16, 14, 16, 14)
        ll.setSpacing(6)
        ll.addWidget(self._section_lbl("Live Event Log"))

        self._log_widget = QLabel("Session not started…")
        self._log_widget.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._log_widget.setWordWrap(True)
        self._log_widget.setTextFormat(Qt.RichText)
        self._log_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._log_widget.setStyleSheet(
            "background:rgba(0,0,0,0.25);border:1px solid rgba(255,255,255,0.05);"
            "border-radius:10px;font-family:Consolas,monospace;font-size:11px;"
            "color:#334155;padding:10px;"
        )

        scroll = QScrollArea()
        scroll.setWidget(self._log_widget)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent;border:none;")
        scroll.setMinimumHeight(160)
        ll.addWidget(scroll)
        col.addWidget(log_card, stretch=1)

        return col

    # ── status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            "background:rgba(255,255,255,0.015);"
            "border-top:1px solid rgba(255,255,255,0.04);"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)
        self._status_text = QLabel("Ready — select a .docx and start a session")
        self._status_text.setStyleSheet("font-size:10px;color:#1e3a4a;background:transparent;")
        lay.addWidget(self._status_text)
        lay.addStretch()
        ver = QLabel("ProcessAuth by Hermit  ·  DuckDuckGo + Wikipedia")
        ver.setStyleSheet("font-size:10px;color:#0f2027;background:transparent;")
        lay.addWidget(ver)
        return bar

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _glass_card() -> QFrame:
        f = QFrame()
        f.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.07);
                border-radius: 14px;
            }
        """)
        return f

    @staticmethod
    def _section_lbl(text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            "font-size:9px;font-weight:700;color:#1e3a4a;"
            "letter-spacing:2px;background:transparent;border:none;"
        )
        return lbl

    def _set_status(self, text: str, dot_color: str, pill_bg: str, pill_border: str) -> None:
        self._status_pill.setText(f"● {text}")
        self._status_pill.setStyleSheet(
            f"font-size:10px;font-weight:700;letter-spacing:1.5px;"
            f"padding:4px 14px;border-radius:20px;"
            f"background:{pill_bg};color:{dot_color};"
            f"border:1px solid {pill_border};margin-right:10px;"
        )

    def _append_log(self, html: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_lines.append(
            f'<span style="color:#1e3a4a">[{ts}]</span> {html}'
        )
        if len(self._log_lines) > 80:
            self._log_lines = self._log_lines[-80:]
        self._log_widget.setText("<br>".join(self._log_lines))

    # ── session controls ──────────────────────────────────────────────────────

    def _on_start(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Document to Monitor", "",
            "Word Documents (*.docx);;All Files (*)"
        )
        if not path:
            return

        from core.session_manager import SessionManager
        self._session = SessionManager(doc_path=path, on_stats_update=emit_stats)
        try:
            self._session.start()
        except Exception as exc:
            QMessageBox.critical(self, "Start Error", str(exc))
            self._session = None
            return

        self._start_time = time.time()
        self._paused = False
        self._last_susp = 0
        self._last_ext  = 0
        self._timer.start(1000)

        short = os.path.basename(path)
        self._doc_label.setText(short)
        self._doc_label.setStyleSheet(
            "font-size:12px;color:#06b6d4;font-weight:700;"
            "background:transparent;border:none;"
        )
        self._btn_start.setEnabled(False)
        self._btn_pause.setEnabled(True)
        self._btn_stop.setEnabled(True)
        self._set_status("MONITORING", "#22c55e",
                         "rgba(34,197,94,0.10)", "rgba(34,197,94,0.30)")
        self._status_text.setText(f"Monitoring: {short}")
        self._append_log(
            f'<span style="color:#22c55e;font-weight:700">● Session started</span>'
            f' — {short}'
        )
        self._append_log(
            '<span style="color:#164e63">ℹ Hermit external detection active</span>'
            ' <span style="color:#1e3a4a">(DuckDuckGo · Wikipedia — free APIs)</span>'
        )

    def _on_pause(self) -> None:
        if not self._session:
            return
        if self._paused:
            self._session.resume()
            self._paused = False
            self._btn_pause.setText("⏸  Pause")
            self._set_status("MONITORING", "#22c55e",
                             "rgba(34,197,94,0.10)", "rgba(34,197,94,0.30)")
            self._append_log('<span style="color:#06b6d4">▶ Resumed</span>')
        else:
            self._session.pause()
            self._paused = True
            self._btn_pause.setText("▶  Resume")
            self._set_status("PAUSED", "#eab308",
                             "rgba(234,179,8,0.10)", "rgba(234,179,8,0.30)")
            self._append_log('<span style="color:#eab308">⏸ Paused</span>')

    def _on_stop(self) -> None:
        if not self._session:
            return
        self._timer.stop()
        fmt   = self._export_fmt.currentText().lower()
        score = self._session.stop()

        from reports.generator import generate_report
        import time as _t
        try:
            path = generate_report(
                session_id=self._session.session_id,
                doc_path=self._session.doc_path,
                stats=self._session.get_stats(),
                suspicious_insertions=self._session.get_suspicious_insertions(),
                started_at=self._session.started_at,
                ended_at=_t.time(),
                fmt=fmt,
            )
            self._session = None
            self._btn_start.setEnabled(True)
            self._btn_pause.setEnabled(False)
            self._btn_stop.setEnabled(False)
            self._set_status("IDLE", "#475569",
                             "rgba(71,85,105,0.10)", "rgba(71,85,105,0.25)")
            self._status_text.setText("Session complete — report saved")
            self._append_log(
                f'<span style="color:#8b5cf6;font-weight:700">✓ Report</span>'
                f' <span style="color:#334155">{os.path.basename(path)}</span>'
            )
            reply = QMessageBox.question(
                self, "Report Ready",
                f"Authenticity Score: {score:.1f}%\n\nOpen report now?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                import subprocess
                subprocess.Popen(["start", "", path], shell=True)
        except Exception as exc:
            QMessageBox.critical(self, "Report Error", str(exc))
            logger.exception("Report generation failed")

    def _safe_close(self) -> None:
        if self._session:
            reply = QMessageBox.question(
                self, "Quit ProcessAuth",
                "A session is active. Stop monitoring and exit?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self._session.stop()
        self.close()

    # ── timer ─────────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        if self._start_time and not self._paused:
            elapsed = int(time.time() - self._start_time)
            h, r = divmod(elapsed, 3600)
            m, s = divmod(r, 60)
            self._timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}")

    # ── stats update (main thread via Qt signal) ──────────────────────────────

    @Slot(object)
    def _on_stats_update(self, stats: SessionStats) -> None:
        score = stats.authenticity_score

        # Arc + label
        self._score_arc.set_score(score)
        if score >= 75:
            clr, lbl = "#22c55e", "High Authenticity"
        elif score >= 50:
            clr, lbl = "#eab308", "Moderate — Review Recommended"
        else:
            clr, lbl = "#ef4444", "Low — Likely Assisted"
        self._score_label.setText(lbl)
        self._score_label.setStyleSheet(
            f"font-size:11px;color:{clr};font-weight:700;"
            "letter-spacing:0.5px;margin-top:2px;"
            "background:transparent;border:none;"
        )

        # Stat cards
        self._card_keys.set_value(str(stats.total_keystrokes))
        self._card_clip.set_value(str(stats.paste_events))
        self._card_susp.set_value(str(stats.suspicious_events))
        avg_spd = stats.typing_speeds[-1] if stats.typing_speeds else 0
        self._card_speed.set_value(f"{avg_spd:.0f}")
        self._card_pasted.set_value(str(stats.total_chars_pasted))
        self._card_ext.set_value(str(stats.external_hits))

        # Typing bar
        self._typing_bar.setValue(min(100, int(avg_spd / 6)))

        # Metrics table
        d = stats.to_dict()
        self._m_keys.setText(str(d["total_keystrokes"]))
        self._m_typed.setText(str(d["total_chars_typed"]))
        self._m_pasted.setText(str(d["total_chars_pasted"]))
        self._m_back.setText(str(d["backspaces"]))
        self._m_speed.setText(str(d["avg_typing_speed"]))
        self._m_clip.setText(str(d["paste_events"]))
        self._m_susp.setText(str(d["suspicious_events"]))
        self._m_ext.setText(str(d["external_hits"]))
        self._m_pen.setText(f"−{d['penalties']}")

        # Log new suspicious events (avoid repeated lines)
        if stats.suspicious_events > self._last_susp:
            diff = stats.suspicious_events - self._last_susp
            self._append_log(
                f'<span style="color:#ef4444;font-weight:700">⚠ {diff} new suspicious event(s)</span>'
                f' — score <span style="color:{clr};font-weight:700">{score:.0f}%</span>'
            )
            self._last_susp = stats.suspicious_events

        if stats.external_hits > self._last_ext:
            self._append_log(
                '<span style="color:#f472b6;font-weight:700">🌐 External source match detected</span>'
                f' — penalty applied, score <span style="color:{clr}">{score:.0f}%</span>'
            )
            self._last_ext = stats.external_hits
