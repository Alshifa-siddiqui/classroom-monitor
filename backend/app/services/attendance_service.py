import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from sqlalchemy.orm import Session as DbSession

from ..models import Attendance, FaceEmbedding, Student
from .face_identity import EMBED_DIM, FaceIdentifier
from .tracking import Track, cosine_similarity

log = logging.getLogger(__name__)

# Track absent for this long before attendance is closed out
EXIT_GRACE_SECONDS = 10.0
GALLERY_SIZE = 10

# SFace cosine-similarity decision zones (OpenCV's benchmark threshold for
# "same person" is 0.363):
#   >= MATCH      -> existing student, confidence = similarity
#   <  NEW_MAX    -> clearly nobody we know, register a new student
#   in between    -> ambiguous: stay "unknown", never create a duplicate
SFACE_MATCH_THRESHOLD = 0.40
SFACE_NEW_MAX = 0.25
MIN_IDENTITY_SAMPLES = 5
MAX_IDENTITY_SAMPLES = 25

# Legacy grayscale-patch matching, used only when the SFace model is missing
LEGACY_MATCH_SIMILARITY = 0.70


def _normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    return v / norm if norm > 1e-6 else v


@dataclass
class PresenceState:
    student_id: int
    attendance_id: int
    track_id: int
    entered_at: datetime
    last_seen: float = field(default_factory=time.time)
    present: bool = True


