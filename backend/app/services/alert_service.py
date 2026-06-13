import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..models import Alert


@dataclass
class StudentAlertState:
    low_attention_since: Optional[float] = None
    negative_emotion_streak: int = 0
    last_alert_at: Dict[str, float] = field(default_factory=dict)


class AlertService:
    """Evaluates alert rules and persists triggered alerts.

    Rules (from spec):
      - absence       : student absent for > ABSENCE_ALERT_SECONDS
      - low_attention : attention < threshold continuously for LOW_ATTENTION_SECONDS
      - emotion       : sleepy/bored for >= N consecutive checks
    """

    def __init__(self, session_id: int):
        self.session_id = session_id
        self.states: Dict[int, StudentAlertState] = {}

    def _state(self, student_id: int) -> StudentAlertState:
        return self.states.setdefault(student_id, StudentAlertState())

    def _cooled_down(self, state: StudentAlertState, alert_type: str) -> bool:
        last = state.last_alert_at.get(alert_type, 0.0)
        return time.time() - last >= settings.ALERT_COOLDOWN_SECONDS

    def _fire(self, db: DbSession, state: StudentAlertState, alert_type: str,
              student_id: Optional[int], message: str) -> dict:
        state.last_alert_at[alert_type] = time.time()
        row = Alert(type=alert_type, student_id=student_id,
                    session_id=self.session_id, message=message)
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "id": row.id, "type": row.type, "student_id": row.student_id,
            "message": row.message, "timestamp": row.timestamp.isoformat(),
        }

    def check_attention(self, db: DbSession, student_id: int, name: str,
                        score: float) -> Optional[dict]:
        state = self._state(student_id)
        now = time.time()
        if score < settings.LOW_ATTENTION_THRESHOLD:
            if state.low_attention_since is None:
                state.low_attention_since = now
            elif (now - state.low_attention_since >= settings.LOW_ATTENTION_SECONDS
                  and self._cooled_down(state, "low_attention")):
                return self._fire(db, state, "low_attention", student_id,
                                  f"{name}: attention below "
                                  f"{settings.LOW_ATTENTION_THRESHOLD:.1f} for "
                                  f"{int(settings.LOW_ATTENTION_SECONDS)}s")
        else:
            state.low_attention_since = None
        return None

    def check_emotion(self, db: DbSession, student_id: int, name: str,
                      emotion: str) -> Optional[dict]:
        state = self._state(student_id)
        if emotion in ("sleepy", "bored"):
            state.negative_emotion_streak += 1
            if (state.negative_emotion_streak > settings.NEGATIVE_EMOTION_CONSECUTIVE
                    and self._cooled_down(state, "emotion")):
                return self._fire(db, state, "emotion", student_id,
                                  f"{name}: {emotion} for "
                                  f"{state.negative_emotion_streak} consecutive checks")
        else:
            state.negative_emotion_streak = 0
        return None

    def check_absence(self, db: DbSession, student_id: int, name: str,
                      seconds_absent: float) -> Optional[dict]:
        state = self._state(student_id)
        if (seconds_absent > settings.ABSENCE_ALERT_SECONDS
                and self._cooled_down(state, "absence")):
            return self._fire(db, state, "absence", student_id,
                              f"{name}: absent for {int(seconds_absent)}s")
        return None
