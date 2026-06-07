#!/usr/bin/env python3
"""One-command post-processor for a finished Chrono24 scrape.

Pipeline:
    1. YOLO-OBB watch detection split → <scrape>_split/{kept,rejected}
    2. DINOv2 face classifier → <scrape>_dino/{dino_keep,dino_drop}
    3. Manifest writer → <scrape>_manifest.json with per-listing stats

After this runs, the face-only training images live at:
    <scrape>_dino/dino_keep/<LISTING>/<image>.jpg

with a top-level manifest summarizing yield per listing.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=REPO_ROOT)
    if res.returncode != 0:
        raise SystemExit(f"step failed: {cmd}")


def count_links(d: Path) -> int:
    if not d.exists():
        return 0
    return sum(1 for _ in d.rglob("*") if _.is_symlink())


def build_manifest(scrape_dir: Path, split_dir: Path, dino_dir: Path,
                   brand: str, model: str, ref: str) -> dict:
    listings = sorted(p for p in scrape_dir.iterdir() if p.is_dir() and not p.name.startswith("_"))
    per_listing = []
    total_raw = total_yolo = total_dino = 0
    for L in listings:
        raw_count = sum(1 for p in L.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
        yolo_count = count_links(split_dir / "kept" / L.name)
        dino_count = count_links(dino_dir / "dino_keep" / L.name)
        per_listing.append({
            "listing": L.name,
            "raw": raw_count,
            "yolo_kept": yolo_count,
            "dino_kept": dino_count,
        })
        total_raw += raw_count
        total_yolo += yolo_count
        total_dino += dino_count
    return {
        "scrape_dir": str(scrape_dir),
        "brand": brand,
        "model": model,
        "reference": ref,
        "n_listings": len(listings),
        "n_raw": total_raw,
        "n_yolo_kept": total_yolo,
        "n_dino_kept": total_dino,
        "yolo_survival_pct": round(100 * total_yolo / max(total_raw, 1), 1),
        "dino_survival_pct": round(100 * total_dino / max(total_yolo, 1), 1),
        "end_to_end_pct": round(100 * total_dino / max(total_raw, 1), 1),
        "per_listing": per_listing,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scrape-dir", type=Path, required=True,
                    help="dir containing raw scraped listings (e.g., scripts/outputs/pretrain_dayt_116500LN)")
    ap.add_argument("--yolo-weights", type=Path,
                    default=Path("/Users/dhayun/ww-repos/Kairos-Workspace/WatchMLProjects/FPJ-WatchId-POC/models/yolo_obb_best.pt"))
    ap.add_argument("--face-clf", type=Path,
                    default=REPO_ROOT / "scripts/outputs/face_clf.joblib")
    ap.add_argument("--brand", required=True, help="e.g. ROLEX")
    ap.add_argument("--model", required=True, help="watch model code, e.g. dayt")
    ap.add_argument("--reference", required=True, help="ref number, e.g. 116500LN")
    ap.add_argument("--yolo-conf", type=float, default=0.25)
    ap.add_argument("--face-thresh", type=float, default=0.5)
    ap.add_argument("--device", default="mps")
    args = ap.parse_args()

    scrape = args.scrape_dir.resolve()
    if not scrape.exists():
        raise SystemExit(f"scrape dir not found: {scrape}")

    split_dir = scrape.parent / f"{scrape.name}_split"
    dino_dir = scrape.parent / f"{scrape.name}_dino"

    # Stage 1 — YOLO split
    print(f"\n=== Stage 1: YOLO split on {scrape} ===")
    run([
        sys.executable, "scripts/yolo_split.py",
        "--images-dir", str(scrape),
        "--weights", str(args.yolo_weights),
        "--out-dir", str(split_dir),
        "--conf", str(args.yolo_conf),
        "--device", args.device,
    ])

    # Stage 2 — DINOv2 face classifier
    print(f"\n=== Stage 2: DINOv2 face classifier on {split_dir}/kept ===")
    run([
        sys.executable, "scripts/face_classifier.py", "apply",
        "--model-in", str(args.face_clf),
        "--images-dir", str(split_dir / "kept"),
        "--out-dir", str(dino_dir),
        "--thresh", str(args.face_thresh),
        "--device", args.device,
    ])

    # Stage 3 — Manifest
    print(f"\n=== Stage 3: writing manifest ===")
    manifest = build_manifest(scrape, split_dir, dino_dir,
                              args.brand, args.model, args.reference)
    manifest_path = scrape.parent / f"{scrape.name}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"  → {manifest_path}")
    print(f"\n=== DONE ===")
    print(f"  brand:    {manifest['brand']}")
    print(f"  model:    {manifest['model']}")
    print(f"  ref:      {manifest['reference']}")
    print(f"  raw:      {manifest['n_raw']}")
    print(f"  YOLO:     {manifest['n_yolo_kept']:5d}  ({manifest['yolo_survival_pct']}%)")
    print(f"  DINO:     {manifest['n_dino_kept']:5d}  ({manifest['dino_survival_pct']}% of YOLO, {manifest['end_to_end_pct']}% e2e)")
    print(f"  face-only training dir → {dino_dir / 'dino_keep'}")


if __name__ == "__main__":
    main()
