import logging
from collections import deque
from typing import Deque, Dict

import cv2
import numpy as np

from ..config import MODELS_DIR

log = logging.getLogger(__name__)

FERPLUS_ONNX = MODELS_DIR / "emotion-ferplus-8.onnx"

# FER+ output order
FERPLUS_LABELS = ["neutral", "happiness", "surprise", "sadness",
                  "anger", "disgust", "fear", "contempt"]

# Map FER+ classes onto the dashboard's 5 classes
FERPLUS_TO_CLASS = {
    "neutral": "neutral",
    "happiness": "happy",
    "surprise": "distracted",
    "anger": "distracted",
    "fear": "distracted",
    "disgust": "distracted",
    "sadness": "bored",
    "contempt": "bored",
}

CLASSES = ["neutral", "happy", "distracted", "sleepy", "bored"]


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()


class EmotionClassifier:
    """FER+ ONNX model via OpenCV DNN, combined with an eye-openness signal.

    Sustained closed eyes override the facial-expression class with 'sleepy',
    since FER+ has no sleepy class.
    """

    def __init__(self, sleepy_window: int = 10, sleepy_ratio: float = 0.8,
                 vote_window: int = 5):
        self.net = None
        if FERPLUS_ONNX.exists():
            self.net = cv2.dnn.readNetFromONNX(str(FERPLUS_ONNX))
            log.info("Emotion model: FER+ ONNX loaded")
        else:
            log.warning("emotion-ferplus-8.onnx missing; using heuristic emotions. "
                        "Run scripts/download_models.py for real inference.")
        self.sleepy_window = sleepy_window
        self.sleepy_ratio = sleepy_ratio
        self.vote_window = vote_window
        self._eye_history: Dict[int, Deque[bool]] = {}
        self._label_history: Dict[int, Deque[str]] = {}

    def classify(self, face_bgr: np.ndarray, track_id: int,
                 eyes_open: "bool | None") -> str:
        history = self._eye_history.setdefault(track_id, deque(maxlen=self.sleepy_window))
        # None means the frame was too small/dark to judge the eyes —
        # only frames with an actual eye verdict count toward sleepy
        if eyes_open is not None:
            history.append(bool(eyes_open))
        closed_ratio = (1.0 - (sum(history) / len(history))) if history else 0.0
        if len(history) == self.sleepy_window and closed_ratio >= self.sleepy_ratio:
            return "sleepy"

        if self.net is not None and face_bgr.size:
            label = self._classify_dnn(face_bgr)
        else:
            label = self._classify_heuristic(face_bgr, eyes_open)

        # single-frame FER is noisy; majority vote over recent frames
        # keeps the reported emotion stable
        votes = self._label_history.setdefault(track_id, deque(maxlen=self.vote_window))
        votes.append(label)
        return max(set(votes), key=lambda l: (votes.count(l), l == label))

    def _classify_dnn(self, face_bgr: np.ndarray) -> str:
        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        resized = cv2.resize(gray, (64, 64)).astype(np.float32)
        blob = resized.reshape(1, 1, 64, 64)
        self.net.setInput(blob)
        scores = softmax(self.net.forward().flatten())
        label = FERPLUS_LABELS[int(np.argmax(scores))]
        return FERPLUS_TO_CLASS[label]

    def _classify_heuristic(self, face_bgr: np.ndarray,
                            eyes_open: "bool | None") -> str:
        if eyes_open is False:
            return "bored"
        if face_bgr.size:
            gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
            h = gray.shape[0]
            mouth_region = gray[int(h * 0.65):, :]
            # bright lower-face variance correlates loosely with smiling
            if mouth_region.size and mouth_region.std() > 55:
                return "happy"
        return "neutral"

    def drop_track(self, track_id: int) -> None:
        self._eye_history.pop(track_id, None)
        self._label_history.pop(track_id, None)

    def prune(self, active_track_ids) -> None:
        """Free per-track state for tracks that no longer exist."""
        for tid in list(self._eye_history):
            if tid not in active_track_ids:
                self.drop_track(tid)
