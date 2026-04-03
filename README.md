# ProcessAuth - Behavioral Writing Authenticity Analyzer

The goal is to create a local desktop application using Python to monitor document editing activity and assess the authenticity of the writing. This involves tracking keyboard inputs, clipboard events, and document changes to detect copy-paste behaviors. The application will have a modern, dark-mode, glassmorphic UI built with PySide6 and ensures data privacy by restricting monitoring only to specified documents, storing all logs locally in SQLite, and generating a local HTML report.

## User Review Required

> [!IMPORTANT]
> - Do you prefer using PySide6 or PyQt6 for the UI framework? Both are capable, but this plan specifies PySide6.
> - The prompt specifies "watchdog," "pynput," "pyperclip," and "python-docx" - I will use these exactly as required.
> - Are there any specific Windows versions we should target for the UI styling (e.g. Windows 11 Acrylic/Mica effect)? The plan uses a cross-platform frameless window approach with styled transparency to achieve the Glassmorphic look.

## Proposed Changes

### Core Architecture and Configuration

- `main.py`
  - Initializes the application and loads the UI.
- `requirements.txt`
  - Defines project dependencies: `PySide6`, `watchdog`, `pynput`, `pyperclip`, `python-docx`, `Jinja2`, `pygetwindow`.

---
### Database Layer

- `database/db.py`
  - SQLite manager.
  - Initializes local tables to store event logs.
  - Implements asynchronous `log_event()` function to ensure non-blocking UI.
  - Implements a fallback mechanism to write to `Logs_Fallback.json` if SQLite operations lock or fail.

---
### Monitoring Modules

- `monitoring/keyboard.py`
  - Uses `pynput` to listen for keyboard activity. Tracks typing rates, character bursts, pauses, and backspaces.
- `monitoring/clipboard.py`
  - Uses `pyperclip` in a polling thread to detect changes to the clipboard.
- `monitoring/file_watcher.py`
  - Uses `watchdog` to track file modification timestamps and trigger snapshot backups.

---
### Analysis Engine

- `analysis/doc_parser.py`
  - Uses `python-docx` to extract text from internal `.docx` targets. Generates text diffs and identifies massive blocks of changes between modifications.
- `analysis/behavioral_engine.py`
  - Core logic. Ruleset: flag text insertion bursts (> 150 chars in < 1 sec). Flag matching clipboard operations to file modification events. Calculates the Authenticity Score utilizing total words vs presumed copied words.

---
### UI Layer

- `ui/styles.py`
  - QSS stylesheets defining the #030712 deep navy background, transparent panels, cyan/purple accents, rounded borders, and modern typography (Segoe UI/Inter).
- `ui/consent.py`
  - A modal frameless `QDialog` that displays the privacy message. App starts monitoring only after "Agree". Exits on "Decline".
- `ui/dashboard.py`
  - The main application window containing dynamic labels to show:
    1. Session Status
    2. File Being Monitored
    3. Clipboard Events Counter
    4. Suspicious Insertions Counter
    5. Start/Pause/Stop controls

---
### Report Generation

- `reports/generator.py`
  - Collates the database logs and analysis data into a structured context.
- `reports/templates/report.html`
  - Jinja2 template formatted to show the timeline, suspicious paragraphs, and final score. Optionally supports conversion via PDF.

---
### Session Orchestration

- `core/session_manager.py`
  - Oversees all threads. Acts as an event bus between monitoring, analysis, database, and UI. Automatically stops if the monitored file is deleted or closed.

## Open Questions

> [!WARNING]
> The app needs a way to select the ".docx" file that will be monitored. Should the app prompt the user with a File Open dialog right after the consent window to choose the file to watch?

> [!CAUTION]
> Tracking keystrokes across the system using `pynput` requires keeping track of whether the user is actively typing in the generic Word Window versus other applications to protect privacy. I will incorporate active window title checking via `pygetwindow` or `win32gui` on Windows to cleanly track keystrokes only when the monitored document is the active window. Does that sound acceptable?

## Verification Plan

### Automated/Unit Tests
- Verify `database/db.py` locks and gracefully degrades to JSON logging.
- Verify `analysis/behavioral_engine.py` copy-paste detection correctly penalizes >150-char burst text.

### Manual Verification
- Start the app, accept the consent screen. 
- Open a `.docx` file and define it in the app.
- Manually type a few normal paragraphs to verify standard behavior logging.
- Copy-paste a massive paragraph and document the dashboard's reaction (counter increments).
- Stop the session, generate the HTML report, and ensure visual data representation aligns with actions taken.
