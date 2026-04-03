"""
reports/generator.py
Aggregates session data and renders the HTML report via Jinja2.
Supports HTML (default), JSON, and optional PDF export.
"""
import datetime
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

from database.db import db
from utils.hashing import compute_session_integrity
from utils.logger import get_logger

if TYPE_CHECKING:
    from analysis.behavioral_engine import SessionStats

logger = get_logger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"
EXPORT_DIR   = Path(__file__).parent.parent / "exports"
EXPORT_DIR.mkdir(exist_ok=True)


def _score_color(score: float) -> str:
    if score >= 75:
        return "#22c55e"
    elif score >= 50:
        return "#eab308"
    return "#ef4444"


def _score_label(score: float) -> str:
    if score >= 75:
        return "High Authenticity"
    elif score >= 50:
        return "Moderate — Review Recommended"
    return "Low — Likely Assisted"


def _score_badge(score: float) -> str:
    if score >= 75:
        return "badge-green"
    elif score >= 50:
        return "badge-yellow"
    return "badge-red"


def _fmt_time(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def generate_report(
    session_id: str,
    doc_path: str,
    stats: "SessionStats",
    suspicious_insertions: list[dict],
    started_at: float,
    ended_at: float,
    fmt: str = "html",
) -> str:
    """
    Build the authenticity report and write it to the exports directory.
    Returns the path to the generated file.
    """
    events = db.get_events(session_id)
    integrity_hash = compute_session_integrity(events)

    duration = _fmt_duration(ended_at - started_at)
    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    year = datetime.datetime.now().year

    stats_dict = stats.to_dict()
    # Derive word counts (rough: chars / 5)
    total_chars = stats_dict["total_chars_typed"] + stats_dict["total_chars_pasted"]
    stats_dict["total_words"]  = max(total_chars // 5, 1)
    stats_dict["typed_words"]  = stats_dict["total_chars_typed"] // 5
    stats_dict["pasted_words"] = stats_dict["total_chars_pasted"] // 5

    score  = stats.authenticity_score
    doc_name = os.path.basename(doc_path)

    # Build suspicious insertions for template
    tmpl_suspicious = [
        {
            "time_str"  : _fmt_time(ev["timestamp"]),
            "new_chars" : ev.get("new_chars", ev.get("chars_added", 0)),
            "penalty"   : ev["penalty"],
            "correlated": ev["correlated"],
            "reasons"   : ev["reasons"],
        }
        for ev in suspicious_insertions
    ]

    # Build timeline (last 50 non-keypress events)
    display_events = [e for e in events if e.get("event_type") != "key_press"][-50:]
    timeline = []
    for ev in display_events:
        etype = ev.get("event_type", "")
        chars = ev.get("chars_added", 0)
        detail_parts = [f"chars={chars}"]
        if ev.get("clipboard"):
            detail_parts.append("clipboard")
        if ev.get("typing_speed", 0) > 0:
            detail_parts.append(f"speed={ev['typing_speed']:.0f} cpm")
        timeline.append({
            "time_str"  : _fmt_time(ev["timestamp"]),
            "event_type": etype.replace("_", " ").title(),
            "detail"    : " · ".join(detail_parts),
            "suspicious": bool(ev.get("suspicion", 0)),
        })

    speed_timeline = stats.typing_speeds[-200:]  # last 200 speed samples

    if fmt == "json":
        return _export_json(
            session_id, stats_dict, tmpl_suspicious, integrity_hash,
            duration, generated_at, doc_path
        )

    # HTML
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    tmpl = env.get_template("report.html")
    html = tmpl.render(
        session_id=session_id,
        generated_at=generated_at,
        year=year,
        stats=stats_dict,
        doc_name=doc_name,
        duration=duration,
        score_color=_score_color(score),
        score_label=_score_label(score),
        score_badge=_score_badge(score),
        suspicious_insertions=tmpl_suspicious,
        timeline=timeline,
        speed_timeline=speed_timeline,
        integrity_hash=integrity_hash,
    )

    out_path = EXPORT_DIR / f"report_{session_id[:8]}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info("HTML report saved: %s", out_path)

    if fmt == "pdf":
        _try_pdf(out_path)

    return str(out_path)


def _export_json(session_id, stats_dict, suspicious, integrity_hash, duration, generated_at, doc_path) -> str:
    data = {
        "session_id"           : session_id,
        "generated_at"         : generated_at,
        "doc_path"             : doc_path,
        "duration"             : duration,
        "stats"                : stats_dict,
        "suspicious_insertions": suspicious,
        "integrity_hash"       : integrity_hash,
    }
    out_path = EXPORT_DIR / f"report_{session_id[:8]}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("JSON report saved: %s", out_path)
    return str(out_path)


def _try_pdf(html_path: Path) -> None:
    try:
        import subprocess
        result = subprocess.run(
            ["wkhtmltopdf", "--quiet", str(html_path), str(html_path.with_suffix(".pdf"))],
            capture_output=True, timeout=30
        )
        if result.returncode == 0:
            logger.info("PDF generated: %s", html_path.with_suffix(".pdf"))
        else:
            logger.warning("wkhtmltopdf failed — HTML report still available.")
    except FileNotFoundError:
        logger.info("wkhtmltopdf not installed — skipping PDF export.")
    except Exception as exc:
        logger.warning("PDF generation error: %s", exc)
