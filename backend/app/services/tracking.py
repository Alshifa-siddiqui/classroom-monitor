import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

EMBED_SIZE = (32, 32)


def compute_embedding(face_bgr: np.ndarray) -> np.ndarray:
    """Lightweight appearance embedding: normalized grayscale patch vector."""
    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    patch = cv2.resize(gray, EMBED_SIZE).astype(np.float32).flatten()
    patch -= patch.mean()
    norm = np.linalg.norm(patch)
    return patch / norm if norm > 1e-6 else patch


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2, bx2, by2 = ax1 + aw, ay1 + ah, bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Track:
    track_id: int
    bbox: Tuple[int, int, int, int]
    embedding: np.ndarray
    student_id: Optional[int] = None
    missed_frames: int = 0
    last_seen: float = field(default_factory=time.time)
    center_history: List[Tuple[float, float]] = field(default_factory=list)

    @property
    def center(self) -> Tuple[float, float]:
        x, y, w, h = self.bbox
        return (x + w / 2.0, y + h / 2.0)

    def update(self, bbox: Tuple[int, int, int, int], embedding: np.ndarray) -> None:
        self.bbox = bbox
        # exponential moving average keeps the embedding cache fresh but stable
        self.embedding = 0.9 * self.embedding + 0.1 * embedding
        norm = np.linalg.norm(self.embedding)
        if norm > 1e-6:
            self.embedding = self.embedding / norm
        self.missed_frames = 0
        self.last_seen = time.time()
        self.center_history.append(self.center)
        if len(self.center_history) > 30:
            self.center_history.pop(0)


class FaceTracker:
    """IoU greedy matcher with embedding-based re-identification.

    Lost tracks are kept in a gallery; a new detection whose embedding is
    similar to a lost track re-acquires that track's ID (and student ID),
    so a student who looks away or leaves briefly keeps their identity.
    """

    def __init__(self, max_missed: int = 30, iou_threshold: float = 0.25,
                 reid_similarity: float = 0.82, gallery_ttl: float = 600.0):
        self.max_missed = max_missed
        self.iou_threshold = iou_threshold
        self.reid_similarity = reid_similarity
        self.gallery_ttl = gallery_ttl
        self.tracks: Dict[int, Track] = {}
        self.lost_gallery: Dict[int, Track] = {}
        self._next_id = 1

    def update(self, frame: np.ndarray,
               detections: List[Tuple[int, int, int, int, float]]) -> List[Track]:
        boxes = [(x, y, w, h) for (x, y, w, h, _c) in detections]
        embeddings = []
        for (x, y, w, h) in boxes:
            crop = frame[y:y + h, x:x + w]
            embeddings.append(compute_embedding(crop) if crop.size else
                              np.zeros(EMBED_SIZE[0] * EMBED_SIZE[1], dtype=np.float32))

        # 1. Greedy IoU matching against active tracks
        unmatched = list(range(len(boxes)))
        pairs: List[Tuple[int, int, float]] = []
        for tid, track in self.tracks.items():
            for di in unmatched:
                pairs.append((tid, di, iou(track.bbox, boxes[di])))
        pairs.sort(key=lambda p: p[2], reverse=True)
        matched_tracks, matched_dets = set(), set()
        for tid, di, score in pairs:
            if score < self.iou_threshold or tid in matched_tracks or di in matched_dets:
                continue
            self.tracks[tid].update(boxes[di], embeddings[di])
            matched_tracks.add(tid)
            matched_dets.add(di)

        # 2. Re-identify remaining detections against the lost-track gallery
        now = time.time()
        self.lost_gallery = {tid: t for tid, t in self.lost_gallery.items()
                             if now - t.last_seen < self.gallery_ttl}
        for di in range(len(boxes)):
            if di in matched_dets:
                continue
            best_tid, best_sim = None, self.reid_similarity
            for tid, lost in self.lost_gallery.items():
                sim = cosine_similarity(lost.embedding, embeddings[di])
                if sim > best_sim:
                    best_tid, best_sim = tid, sim
            if best_tid is not None:
                track = self.lost_gallery.pop(best_tid)
                track.update(boxes[di], embeddings[di])
                self.tracks[best_tid] = track
            else:
                tid = self._next_id
                self._next_id += 1
                self.tracks[tid] = Track(track_id=tid, bbox=boxes[di],
                                         embedding=embeddings[di])
                self.tracks[tid].center_history.append(self.tracks[tid].center)
            matched_dets.add(di)

        # 3. Age out unmatched tracks
        for tid in list(self.tracks.keys()):
            if tid in matched_tracks:
                continue
            track = self.tracks[tid]
            track.missed_frames += 1
            if track.missed_frames > self.max_missed:
                self.lost_gallery[tid] = self.tracks.pop(tid)

        return [t for t in self.tracks.values() if t.missed_frames == 0]

    def active_tracks(self) -> List[Track]:
        return list(self.tracks.values())
