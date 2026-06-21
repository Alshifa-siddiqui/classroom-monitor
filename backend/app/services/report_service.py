"""Attendance / attention / emotion report generation with CSV and PDF export."""
import csv
import io
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Dict, List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from ..models import Attendance, AttentionLog, EmotionLog, Student


def period_range(period: str, anchor: date) -> Tuple[date, date]:
    """Inclusive [start, end] date range for a report period."""
    if period == "daily":
        return anchor, anchor
    if period == "weekly":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if period == "monthly":
        start = anchor.replace(day=1)
        return start, start.replace(day=monthrange(anchor.year, anchor.month)[1])
    raise ValueError(f"Unknown period: {period}")


def _bounds(start: date, end: date) -> Tuple[datetime, datetime]:
    return (datetime.combine(start, dtime.min, tzinfo=timezone.utc),
            datetime.combine(end, dtime.max, tzinfo=timezone.utc))


def _names(db: DbSession) -> Dict[int, str]:
    return {s.id: s.name for s in db.query(Student).all()}


def attendance_report(db: DbSession, start: date, end: date) -> Tuple[List[str], List[list]]:
    """Per student per day: sessions attended, minutes present, first in, last out."""
    lo, hi = _bounds(start, end)
    rows = (db.query(Attendance)
            .filter(Attendance.timestamp_in >= lo, Attendance.timestamp_in <= hi)
            .order_by(Attendance.timestamp_in).all())
    names = _names(db)
    grouped: Dict[Tuple[str, int], list] = defaultdict(list)
    for r in rows:
        grouped[(r.timestamp_in.date().isoformat(), r.student_id)].append(r)

    header = ["date", "student", "entries", "minutes_present", "first_in", "last_out"]
    out: List[list] = []
    for (day, student_id), recs in sorted(grouped.items()):
        total_s = sum(r.duration or 0 for r in recs)
        first_in = min(r.timestamp_in for r in recs).strftime("%H:%M:%S")
        outs = [r.timestamp_out for r in recs if r.timestamp_out]
        last_out = max(outs).strftime("%H:%M:%S") if outs else ""
        out.append([day, names.get(student_id, f"#{student_id}"), len(recs),
                    round(total_s / 60, 1), first_in, last_out])
    return header, out


def attention_report(db: DbSession, start: date, end: date) -> Tuple[List[str], List[list]]:
    """Per student per day: average / min / max attention and sample count."""
    lo, hi = _bounds(start, end)
    rows = (db.query(
                func.date(AttentionLog.timestamp),
                AttentionLog.student_id,
                func.avg(AttentionLog.attention_score),
                func.min(AttentionLog.attention_score),
                func.max(AttentionLog.attention_score),
                func.count(AttentionLog.id))
            .filter(AttentionLog.timestamp >= lo, AttentionLog.timestamp <= hi)
            .group_by(func.date(AttentionLog.timestamp), AttentionLog.student_id)
            .order_by(func.date(AttentionLog.timestamp)).all())
    names = _names(db)
    header = ["date", "student", "avg_attention", "min", "max", "samples"]
    return header, [[str(day), names.get(sid, f"#{sid}"), round(avg or 0, 3),
                     round(mn or 0, 3), round(mx or 0, 3), n]
                    for day, sid, avg, mn, mx, n in rows]


def emotion_report(db: DbSession, start: date, end: date) -> Tuple[List[str], List[list]]:
    """Per day: count of each emotion class."""
    lo, hi = _bounds(start, end)
    rows = (db.query(func.date(EmotionLog.timestamp), EmotionLog.emotion,
                     func.count(EmotionLog.id))
            .filter(EmotionLog.timestamp >= lo, EmotionLog.timestamp <= hi)
            .group_by(func.date(EmotionLog.timestamp), EmotionLog.emotion).all())
    classes = ["neutral", "happy", "distracted", "sleepy", "bored"]
    per_day: Dict[str, Dict[str, int]] = defaultdict(dict)
    for day, emotion, count in rows:
        per_day[str(day)][emotion] = count
    header = ["date"] + classes + ["total"]
    out = []
    for day in sorted(per_day):
        counts = [per_day[day].get(c, 0) for c in classes]
        out.append([day] + counts + [sum(counts)])
    return header, out


REPORTS = {
    "attendance": attendance_report,
    "attention": attention_report,
    "emotion": emotion_report,
}


def to_csv(header: List[str], rows: List[list]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")  # BOM so Excel opens it cleanly


def to_pdf(title: str, header: List[str], rows: List[list]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 6, f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                   f" | {len(rows)} rows", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    usable = pdf.w - pdf.l_margin - pdf.r_margin
    col_w = usable / max(len(header), 1)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(230, 233, 239)
    for cell in header:
        pdf.cell(col_w, 7, str(cell), border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    if not rows:
        pdf.cell(usable, 7, "No data for this period", border=1, align="C")
        pdf.ln()
    for row in rows:
        for cell in row:
            pdf.cell(col_w, 6.5, str(cell)[:28], border=1)
        pdf.ln()
    return bytes(pdf.output())
