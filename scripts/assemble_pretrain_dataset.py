#!/usr/bin/env python3
"""Assemble the watch-domain pretrain corpus (015 input) into a training manifest.

Combines two sources into one class-labeled image manifest:
  1. Scraped classes — every `scripts/outputs/pretrain_*_dino/dino_keep/` tree,
     labeled (brand, model, reference) from the per-ref `*_manifest.json`.
  2. v6 aligned families — `s3://.../datasets/watchid_manalign_v6/images/`,
     labeled by the `{BRAND}_{model}` instance prefix (e.g. FPJ_el, PATEK_nab).

Class key = brand_model_reference (scraped) / brand_model (v6). Near-twins
(e.g. ROLEX_sub_116610LN vs 116610LV) stay distinct on purpose — robustness
to within-family reference noise is a training-time concern (label smoothing
+ auxiliary brand/family heads per exp 013), NOT a label-collapse here.

Default = dry run: writes the manifest + class histogram, uploads nothing.
`--materialize` is where the S3 dataset copy will live (post-review, gated).
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from pathlib import Path

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
V6_S3 = "s3://watchid-fpj-ml-data/datasets/watchid_manalign_v6/images/"


def scraped_classes(outputs_root: Path, cropped_root: Path | None = None,
                    excl: set[str] | None = None) -> dict[str, dict]:
    """Scraped classes labeled from the per-ref manifests. If cropped_root is set,
    take images from the class-foldered crop tree (dropping anything in excl)
    instead of the raw dino_keep symlinks."""
    excl = excl or set()
    classes: dict[str, dict] = {}
    for keep in sorted(outputs_root.glob("pretrain_*_dino/dino_keep")):
        man = Path(str(keep.parent).replace("_dino", "") + "_manifest.json")
        if not man.exists():
            print(f"  WARN no manifest for {keep.parent.name}, skipping")
            continue
        m = json.loads(man.read_text())
        key = f"{m['brand']}_{m['model']}_{m['reference']}".replace("/", "-").replace(" ", "")
        if cropped_root is not None:
            d = cropped_root / key
            imgs = [str(p) for p in sorted(d.glob("*"))
                    if p.suffix.lower() in IMG_EXT and f"{key}/{p.name}" not in excl] if d.is_dir() else []
            src = "scraped_cropped"
        else:
            imgs = [str(p) for p in keep.rglob("*") if p.suffix.lower() in IMG_EXT]
            src = "scraped"
        classes[key] = {"brand": m["brand"], "model": m["model"], "reference": m["reference"],
                        "source": src, "n_images": len(imgs), "images": imgs}
    return classes


def v6_classes() -> dict[str, dict]:
    """List v6 image keys from S3 and group by BRAND_model family prefix."""
    out = subprocess.run(["aws", "s3", "ls", V6_S3, "--recursive"],
                         capture_output=True, text=True)
    fams: dict[str, list[str]] = defaultdict(list)
    for line in out.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        key = parts[-1]
        if Path(key).suffix.lower() not in IMG_EXT:
            continue
        watch_id = Path(key).parent.name           # e.g. FPJ_el_001
        fam = "_".join(watch_id.split("_")[:2])     # FPJ_el
        fams[fam].append("s3://watchid-fpj-ml-data/" + key)
    classes = {}
    for fam, imgs in fams.items():
        brand, _, model = fam.partition("_")
        classes[fam] = {"brand": brand, "model": model, "reference": model,
                        "source": "v6_aligned", "n_images": len(imgs), "images": imgs}
    return classes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outputs-root", type=Path, default=Path("scripts/outputs"))
    ap.add_argument("--out", type=Path, default=Path("scripts/outputs/_pretrain_v1_manifest.json"))
    ap.add_argument("--min-floor", type=int, default=20, help="drop classes below N images (013)")
    ap.add_argument("--cap", type=int, default=500, help="per-epoch sampling cap (recorded, not pruned)")
    ap.add_argument("--no-v6", action="store_true", help="skip the S3 v6 listing")
    ap.add_argument("--cropped-root", type=Path, default=None,
                    help="source scraped images from this crop tree instead of dino_keep")
    ap.add_argument("--exclusions", type=Path, default=None,
                    help="JSON list of <class>/<file> to drop (from review_server)")
    args = ap.parse_args()

    excl: set[str] = set()
    if args.exclusions and args.exclusions.exists():
        excl = set(json.loads(args.exclusions.read_text()))
        print(f"loaded {len(excl)} exclusions from {args.exclusions}")
    classes = scraped_classes(args.outputs_root, args.cropped_root, excl)
    n_scraped = len(classes)
    if not args.no_v6:
        classes.update(v6_classes())

    kept = {k: v for k, v in classes.items() if v["n_images"] >= args.min_floor}
    dropped = {k: v["n_images"] for k, v in classes.items() if v["n_images"] < args.min_floor}

    total_imgs = sum(v["n_images"] for v in kept.values())
    capped_imgs = sum(min(v["n_images"], args.cap) for v in kept.values())
    manifest = {"cap_per_class": args.cap, "min_floor": args.min_floor,
                "n_classes": len(kept), "n_images_raw": total_imgs,
                "n_images_capped": capped_imgs, "classes": kept}
    args.out.write_text(json.dumps(manifest, indent=2))

    rows = sorted(kept.items(), key=lambda kv: kv[1]["n_images"], reverse=True)
    print(f"\n=== PRETRAIN CORPUS MANIFEST (015 input) ===")
    print(f"classes: {len(kept)}  ({n_scraped} scraped + {len(kept)-n_scraped} v6)")
    print(f"images: {total_imgs} raw  /  {capped_imgs} after {args.cap}/class cap")
    if dropped:
        print(f"dropped below floor({args.min_floor}): {dropped}")
    print(f"\n{'class':<34}{'src':<10}{'n':>6}{'capped':>8}")
    for k, v in rows:
        print(f"{k:<34}{v['source']:<10}{v['n_images']:>6}{min(v['n_images'],args.cap):>8}")
    print(f"\nmanifest → {args.out}")
    print("dry run — no images copied/uploaded. Re-run with --materialize after review to stage to S3.")


if __name__ == "__main__":
    main()
