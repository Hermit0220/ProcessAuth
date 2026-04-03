"""
ui/styles.py
Global QSS stylesheet for ProcessAuth — glassmorphic dark theme.
"""

STYLESHEET = """
/* ═══════════════════════════════════════════════════════════════
   ProcessAuth · Global Theme · Deep Navy + Glassmorphism
═══════════════════════════════════════════════════════════════ */

QWidget {
    background-color: transparent;
    color: #e2e8f0;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
}

QMainWindow, #RootWidget {
    background-color: #030712;
}

/* ── Glass panels ─────────────────────────────────────────────── */
#GlassPanel {
    background-color: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
}

#GlassPanelAccent {
    background-color: rgba(6, 182, 212, 0.04);
    border: 1px solid rgba(6, 182, 212, 0.15);
    border-radius: 16px;
}

#GlassPanelDanger {
    background-color: rgba(239, 68, 68, 0.06);
    border: 1px solid rgba(239, 68, 68, 0.2);
    border-radius: 12px;
}

/* ── Title bar ────────────────────────────────────────────────── */
#TitleBar {
    background-color: rgba(255, 255, 255, 0.03);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 0;
    min-height: 48px;
}

/* ── Labels ───────────────────────────────────────────────────── */
#AppTitle {
    font-size: 16px;
    font-weight: 700;
    color: #06b6d4;
    letter-spacing: 1px;
}

#AppSubtitle {
    font-size: 11px;
    color: #475569;
    letter-spacing: 0.5px;
}

#SectionLabel {
    font-size: 10px;
    font-weight: 600;
    color: #475569;
    letter-spacing: 2px;
    text-transform: uppercase;
}

#StatValue {
    font-size: 32px;
    font-weight: 700;
    color: #06b6d4;
}

#StatValueGreen { font-size: 32px; font-weight: 700; color: #22c55e; }
#StatValueYellow { font-size: 32px; font-weight: 700; color: #eab308; }
#StatValueRed { font-size: 32px; font-weight: 700; color: #ef4444; }
#StatValuePurple { font-size: 32px; font-weight: 700; color: #8b5cf6; }

#StatLabel {
    font-size: 11px;
    color: #475569;
    margin-top: 2px;
}

#ScoreDisplay {
    font-size: 52px;
    font-weight: 800;
    letter-spacing: -2px;
}

#TimerLabel {
    font-size: 22px;
    font-weight: 600;
    color: #94a3b8;
    font-family: 'Consolas', monospace;
}

#StatusIndicator {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 4px 12px;
    border-radius: 999px;
}

#StatusMonitoring {
    background-color: rgba(34, 197, 94, 0.1);
    color: #22c55e;
    border: 1px solid rgba(34, 197, 94, 0.3);
}

#StatusPaused {
    background-color: rgba(234, 179, 8, 0.1);
    color: #eab308;
    border: 1px solid rgba(234, 179, 8, 0.3);
}

#StatusIdle {
    background-color: rgba(148, 163, 184, 0.08);
    color: #94a3b8;
    border: 1px solid rgba(148, 163, 184, 0.2);
}

/* ── Buttons ─────────────────────────────────────────────────── */
QPushButton {
    border: none;
    border-radius: 10px;
    padding: 10px 24px;
    font-size: 13px;
    font-weight: 600;
}

#BtnPrimary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #0891b2, stop:1 #06b6d4);
    color: #ffffff;
}
#BtnPrimary:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0e7490, stop:1 #0891b2); }
#BtnPrimary:pressed { background: #0e7490; }
#BtnPrimary:disabled { background: rgba(255,255,255,0.08); color: #475569; }

#BtnDanger {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #dc2626, stop:1 #ef4444);
    color: #ffffff;
}
#BtnDanger:hover { background: #dc2626; }
#BtnDanger:pressed { background: #b91c1c; }

#BtnWarning {
    background: rgba(234, 179, 8, 0.12);
    color: #eab308;
    border: 1px solid rgba(234, 179, 8, 0.3);
}
#BtnWarning:hover { background: rgba(234, 179, 8, 0.2); }
#BtnWarning:pressed { background: rgba(234, 179, 8, 0.3); }

#BtnGhost {
    background: rgba(255, 255, 255, 0.04);
    color: #94a3b8;
    border: 1px solid rgba(255, 255, 255, 0.08);
}
#BtnGhost:hover { background: rgba(255, 255, 255, 0.08); color: #e2e8f0; }

/* Consent buttons */
#BtnAgree {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0891b2, stop:1 #8b5cf6);
    color: #ffffff;
    min-width: 140px;
    min-height: 42px;
    font-size: 14px;
}
#BtnAgree:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0e7490, stop:1 #7c3aed); }

#BtnDecline {
    background: rgba(255,255,255,0.04);
    color: #64748b;
    border: 1px solid rgba(255,255,255,0.08);
    min-width: 140px;
    min-height: 42px;
    font-size: 14px;
}
#BtnDecline:hover { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }

/* ── Progress / Activity ─────────────────────────────────────── */
QProgressBar {
    border: none;
    border-radius: 4px;
    background: rgba(255,255,255,0.05);
    max-height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #06b6d4, stop:1 #8b5cf6);
}

/* ── Scrollbars ──────────────────────────────────────────────── */
QScrollBar:vertical {
    width: 6px;
    background: transparent;
}
QScrollBar::handle:vertical {
    background: rgba(255,255,255,0.12);
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: rgba(6, 182, 212, 0.4); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ── Log area ────────────────────────────────────────────────── */
#EventLog {
    background: rgba(0,0,0,0.3);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
    color: #64748b;
    padding: 8px;
}

/* ── Separator ──────────────────────────────────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: rgba(255,255,255,0.07);
}

/* ── ComboBox ───────────────────────────────────────────────── */
QComboBox {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    padding: 6px 12px;
    color: #e2e8f0;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background: #0f172a;
    border: 1px solid rgba(255,255,255,0.1);
    selection-background-color: rgba(6,182,212,0.2);
    color: #e2e8f0;
}
"""
