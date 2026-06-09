#!/usr/bin/env python3
"""Crop each kept face image to its YOLO-OBB watch box (scale/framing normalization).

The scraped corpus images are full seller photos — the watch occupies anywhere
from 10% to 90% of the frame, off-center, with wrist/box/backdrop context. Feeding
those to the 015 classification pretext invites background/framing shortcuts and a
v6(aligned)-vs-scraped(loose) shortcut. Cropping to the detection box makes the watch
watch-dominant and consistent with v6, WITHOUT rotational registration (orientation is
left to light aug + downstream re-alignment — see exp 013).

YOLO boxes were not persisted by yolo_split, so we re-detect (YOLO is ~10x lighter
than DINOv2). Uses the axis-aligned envelope of the top-confidence OBB + margin.

Output: <out-root>/<class_key>/<listing>__<file>.jpg  — a class-foldered image tree
that doubles as the materialized 015 dataset layout (scraped portion; v6 added at upload).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from ultralytics import YOLO

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_WEIGHTS = Path(__file__).resolve().parents[2] / "FPJ-WatchId-POC/models/yolo_obb_best.pt"


def class_key(manifest: Path) -> str:
    m = json.loads(manifest.read_text())
    return f"{m['brand']}_{m['model']}_{m['reference']}".replace("/", "-").replace(" ", "")


def crop_box(im: Image.Image, box: tuple[float, float, float, float], margin: float) -> Image.Image:
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    mx, my = bw * margin, bh * margin
    L = max(0, int(x1 - mx)); T = max(0, int(y1 - my))
    R = min(im.width, int(x2 + mx)); B = min(im.height, int(y2 + my))
    if R <= L or B <= T:
        return im
    return im.crop((L, T, R, B))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outputs-root", type=Path, default=Path("scripts/outputs"))
    ap.add_argument("--out-root", type=Path, default=Path("scripts/outputs/_cropped"))
    ap.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    ap.add_argument("--margin", type=float, default=0.15, help="box expansion fraction")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--max-side", type=int, default=768, help="cap long side of saved crop")
    ap.add_argument("--device", default="mps")
    args = ap.parse_args()
    args.out_root.mkdir(parents=True, exist_ok=True)
    prog = args.out_root / "crop_progress.log"
    prog.write_text("")

    def log(msg: str) -> None:
        print(msg, flush=True)
        with prog.open("a") as fh:
            fh.write(msg + "\n")

    keeps = sorted(args.outputs_root.glob("pretrain_*_dino/dino_keep"))
    model = YOLO(str(args.weights))
    log(f"loaded {args.weights.name} task={model.task} | {len(keeps)} classes")

    grand_in = grand_out = grand_nobox = 0
    for kp in keeps:
        man = Path(str(kp.parent).replace("_dino", "") + "_manifest.json")
        if not man.exists():
            log(f"  WARN no manifest for {kp.parent.name}, skipping"); continue
        key = class_key(man)
        dest = args.out_root / key
        dest.mkdir(parents=True, exist_ok=True)
        imgs = [p for p in kp.rglob("*") if p.suffix.lower() in IMG_EXT]
        n_out = n_nobox = 0
        for p in imgs:
            try:
                im = Image.open(p).convert("RGB")
            except (UnidentifiedImageError, OSError):
                continue
            try:
                r = model.predict(source=str(p), conf=args.conf, device=args.device, verbose=False)[0]
            except (ValueError, RuntimeError):
                r = None
            box = None
            obb = getattr(r, "obb", None) if r is not None else None
            if obb is not None and obb.conf is not None and len(obb) > 0:
                top = int(obb.conf.argmax())
                xy = obb.xyxy[top].cpu().tolist()  # axis-aligned envelope of the OBB
                box = tuple(xy)
            if box is None:
                n_nobox += 1
                out = im  # keep full image rather than drop — it passed YOLO once
            else:
                out = crop_box(im, box, args.margin)
            if max(out.size) > args.max_side:
                out.thumbnail((args.max_side, args.max_side))
            name = f"{p.parent.name}__{p.name}".replace("/", "_")
            out.convert("RGB").save(dest / name, quality=92)
            n_out += 1
        grand_in += len(imgs); grand_out += n_out; grand_nobox += n_nobox
        log(f"  {key}: {len(imgs)} → {n_out} cropped ({n_nobox} no-box kept full)")

    log(f"\nDONE  {grand_out}/{grand_in} cropped into {args.out_root}  ({grand_nobox} no-box)")


if __name__ == "__main__":
    main()
