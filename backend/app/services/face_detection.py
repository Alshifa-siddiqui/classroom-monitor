import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np

from ..config import MODELS_DIR

log = logging.getLogger(__name__)

Box = Tuple[int, int, int, int, float]  # x, y, w, h, confidence

PROTOTXT = MODELS_DIR / "deploy.prototxt"
CAFFEMODEL = MODELS_DIR / "res10_300x300_ssd_iter_140000.caffemodel"
YUNET_ONNX = MODELS_DIR / "face_detection_yunet_2023mar.onnx"


class FaceDetector:
    """Face detector: YuNet (with 5-point landmarks for SFace alignment),
    falling back to res10 SSD, then Haar cascade.

    After detect(), `last_rows[i]` holds the raw YuNet row for box i
    (None per box when a fallback detector produced it).
    """

    def __init__(self, confidence: float = 0.5):
        self.confidence = confidence
        self.last_rows: List[Optional[np.ndarray]] = []
        self.yunet = None
        if YUNET_ONNX.exists():
            self.yunet = cv2.FaceDetectorYN_create(
                str(YUNET_ONNX), "", (320, 320),
                score_threshold=max(confidence, 0.6))
            log.info("Face detector: YuNet (landmark-aware)")
        self.net = None
        if PROTOTXT.exists() and CAFFEMODEL.exists():
            self.net = cv2.dnn.readNetFromCaffe(str(PROTOTXT), str(CAFFEMODEL))
            if self.yunet is None:
                log.info("Face detector: OpenCV DNN (res10 SSD)")
        elif self.yunet is None:
            log.warning("DNN model files missing, falling back to Haar cascade. "
                        "Run scripts/download_models.py for better accuracy.")
        self.haar = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

    def detect(self, frame: np.ndarray) -> List[Box]:
        if self.yunet is not None:
            boxes = self._detect_yunet(frame)
            return boxes
        if self.net is not None:
            boxes = self._detect_dnn(frame)
        else:
            boxes = self._detect_haar(frame)
        self.last_rows = [None] * len(boxes)
        return boxes

    def _detect_yunet(self, frame: np.ndarray) -> List[Box]:
        h, w = frame.shape[:2]
        self.yunet.setInputSize((w, h))
        _, faces = self.yunet.detect(frame)
        boxes: List[Box] = []
        self.last_rows = []
        if faces is None:
            return boxes
        for row in faces:
            conf = float(row[14])
            x, y, fw, fh = row[:4].astype(int)
            x, y = max(0, x), max(0, y)
            fw, fh = min(w - x, fw), min(h - y, fh)
            if fw < 20 or fh < 20:
                continue
            boxes.append((int(x), int(y), int(fw), int(fh), conf))
            self.last_rows.append(row)
        return boxes

    def _detect_dnn(self, frame: np.ndarray) -> List[Box]:
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0)
        )
        self.net.setInput(blob)
        detections = self.net.forward()
        boxes: List[Box] = []
        for i in range(detections.shape[2]):
            conf = float(detections[0, 0, i, 2])
            if conf < self.confidence:
                continue
            x1, y1, x2, y2 = (detections[0, 0, i, 3:7] * np.array([w, h, w, h])).astype(int)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w - 1, x2), min(h - 1, y2)
            if x2 - x1 < 20 or y2 - y1 < 20:
                continue
            boxes.append((x1, y1, x2 - x1, y2 - y1, conf))
        return boxes

    def _detect_haar(self, frame: np.ndarray) -> List[Box]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                           minSize=(40, 40))
        return [(int(x), int(y), int(w), int(h), 0.8) for (x, y, w, h) in faces]
