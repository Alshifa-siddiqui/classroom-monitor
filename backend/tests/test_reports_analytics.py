from datetime import date, datetime, timedelta, timezone


def _seed_history(client, admin_headers):
    """Insert log rows directly; the live pipeline is camera-bound."""
    from app.database import SessionLocal
    from app.models import (Attendance, AttentionLog, ClassSession, EmotionLog,
                            Student)

    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.name == "Seed Student").first()
        if student is None:
            student = Student(name="Seed Student")
            db.add(student)
            db.commit()
            db.refresh(student)
        session = ClassSession(name="Seed Session")
        db.add(session)
        db.commit()
        db.refresh(session)
        now = datetime.now(timezone.utc)
        db.add(Attendance(student_id=student.id, session_id=session.id,
                          timestamp_in=now - timedelta(hours=1),
                          timestamp_out=now, duration=3600))
        for i in range(6):
            ts = now - timedelta(minutes=10 * i)
            db.add(AttentionLog(student_id=student.id, session_id=session.id,
                                attention_score=0.5 + 0.05 * i, timestamp=ts))
            db.add(EmotionLog(student_id=student.id, session_id=session.id,
                              emotion="neutral" if i % 2 else "happy",
                              timestamp=ts))
        db.commit()
        return student.id, session.id
    finally:
        db.close()


def test_reports_json_csv_pdf(client, admin_headers, teacher_headers):
    _seed_history(client, admin_headers)
    today = date.today().isoformat()

    r = client.get(f"/reports/attendance?period=daily&date={today}&format=json",
                   headers=teacher_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["header"][0] == "date"
    assert any("Seed Student" in str(row) for row in body["rows"])

    r = client.get(f"/reports/attention?period=weekly&date={today}&format=csv",
                   headers=teacher_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert b"avg_attention" in r.content

    r = client.get(f"/reports/emotion?period=monthly&date={today}&format=pdf",
                   headers=teacher_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_report_validation(client, teacher_headers):
    assert client.get("/reports/unknown", headers=teacher_headers).status_code == 404
    assert client.get("/reports/attendance?period=hourly",
                      headers=teacher_headers).status_code == 422
    assert client.get("/reports/attendance?format=xlsx",
                      headers=teacher_headers).status_code == 422


def test_analytics_and_trends(client, admin_headers, teacher_headers):
    _seed_history(client, admin_headers)
    r = client.get("/analytics?minutes=120", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total_students"] >= 1
    assert len(body["attention_timeline"]) >= 1
    assert sum(body["emotion_distribution"].values()) >= 1

    today = date.today()
    frm = (today - timedelta(days=2)).isoformat()
    r = client.get(f"/analytics/trends?from={frm}&to={today.isoformat()}&bucket=day",
                   headers=teacher_headers)
    assert r.status_code == 200
    trends = r.json()
    assert len(trends["attention"]) >= 1
    assert len(trends["attendance"]) >= 1
    assert trends["peak_attendance"] is not None
    assert trends["most_distracted"] is not None

    # bad ranges rejected
    r = client.get(f"/analytics/trends?from={today.isoformat()}&to={frm}",
                   headers=teacher_headers)
    assert r.status_code == 422


def test_audit_log_written(client, admin_headers):
    r = client.post("/students", json={"name": "Audit Probe"},
                    headers=admin_headers)
    assert r.status_code == 201
    client.delete(f"/students/{r.json()['id']}", headers=admin_headers)

    from app.database import SessionLocal
    from app.models import AuditLog
    db = SessionLocal()
    try:
        actions = {a.action for a in db.query(AuditLog).all()}
    finally:
        db.close()
    for expected in ("login", "login_failed", "student_created",
                     "student_deleted", "report_exported", "user_created"):
        assert expected in actions, expected
