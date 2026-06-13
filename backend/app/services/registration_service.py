"""Face enrollment: capture embeddings from the camera for a named student."""
import logging
import time
from typing import List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..models import FaceEmbedding, Student
from .face_detection import FaceDetector
from .face_identity import FaceIdentifier
from .tracking import cosine_similarity

log = logging.getLogger(__name__)

ENROLL_SAMPLES = 5
ENROLL_TIMEOUT_S = 10.0
# captured face must match an existing student this strongly to be a duplicate
DUPLICATE_SIMILARITY = 0.40


class EnrollmentError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    return v / norm if norm > 1e-6 else v


def _largest_face(detections) -> Optional[int]:
    if not detections:
        return None
    return max(range(len(detections)),
               key=lambda i: detections[i][2] * detections[i][3])


def capture_embeddings(grabber, samples: int = ENROLL_SAMPLES,
                       timeout_s: float = ENROLL_TIMEOUT_S
                       ) -> Tuple[List[np.ndarray], float]:
    """Collect SFace embeddings of the largest face in view.

    Uses dedicated detector/identifier instances so a concurrently running
    monitoring pipeline is never raced on shared cv2 model state.
    Returns (embeddings, quality) where quality is the mean pairwise
    similarity of the captured samples.
    """
    detector = FaceDetector()
    identifier = FaceIdentifier()
    if not identifier.available:
        raise EnrollmentError(503, "SFace model not available; run "
                                   "scripts/download_models.py")

    collected: List[np.ndarray] = []
    deadline = time.time() + timeout_s
    last_capture = 0.0
    while time.time() < deadline and len(collected) < samples:
        frame = grabber.latest()
        if frame is None:
            time.sleep(0.1)
            continue
        # space captures out so samples cover slight pose variation
        if time.time() - last_capture < 0.4:
            time.sleep(0.05)
            continue
        detections = detector.detect(frame)
        idx = _largest_face(detections)
        if idx is None:
            time.sleep(0.1)
            continue
        row = detector.last_rows[idx] if idx < len(detector.last_rows) else None
        x, y, w, h, _ = detections[idx]
        emb = identifier.embed(frame, det_row=row, bbox=(x, y, w, h))
        if emb is not None:
            collected.append(emb)
            last_capture = time.time()

    if len(collected) < max(3, samples // 2):
        raise EnrollmentError(
            422, f"Could not capture enough face samples "
                 f"({len(collected)}/{samples}). Make sure exactly one person "
                 f"faces the camera in good light.")

    sims = [cosine_similarity(a, b)
            for i, a in enumerate(collected) for b in collected[i + 1:]]
    quality = float(np.mean(sims)) if sims else 1.0
    if quality < 0.35:
        raise EnrollmentError(
            422, "Captured samples are inconsistent (possibly more than one "
                 "person in view). Try again.")
    return collected, round(quality, 3)


def find_duplicate(db: DbSession, mean_embedding: np.ndarray,
                   exclude_student_id: int) -> Optional[Student]:
    """Returns an already-enrolled student whose face matches the capture."""
    candidates: dict = {}
    for row in db.query(FaceEmbedding).all():
        emb = np.frombuffer(row.embedding, dtype=np.float32)
        if emb.shape == mean_embedding.shape:
            candidates.setdefault(row.student_id, []).append(emb)
    for student in db.query(Student).filter(Student.face_embedding.isnot(None)).all():
        emb = np.frombuffer(student.face_embedding, dtype=np.float32)
        if emb.shape == mean_embedding.shape:
            candidates.setdefault(student.id, []).append(emb)

    best_id, best_sim = None, DUPLICATE_SIMILARITY
    for student_id, embs in candidates.items():
        if student_id == exclude_student_id:
            continue
        sim = max(cosine_similarity(e, mean_embedding) for e in embs)
        if sim >= best_sim:
            best_id, best_sim = student_id, sim
    return db.get(Student, best_id) if best_id is not None else None


def store_enrollment(db: DbSession, student: Student,
                     embeddings: List[np.ndarray]) -> None:
    """Replace the student's stored embeddings with the new capture set."""
    db.query(FaceEmbedding).filter(FaceEmbedding.student_id == student.id).delete()
    for emb in embeddings:
        db.add(FaceEmbedding(student_id=student.id,
                             embedding=emb.astype(np.float32).tobytes()))
    mean = _normalize(np.mean(embeddings, axis=0))
    student.face_embedding = mean.astype(np.float32).tobytes()
    db.commit()


class TemporaryCamera:
    """Context manager providing a grabber when no session is running."""

    def __init__(self):
        from .pipeline import FrameGrabber
        self.grabber = FrameGrabber(settings.CAMERA_SOURCE, settings.FRAME_WIDTH)

    def __enter__(self):
        if not self.grabber.start():
            raise EnrollmentError(503, self.grabber.error or "Camera unavailable")
        return self.grabber

    def __exit__(self, *exc):
        self.grabber.stop()
        return False
