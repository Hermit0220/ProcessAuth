"""
ui/consent.py
Glassmorphic consent modal that must be accepted before monitoring begins.
Blocks the event loop until the user clicks Agree or Decline.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QLinearGradient, QColor, QPainter, QBrush
from PySide6.QtWidgets import (
    QDialog, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QFrame, QWidget, QSizePolicy,
)


class ConsentDialog(QDialog):
    """
    Full-screen-blurred consent dialog.
    `accepted` → True if user clicked Agree, False if Decline / closed.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ProcessAuth – Behavioral Authentisizer by Hermit")
        self.setFixedSize(560, 480)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self._accepted = False
        self._build_ui()

    # ── result ────────────────────────────────────────────────────────────────

    @property
    def accepted_consent(self) -> bool:
        return self._accepted

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Outer glow border
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(6, 182, 212, 18)))
        painter.drawRoundedRect(self.rect(), 20, 20)
        # Glass body
        painter.setBrush(QBrush(QColor(3, 7, 18, 235)))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 19, 19)
        super().paintEvent(event)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 36, 40, 36)
        root.setSpacing(0)

        # ── TOP ICON / BADGE ─────────────────────────────────────────────────
        badge = QLabel("🔍")
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet("font-size: 42px; margin-bottom: 8px;")
        root.addWidget(badge)

        # ── TITLE ──────────────────────────────────────────────────────
        title = QLabel("Behavioral Writing Authentisizer")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet("""
            font-size: 22px;
            font-weight: 800;
            color: #06b6d4;
            margin-bottom: 4px;
            letter-spacing: -0.5px;
        """)
        root.addWidget(title)

        hermit_lbl = QLabel("by Hermit")
        hermit_lbl.setAlignment(Qt.AlignCenter)
        hermit_lbl.setStyleSheet("""
            font-size: 10px;
            font-weight: 700;
            color: #164e63;
            letter-spacing: 3px;
            text-transform: uppercase;
            margin-bottom: 2px;
        """)
        root.addWidget(hermit_lbl)

        root.addSpacing(18)

        # ── DIVIDER ──────────────────────────────────────────────────────────
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: rgba(255,255,255,0.08);")
        root.addWidget(divider)

        root.addSpacing(20)

        # ── BODY TEXT ────────────────────────────────────────────────────────
        body = QLabel(
            "This application monitors your <b>writing behavior</b> including:<br><br>"
            "&nbsp;&nbsp;• Typing patterns &amp; keystroke timing<br>"
            "&nbsp;&nbsp;• Clipboard activity (content is <b>hashed</b>, never stored)<br>"
            "&nbsp;&nbsp;• Document modification events<br><br>"
            "The data is used <b>solely</b> to generate a writing authenticity report. "
            "<br><br>"
            "<span style='color:#64748b'>"
            "No screen recording, browser history, or personal files are accessed. "
            "All session data is stored locally on this device only."
            "</span>"
        )
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        body.setStyleSheet("""
            font-size: 13px;
            color: #cbd5e1;
            line-height: 1.7;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.07);
            border-radius: 12px;
            padding: 18px;
        """)
        body.setTextFormat(Qt.RichText)
        root.addWidget(body)

        root.addSpacing(24)

        # ── BUTTONS ──────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(14)

        self._btn_decline = QPushButton("Decline")
        self._btn_decline.setObjectName("BtnDecline")
        self._btn_decline.setFixedHeight(44)
        self._btn_decline.setCursor(Qt.PointingHandCursor)
        self._btn_decline.clicked.connect(self._on_decline)

        self._btn_agree = QPushButton("✓  Agree & Continue")
        self._btn_agree.setObjectName("BtnAgree")
        self._btn_agree.setFixedHeight(44)
        self._btn_agree.setCursor(Qt.PointingHandCursor)
        self._btn_agree.clicked.connect(self._on_agree)

        btn_row.addWidget(self._btn_decline)
        btn_row.addWidget(self._btn_agree)
        root.addLayout(btn_row)

        root.addSpacing(12)

        # ── FOOTER ───────────────────────────────────────────────────────────
        footer = QLabel("ProcessAuth · Behavioral Authentisizer by Hermit")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("font-size: 10px; color: #164e63; letter-spacing: 0.5px;")
        root.addWidget(footer)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _on_agree(self) -> None:
        self._accepted = True
        self.accept()

    def _on_decline(self) -> None:
        self._accepted = False
        self.reject()

    # ── drag support ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag_pos"):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
