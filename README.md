# ProcessAuth – Behavioral Writing Authenticity Analyzer

ProcessAuth is a **local desktop application** designed to analyze *how a document was written* rather than only evaluating the final text.

The system monitors writing behavior such as **typing patterns, clipboard events, and document modifications** to estimate whether content was typed organically or inserted through copy-paste actions.

Unlike traditional plagiarism tools such as Turnitin, ProcessAuth focuses on **behavior-based authenticity analysis**, providing a timeline of writing activity and identifying suspicious insertion events.

The application prioritizes **privacy, transparency, and user consent**, ensuring that all monitoring occurs locally and only on explicitly selected documents.

---

# Features

### Behavioral Writing Analysis

ProcessAuth evaluates the *process of writing*, including:

* Typing patterns and burst typing
* Clipboard copy/paste events
* Document modification patterns
* Text insertion speed
* Editing behavior and revision activity

The system produces an **Authenticity Score** based on observed writing behavior.

---

### Privacy-Focused Monitoring

ProcessAuth is designed with strict privacy protections:

* Monitoring only occurs **after explicit user consent**
* Only the **selected document** is analyzed
* No screenshots or screen recording
* No browser monitoring
* No external data transmission
* All logs are stored **locally**

---

### Glassmorphic UI

The interface uses a **minimalistic glassmorphic design** with:

* Dark-mode interface
* Semi-transparent panels
* Soft glow accents
* Rounded UI elements
* Lightweight dashboard

---

### Real-Time Monitoring Dashboard

During a session, the dashboard displays:

* Session status
* Monitored document name
* Clipboard event counter
* Suspicious insertion counter
* Writing session timer

---

### Behavioral Detection Engine

The detection engine flags suspicious behavior based on rules such as:

* Large text insertions appearing instantly
* Clipboard activity immediately before document changes
* Typing bursts inconsistent with human typing patterns

Suspicious events are categorized into multiple severity tiers.

---

### Authenticity Report Generation

When the monitoring session ends, ProcessAuth generates a **local report** containing:

* Writing timeline
* Suspicious insertion events
* Clipboard correlations
* Typing activity statistics
* Authenticity score

Reports can be exported as:

* HTML
* JSON
* PDF (optional)

---

# Architecture Overview

ProcessAuth uses a modular architecture designed for stability and extensibility.

```
ProcessAuth/

main.py

core/
    session_manager.py

monitoring/
    keyboard.py
    clipboard.py
    file_watcher.py

analysis/
    behavioral_engine.py
    doc_parser.py

database/
    db.py

ui/
    consent.py
    dashboard.py
    styles.py

reports/
    generator.py
    templates/

utils/
    hashing.py
    logging.py
```

---

# Technology Stack

Programming Language

* Python 3.11+

Frameworks and Libraries

UI Framework

* PySide6

Monitoring Libraries

* watchdog
* pynput
* pyperclip

Document Processing

* python-docx

Database

* SQLite

Report Generation

* Jinja2

Optional utilities

* pygetwindow

---

# Installation

### 1. Clone the repository

```
git clone https://github.com/yourusername/ProcessAuth.git
cd ProcessAuth
```

### 2. Install dependencies

```
pip install -r requirements.txt
```

### 3. Run the application

```
python main.py
```

---

# Application Workflow

### 1. Consent Screen

When the program starts, a **consent window** appears explaining what will be monitored.

The user must either:

* Agree → monitoring starts
* Decline → program exits

---

### 2. File Selection

After consent, the user selects a `.docx` file to monitor.

Only that document will be analyzed.

---

### 3. Monitoring Session

While the session runs, the application records:

* typing activity
* clipboard usage
* document modifications

These events are stored locally.

---

### 4. Session End

When the session stops, ProcessAuth:

1. analyzes recorded behavior
2. calculates authenticity score
3. generates the report

---

# Authenticity Score Model

The authenticity score is calculated using behavioral indicators.

Example scoring model:

```
Score = 100
Score -= suspicious_insertions × 5
Score -= clipboard_linked_events × 10
Score -= large_text_insertions × 15
```

The final score is constrained between **0 and 100**.

---

# Example Report Output

```
Writing Analysis Report

Total Words: 1450

Typed Words: 910
Likely Pasted Words: 540

Clipboard Events: 3
Suspicious Insertions: 2

Authenticity Score: 67%
```

The report also includes a **timeline of detected events**.

---

# Privacy Policy

ProcessAuth does **not collect personal data**.

The application:

* does not record screens
* does not track browser activity
* does not access unrelated files
* does not send data to external servers

All monitoring data remains **local to the user's machine**.

---

# Limitations

ProcessAuth provides **behavioral indicators**, not definitive proof of plagiarism.

The system cannot guarantee detection in cases such as:

* manually typing copied content
* paraphrasing external material
* writing from memory

The authenticity score should be interpreted as **an analytical indicator**, not a final judgment.

---

# Security

To protect log integrity, ProcessAuth includes:

* session hashing
* local encrypted log storage
* automatic crash recovery

---

# Development Goals

Future improvements may include:

* machine learning typing analysis
* paraphrase similarity detection
* advanced timeline visualizations
* academic database comparison

---

# License

This project is intended for **educational and research purposes**.

---

# Disclaimer

ProcessAuth is an **analysis tool**, not a plagiarism verdict system.
Results should always be interpreted with human judgment.

---

# Author

Created and developed by Hermitt0220 as a behavioral writing authenticity research project. 
