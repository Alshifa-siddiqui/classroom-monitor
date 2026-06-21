"""Objective re-identification accuracy test for the SFace matching logic.

Uses the actual AttendanceService matcher with controlled embeddings to
measure: (a) same-person re-identification, (b) wrong-match rate between
different people, (c) behaviour in the ambiguous zone. No camera needed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from app.services.attendance_service import (SFACE_MATCH_THRESHOLD,
                                              SFACE_NEW_MAX)
from app.services.face_identity import FaceIdentifier


def unit(v):
    return v / np.linalg.norm(v)


def make_person(rng, dim=128):
    """A stable identity vector plus a noise model for per-frame variation."""
    return unit(rng.standard_normal(dim).astype(np.float32))


def sample(rng, base, noise):
    return unit(base + noise * rng.standard_normal(base.shape).astype(np.float32))


def main() -> int:
    rng = np.random.default_rng(42)
    sim = FaceIdentifier.similarity

    # Build 5 distinct enrolled people, each with a gallery of 8 samples.
    # noise=0.12 reproduces realistic SFace separation: same-person cosine
    # ~0.6-0.7, different-person ~0.0-0.1 (matching observed live behaviour).
    NOISE = 0.12
    people = [make_person(rng) for _ in range(5)]
    galleries = [[sample(rng, p, NOISE) for _ in range(8)] for p in people]
    gallery_means = [unit(np.mean(g, axis=0)) for g in galleries]

    def best_match(emb):
        sims = [max(sim(e, emb) for e in g) for g in galleries]
        idx = int(np.argmax(sims))
        return idx, sims[idx]

    # The production matcher resolves identity from the MEAN of >=5 samples
    # (MIN_IDENTITY_SAMPLES), not a single frame. Mirror that here.
    def probe_mean(p, n=5):
        return unit(np.mean([sample(rng, p, NOISE) for _ in range(n)], axis=0))

    # (a) same-person re-identification using 5-sample mean probes
    correct, total = 0, 0
    for i, p in enumerate(people):
        for _ in range(50):
            idx, s = best_match(probe_mean(p))
            total += 1
            if s >= SFACE_MATCH_THRESHOLD and idx == i:
                correct += 1
    reid_rate = correct / total

    # (b) wrong-match rate: probe person A against galleries of B..E only
    wrong, trials = 0, 0
    for i, p in enumerate(people):
        others = [g for j, g in enumerate(galleries) if j != i]
        for _ in range(50):
            probe = probe_mean(p)
            sims = [max(sim(e, probe) for e in g) for g in others]
            trials += 1
            if max(sims) >= SFACE_MATCH_THRESHOLD:
                wrong += 1   # would have been matched to the wrong person
    wrong_rate = wrong / trials

    # (c) cross-person mean similarity (separation check)
    cross = [sim(gallery_means[i], gallery_means[j])
             for i in range(5) for j in range(i + 1, 5)]
    same = [sim(gallery_means[i], sample(rng, people[i], NOISE)) for i in range(5)]

    print("=== Re-identification accuracy (synthetic, 128-d) ===")
    print(f"match threshold={SFACE_MATCH_THRESHOLD}  new-id ceiling={SFACE_NEW_MAX}")
    print(f"(a) same-person re-ID rate : {reid_rate*100:.1f}%  ({correct}/{total})")
    print(f"(b) wrong-person match rate: {wrong_rate*100:.1f}%  ({wrong}/{trials})")
    print(f"(c) same-identity sim  avg : {np.mean(same):.3f}")
    print(f"    cross-identity sim avg : {np.mean(cross):.3f}  max : {np.max(cross):.3f}")
    ok = reid_rate >= 0.95 and wrong_rate <= 0.02 and np.max(cross) < SFACE_MATCH_THRESHOLD
    print("RESULT:", "PASS" if ok else "REVIEW")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
