"""Download the face-detection and emotion ONNX models into backend/models/."""
import sys
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

FILES = {
    "deploy.prototxt":
        "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/"
        "face_detector/deploy.prototxt",
    "res10_300x300_ssd_iter_140000.caffemodel":
        "https://github.com/opencv/opencv_3rdparty/raw/"
        "dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel",
    "emotion-ferplus-8.onnx":
        "https://github.com/onnx/models/raw/main/validated/vision/body_analysis/"
        "emotion_ferplus/model/emotion-ferplus-8.onnx",
    "face_detection_yunet_2023mar.onnx":
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx":
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx",
}

# opencv_zoo stores models in git-lfs; a failed LFS resolution yields a
# ~130-byte pointer file instead of the model
MIN_SIZES = {
    "face_detection_yunet_2023mar.onnx": 100_000,
    "face_recognition_sface_2021dec.onnx": 10_000_000,
}


def main() -> int:
    MODELS_DIR.mkdir(exist_ok=True)
    failed = False
    for name, url in FILES.items():
        dest = MODELS_DIR / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"[skip] {name} already present")
            continue
        print(f"[get ] {name} ...")
        try:
            urllib.request.urlretrieve(url, dest)
            if dest.stat().st_size < MIN_SIZES.get(name, 1):
                dest.unlink()
                raise RuntimeError("downloaded file too small (git-lfs pointer?)")
            print(f"[ ok ] {name} ({dest.stat().st_size // 1024} KB)")
        except Exception as exc:
            print(f"[fail] {name}: {exc}")
            failed = True
    if failed:
        print("\nSome downloads failed. The system still runs with Haar-cascade "
              "fallbacks, but accuracy is lower.")
        return 1
    print("\nAll models ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
