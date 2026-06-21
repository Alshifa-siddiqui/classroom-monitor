"""Offline smoke test: loads models and runs one synthetic frame through the CV stack."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from app.services.attention_logic import AttentionEstimator, attention_label
from app.services.emotion_model import CLASSES, EmotionClassifier
from app.services.face_detection import FaceDetector
from app.services.tracking import FaceTracker, Track, compute_embedding


def main() -> int:
    det = FaceDetector()
    emo = EmotionClassifier()
    trk = FaceTracker()
    att = AttentionEstimator()

    assert det.net is not None, "DNN face detector not loaded"
    assert emo.net is not None, "FER+ model not loaded"

    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    boxes = det.detect(frame)
    trk.update(frame, boxes)

    fake_face = np.random.randint(0, 255, (96, 80, 3), dtype=np.uint8)
    label = emo._classify_dnn(fake_face)
    assert label in CLASSES, label

    track = Track(track_id=99, bbox=(100, 100, 80, 100),
                  embedding=compute_embedding(fake_face))
    score, eyes_open = att.estimate(frame, track)
    assert 0.0 <= score <= 1.0
    assert attention_label(score) in ("focused", "partial", "distracted")

    print(f"CV smoke test OK | detections={len(boxes)} | emotion={label} | "
          f"attention={score} ({attention_label(score)}) eyes_open={eyes_open}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