class AttendanceService:
    """Maps tracks to student identities and maintains attendance rows.

    Identity resolution (SFace): each unresolved track accumulates aligned
    face embeddings; once enough samples agree, the mean embedding is
    matched against per-student galleries. Ambiguous matches stay unknown
    rather than spawning duplicate students.
    """

    def __init__(self, session_id: int, identifier: Optional[FaceIdentifier] = None):
        self.session_id = session_id
        self.identifier = identifier
        self.states: Dict[int, PresenceState] = {}  # keyed by student_id
        self._track_to_student: Dict[int, int] = {}
        self._galleries: Dict[int, List[np.ndarray]] = {}
        self._galleries_loaded = False
        self._pending: Dict[int, List[np.ndarray]] = {}  # track_id -> samples
        self._confidence: Dict[int, float] = {}  # student_id -> match confidence

    # -- gallery management -------------------------------------------------

    @property
    def _embed_dim(self) -> int:
        if self.identifier is not None and self.identifier.available:
            return EMBED_DIM
        return 32 * 32  # legacy patch embedding

    def _load_galleries(self, db: DbSession) -> None:
        dim = self._embed_dim
        # enrollment embeddings first (multiple per student), then the
        # legacy/mean embedding column
        for row in db.query(FaceEmbedding).all():
            stored = np.frombuffer(row.embedding, dtype=np.float32)
            if stored.shape[0] == dim:
                self._galleries.setdefault(row.student_id, []).append(stored.copy())
        for student in db.query(Student).filter(Student.face_embedding.isnot(None)).all():
            stored = np.frombuffer(student.face_embedding, dtype=np.float32)
            if stored.shape[0] == dim:
                self._galleries.setdefault(student.id, []).append(stored.copy())
        self._galleries_loaded = True
        log.info("Loaded %d student galleries (%d-d embeddings)",
                 len(self._galleries), dim)

    def reload_galleries(self, db: DbSession) -> None:
        """Re-read galleries after enrollment changes mid-session."""
        self._galleries.clear()
        self._load_galleries(db)

    def _best_match(self, embedding: np.ndarray) -> Tuple[Optional[int], float]:
        best_id, best_sim = None, -1.0
        for student_id, gallery in self._galleries.items():
            sims = [cosine_similarity(e, embedding) for e in gallery
                    if e.shape == embedding.shape]
            if sims and max(sims) > best_sim:
                best_id, best_sim = student_id, max(sims)
        return best_id, best_sim

    def _add_to_gallery(self, db: DbSession, student_id: int,
                        embedding: np.ndarray) -> None:
        gallery = self._galleries.setdefault(student_id, [])
        gallery.append(embedding.astype(np.float32).copy())
        if len(gallery) > GALLERY_SIZE:
            gallery.pop(0)
        # persist the gallery mean so identity survives restarts
        mean = _normalize(np.mean(gallery, axis=0))
        student = db.get(Student, student_id)
        if student is not None:
            student.face_embedding = mean.astype(np.float32).tobytes()
            db.commit()

    def _register_student(self, db: DbSession, embedding: np.ndarray) -> int:
        count = db.query(Student).count()
        student = Student(name=f"Student {count + 1}",
                          face_embedding=embedding.astype(np.float32).tobytes())
        db.add(student)
        db.commit()
        db.refresh(student)
        self._galleries[student.id] = []
        log.info("Registered new student id=%s", student.id)
        return student.id

    # -- identity resolution ------------------------------------------------

    def resolve_student(self, db: DbSession, track: Track,
                        frame: Optional[np.ndarray] = None,
                        det_row: Optional[np.ndarray] = None
                        ) -> Optional[Tuple[int, float]]:
        """Returns (student_id, confidence) or None while identity is unknown."""
        if track.track_id in self._track_to_student:
            sid = self._track_to_student[track.track_id]
            return sid, self._confidence.get(sid, 1.0)
        if not self._galleries_loaded:
            self._load_galleries(db)

        if self.identifier is not None and self.identifier.available and frame is not None:
            return self._resolve_sface(db, track, frame, det_row)
        return self._resolve_legacy(db, track)

    def _resolve_sface(self, db: DbSession, track: Track, frame: np.ndarray,
                       det_row: Optional[np.ndarray]) -> Optional[Tuple[int, float]]:
        emb = self.identifier.embed(frame, det_row=det_row, bbox=track.bbox)
        if emb is None:
            return None
        samples = self._pending.setdefault(track.track_id, [])
        samples.append(emb)
        if len(samples) < MIN_IDENTITY_SAMPLES:
            return None

        mean = _normalize(np.mean(samples, axis=0))
        best_id, best_sim = self._best_match(mean)

        if best_id is not None and best_sim >= SFACE_MATCH_THRESHOLD:
            student_id, confidence = best_id, round(best_sim, 3)
        elif best_sim < SFACE_NEW_MAX:
            student_id, confidence = self._register_student(db, mean), 1.0
        else:
            # ambiguous zone: keep observing with a sliding window instead
            # of creating a duplicate identity
            if len(samples) >= MAX_IDENTITY_SAMPLES:
                samples.pop(0)
            return None

        self._pending.pop(track.track_id, None)
        self._track_to_student[track.track_id] = student_id
        self._confidence[student_id] = confidence
        track.student_id = student_id
        self._add_to_gallery(db, student_id, mean)
        return student_id, confidence

    def _resolve_legacy(self, db: DbSession, track: Track) -> Tuple[int, float]:
        best_id, best_sim = self._best_match(track.embedding)
        if best_id is None or best_sim < LEGACY_MATCH_SIMILARITY:
            best_id = self._register_student(db, track.embedding)
            best_sim = 1.0
        self._track_to_student[track.track_id] = best_id
        self._confidence[best_id] = round(max(best_sim, 0.0), 3)
        track.student_id = best_id
        self._add_to_gallery(db, best_id, track.embedding)
        return best_id, self._confidence[best_id]

    def prune_pending(self, active_track_ids: Set[int]) -> None:
        for tid in list(self._pending.keys()):
            if tid not in active_track_ids:
                del self._pending[tid]

    # -- attendance bookkeeping ----------------------------------------------

    def mark_present(self, db: DbSession, student_id: int, track_id: int) -> None:
        state = self.states.get(student_id)
        now = time.time()
        if state is None or not state.present:
            entered = datetime.now(timezone.utc)
            row = Attendance(student_id=student_id, session_id=self.session_id,
                             timestamp_in=entered)
            db.add(row)
            db.commit()
            db.refresh(row)
            self.states[student_id] = PresenceState(
                student_id=student_id, attendance_id=row.id,
                track_id=track_id, entered_at=entered, last_seen=now)
        else:
            state.last_seen = now
            state.track_id = track_id

    def close_absent(self, db: DbSession) -> List[int]:
        """Close attendance rows for students unseen past the grace period.
        Returns student ids that just exited."""
        exited: List[int] = []
        now = time.time()
        for state in self.states.values():
            if state.present and now - state.last_seen > EXIT_GRACE_SECONDS:
                row = db.get(Attendance, state.attendance_id)
                if row is not None:
                    out = datetime.now(timezone.utc)
                    row.timestamp_out = out
                    ts_in = row.timestamp_in
                    if ts_in.tzinfo is None:
                        ts_in = ts_in.replace(tzinfo=timezone.utc)
                    row.duration = int((out - ts_in).total_seconds())
                    db.commit()
                state.present = False
                exited.append(state.student_id)
        return exited

    def end_session(self, db: DbSession) -> None:
        for state in self.states.values():
            if state.present:
                row = db.get(Attendance, state.attendance_id)
                if row is not None and row.timestamp_out is None:
                    out = datetime.now(timezone.utc)
                    row.timestamp_out = out
                    ts_in = row.timestamp_in
                    if ts_in.tzinfo is None:
                        ts_in = ts_in.replace(tzinfo=timezone.utc)
                    row.duration = int((out - ts_in).total_seconds())
                state.present = False
        db.commit()

    def seconds_absent(self, student_id: int) -> Optional[float]:
        state = self.states.get(student_id)
        if state is None or state.present:
            return None
        return time.time() - state.last_seen

    def present_students(self) -> List[int]:
        return [s.student_id for s in self.states.values() if s.present]
