import logging
from typing import Optional

import cv2
import numpy as np

from ..config import MODELS_DIR

log = logging.getLogger(__name__)

SFACE_ONNX = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

EMBED_DIM = 128


class FaceIdentifier:
    """SFace face-recognition embeddings via OpenCV's FaceRecognizerSF.

    Produces L2-normalized 128-d embeddings. When a YuNet detection row
    (with 5 landmarks) is available the face is properly aligned first;
    otherwise a padded square crop resized to 112x112 is used, which is
    less accurate but still far better than raw pixel matching.
    """

    def __init__(self):
        self.recognizer = None
        if SFACE_ONNX.exists():
            self.recognizer = cv2.FaceRecognizerSF_create(str(SFACE_ONNX), "")
            log.info("Identity model: SFace ONNX loaded")
        else:
            log.warning("SFace model missing; falling back to legacy patch "
                        "embeddings. Run scripts/download_models.py.")

    @property
    def available(self) -> bool:
        return self.recognizer is not None

    def embed(self, frame: np.ndarray, det_row: Optional[np.ndarray] = None,
              bbox: Optional[tuple] = None) -> Optional[np.ndarray]:
        if self.recognizer is None:
            return None
        try:
            if det_row is not None:
                crop = self.recognizer.alignCrop(frame, det_row)
            elif bbox is not None:
                x, y, w, h = bbox
                fh, fw = frame.shape[:2]
                pad = int(0.1 * max(w, h))
                x1, y1 = max(0, x - pad), max(0, y - pad)
                x2, y2 = min(fw, x + w + pad), min(fh, y + h + pad)
                face = frame[y1:y2, x1:x2]
                if face.size == 0:
                    return None
                crop = cv2.resize(face, (112, 112))
            else:
                return None
            feat = self.recognizer.feature(crop).flatten().astype(np.float32)
        except cv2.error:
            return None
        norm = np.linalg.norm(feat)
        if norm < 1e-6:
            return None
        return feat / norm

    @staticmethod
    def similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))
