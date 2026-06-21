"""Historical trend analytics and a small TTL cache for hot endpoints."""
import threading
import time
from collections import defaultdict
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from ..models import Attendance, AttentionLog, EmotionLog


class TTLCache:
    def __init__(self, ttl_seconds: float):
        self.ttl = ttl_seconds
        self._data: Dict[Any, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            item = self._data.get(key)
            if item is None or item[0] < time.time():
                return None
            return item[1]

    def set(self, key, value) -> None:
        with self._lock:
            if len(self._data) > 256:  # bounded; entries are tiny
                self._data.clear()
            self._data[key] = (time.time() + self.ttl, value)


def _bucket_key(ts: datetime, bucket: str) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if bucket == "hour":
        return ts.strftime("%Y-%m-%d %H:00")
    return ts.strftime("%Y-%m-%d")


def compute_trends(db: DbSession, start: date, end: date, bucket: str) -> dict:
    lo = datetime.combine(start, dtime.min, tzinfo=timezone.utc)
    hi = datetime.combine(end, dtime.max, tzinfo=timezone.utc)

    # attention per bucket
    att_sum: Dict[str, float] = defaultdict(float)
    att_n: Dict[str, int] = defaultdict(int)
    for ts, score in (db.query(AttentionLog.timestamp, AttentionLog.attention_score)
                      .filter(AttentionLog.timestamp >= lo,
                              AttentionLog.timestamp <= hi).all()):
        key = _bucket_key(ts, bucket)
        att_sum[key] += score
        att_n[key] += 1
    attention = [{"bucket": k, "value": round(att_sum[k] / att_n[k], 3)}
                 for k in sorted(att_n)]

    # emotions per bucket
    emo: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ts, emotion in (db.query(EmotionLog.timestamp, EmotionLog.emotion)
                        .filter(EmotionLog.timestamp >= lo,
                                EmotionLog.timestamp <= hi).all()):
        emo[_bucket_key(ts, bucket)][emotion] += 1
    emotions = [{"bucket": k, "counts": dict(emo[k])} for k in sorted(emo)]

    # distinct students present per bucket (an entry row spans its bucket)
    present: Dict[str, set] = defaultdict(set)
    for r in (db.query(Attendance)
              .filter(Attendance.timestamp_in <= hi)
              .filter((Attendance.timestamp_out.is_(None))
                      | (Attendance.timestamp_out >= lo)).all()):
        ts_in = r.timestamp_in if r.timestamp_in.tzinfo else r.timestamp_in.replace(
            tzinfo=timezone.utc)
        ts_out = r.timestamp_out or hi
        if ts_out.tzinfo is None:
            ts_out = ts_out.replace(tzinfo=timezone.utc)
        step = timedelta(hours=1) if bucket == "hour" else timedelta(days=1)
        cursor = max(ts_in, lo)
        while cursor <= min(ts_out, hi):
            present[_bucket_key(cursor, bucket)].add(r.student_id)
            cursor += step
    attendance = [{"bucket": k, "value": float(len(present[k]))}
                  for k in sorted(present)]

    peak: Optional[dict] = max(attendance, key=lambda p: p["value"], default=None)
    distracted: Optional[dict] = min(attention, key=lambda p: p["value"], default=None)

    return {
        "attendance": attendance,
        "attention": attention,
        "emotions": emotions,
        "peak_attendance": peak,
        "most_distracted": distracted,
    }
