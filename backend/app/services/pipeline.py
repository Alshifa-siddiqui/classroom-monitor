import asyncio
import base64
import logging
import threading
import time
from typing import Dict, List, Optional

import cv2
import numpy as np

from ..config import settings
from ..database import SessionLocal
from ..models import AttentionLog, EmotionLog, Student
from .alert_service import AlertService
from .attendance_service import AttendanceService
from .attention_logic import AttentionEstimator, attention_label
from .emotion_model import EmotionClassifier
from .face_detection import FaceDetector
from .face_identity import FaceIdentifier
from .tracking import FaceTracker

log = logging.getLogger(__name__)

# OpenCV's MSMF backend logs a warning per failed grab — at 30fps a dead
# camera floods the log with thousands of lines per minute
cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)

COLORS = {"focused": (80, 200, 80), "partial": (60, 180, 255), "distracted": (60, 60, 230)}

# Consecutive failed reads before the stream is declared dead
MAX_READ_FAILURES = 50
RECONNECT_DELAY = 3.0


class FrameGrabber:
    """Background capture thread holding only the latest frame (frame skipping).

    If the device stops streaming (claimed by another app, unplugged,
    privacy shutter), the grabber drops the stale frame and keeps trying to
    reopen the source until it comes back or the session ends.
    """

    def __init__(self, source: str, width: int):
        self.source = int(source) if source.isdigit() else source
        self.width = width
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.error: Optional[str] = None

    def start(self) -> bool:
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            self.error = f"Cannot open camera source: {self.source}"
            return False
        self._cap = cap
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def _loop(self) -> None:
        failures = 0
        while self._running:
            ok, frame = self._cap.read()
            if ok:
                failures = 0
                h, w = frame.shape[:2]
                if w > self.width:
                    frame = cv2.resize(frame, (self.width, int(h * self.width / w)))
                with self._lock:
                    self._frame = frame
                continue

            failures += 1
            if isinstance(self.source, str) and failures < MAX_READ_FAILURES:
                # video file reached EOF: rewind and loop
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                time.sleep(0.02)
                continue
            if failures < MAX_READ_FAILURES:
                time.sleep(0.05)
                continue

            # stream is dead: drop the stale frame so the pipeline stops
            # analyzing a frozen image, then try to reopen the device
            with self._lock:
                self._frame = None
            if failures == MAX_READ_FAILURES:
                log.warning("Camera stream dead after %d failed reads; "
                            "will retry every %.0fs", failures, RECONNECT_DELAY)
            self._cap.release()
            time.sleep(RECONNECT_DELAY)
            self._cap = cv2.VideoCapture(self.source)
            if self._cap.isOpened() and self._cap.read()[0]:
                log.info("Camera reconnected")
                failures = 0
        self._cap.release()

    def latest(self) -> Optional[np.ndarray]:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)


