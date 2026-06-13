from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from .tracking import Track

# Frontal face boxes are roughly 0.75-0.85 wide relative to height;
# turning the head shrinks apparent width.
FRONTAL_ASPECT = 0.80


class AttentionEstimator:
    """Heuristic attention score in [0, 1] from three signals:

    1. eye focus      - Haar eye detection inside the upper face region
    2. head pose      - face aspect-ratio deviation + horizontal eye symmetry
    3. stability      - variance of recent face centers relative to face size

    score >= 0.7 focused, 0.4-0.7 partial, < 0.4 distracted.
    """

    def __init__(self):
        self.eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye.xml"
        )
        self.eye_glasses_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml"
        )
        self._smoothed: Dict[int, float] = {}

    def _detect_eyes(self, gray_face: np.ndarray, h: int):
        """Eye detection on the upper face region, trying variants in order.

        The raw image works best in decent light; equalization amplifies
        shadow noise and can lose eyes, so it is a fallback, not a default.
        Small faces also get upscaled before detection.
        """
        upper = gray_face[: int(h * 0.6), :]
        if upper.size == 0:
            return []
        variants = [(upper, 1.0)]
        if upper.shape[1] < 160:
            scale = 160.0 / upper.shape[1]
            variants.append((cv2.resize(upper, None, fx=scale, fy=scale), scale))
        variants.append((cv2.equalizeHist(variants[-1][0]), variants[-1][1]))
        for img, scale in variants:
            for cascade in (self.eye_cascade, self.eye_glasses_cascade):
                eyes = cascade.detectMultiScale(img, scaleFactor=1.1,
                                                minNeighbors=3, minSize=(18, 18))
                if len(eyes):
                    return [(ex / scale, ey / scale, ew / scale, eh / scale)
                            for (ex, ey, ew, eh) in eyes]
        return []

    def estimate(self, frame: np.ndarray, track: Track) -> Tuple[float, Optional[bool]]:
        """Returns (attention_score, eyes_open).

        eyes_open is True (eyes found), False (good conditions but no eyes,
        i.e. likely closed), or None (face too small/dark to judge — callers
        must not treat this as evidence of closed eyes).
        """
        x, y, w, h = track.bbox
        face = frame[y:y + h, x:x + w]
        if face.size == 0:
            return self._smooth(track.track_id, 0.0), None

        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
        upper_raw = gray[: int(h * 0.6), :]
        reliable = (w >= 60 and upper_raw.size > 0
                    and upper_raw.mean() >= 45 and upper_raw.std() >= 22)
        eyes = self._detect_eyes(gray, h)
        if eyes:
            eyes_open: Optional[bool] = True
        elif reliable:
            eyes_open = False
        else:
            eyes_open = None

        # 1. eye focus: both eyes visible -> frontal, focused;
        #    unjudgeable frames get a neutral score instead of zero
        if eyes:
            eye_score = min(len(eyes), 2) / 2.0
        else:
            eye_score = 0.0 if reliable else 0.5

        # 2. head pose: aspect deviation + eye horizontal symmetry
        aspect = w / h if h > 0 else 0.0
        aspect_dev = min(abs(aspect - FRONTAL_ASPECT) / 0.35, 1.0)
        pose_score = 1.0 - aspect_dev
        if len(eyes) >= 2:
            centers = sorted((ex + ew / 2.0) / w for (ex, ey, ew, eh) in eyes[:2])
            midpoint = (centers[0] + centers[1]) / 2.0
            symmetry = 1.0 - min(abs(midpoint - 0.5) / 0.25, 1.0)
            pose_score = 0.5 * pose_score + 0.5 * symmetry

        # 3. stability: jittery heads indicate looking around
        stability = 1.0
        if len(track.center_history) >= 5:
            pts = np.array(track.center_history[-10:])
            spread = float(np.std(pts[:, 0]) + np.std(pts[:, 1]))
            stability = 1.0 - min(spread / max(w, 1) / 0.5, 1.0)

        raw = 0.45 * eye_score + 0.35 * pose_score + 0.20 * stability
        return self._smooth(track.track_id, raw), eyes_open

    def _smooth(self, track_id: int, raw: float) -> float:
        prev = self._smoothed.get(track_id, raw)
        smoothed = 0.7 * prev + 0.3 * raw
        self._smoothed[track_id] = smoothed
        return round(float(np.clip(smoothed, 0.0, 1.0)), 3)

    def drop_track(self, track_id: int) -> None:
        self._smoothed.pop(track_id, None)

    def prune(self, active_track_ids) -> None:
        """Free per-track state for tracks that no longer exist."""
        for tid in list(self._smoothed):
            if tid not in active_track_ids:
                self._smoothed.pop(tid, None)


def attention_label(score: float) -> str:
    if score < 0.4:
        return "distracted"
    if score < 0.7:
        return "partial"
    return "focused"
