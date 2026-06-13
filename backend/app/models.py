from datetime import datetime, timezone

from sqlalchemy import (Column, Integer, Float, String, DateTime, ForeignKey,
                        Index, LargeBinary)

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClassSession(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, default="Session")
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)


class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    # human-facing unique ID, e.g. STU-2026-014
    student_code = Column(String(20), nullable=True, unique=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(120), nullable=True, index=True)
    # linked login account (role "student")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=True)
    # mean embedding, kept for backward compatibility and fast matching
    face_embedding = Column(LargeBinary, nullable=True)


class FaceEmbedding(Base):
    """Individual enrollment embeddings (multiple per student)."""
    __tablename__ = "face_embeddings"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    embedding = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(60), nullable=False, unique=True, index=True)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    username = Column(String(60), nullable=False, index=True)
    action = Column(String(60), nullable=False, index=True)
    detail = Column(String(300), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class Attendance(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    timestamp_in = Column(DateTime(timezone=True), nullable=False)
    timestamp_out = Column(DateTime(timezone=True), nullable=True)
    duration = Column(Integer, nullable=True)  # seconds


class EmotionLog(Base):
    __tablename__ = "emotion_logs"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    emotion = Column(String(20), nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class AttentionLog(Base):
    __tablename__ = "attention_logs"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    attention_score = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    type = Column(String(40), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True, index=True)
    message = Column(String(300), nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


# composite indexes for the analytics/report range queries
Index("ix_attention_session_ts", AttentionLog.session_id, AttentionLog.timestamp)
Index("ix_emotion_session_ts", EmotionLog.session_id, EmotionLog.timestamp)
Index("ix_attendance_in", Attendance.timestamp_in)
