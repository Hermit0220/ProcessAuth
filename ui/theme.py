"""
ui/theme.py
Global Theme Manager for PySide6 iOS-style Glassmorphism.
Handles dynamic Light/Dark mode toggling and centralized UI styling tokens.
"""
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor

class _ThemeManager(QObject):
    theme_changed = Signal()

    def __init__(self):
        super().__init__()
        self.mode = "dark"
        
        # ── Color Palette Definitions ────────────
        self.themes = {
            "dark": {
                # Base window (translucent to simulate desktop blur behind)
                "window_bg": QColor(5, 9, 20, 230),
                "text_main": "#f1f5f9",
                "text_muted": "#94a3b8",
                "border_subtle": "rgba(255, 255, 255, 0.08)",
                "border_glow": "rgba(255, 255, 255, 0.15)",
                # iOS Glass panels
                "glass_bg": "rgba(255, 255, 255, 0.04)",
                "glass_bg_solid": "#0f172a", # fallback
                "glass_hover": "rgba(255, 255, 255, 0.08)",
                "input_bg": "rgba(0, 0, 0, 0.25)",
                # Accents
                "cyan": "#06b6d4",
                "cyan_bg": "rgba(6, 182, 212, 0.1)",
                "purple": "#8b5cf6",
                "purple_bg": "rgba(139, 92, 246, 0.1)",
                "red": "#ef4444",
                "red_bg": "rgba(239, 68, 68, 0.1)",
                "green": "#22c55e",
                "green_bg": "rgba(34, 197, 94, 0.1)",
                "yellow": "#f59e0b",
                "pink": "#f472b6",
                "title_bar": "rgba(255, 255, 255, 0.03)",
                "icon_color": "#06b6d4",
            },
            "light": {
                # Base window (bright but highly translucent)
                "window_bg": QColor(248, 250, 252, 235),
                "text_main": "#1e293b",
                "text_muted": "#64748b",
                "border_subtle": "rgba(0, 0, 0, 0.06)",
                "border_glow": "rgba(0, 0, 0, 0.12)",
                # iOS Glass panels (frosted white effect)
                "glass_bg": "rgba(255, 255, 255, 0.55)",
                "glass_bg_solid": "#ffffff",
                "glass_hover": "rgba(255, 255, 255, 0.8)",
                "input_bg": "rgba(255, 255, 255, 0.75)",
                # Accents (slightly bolder for light mode contrast)
                "cyan": "#0891b2",
                "cyan_bg": "rgba(6, 182, 212, 0.15)",
                "purple": "#7c3aed",
                "purple_bg": "rgba(139, 92, 246, 0.15)",
                "red": "#dc2626",
                "red_bg": "rgba(239, 68, 68, 0.15)",
                "green": "#16a34a",
                "green_bg": "rgba(34, 197, 94, 0.15)",
                "yellow": "#d97706",
                "pink": "#db2777",
                "title_bar": "rgba(0, 0, 0, 0.02)",
                "icon_color": "#0891b2",
            }
        }

    def toggle(self):
        self.mode = "light" if self.mode == "dark" else "dark"
        self.theme_changed.emit()

    def get(self, key: str):
        return self.themes[self.mode][key]

# Global singleton
theme_manager = _ThemeManager()
