#!/usr/bin/env python3
"""Run YOLO-OBB watch-face detection on a scraped image dir and split into
kept/ (detected) vs rejected/ (no detection).

Uses symlinks (no copies) so disk usage stays flat. Writes a per-image
JSONL log with confidence + box.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ultralytics import YOLO


def iter_images(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            yield p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images-dir", required=True, type=Path)
    ap.add_argument("--weights", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--device", default="mps")
    args = ap.parse_args()

    images_dir: Path = args.images_dir.resolve()
    out_dir: Path = args.out_dir.resolve()
    kept_dir = out_dir / "kept"
    rejected_dir = out_dir / "rejected"
    kept_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(args.weights))
    print(f"loaded weights={args.weights} task={model.task} names={model.names}")

    log_path = out_dir / "yolo_split.jsonl"
    n_kept = 0
    n_rejected = 0
    images = list(iter_images(images_dir))
    print(f"found {len(images)} images under {images_dir}")

    with log_path.open("w") as log_f:
        for i, img_path in enumerate(images, 1):
            try:
                results = model.predict(
                    source=str(img_path),
                    conf=args.conf,
                    device=args.device,
                    verbose=False,
                )
                r = results[0]
            except (ValueError, RuntimeError) as exc:
                print(f"  skip unreadable: {img_path.name} ({exc})")
                log_f.write(
                    json.dumps({"image": str(img_path.relative_to(images_dir)), "detected": False, "top_conf": 0.0, "n_detections": 0, "error": str(exc)})
                    + "\n"
                )
                n_rejected += 1
                continue
            obb = getattr(r, "obb", None)
            if obb is not None and len(obb) > 0:
                confs = obb.conf.cpu().tolist() if obb.conf is not None else []
                top_conf = max(confs) if confs else 0.0
                detected = top_conf >= args.conf
            else:
                boxes = getattr(r, "boxes", None)
                confs = boxes.conf.cpu().tolist() if boxes is not None and boxes.conf is not None else []
                top_conf = max(confs) if confs else 0.0
                detected = top_conf >= args.conf

            rel = img_path.relative_to(images_dir)
            target_dir = (kept_dir if detected else rejected_dir) / rel.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            link = target_dir / img_path.name
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(img_path)

            log_f.write(
                json.dumps(
                    {
                        "image": str(rel),
                        "detected": detected,
                        "top_conf": top_conf,
                        "n_detections": len(confs),
                    }
                )
                + "\n"
            )

            if detected:
                n_kept += 1
            else:
                n_rejected += 1

            if i % 25 == 0 or i == len(images):
                print(f"  [{i}/{len(images)}] kept={n_kept} rejected={n_rejected}")

    print(f"\nDONE  kept={n_kept}  rejected={n_rejected}  total={len(images)}")
    print(f"  kept   → {kept_dir}")
    print(f"  reject → {rejected_dir}")
    print(f"  log    → {log_path}")


if __name__ == "__main__":
    main()
