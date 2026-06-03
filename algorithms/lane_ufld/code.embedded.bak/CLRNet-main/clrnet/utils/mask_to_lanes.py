"""Extract lane polylines from MUFLD/CULane-style segmentation masks."""

from __future__ import annotations

import numpy as np


def normalize_mask_labels(arr: np.ndarray, num_lanes: int = 4) -> np.ndarray:
    """Map MUFLD ids 0,2,3,4,5 -> 0,1,2,3,4 for seg training."""
    if arr.max() <= num_lanes:
        return arr.astype(np.uint8)
    out = np.zeros_like(arr, dtype=np.uint8)
    for lane_idx in range(1, num_lanes + 1):
        out[arr == (lane_idx + 1)] = lane_idx
    return out


def lane_pixel_id(lane_idx: int, mask_max: int) -> int:
    if mask_max == 2:
        return lane_idx
    return lane_idx + 1


def lanes_from_mask(
    mask: np.ndarray,
    sample_ys: list | range,
    num_lanes: int = 4,
) -> list[list[tuple[float, float]]]:
    """Return list of lanes; each lane is [(x,y), ...] sorted by y descending."""
    if mask.ndim > 2:
        mask = mask[:, :, 0]
    mask = normalize_mask_labels(mask.astype(np.uint8), num_lanes)
    mx = int(mask.max())
    lanes = []
    for lane_idx in range(1, num_lanes + 1):
        vid = lane_pixel_id(lane_idx, mx)
        pts = []
        for y in sample_ys:
            yi = int(round(y))
            if yi < 0 or yi >= mask.shape[0]:
                continue
            xs = np.where(mask[yi] == vid)[0]
            if len(xs) == 0:
                continue
            pts.append((float(np.mean(xs)), float(yi)))
        if len(pts) >= 2:
            pts = sorted(pts, key=lambda p: -p[1])
            lanes.append(pts)
    return lanes


def lanes_to_lines_txt(lanes: list[list[tuple[float, float]]]) -> str:
  lines = []
  for lane in lanes:
    parts = []
    for x, y in lane:
      parts.append(f"{x:.5f} {y:.5f}")
    if parts:
      lines.append(" ".join(parts))
  return "\n".join(lines) + ("\n" if lines else "")
