"""Live data-path test: registration -> student account -> portal -> reports.

Seeds a session's worth of attendance/attention/emotion directly (the live
pipeline is camera-bound), then exercises the real HTTP endpoints.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://localhost:8000"


def seed(student_id):
    from app.database import SessionLocal
    from app.models import (Attendance, AttentionLog, ClassSession, EmotionLog)
    db = SessionLocal()
    try:
        sess = ClassSession(name="Portal Test Session",
                            ended_at=datetime.now(timezone.utc))
        db.add(sess); db.commit(); db.refresh(sess)
        now = datetime.now(timezone.utc)
        db.add(Attendance(student_id=student_id, session_id=sess.id,
                          timestamp_in=now - timedelta(minutes=40),
                          timestamp_out=now, duration=2400))
        for i in range(12):
            ts = now - timedelta(minutes=3 * i)
            db.add(AttentionLog(student_id=student_id, session_id=sess.id,
                                attention_score=0.6 + 0.03 * (i % 5), timestamp=ts))
            db.add(EmotionLog(student_id=student_id, session_id=sess.id,
                              emotion=["neutral", "happy", "neutral", "distracted"][i % 4],
                              timestamp=ts))
        db.commit()
        return sess.id
    finally:
        db.close()


def main() -> int:
    s = requests.Session()
    fails = []

    def check(name, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
        if not ok:
            fails.append(name)

    admin = s.post(f"{BASE}/auth/login",
                   json={"username": "admin", "password": "admin123"}).json()
    ah = {"Authorization": f"Bearer {admin['token']}"}

    # 1. register student WITH login account
    import random
    uid = random.randint(1000, 9999)
    email = f"portaltest{uid}@school.edu"
    r = s.post(f"{BASE}/students", headers=ah,
               json={"name": f"Portal Test {uid}", "email": email,
                     "password": "studentpass1"})
    check("register student with account", r.status_code == 201, r.text[:80])
    stu = r.json()
    check("auto student ID issued", bool(stu.get("student_code")), stu.get("student_code"))
    check("account linked", stu.get("has_account") is True)
    check("registration date set", stu.get("registered_at") is not None)

    # seed a session's data for this student
    seed(stu["id"])

    # 2. student logs in with email + password
    r = s.post(f"{BASE}/auth/login", json={"username": email, "password": "studentpass1"})
    check("student email login", r.status_code == 200 and r.json()["role"] == "student")
    sh = {"Authorization": f"Bearer {r.json()['token']}"}

    # 3. student portal shows their own data
    r = s.get(f"{BASE}/me/student", headers=sh)
    prof = r.json()
    check("portal returns profile", r.status_code == 200)
    check("portal: attendance %", prof.get("attendance_percentage", 0) > 0,
          f"{prof.get('attendance_percentage')}%")
    check("portal: avg attention", prof.get("avg_attention", 0) > 0,
          str(prof.get("avg_attention")))
    check("portal: emotion stats", sum(prof.get("emotion_stats", {}).values()) > 0,
          str(prof.get("emotion_stats")))
    check("portal: attendance history", len(prof.get("attendance_history", [])) > 0)
    check("portal: last seen set", prof.get("last_seen") is not None)

    # 4. student CANNOT reach staff endpoints
    check("portal blocks /students", s.get(f"{BASE}/students", headers=sh).status_code == 403)
    check("portal blocks /analytics", s.get(f"{BASE}/analytics", headers=sh).status_code == 403)

    # 5. reports generate in all formats (as admin)
    today = datetime.now(timezone.utc).date().isoformat()
    for rtype in ("attendance", "attention", "emotion"):
        rc = s.get(f"{BASE}/reports/{rtype}",
                   params={"period": "daily", "date": today, "format": "csv"}, headers=ah)
        check(f"report {rtype} CSV", rc.status_code == 200 and len(rc.content) > 0)
        rp = s.get(f"{BASE}/reports/{rtype}",
                   params={"period": "daily", "date": today, "format": "pdf"}, headers=ah)
        check(f"report {rtype} PDF", rp.status_code == 200 and rp.content[:4] == b"%PDF")

    # teacher-side profile view
    r = s.get(f"{BASE}/students/{stu['id']}/profile", headers=ah)
    check("teacher profile view", r.status_code == 200 and r.json()["name"] == stu["name"])

    # cleanup
    s.delete(f"{BASE}/students/{stu['id']}", headers=ah)
    print()
    print("RESULT:", "ALL PASS" if not fails else f"FAILED: {fails}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
