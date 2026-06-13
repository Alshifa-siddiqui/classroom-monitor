from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..database import SessionLocal
from ..models import (Alert, Attendance, AttentionLog, ClassSession, EmotionLog,
                      FaceEmbedding, Student)
from ..schemas import (AlertOut, AnalyticsOut, AttendanceOut, AttentionPoint,
                       EnrollResult, SessionOut, StartSessionRequest,
                       StudentCreate, StudentDetailOut, StudentUpdate,
                       TrendsOut)
from ..security import AuthContext, audit, require_role
from ..services import report_service
from ..services.analytics_service import TTLCache, compute_trends

router = APIRouter()

_analytics_cache = TTLCache(settings.ANALYTICS_CACHE_SECONDS)
_trends_cache = TTLCache(30.0)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------- sessions --

@router.post("/start-session", response_model=SessionOut)
async def start_session(body: StartSessionRequest, request: Request,
                        db: DbSession = Depends(get_db),
                        user: AuthContext = Depends(require_role("admin"))):
    app_state = request.app.state
    if getattr(app_state, "pipeline", None) is not None and app_state.pipeline.running:
        raise HTTPException(status_code=409, detail="A session is already running")

    session = ClassSession(name=body.name)
    db.add(session)
    db.commit()
    db.refresh(session)

    from ..services.pipeline import MonitoringPipeline
    from .websocket import manager
    pipeline = MonitoringPipeline(session_id=session.id, broadcaster=manager.broadcast)
    try:
        await pipeline.start()
    except RuntimeError as exc:
        session.ended_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc))
    app_state.pipeline = pipeline
    audit(db, user.username, "session_started", f"id={session.id} {body.name}")
    return session


@router.post("/end-session", response_model=SessionOut)
async def end_session(request: Request, db: DbSession = Depends(get_db),
                      user: AuthContext = Depends(require_role("admin"))):
    app_state = request.app.state
    pipeline = getattr(app_state, "pipeline", None)
    if pipeline is None or not pipeline.running:
        raise HTTPException(status_code=409, detail="No session is running")
    await pipeline.stop()
    session = db.get(ClassSession, pipeline.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    session.ended_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    app_state.pipeline = None
    audit(db, user.username, "session_ended", f"id={session.id}")
    # tell every connected client to clear the live feed / camera state
    from .websocket import manager
    await manager.broadcast({"type": "session_ended", "session_id": session.id})
    return session


# ---------------------------------------------------------------- students --

def _student_detail(db: DbSession, student: Student) -> dict:
    count = (db.query(func.count(FaceEmbedding.id))
             .filter(FaceEmbedding.student_id == student.id).scalar() or 0)
    enrolled = count > 0 or student.face_embedding is not None
    return {"id": student.id, "student_code": student.student_code,
            "name": student.name, "email": student.email,
            "registered_at": student.created_at,
            "embedding_count": int(count), "enrolled": enrolled,
            "has_account": student.user_id is not None}


@router.get("/students", response_model=List[StudentDetailOut])
def list_students(db: DbSession = Depends(get_db),
                  _: AuthContext = Depends(require_role("teacher")),
                  search: Optional[str] = Query(default=None, max_length=120),
                  limit: int = Query(default=200, ge=1, le=1000)):
    q = db.query(Student)
    if search:
        q = q.filter(Student.name.ilike(f"%{search.strip()}%"))
    return [_student_detail(db, s) for s in q.order_by(Student.id).limit(limit).all()]


@router.post("/students", response_model=StudentDetailOut, status_code=201)
def create_student(body: StudentCreate, db: DbSession = Depends(get_db),
                   user: AuthContext = Depends(require_role("admin"))):
    """Register a student. With email+password a linked login account
    (role 'student') is created so they can view their own history."""
    from datetime import datetime as dt

    from ..auth import hash_password
    from ..models import User

    name = body.name.strip()
    if db.query(Student).filter(func.lower(Student.name) == name.lower()).first():
        raise HTTPException(status_code=409,
                            detail=f"A student named '{name}' already exists")
    if bool(body.email) != bool(body.password):
        raise HTTPException(status_code=422,
                            detail="Provide both email and password, or neither")

    account = None
    email = body.email.strip().lower() if body.email else None
    if email:
        if db.query(Student).filter(func.lower(Student.email) == email).first():
            raise HTTPException(status_code=409,
                                detail=f"A student with email '{email}' already exists")
        if db.query(User).filter(func.lower(User.username) == email).first():
            raise HTTPException(status_code=409,
                                detail=f"An account for '{email}' already exists")
        account = User(username=email, password_hash=hash_password(body.password),
                       role="student")
        db.add(account)
        db.flush()

    student = Student(name=name, email=email,
                      user_id=account.id if account else None,
                      created_at=datetime.now(timezone.utc))
    db.add(student)
    db.flush()
    student.student_code = f"STU-{dt.now(timezone.utc).year}-{student.id:03d}"
    db.commit()
    db.refresh(student)
    audit(db, user.username, "student_created",
          f"{student.student_code} {name}" + (f" account={email}" if email else ""))
    return _student_detail(db, student)


@router.put("/students/{student_id}", response_model=StudentDetailOut)
def update_student(student_id: int, body: StudentUpdate, request: Request,
                   db: DbSession = Depends(get_db),
                   user: AuthContext = Depends(require_role("admin"))):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    name = body.name.strip()
    clash = (db.query(Student)
             .filter(func.lower(Student.name) == name.lower(),
                     Student.id != student_id).first())
    if clash:
        raise HTTPException(status_code=409,
                            detail=f"A student named '{name}' already exists")
    old = student.name
    student.name = name
    db.commit()
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is not None:
        pipeline.invalidate_name(student_id)
    audit(db, user.username, "student_renamed", f"id={student_id} {old} -> {name}")
    return _student_detail(db, student)


@router.delete("/students/{student_id}", status_code=204)
def delete_student(student_id: int, db: DbSession = Depends(get_db),
                   user: AuthContext = Depends(require_role("admin"))):
    from ..models import User

    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    # full removal, including history rows and the linked login account
    db.query(FaceEmbedding).filter(FaceEmbedding.student_id == student_id).delete()
    db.query(Attendance).filter(Attendance.student_id == student_id).delete()
    db.query(AttentionLog).filter(AttentionLog.student_id == student_id).delete()
    db.query(EmotionLog).filter(EmotionLog.student_id == student_id).delete()
    db.query(Alert).filter(Alert.student_id == student_id).delete()
    if student.user_id is not None:
        account = db.get(User, student.user_id)
        if account is not None:
            db.delete(account)
    db.delete(student)
    db.commit()
    audit(db, user.username, "student_deleted", f"id={student_id} {student.name}")


@router.post("/students/{student_id}/enroll", response_model=EnrollResult)
def enroll_student(student_id: int, request: Request,
                   db: DbSession = Depends(get_db),
                   user: AuthContext = Depends(require_role("admin"))):
    """Capture face embeddings from the camera for this student.

    Sync handler on purpose: FastAPI runs it in the threadpool, so the
    multi-second capture never blocks the event loop.
    """
    import numpy as np

    from ..services.registration_service import (EnrollmentError,
                                                 TemporaryCamera, _normalize,
                                                 capture_embeddings,
                                                 find_duplicate,
                                                 store_enrollment)

    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    pipeline = getattr(request.app.state, "pipeline", None)
    try:
        if pipeline is not None and pipeline.running:
            embeddings, quality = capture_embeddings(pipeline.grabber)
        else:
            with TemporaryCamera() as grabber:
                embeddings, quality = capture_embeddings(grabber)
    except EnrollmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    mean = _normalize(np.mean(embeddings, axis=0))
    duplicate = find_duplicate(db, mean, exclude_student_id=student_id)
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail=f"This face is already enrolled as '{duplicate.name}'")

    store_enrollment(db, student, embeddings)
    if pipeline is not None and pipeline.running:
        pipeline.attendance.reload_galleries(db)
    audit(db, user.username, "student_enrolled",
          f"id={student_id} samples={len(embeddings)} quality={quality}")
    return EnrollResult(student_id=student_id, name=student.name,
                        samples_captured=len(embeddings), quality=quality)


