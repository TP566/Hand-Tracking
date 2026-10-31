"""Downscale large Domain videos once so playback stays cheap.

Decoding a 4K/60 fps clip every frame costs more than the rest of the pipeline
combined, so videos bigger than the camera output (or faster than ``max_fps``)
are converted once into a cache folder and reused on later runs.
"""

import os
from pathlib import Path

import cv2


def _target_size(w: int, h: int, width: int, height: int) -> tuple[int, int]:
    # Scale to cover width x height (playback centre-crops), keeping even dimensions.
    scale = max(width / w, height / h)
    return max(2, round(w * scale / 2) * 2), max(2, round(h * scale / 2) * 2)


def prepare(path: Path, width: int, height: int, cache_dir: Path, max_fps: float = 30.0) -> Path:
    """Return a playback-friendly version of ``path``, converting it on first use."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise SystemExit(f"Cannot open video: {path}")
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out_w, out_h = _target_size(w, h, width, height)
    out_fps = min(fps, max_fps)
    if (out_w >= w and out_h >= h) and fps <= max_fps + 0.5:
        cap.release()
        return path

    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{path.stem}_{out_w}x{out_h}_{round(out_fps)}fps.mp4"
    if target.exists() and target.stat().st_mtime >= path.stat().st_mtime:
        cap.release()
        return target

    print(f"Optimising '{path.name}' ({w}x{h} @ {fps:.0f} fps -> {out_w}x{out_h} @ {out_fps:.0f} fps), first run only...")
    tmp = target.with_name(target.stem + ".tmp.mp4")
    writer = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), out_fps, (out_w, out_h))
    written, index, last_pct = 0, 0, -1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        # Keep the frames that land on the output frame grid (e.g. every 2nd for 60 -> 30 fps).
        if int(index * out_fps / fps) >= written:
            writer.write(cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA))
            written += 1
        index += 1
        pct = index * 100 // max(1, total)
        if pct // 10 != last_pct // 10:
            print(f"  {pct}%")
            last_pct = pct
    writer.release()
    cap.release()
    os.replace(tmp, target)
    return target
