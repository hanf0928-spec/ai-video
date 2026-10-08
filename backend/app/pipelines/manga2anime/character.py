
"""Stage 4: Character consistency - detect & cluster character faces across panels."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict

import cv2
import numpy as np

from ...core.logger import logger


@dataclass
class CharacterInstance:
    panel_index: int
    bbox: tuple[int, int, int, int]
    embedding: np.ndarray | None = None
    cluster_id: int = -1


def extract_faces(panel_image: str | Path) -> List[CharacterInstance]:
    """Detect faces (anime-friendly) in a panel.

    Preference order:
      1. animeface via `anime-face-detector` if installed.
      2. OpenCV Haar cascade (lbpcascade_animeface.xml if available).
      3. Nothing.
    """
    img = cv2.imread(str(panel_image))
    if img is None:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    cascade_path = Path(__file__).resolve().parents[4] / "data" / "models" / "lbpcascade_animeface.xml"
    results: list[CharacterInstance] = []
    if cascade_path.exists():
        try:
            cascade = cv2.CascadeClassifier(str(cascade_path))
            faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(48, 48))
            for (x, y, w, h) in faces:
                results.append(CharacterInstance(panel_index=0, bbox=(x, y, x + w, y + h)))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"anime cascade failed: {e}")
    return results


def _embed_face(img: np.ndarray) -> np.ndarray:
    """Return a cheap descriptor for clustering. In production use CLIP/ArcFace."""
    try:
        resized = cv2.resize(img, (64, 64))
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        return hist.flatten().astype(np.float32)
    except Exception:
        return np.zeros(256, dtype=np.float32)


def cluster_characters(instances: List[CharacterInstance], threshold: float = 0.4) -> Dict[int, List[CharacterInstance]]:
    """Simple greedy clustering by cosine similarity of embeddings."""
    clusters: Dict[int, List[CharacterInstance]] = {}
    centroids: Dict[int, np.ndarray] = {}
    next_id = 0

    for inst in instances:
        if inst.embedding is None:
            inst.cluster_id = -1
            continue
        best_id = -1
        best_sim = -1.0
        for cid, centroid in centroids.items():
            denom = (np.linalg.norm(inst.embedding) * np.linalg.norm(centroid)) + 1e-8
            sim = float(np.dot(inst.embedding, centroid) / denom)
            if sim > best_sim:
                best_sim = sim
                best_id = cid
        if best_sim >= threshold and best_id != -1:
            inst.cluster_id = best_id
            clusters[best_id].append(inst)
            # update centroid (running mean)
            centroids[best_id] = 0.9 * centroids[best_id] + 0.1 * inst.embedding
        else:
            inst.cluster_id = next_id
            clusters[next_id] = [inst]
            centroids[next_id] = inst.embedding.copy()
            next_id += 1
    return clusters


def build_character_bank(panels: list[dict], workdir: str | Path) -> list[dict]:
    """Scan every panel, extract character crops, cluster, dump reference images.

    Returns a list of character records:
        [{"cluster_id": 0, "reference_images": [path,...], "count": n}, ...]
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    all_instances: list[CharacterInstance] = []

    for p in panels:
        img = cv2.imread(p["image_path"])
        if img is None:
            continue
        faces = extract_faces(p["image_path"])
        for f in faces:
            x1, y1, x2, y2 = f.bbox
            crop = img[y1:y2, x1:x2]
            f.embedding = _embed_face(crop)
            f.panel_index = p.get("order", 0)
            all_instances.append(f)

    clusters = cluster_characters(all_instances)
    records: list[dict] = []
    for cid, items in clusters.items():
        refs: list[str] = []
        for i, inst in enumerate(items[:5]):
            # Save reference crop
            panel = next((p for p in panels if p.get("order") == inst.panel_index), None)
            if panel is None:
                continue
            img = cv2.imread(panel["image_path"])
            if img is None:
                continue
            x1, y1, x2, y2 = inst.bbox
            crop = img[y1:y2, x1:x2]
            dst = workdir / f"char_{cid:03d}_{i}.png"
            cv2.imwrite(str(dst), crop)
            refs.append(str(dst))
        records.append({
            "cluster_id": cid,
            "reference_images": refs,
            "count": len(items),
        })
    logger.info(f"[character] clustered {len(records)} identities from {len(all_instances)} face crops")
    return records
