"""
ui/humanizer_panel.py
AI Humanizer panel — glassmorphic PySide6 widget.

Integrates with:
  - Gemini REST API  (humanize · ask · facts · summarize · intent-detect)
  - API Ninjas       (random fact · inspirational quote · live weather)
  - Wikipedia + DuckDuckGo (silent context enrichment)
"""
from __future__ import annotations

from PySide6.QtCore  import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QComboBox,
    QLineEdit, QFrame, QSizePolicy, QApplication,
)
from utils.logger import get_logger
from ui.theme import theme_manager
from ai import ollama_client

logger = get_logger(__name__)


# ── Mode metadata ──────────────────────────────────────────────────────────────

MODES = {
    "Auto":         ("🤖", "#06b6d4",  "AI detects intent automatically"),
    "HumanRewrite": ("✍",  "#8b5cf6",  "Rewrite text to sound natural & human"),
    "Ask":          ("💬", "#22c55e",  "General Q&A and explanations"),
    "Facts":        ("🔍", "#f59e0b",  "Real-world data, weather, definitions"),
    "Summarize":    ("📝", "#f472b6",  "Condense long text into key ideas"),
}
DISPLAY_NAMES = {
    "Auto": "Auto", "HumanRewrite": "Human-style Rewrite",
    "Ask": "Ask AI", "Facts": "Facts & Data", "Summarize": "Summarize",
}


# ── Worker threads ─────────────────────────────────────────────────────────────

class _Worker(QThread):
    result_ready   = Signal(str)
    error_occurred = Signal(str)
    mode_detected  = Signal(str)

    def __init__(self, text: str, mode: str, city: str, llm_model: str) -> None:
        super().__init__()
        self._text = text
        self._mode = mode
        self._city = city
        self._llm_model = llm_model

    def run(self) -> None:
        try:
            from ai import humanizer_engine as engine
            from ai.ollama_client import detect_mode_local
            mode = self._mode

            # Show badge instantly using local heuristic (zero API cost)
            if mode == "Auto":
                local_mode = detect_mode_local(self._text)
                self.mode_detected.emit(local_mode)

            # Single Gemini call inside engine.process()
            result = engine.process(self._text, mode=mode, llm_model=self._llm_model, city=self._city)
            self.result_ready.emit(result)

        except Exception as exc:
            logger.exception("Humanizer worker error")
            msg = str(exc)
            if "Rate limit" in msg or "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                self.error_occurred.emit(
                    "Rate limit reached (free tier: 15 req/min). "
                    "Wait ~60 seconds and try again."
                )
            elif "401" in msg or "403" in msg or "API key" in msg.lower():
                self.error_occurred.emit(
                    "API key rejected — check your .env GEMINI_API_KEY."
                )
            elif "internet" in msg.lower() or "connection" in msg.lower():
                self.error_occurred.emit(
                    "Could not reach the AI service. Check your internet connection."
                )
            elif "too long" in msg.lower() or "timeout" in msg.lower():
                self.error_occurred.emit(
                    "Request timed out. Try again or shorten your input."
                )
            else:
                self.error_occurred.emit(msg)


class _QuickWorker(QThread):
    done = Signal(str)
    fail = Signal(str)

    def __init__(self, action: str, city: str = "") -> None:
        super().__init__()
        self._action = action
        self._city   = city

    def run(self) -> None:
        try:
            from ai import ninja_client as ninja
            if self._action == "fact":
                self.done.emit(f"⚡  Did you know?\n\n{ninja.get_fact()}")
            elif self._action == "quote":
                q = ninja.get_quote()
                self.done.emit(f'💬  "{q["quote"]}"\n\n— {q["author"]}')
            elif self._action == "weather":
                w = ninja.get_weather(self._city)
                self.done.emit(ninja.format_weather(w))
        except Exception as exc:
            self.fail.emit(str(exc))


# ── Style helpers ──────────────────────────────────────────────────────────────

def _btn(text: str, bg: str, fg: str = "#fff",
         border: str = "transparent", h: int = 36) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(h)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet(f"""
        QPushButton {{
            background: {bg}; color: {fg};
            border: 1px solid {border}; border-radius: 10px;
            font-size: 12px; font-weight: 700; padding: 0 14px;
        }}
        QPushButton:hover   {{ border-color: rgba(255,255,255,0.25); }}
        QPushButton:pressed {{ opacity: 0.7; }}
        QPushButton:disabled {{
            background: rgba(255,255,255,0.04); color: #94a3b8;
            border-color: rgba(255,255,255,0.06);
        }}
    """)
    return b


