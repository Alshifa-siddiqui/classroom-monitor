"""Per-student profile statistics: attendance %, attention, emotions, history."""
from collections import Counter
from datetime import timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from ..models import Attendance, AttentionLog, ClassSession, EmotionLog, Student


def _iso(dt) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def build_student_profile(db: DbSession, student: Student,
                          history_limit: int = 50) -> dict:
    attendance_rows = (db.query(Attendance)
                       .filter(Attendance.student_id == student.id)
                       .order_by(Attendance.timestamp_in.desc())
                       .limit(history_limit).all())

    sessions_attended = (db.query(func.count(func.distinct(Attendance.session_id)))
                         .filter(Attendance.student_id == student.id).scalar() or 0)
    total_sessions = db.query(func.count(ClassSession.id)).scalar() or 0
    attendance_pct = (round(100.0 * sessions_attended / total_sessions, 1)
                      if total_sessions else 0.0)

    avg_attention = (db.query(func.avg(AttentionLog.attention_score))
                     .filter(AttentionLog.student_id == student.id).scalar())
    attention_samples = (db.query(func.count(AttentionLog.id))
                         .filter(AttentionLog.student_id == student.id).scalar() or 0)

    emotion_stats = Counter(dict(
        db.query(EmotionLog.emotion, func.count(EmotionLog.id))
        .filter(EmotionLog.student_id == student.id)
        .group_by(EmotionLog.emotion).all()))

    last_seen = (db.query(func.max(Attendance.timestamp_in))
                 .filter(Attendance.student_id == student.id).scalar())
    last_out = (db.query(func.max(Attendance.timestamp_out))
                .filter(Attendance.student_id == student.id).scalar())
    if last_out is not None and (last_seen is None or last_out > last_seen):
        last_seen = last_out

    # recent attention timeline (for the portal chart)
    attention_history = [
        {"timestamp": _iso(row.timestamp), "score": row.attention_score}
        for row in (db.query(AttentionLog)
                    .filter(AttentionLog.student_id == student.id)
                    .order_by(AttentionLog.timestamp.desc())
                    .limit(history_limit).all())][::-1]

    return {
        "id": student.id,
        "student_code": student.student_code,
        "name": student.name,
        "email": student.email,
        "registered_at": _iso(student.created_at),
        "enrolled": student.face_embedding is not None,
        "attendance_percentage": attendance_pct,
        "sessions_attended": int(sessions_attended),
        "total_sessions": int(total_sessions),
        "avg_attention": round(float(avg_attention), 3) if avg_attention else 0.0,
        "attention_samples": int(attention_samples),
        "emotion_stats": dict(emotion_stats),
        "last_seen": _iso(last_seen),
        "attendance_history": [
            {"session_id": r.session_id, "timestamp_in": _iso(r.timestamp_in),
             "timestamp_out": _iso(r.timestamp_out), "duration": r.duration}
            for r in attendance_rows],
        "attention_history": attention_history,
    }