@router.get("/students/{student_id}/profile")
def student_profile(student_id: int, db: DbSession = Depends(get_db),
                    _: AuthContext = Depends(require_role("teacher"))):
    from ..services.profile_service import build_student_profile
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return build_student_profile(db, student)


@router.get("/me/student")
def my_student_profile(db: DbSession = Depends(get_db),
                       user: AuthContext = Depends(require_role("student"))):
    """The signed-in student's own profile and history."""
    from ..services.profile_service import build_student_profile
    if user.student_id is None:
        raise HTTPException(status_code=403,
                            detail="This account is not linked to a student record")
    student = db.get(Student, user.student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student record not found")
    return build_student_profile(db, student)


# -------------------------------------------------------------- attendance --

@router.get("/attendance", response_model=List[AttendanceOut])
def list_attendance(db: DbSession = Depends(get_db),
                    _: AuthContext = Depends(require_role("teacher")),
                    session_id: Optional[int] = Query(default=None, ge=1),
                    student_id: Optional[int] = Query(default=None, ge=1),
                    limit: int = Query(default=200, ge=1, le=1000)):
    q = db.query(Attendance)
    if session_id is not None:
        q = q.filter(Attendance.session_id == session_id)
    if student_id is not None:
        q = q.filter(Attendance.student_id == student_id)
    return q.order_by(Attendance.timestamp_in.desc()).limit(limit).all()


# --------------------------------------------------------------- analytics --

@router.get("/analytics", response_model=AnalyticsOut)
def analytics(request: Request, db: DbSession = Depends(get_db),
              _: AuthContext = Depends(require_role("viewer")),
              session_id: Optional[int] = Query(default=None, ge=1),
              student_id: Optional[int] = Query(default=None, ge=1),
              minutes: int = Query(default=60, ge=1, le=720)):
    pipeline = getattr(request.app.state, "pipeline", None)
    if session_id is None and pipeline is not None:
        session_id = pipeline.session_id

    cache_key = (session_id, student_id, minutes)
    cached = _analytics_cache.get(cache_key)
    if cached is not None:
        return cached

    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    att_q = db.query(AttentionLog).filter(AttentionLog.timestamp >= since)
    emo_q = (db.query(EmotionLog.emotion, func.count(EmotionLog.id))
             .filter(EmotionLog.timestamp >= since))
    alert_q = db.query(Alert).filter(Alert.timestamp >= since)
    if session_id is not None:
        att_q = att_q.filter(AttentionLog.session_id == session_id)
        emo_q = emo_q.filter(EmotionLog.session_id == session_id)
        alert_q = alert_q.filter(Alert.session_id == session_id)
    if student_id is not None:
        att_q = att_q.filter(AttentionLog.student_id == student_id)
        emo_q = emo_q.filter(EmotionLog.student_id == student_id)
        alert_q = alert_q.filter(Alert.student_id == student_id)

    rows = att_q.order_by(AttentionLog.timestamp).all()
    timeline: List[AttentionPoint] = []
    if rows:
        bucket_seconds = max(int(minutes * 60 / 60), 10)
        bucket_start, bucket_scores = None, []
        for row in rows:
            ts = row.timestamp if row.timestamp.tzinfo else row.timestamp.replace(
                tzinfo=timezone.utc)
            if bucket_start is None:
                bucket_start = ts
            if (ts - bucket_start).total_seconds() > bucket_seconds and bucket_scores:
                timeline.append(AttentionPoint(
                    timestamp=bucket_start,
                    avg_score=round(sum(bucket_scores) / len(bucket_scores), 3)))
                bucket_start, bucket_scores = ts, []
            bucket_scores.append(row.attention_score)
        if bucket_scores and bucket_start is not None:
            timeline.append(AttentionPoint(
                timestamp=bucket_start,
                avg_score=round(sum(bucket_scores) / len(bucket_scores), 3)))

    emotion_distribution = {emotion: count for emotion, count in emo_q.group_by(
        EmotionLog.emotion).all()}
    alerts = [AlertOut.model_validate(a) for a in
              alert_q.order_by(Alert.timestamp.desc()).limit(50).all()]

    present_count = 0
    avg_attention = 0.0
    if pipeline is not None and pipeline.running:
        summary = pipeline.latest_snapshot.get("summary", {})
        present_count = summary.get("present_count", 0)
        avg_attention = summary.get("avg_attention", 0.0)

    result = AnalyticsOut(
        session_id=session_id,
        present_count=present_count,
        total_students=db.query(Student).count(),
        avg_attention=avg_attention,
        attention_timeline=timeline,
        emotion_distribution=emotion_distribution,
        alerts=alerts,
    )
    _analytics_cache.set(cache_key, result)
    return result


@router.get("/analytics/trends", response_model=TrendsOut)
def analytics_trends(db: DbSession = Depends(get_db),
                     _: AuthContext = Depends(require_role("teacher")),
                     date_from: date = Query(alias="from"),
                     date_to: date = Query(alias="to"),
                     bucket: str = Query(default="day", pattern="^(hour|day)$")):
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="'to' is before 'from'")
    if (date_to - date_from).days > 366:
        raise HTTPException(status_code=422, detail="Range too large (max 1 year)")
    cache_key = (date_from, date_to, bucket)
    cached = _trends_cache.get(cache_key)
    if cached is not None:
        return cached
    result = compute_trends(db, date_from, date_to, bucket)
    _trends_cache.set(cache_key, result)
    return result