# ── Main Panel ─────────────────────────────────────────────────────────────────

class HumanizerPanel(QWidget):
    """Drop-in widget for the AI Humanizer tab inside the Dashboard."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._worker       : _Worker      | None = None
        self._quick_worker : _QuickWorker | None = None
        self._dot_timer    = QTimer(self)
        self._dot_count    = 0
        self._dot_timer.timeout.connect(self._animate_dots)
        self._glass_panels: list = []
        self._section_labels: list = []
        self._build_ui()
        self.apply_theme()
        theme_manager.theme_changed.connect(self.apply_theme)
        self._populate_models()
        
    def _populate_models(self):
        models = ollama_client.fetch_local_models()
        if not models:
            self._model_combo.addItem("llama3.2:latest")
        else:
            for m in models:
                self._model_combo.addItem(m)
        self._populate_models()
        
    def _populate_models(self):
        self._model_combo.clear()
        
        # Preferred custom-trained models first
        preferred = ["processauth-llama", "processauth-gemma"]
        
        models = ollama_client.fetch_local_models()
        # Put custom trained models at the top
        for name in preferred:
            if name in models:
                self._model_combo.addItem(f"✦ Custom Trained · {name}")
                models.remove(name)
        # Remaining Ollama models
        for m in models:
            self._model_combo.addItem(m)
        # Fallback if Ollama is empty
        if self._model_combo.count() == 0:
            self._model_combo.addItem("llama3.2:latest")
        # Cloud option always at the end
        self._model_combo.addItem("🥷 Ninja")

    # ── UI Layout ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        root.addWidget(self._build_header())
        root.addWidget(self._build_quick_bar())
        root.addWidget(self._build_mode_row())
        root.addWidget(self._build_input_card(), stretch=2)
        root.addWidget(self._build_output_card(), stretch=3)

    def _glass_card(self, border: str = "") -> QFrame:
        f = QFrame()
        self._glass_panels.append(f)
        return f

    def _section_lbl(self, text: str) -> QLabel:
        lbl = QLabel(text.upper())
        self._section_labels.append(lbl)
        return lbl

    def _build_header(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0)

        self._h_icon = QLabel("✦")
        self._h_icon.setStyleSheet("font-size:20px;color:#8b5cf6;background:transparent;border:none;")
        self._h_title = QLabel("AI Humanizer")
        self._h_sub = QLabel("  ·  Ollama · Ninja APIs · Wikipedia")

        lay.addWidget(self._h_icon); lay.addWidget(self._h_title); lay.addWidget(self._h_sub)
        lay.addStretch()
        return w

    def _build_quick_bar(self) -> QFrame:
        card = self._glass_card()
        lay  = QHBoxLayout(card)
        lay.setContentsMargins(16, 10, 16, 10); lay.setSpacing(10)

        lay.addWidget(self._section_lbl("Quick Actions"))
        lay.addSpacing(6)

        self._btn_fact    = _btn("⚡  Random Fact",    "rgba(6,182,212,0.12)",  "#06b6d4", "rgba(6,182,212,0.30)")
        self._btn_quote   = _btn("💬  Inspire Me",     "rgba(139,92,246,0.12)", "#8b5cf6", "rgba(139,92,246,0.30)")
        self._btn_weather = _btn("🌤  Weather",        "rgba(245,158,11,0.12)", "#f59e0b", "rgba(245,158,11,0.30)")

        self._city_input = QLineEdit()
        self._city_input.setPlaceholderText("City…")
        self._city_input.setFixedSize(110, 36)

        self._btn_fact.clicked.connect(self._on_quick_fact)
        self._btn_quote.clicked.connect(self._on_quick_quote)
        self._btn_weather.clicked.connect(self._on_quick_weather)

        lay.addWidget(self._btn_fact)
        lay.addWidget(self._btn_quote)
        lay.addWidget(self._btn_weather)
        lay.addWidget(self._city_input)
        lay.addStretch()
        return card

    def _build_mode_row(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(12)

        self._mode_lbl = QLabel("Mode:")

        self._mode_combo = QComboBox()
        for key, display in DISPLAY_NAMES.items():
            self._mode_combo.addItem(f"{MODES[key][0]}  {display}", userData=key)
        self._mode_combo.setCurrentIndex(0)
        self._mode_combo.setFixedSize(220, 36)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_change)

        self._mode_badge = QLabel("")
        self._mode_badge.hide()
        
        # MODEL SELECTOR
        self._model_lbl = QLabel("Model:")
        self._model_combo = QComboBox()
        self._model_combo.setFixedSize(180, 36)

        self._mode_hint = QLabel(MODES["Auto"][2])

        lay.addWidget(self._mode_lbl); lay.addWidget(self._mode_combo); lay.addWidget(self._mode_badge)
        lay.addStretch()
        lay.addWidget(self._model_lbl); lay.addWidget(self._model_combo)
        lay.addSpacing(16)
        lay.addWidget(self._mode_hint)
        return w

    def _build_input_card(self) -> QFrame:
        card = self._glass_card()
        lay  = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14); lay.setSpacing(10)

        top = QHBoxLayout()
        top.addWidget(self._section_lbl("Your Input"))
        top.addStretch()
        self._char_count = QLabel("0 chars")
        top.addWidget(self._char_count)
        lay.addLayout(top)

        self._input_box = QTextEdit()
        self._input_box.setPlaceholderText(
            "Type or paste your text / question here…\n\n"
            "Examples:\n"
            "  • Rewrite this paragraph to sound more natural: [your text]\n"
            "  • What is machine learning?\n"
            "  • Summarize: [paste a long article]\n"
            "  • Weather in London"
        )
        self._input_box.setMinimumHeight(100)
        self._input_box.textChanged.connect(
            lambda: self._char_count.setText(f"{len(self._input_box.toPlainText()):,} chars")
        )
        lay.addWidget(self._input_box)

        btn_row = QHBoxLayout(); btn_row.setSpacing(10)
        self._btn_generate = _btn(
            "✦  Generate",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7c3aed,stop:1 #06b6d4)",
            h=40
        )
        self._btn_generate.setFixedWidth(140)
        self._btn_generate.clicked.connect(self._on_generate)

        self._btn_clear = _btn("Clear", "rgba(255,255,255,0.05)", "#64748b",
                               "rgba(255,255,255,0.10)", h=40)
        self._btn_clear.setFixedWidth(80)
        self._btn_clear.clicked.connect(self._on_clear)

        btn_row.addStretch()
        btn_row.addWidget(self._btn_clear)
        btn_row.addWidget(self._btn_generate)
        lay.addLayout(btn_row)
        return card

    def _build_output_card(self) -> QFrame:
        self._output_card = self._glass_card()
        lay = QVBoxLayout(self._output_card)
        lay.setContentsMargins(16, 14, 16, 14); lay.setSpacing(10)

        top = QHBoxLayout()
        top.addWidget(self._section_lbl("Result"))
        top.addStretch()
        self._status_pill = QLabel("● IDLE")
        top.addWidget(self._status_pill)
        lay.addLayout(top)

        self._output_box = QTextEdit()
        self._output_box.setReadOnly(True)
        self._output_box.setPlaceholderText("Your result will appear here…")
        self._output_box.setMinimumHeight(130)
        lay.addWidget(self._output_box)

        copy_row = QHBoxLayout(); copy_row.setSpacing(8)
        self._word_count = QLabel("")
        copy_row.addWidget(self._word_count)
        copy_row.addStretch()

        self._btn_copy = _btn("📋  Copy", "rgba(6,182,212,0.12)", "#06b6d4",
                              "rgba(6,182,212,0.30)", h=32)
        self._btn_copy.setFixedWidth(100)
        self._btn_copy.setEnabled(False)
        self._btn_copy.clicked.connect(self._on_copy)
        copy_row.addWidget(self._btn_copy)
        lay.addLayout(copy_row)
        return self._output_card

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _on_mode_change(self) -> None:
        key = self._mode_combo.currentData()
        if key in MODES:
            self._mode_hint.setText(MODES[key][2])
            self._mode_badge.hide()

    def _on_clear(self) -> None:
        self._input_box.clear()
        self._output_box.clear()
        self._word_count.setText("")
        self._btn_copy.setEnabled(False)
        self._mode_badge.hide()
        self._set_status("IDLE", "#475569", "rgba(148,163,184,0.10)", "rgba(148,163,184,0.20)")
        self._reset_card_border()

    def _on_generate(self) -> None:
        text = self._input_box.toPlainText().strip()
        if not text:
            self._output_box.setPlainText("⚠  Please type something first.")
            return
        mode = self._mode_combo.currentData() or "Auto"
        llm_model = self._model_combo.currentText()
        city = self._city_input.text().strip()

        self._set_thinking()
        self._btn_generate.setEnabled(False)
        self._btn_copy.setEnabled(False)
        self._mode_badge.hide()

        self._worker = _Worker(text, mode, city, llm_model)
        self._worker.result_ready.connect(self._on_result)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.mode_detected.connect(self._on_mode_detected)
        self._worker.start()

    def _on_mode_detected(self, mode: str) -> None:
        if mode in MODES:
            icon, color, _ = MODES[mode]
            display = DISPLAY_NAMES.get(mode, mode)
            self._mode_badge.setText(f"{icon}  Auto → {display}")
            self._mode_badge.setStyleSheet(
                f"font-size:10px;font-weight:700;padding:3px 10px;border-radius:12px;"
                f"background:rgba(139,92,246,0.12);color:{color};"
                f"border:1px solid rgba(139,92,246,0.28);"
            )
            self._mode_badge.show()

    def _on_result(self, result: str) -> None:
        self._dot_timer.stop()
        self._output_box.setPlainText(result)
        words = len(result.split())
        self._word_count.setText(f"{words} words · {len(result):,} chars")
        self._btn_copy.setEnabled(True)
        self._btn_generate.setEnabled(True)
        self._set_status("DONE", "#22c55e", "rgba(34,197,94,0.10)", "rgba(34,197,94,0.28)")
        # Glow green then fade back
        self._output_card.setStyleSheet(
            "QFrame{background:rgba(255,255,255,0.04);"
            "border:1px solid rgba(34,197,94,0.40);border-radius:14px;}"
        )
        QTimer.singleShot(2500, self._reset_card_border)

    def _on_error(self, msg: str) -> None:
        self._dot_timer.stop()
        self._output_box.setPlainText(f"⚠  {msg}")
        self._btn_generate.setEnabled(True)
        self._set_status("ERROR", "#ef4444", "rgba(239,68,68,0.10)", "rgba(239,68,68,0.28)")
        self._output_card.setStyleSheet(
            "QFrame{background:rgba(239,68,68,0.04);"
            "border:1px solid rgba(239,68,68,0.30);border-radius:14px;}"
        )

    def _on_copy(self) -> None:
        text = self._output_box.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._btn_copy.setText("✓  Copied!")
            QTimer.singleShot(1800, lambda: self._btn_copy.setText("📋  Copy"))

    # ── Quick Actions ──────────────────────────────────────────────────────────

    def _on_quick_fact(self)    : self._run_quick("fact")
    def _on_quick_quote(self)   : self._run_quick("quote")
    def _on_quick_weather(self) :
        city = self._city_input.text().strip()
        if not city:
            self._output_box.setPlainText("⚠  Enter a city name in the field beside the Weather button.")
            return
        self._run_quick("weather", city)

    def _run_quick(self, action: str, city: str = "") -> None:
        self._set_thinking()
        self._btn_generate.setEnabled(False)
        self._quick_worker = _QuickWorker(action, city)
        self._quick_worker.done.connect(self._on_quick_done)
        self._quick_worker.fail.connect(self._on_error)
        self._quick_worker.start()

    def _on_quick_done(self, text: str) -> None:
        self._dot_timer.stop()
        self._output_box.setPlainText(text)
        self._word_count.setText(f"{len(text.split())} words")
        self._btn_copy.setEnabled(True)
        self._btn_generate.setEnabled(True)
        self._set_status("DONE", "#22c55e", "rgba(34,197,94,0.10)", "rgba(34,197,94,0.28)")
        self._reset_card_border()

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _set_thinking(self) -> None:
        self._output_box.setPlainText("")
        self._word_count.setText("")
        self._dot_count = 0
        self._dot_timer.start(500)
        self._set_status("THINKING", "#06b6d4", "rgba(6,182,212,0.10)", "rgba(6,182,212,0.28)")
        self._output_card.setStyleSheet(
            "QFrame{background:rgba(255,255,255,0.04);"
            "border:1px solid rgba(6,182,212,0.40);border-radius:14px;}"
        )

    def _animate_dots(self) -> None:
        self._dot_count = (self._dot_count + 1) % 4
        self._status_pill.setText(f"● THINKING{'.' * self._dot_count}")

    def _set_status(self, text: str, color: str, bg: str, border: str) -> None:
        self._status_pill.setText(f"● {text}")
        self._status_pill.setStyleSheet(
            f"font-size:10px;font-weight:700;letter-spacing:1.5px;"
            f"padding:3px 12px;border-radius:20px;"
            f"background:{bg};color:{color};border:1px solid {border};"
        )

    def _reset_card_border(self) -> None:
        t = theme_manager
        self._output_card.setStyleSheet(f"""
            QFrame{{
                background:{t.get('glass_bg')};
                border:1px solid {t.get('border_subtle')};
                border-radius:14px;
            }}
        """)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def apply_theme(self) -> None:
        t = theme_manager
        # All glass panel cards
        for panel in self._glass_panels:
            panel.setStyleSheet(f"""
                QFrame {{
                    background: {t.get('glass_bg')};
                    border: 1px solid {t.get('border_subtle')};
                    border-radius: 14px;
                }}
            """)
        # Section labels
        for lbl in self._section_labels:
            lbl.setStyleSheet(f"font-size:9px;font-weight:700;color:{t.get('text_muted')};"
                              "letter-spacing:2px;background:transparent;border:none;")
        # Header
        if hasattr(self, '_h_title'):
            self._h_title.setStyleSheet(f"font-size:16px;font-weight:800;color:{t.get('text_main')};"
                                        "background:transparent;border:none;letter-spacing:0.5px;")
            self._h_sub.setStyleSheet(f"font-size:11px;color:{t.get('text_muted')};background:transparent;border:none;")
        # Mode row
        if hasattr(self, '_mode_lbl'):
            self._mode_lbl.setStyleSheet(f"font-size:12px;font-weight:700;color:{t.get('text_muted')};background:transparent;border:none;")
            self._mode_hint.setStyleSheet(f"font-size:11px;color:{t.get('text_muted')};background:transparent;border:none;")
            
            combo_style = f"""
                QComboBox {{
                    background: {t.get('input_bg')}; border: 1px solid {t.get('border_glow')};
                    border-radius: 10px; padding: 0 12px; color: {t.get('text_main')};
                    font-size: 12px; font-weight: 600;
                }}
                QComboBox::drop-down {{ border: none; width: 20px; }}
                QComboBox QAbstractItemView {{
                    background: {t.get('glass_bg_solid')}; border: 1px solid {t.get('border_subtle')};
                    selection-background-color: {t.get('purple_bg')}; color: {t.get('text_main')};
                }}
            """
            self._mode_combo.setStyleSheet(combo_style)
            
            if hasattr(self, '_model_lbl'):
                self._model_lbl.setStyleSheet(f"font-size:12px;font-weight:700;color:{t.get('text_muted')};background:transparent;border:none;")
                self._model_combo.setStyleSheet(combo_style)
        # Text inputs
        if hasattr(self, '_input_box'):
            self._input_box.setStyleSheet(f"""
                QTextEdit {{
                    background: {t.get('input_bg')}; border: 1px solid {t.get('border_subtle')};
                    border-radius: 10px; color: {t.get('text_main')}; font-size: 13px;
                    font-family: 'Segoe UI', 'Inter', sans-serif; padding: 10px;
                    selection-background-color: {t.get('purple_bg')};
                }}
                QTextEdit:focus {{ border-color: {t.get('purple')}; }}
            """)
            self._char_count.setStyleSheet(f"font-size:10px;color:{t.get('text_muted')};background:transparent;border:none;")
        if hasattr(self, '_output_box'):
            self._output_box.setStyleSheet(f"""
                QTextEdit {{
                    background: {t.get('input_bg')}; border: 1px solid {t.get('border_subtle')};
                    border-radius: 10px; color: {t.get('text_main')}; font-size: 13px;
                    font-family: 'Segoe UI', 'Inter', sans-serif; padding: 10px;
                    selection-background-color: {t.get('cyan_bg')};
                }}
            """)
            self._word_count.setStyleSheet(f"font-size:10px;color:{t.get('text_muted')};background:transparent;border:none;")
        # City input
        if hasattr(self, '_city_input'):
            self._city_input.setStyleSheet(f"""
                QLineEdit {{
                    background: {t.get('input_bg')}; border: 1px solid {t.get('border_glow')};
                    border-radius: 10px; padding: 0 10px; color: {t.get('text_main')}; font-size: 12px;
                }}
                QLineEdit:focus {{ border-color: {t.get('yellow')}; }}
            """)
