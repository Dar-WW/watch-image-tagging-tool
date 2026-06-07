#!/usr/bin/env python3
"""Reconstruct labels_staging/{face,not_face,skipped,unlabeled} from the
portable JSON manifest produced by dump_labels_manifest.py.

The manifest stores image paths relative to scripts/outputs/. The raw
scrape data (`pretrain_*/`) must already exist at that root — otherwise
we'd be re-creating symlinks pointing at nothing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def restore_class(out_dir: Path, outputs_root: Path, rel_paths: list[str]) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    made = 0
    for rel in rel_paths:
        target = (outputs_root / rel).resolve()
        if not target.exists():
            missing.append(rel)
            continue
        link = out_dir / f"{rel.replace('/', '__')}"
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)
        made += 1
    if missing:
        print(f"  WARN: {len(missing)} target files missing under {outputs_root} — skipped")
        for r in missing[:5]:
            print(f"    {r}")
        if len(missing) > 5:
            print(f"    ... and {len(missing) - 5} more")
    return made


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--outputs-root", type=Path, default=Path("scripts/outputs"))
    ap.add_argument("--out-dir", type=Path, default=Path("scripts/outputs/labels_staging"))
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    print(f"manifest generated_at: {manifest.get('generated_at')}")
    print(f"counts: {manifest.get('counts')}")

    outputs_root = args.outputs_root.resolve()
    for cls in ("face", "not_face", "skipped", "unlabeled"):
        n = restore_class(args.out_dir / cls, outputs_root, manifest.get(cls, []))
        print(f"  {cls}: restored {n} symlinks under {args.out_dir / cls}")


if __name__ == "__main__":
    main()