# ----------------------------------------------------------------- reports --

_MEDIA_TYPES = {"csv": "text/csv", "pdf": "application/pdf",
                "json": "application/json"}


@router.get("/reports/{report_type}")
def generate_report(report_type: str, db: DbSession = Depends(get_db),
                    user: AuthContext = Depends(require_role("teacher")),
                    period: str = Query(default="daily",
                                        pattern="^(daily|weekly|monthly)$"),
                    anchor: Optional[date] = Query(default=None, alias="date"),
                    format: str = Query(default="csv", pattern="^(csv|pdf|json)$")):
    if report_type not in report_service.REPORTS:
        raise HTTPException(status_code=404, detail="Unknown report type")
    anchor = anchor or datetime.now(timezone.utc).date()
    start, end = report_service.period_range(period, anchor)
    header, rows = report_service.REPORTS[report_type](db, start, end)
    audit(db, user.username, "report_exported",
          f"{report_type} {period} {start}..{end} {format}")

    filename = f"{report_type}_{period}_{start.isoformat()}"
    if format == "json":
        return {"report": report_type, "period": period,
                "from": start.isoformat(), "to": end.isoformat(),
                "header": header, "rows": rows}
    if format == "csv":
        content = report_service.to_csv(header, rows)
    else:
        title = (f"{report_type.capitalize()} report ({period}) "
                 f"{start.isoformat()} to {end.isoformat()}")
        content = report_service.to_pdf(title, header, rows)
    return Response(
        content=content, media_type=_MEDIA_TYPES[format],
        headers={"Content-Disposition":
                 f'attachment; filename="{filename}.{format}"'})