class MonitoringPipeline:
    """Async processing loop: detect -> track -> emotion/attention -> broadcast/persist."""

    def __init__(self, session_id: int, broadcaster):
        self.session_id = session_id
        self.broadcaster = broadcaster  # async callable(dict)
        self.detector = FaceDetector()
        self.tracker = FaceTracker(max_missed=settings.TRACK_LOST_FRAMES,
                                   reid_similarity=settings.REID_SIMILARITY)
        self.emotion = EmotionClassifier()
        self.attention = AttentionEstimator()
        self.identifier = FaceIdentifier()
        self.attendance = AttendanceService(session_id, identifier=self.identifier)
        self.alerts = AlertService(session_id)
        self.grabber = FrameGrabber(settings.CAMERA_SOURCE, settings.FRAME_WIDTH)
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._student_names: Dict[int, str] = {}
        self.latest_snapshot: dict = {"students": [], "summary": {}}

    async def start(self) -> None:
        if not self.grabber.start():
            raise RuntimeError(self.grabber.error)
        self.running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self.running = False
        if self._task is not None:
            await self._task
            self._task = None
        self.grabber.stop()
        db = SessionLocal()
        try:
            self.attendance.end_session(db)
        finally:
            db.close()

    @staticmethod
    def _encode_jpeg(frame: np.ndarray) -> Optional[str]:
        ok, buf = cv2.imencode(".jpg", frame,
                               [cv2.IMWRITE_JPEG_QUALITY, settings.JPEG_QUALITY])
        return base64.b64encode(buf.tobytes()).decode("ascii") if ok else None

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        interval = 1.0 / settings.TARGET_FPS
        last_frame_sent = 0.0
        last_analytics_sent = 0.0
        last_flush = time.time()
        frame_period = 1.0 / settings.FRAME_BROADCAST_FPS
        frame_counter = 0
        empty_streak = 0

        while self.running:
            start = time.time()
            frame = self.grabber.latest()
            if frame is None:
                await asyncio.sleep(0.05)
                continue

            # idle throttle: after a long run of empty frames, only run the
            # CV stack on every Nth frame; the live feed keeps streaming
            frame_counter += 1
            idle = empty_streak >= settings.IDLE_AFTER_FRAMES
            if idle and frame_counter % settings.IDLE_DETECT_EVERY != 0:
                now = time.time()
                if now - last_frame_sent >= frame_period:
                    last_frame_sent = now
                    data = await loop.run_in_executor(None, self._encode_jpeg, frame)
                    if data:
                        await self.broadcaster({"type": "frame", "data": data})
                await asyncio.sleep(max(0.0, interval - (time.time() - start)))
                continue

            try:
                # heavy CV work off the event loop (async inference)
                results, annotated = await loop.run_in_executor(
                    None, self._process_frame, frame)
            except Exception:
                log.exception("Frame processing failed")
                await asyncio.sleep(interval)
                continue

            summary = results.get("summary", {})
            if summary.get("present_count", 0) or summary.get("identifying_count", 0):
                empty_streak = 0
            else:
                empty_streak += 1

            now = time.time()
            for alert in results.pop("new_alerts", []):
                await self.broadcaster({"type": "alert", "alert": alert})
            if now - last_analytics_sent >= settings.ANALYTICS_BROADCAST_INTERVAL:
                last_analytics_sent = now
                self.latest_snapshot = results
                await self.broadcaster({"type": "analytics", **results})
            if now - last_frame_sent >= frame_period:
                last_frame_sent = now
                data = await loop.run_in_executor(None, self._encode_jpeg, annotated)
                if data:
                    await self.broadcaster({"type": "frame", "data": data})
            if now - last_flush >= settings.SUMMARY_FLUSH_INTERVAL:
                last_flush = now
                flush_alerts = await loop.run_in_executor(
                    None, self._flush_summaries, results)
                for alert in flush_alerts:
                    await self.broadcaster({"type": "alert", "alert": alert})
                # prevent per-track state growing forever on long sessions
                known = ({t.track_id for t in self.tracker.active_tracks()}
                         | set(self.tracker.lost_gallery.keys()))
                self.emotion.prune(known)
                self.attention.prune(known)

            elapsed = time.time() - start
            await asyncio.sleep(max(0.0, interval - elapsed))

    def _student_label(self, db, student_id: int):
        """Returns (name, student_code), cached."""
        if student_id not in self._student_names:
            student = db.get(Student, student_id)
            if student is not None:
                self._student_names[student_id] = (student.name,
                                                   student.student_code or "")
            else:
                self._student_names[student_id] = (f"#{student_id}", "")
        return self._student_names[student_id]

    def invalidate_name(self, student_id: int) -> None:
        """Drop the cached display name after a rename."""
        self._student_names.pop(student_id, None)

    @staticmethod
    def _draw_overlay(frame, x, y, w, h, color, lines) -> None:
        """Bounding box plus a multi-line label card above it."""
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1
        line_h = 15
        widths = [cv2.getTextSize(line, font, scale, thick)[0][0] for line in lines]
        card_w = max(widths) + 10
        card_h = line_h * len(lines) + 8
        ty = max(0, y - card_h - 2)
        tx = max(0, min(x, frame.shape[1] - card_w))
        cv2.rectangle(frame, (tx, ty), (tx + card_w, ty + card_h), (24, 27, 34), -1)
        cv2.rectangle(frame, (tx, ty), (tx + card_w, ty + card_h), color, 1)
        for i, line in enumerate(lines):
            cv2.putText(frame, line, (tx + 5, ty + line_h * (i + 1)),
                        font, scale, (235, 238, 244), thick, cv2.LINE_AA)

    def _process_frame(self, frame: np.ndarray):
        db = SessionLocal()
        try:
            detections = self.detector.detect(frame)
            rows = list(self.detector.last_rows)
            row_by_box = {det[:4]: row for det, row in zip(detections, rows)}
            tracks = self.tracker.update(frame, detections)
            self.attendance.prune_pending({t.track_id for t in tracks})

            students: List[dict] = []
            new_alerts: List[dict] = []
            identifying = 0
            for track in tracks:
                det_row = row_by_box.get(tuple(track.bbox))
                x, y, w, h = track.bbox
                resolved = self.attendance.resolve_student(
                    db, track, frame=frame, det_row=det_row)
                if resolved is None:
                    # identity not confident yet: show the box, log nothing
                    identifying += 1
                    self._draw_overlay(frame, x, y, w, h, (160, 160, 160),
                                       ["identifying..."])
                    continue
                student_id, confidence = resolved
                self.attendance.mark_present(db, student_id, track.track_id)
                name, student_code = self._student_label(db, student_id)

                score, eyes_open = self.attention.estimate(frame, track)
                # FER+ was trained on faces with margin; pad the tight box
                fh, fw = frame.shape[:2]
                pad_x, pad_y = int(w * 0.15), int(h * 0.15)
                x1, y1 = max(0, x - pad_x), max(0, y - pad_y)
                x2, y2 = min(fw, x + w + pad_x), min(fh, y + h + pad_y)
                face = frame[y1:y2, x1:x2]
                emotion = self.emotion.classify(face, track.track_id, eyes_open)
                label = attention_label(score)

                alert = self.alerts.check_attention(db, student_id, name, score)
                if alert:
                    new_alerts.append(alert)

                students.append({
                    "student_id": student_id, "student_code": student_code,
                    "track_id": track.track_id,
                    "name": name, "present": True, "attention": score,
                    "attention_label": label, "emotion": emotion,
                    "identity_confidence": confidence,
                })

                conf_pct = min(confidence, 1.0) * 100
                self._draw_overlay(frame, x, y, w, h, COLORS[label], [
                    f"{name}" + (f"  {student_code}" if student_code else ""),
                    f"{label.capitalize()} | {emotion}",
                    f"Attention {score * 100:.0f}% | Conf {conf_pct:.0f}%",
                ])

            # absent students
            self.attendance.close_absent(db)
            for state in self.attendance.states.values():
                if state.present:
                    continue
                name, student_code = self._student_label(db, state.student_id)
                students.append({
                    "student_id": state.student_id, "student_code": student_code,
                    "track_id": state.track_id,
                    "name": name, "present": False, "attention": 0.0,
                    "attention_label": "absent", "emotion": "absent",
                    "identity_confidence": None,
                })
                seconds = self.attendance.seconds_absent(state.student_id)
                if seconds is not None:
                    alert = self.alerts.check_absence(db, state.student_id, name, seconds)
                    if alert:
                        new_alerts.append(alert)

            present = [s for s in students if s["present"]]
            emotion_dist: Dict[str, int] = {}
            for s in present:
                emotion_dist[s["emotion"]] = emotion_dist.get(s["emotion"], 0) + 1
            avg_attention = (round(sum(s["attention"] for s in present) / len(present), 3)
                             if present else 0.0)

            return ({
                "students": students,
                "summary": {
                    "present_count": len(present),
                    "total_students": len(students),
                    "avg_attention": avg_attention,
                    "emotion_distribution": emotion_dist,
                    "identifying_count": identifying,
                },
                "new_alerts": new_alerts,
                "ts": time.time(),
            }, frame)
        finally:
            db.close()

    def _flush_summaries(self, results: dict) -> List[dict]:
        """Persist per-student attention/emotion samples; runs emotion streak checks."""
        db = SessionLocal()
        new_alerts: List[dict] = []
        try:
            for s in results.get("students", []):
                if not s["present"]:
                    continue
                db.add(AttentionLog(student_id=s["student_id"], session_id=self.session_id,
                                    attention_score=s["attention"]))
                db.add(EmotionLog(student_id=s["student_id"], session_id=self.session_id,
                                  emotion=s["emotion"]))
                alert = self.alerts.check_emotion(db, s["student_id"], s["name"],
                                                  s["emotion"])
                if alert:
                    new_alerts.append(alert)
            db.commit()
        except Exception:
            log.exception("Summary flush failed")
            db.rollback()
        finally:
            db.close()
        return new_alerts
