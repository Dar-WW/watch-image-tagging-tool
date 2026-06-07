#!/usr/bin/env python3
"""Sample N images per source dir into a flat unlabeled/ dir for hand-labeling.

Creates:
    <out-dir>/face/        (empty — drag face shots here)
    <out-dir>/not_face/    (empty — drag non-face shots here)
    <out-dir>/unlabeled/   (N samples per source, all flat — drag from here)

Use symlinks (no copies). Filenames are prefixed with the source dir's name
so collisions across sources are impossible.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path


def collect_images(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--src",
        nargs="+",
        required=True,
        type=Path,
        help="One or more YOLO-kept source dirs (e.g., scripts/outputs/*_split/kept)",
    )
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--per-src", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out_dir: Path = args.out_dir.resolve()
    unlabeled = out_dir / "unlabeled"
    face = out_dir / "face"
    not_face = out_dir / "not_face"
    for d in (unlabeled, face, not_face):
        d.mkdir(parents=True, exist_ok=True)

    total = 0
    for src in args.src:
        src = src.resolve()
        all_imgs = collect_images(src)
        if not all_imgs:
            print(f"WARN: no images under {src}")
            continue
        picked = rng.sample(all_imgs, min(args.per_src, len(all_imgs)))
        # Use the source dir's parent name to uniquify (e.g., pretrain_sub_116610LN_split)
        prefix = src.parent.name
        for p in picked:
            # Resolve through symlinks so we always point at the original image
            real = p.resolve()
            link_name = f"{prefix}__{p.parent.name}__{p.name}"
            link = unlabeled / link_name
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(real)
            total += 1
        print(f"  {src.name}: sampled {len(picked)} / {len(all_imgs)}")
    print(f"\nDONE  {total} images linked into {unlabeled}")
    print(f"  Drag into:")
    print(f"    {face}")
    print(f"    {not_face}")


if __name__ == "__main__":
    main()
