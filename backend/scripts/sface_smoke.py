"""Offline smoke test for the SFace identity stack (no camera needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from app.services.face_detection import FaceDetector
from app.services.face_identity import EMBED_DIM, FaceIdentifier


def main() -> int:
    det = FaceDetector()
    ident = FaceIdentifier()
    assert det.yunet is not None, "YuNet not loaded"
    assert ident.available, "SFace not loaded"

    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    boxes = det.detect(frame)
    assert len(det.last_rows) == len(boxes)

    # bbox path (no landmarks)
    emb = ident.embed(frame, bbox=(100, 100, 120, 150))
    assert emb is not None and emb.shape == (EMBED_DIM,), emb if emb is None else emb.shape
    assert abs(float(np.linalg.norm(emb)) - 1.0) < 1e-3

    # same crop must be highly similar to itself, different crop less so
    emb2 = ident.embed(frame, bbox=(100, 100, 120, 150))
    emb3 = ident.embed(frame, bbox=(300, 200, 120, 150))
    same = FaceIdentifier.similarity(emb, emb2)
    diff = FaceIdentifier.similarity(emb, emb3)
    assert same > 0.99, same
    print(f"SFace smoke OK | dim={EMBED_DIM} | self-sim={same:.3f} | "
          f"other-crop-sim={diff:.3f} | detections-on-noise={len(boxes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
