#!/usr/bin/env python3
"""Dump the hand-labeled face/not_face/skipped sets to a portable JSON manifest.

The labels_staging/ dirs hold symlinks pointing at original scraped images.
Symlinks don't survive across machines, but the *relative image path* does.
This script writes a manifest mapping each label class to a list of relative
paths, so a new machine can reconstruct the labeling dirs from the same
underlying scrape data.

Inverse op: `restore_labels_from_manifest.py` reads the manifest and
re-creates the symlinks under labels_staging/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

OUTPUTS_PREFIX = "scripts/outputs/"


def normalize(symlink_path: Path, outputs_root: Path) -> str:
    """Return a path relative to scripts/outputs/ pointing at the real file."""
    real = symlink_path.resolve()
    try:
        return str(real.relative_to(outputs_root.resolve()))
    except ValueError:
        # Symlink points outside outputs/ — keep absolute as last resort
        return str(real)


def collect(label_dir: Path, outputs_root: Path) -> list[str]:
    out: list[str] = []
    if not label_dir.exists():
        return out
    for p in sorted(label_dir.iterdir()):
        if p.name.startswith("."):
            continue
        out.append(normalize(p, outputs_root))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--staging-dir",
        type=Path,
        default=Path("scripts/outputs/labels_staging"),
    )
    ap.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("scripts/outputs"),
        help="Used to make paths relative; should be the parent of the pretrain_* scrape dirs",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("scripts/outputs/labels_manifest.json"),
    )
    args = ap.parse_args()

    face = collect(args.staging_dir / "face", args.outputs_root)
    not_face = collect(args.staging_dir / "not_face", args.outputs_root)
    skipped = collect(args.staging_dir / "skipped", args.outputs_root)
    unlabeled = collect(args.staging_dir / "unlabeled", args.outputs_root)

    manifest = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "outputs_root": OUTPUTS_PREFIX,
        "counts": {
            "face": len(face),
            "not_face": len(not_face),
            "skipped": len(skipped),
            "unlabeled": len(unlabeled),
        },
        "face": face,
        "not_face": not_face,
        "skipped": skipped,
        "unlabeled": unlabeled,
    }
    args.out.write_text(json.dumps(manifest, indent=2))
    print(f"wrote {args.out}")
    print(f"  face: {len(face)}   not_face: {len(not_face)}   skipped: {len(skipped)}   unlabeled: {len(unlabeled)}")


if __name__ == "__main__":
    main()
