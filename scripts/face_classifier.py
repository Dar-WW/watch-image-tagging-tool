#!/usr/bin/env python3
"""DINOv2-based binary face/not-face classifier.

Two subcommands:

    train   — read face/ and not_face/ symlink dirs, extract DINOv2 features,
              fit sklearn LogReg, report stratified 5-fold CV accuracy, save
              model + label_index.json

    apply   — load saved model, score every image under --images-dir,
              symlink-split into dino_keep/ and dino_drop/, write per-image
              probabilities to dino_split.jsonl

The DINOv2 model used is timm's `vit_base_patch14_dinov2.lvd142m` (768-d CLS).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import torch
from PIL import Image, UnidentifiedImageError

import timm
from timm.data import resolve_data_config, create_transform

from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler


MODEL_NAME = "vit_base_patch14_dinov2.lvd142m"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def iter_images(root: Path) -> Iterable[Path]:
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            yield p


def load_dinov2(device: str) -> tuple[torch.nn.Module, "callable"]:
    print(f"loading timm {MODEL_NAME} on {device}")
    model = timm.create_model(MODEL_NAME, pretrained=True, num_classes=0)
    cfg = resolve_data_config({}, model=model)
    transform = create_transform(**cfg, is_training=False)
    model = model.to(device).eval()
    return model, transform


def encode(model, transform, paths: list[Path], device: str, batch: int = 32) -> np.ndarray:
    feats: list[np.ndarray] = []
    n = len(paths)
    with torch.no_grad():
        for i in range(0, n, batch):
            chunk = paths[i : i + batch]
            tensors = []
            for p in chunk:
                try:
                    img = Image.open(p).convert("RGB")
                except (UnidentifiedImageError, OSError) as exc:
                    print(f"  skip unreadable: {p.name} ({exc})", file=sys.stderr)
                    tensors.append(None)
                    continue
                tensors.append(transform(img))
            ok_idx = [j for j, t in enumerate(tensors) if t is not None]
            if not ok_idx:
                # Skip the whole batch's contributions; the caller filters by valid_mask later.
                feats.extend([np.zeros(model.num_features, dtype=np.float32)] * len(chunk))
                continue
            stacked = torch.stack([tensors[j] for j in ok_idx]).to(device)
            out = model(stacked).detach().float().cpu().numpy()
            batch_feats = np.zeros((len(chunk), out.shape[1]), dtype=np.float32)
            for slot, j in enumerate(ok_idx):
                batch_feats[j] = out[slot]
            feats.append(batch_feats)
            if (i // batch) % 4 == 0:
                print(f"    encoded {min(i + batch, n)}/{n}")
    if not feats:
        return np.zeros((0, model.num_features), dtype=np.float32)
    return np.concatenate(feats, axis=0)


def cmd_train(args: argparse.Namespace) -> None:
    base = args.base_dir.resolve()
    face_dir = base / "face"
    not_face_dir = base / "not_face"
    face_paths = list(iter_images(face_dir))
    not_face_paths = list(iter_images(not_face_dir))
    print(f"face: {len(face_paths)}   not_face: {len(not_face_paths)}")
    if len(face_paths) < 20 or len(not_face_paths) < 20:
        raise SystemExit("need at least 20 examples per class")

    device = args.device
    model, transform = load_dinov2(device)

    print("encoding face/ ...")
    X_face = encode(model, transform, face_paths, device, args.batch)
    print("encoding not_face/ ...")
    X_not = encode(model, transform, not_face_paths, device, args.batch)

    X = np.concatenate([X_face, X_not], axis=0)
    y = np.concatenate(
        [np.ones(len(face_paths), dtype=np.int64), np.zeros(len(not_face_paths), dtype=np.int64)],
        axis=0,
    )
    print(f"feature matrix: X={X.shape} y={y.shape}")

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    clf = LogisticRegression(max_iter=2000, class_weight="balanced", C=1.0)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(clf, Xs, y, cv=cv, scoring="accuracy")
    print(f"\nstratified 5-fold CV accuracy: mean={scores.mean():.4f}  std={scores.std():.4f}")
    for i, s in enumerate(scores):
        print(f"  fold {i + 1}: {s:.4f}")

    clf.fit(Xs, y)
    train_acc = clf.score(Xs, y)
    print(f"train accuracy (full set): {train_acc:.4f}")

    out_path = args.model_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"scaler": scaler, "clf": clf, "model_name": MODEL_NAME}, out_path)
    print(f"\nsaved: {out_path}")


def cmd_apply(args: argparse.Namespace) -> None:
    bundle = joblib.load(args.model_in)
    scaler = bundle["scaler"]
    clf = bundle["clf"]
    print(f"loaded classifier from {args.model_in}")

    device = args.device
    model, transform = load_dinov2(device)

    images_dir = args.images_dir.resolve()
    paths = list(iter_images(images_dir))
    print(f"scoring {len(paths)} images under {images_dir}")
    feats = encode(model, transform, paths, device, args.batch)
    Xs = scaler.transform(feats)
    probs = clf.predict_proba(Xs)[:, 1]  # P(face=1)

    out_dir = args.out_dir.resolve()
    keep_dir = out_dir / "dino_keep"
    drop_dir = out_dir / "dino_drop"
    keep_dir.mkdir(parents=True, exist_ok=True)
    drop_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "dino_split.jsonl"

    n_keep = n_drop = 0
    with log_path.open("w") as f:
        for p, prob in zip(paths, probs):
            keep = prob >= args.thresh
            rel = p.relative_to(images_dir)
            target_dir = (keep_dir if keep else drop_dir) / rel.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            link = target_dir / p.name
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(p.resolve())
            f.write(json.dumps({"image": str(rel), "p_face": float(prob), "keep": bool(keep)}) + "\n")
            if keep:
                n_keep += 1
            else:
                n_drop += 1
    print(f"\nDONE  keep={n_keep}  drop={n_drop}  total={len(paths)}")
    print(f"  keep → {keep_dir}")
    print(f"  drop → {drop_dir}")
    print(f"  log  → {log_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("train")
    t.add_argument("--base-dir", type=Path, required=True,
                   help="dir containing face/ and not_face/ subdirs")
    t.add_argument("--model-out", type=Path,
                   default=Path("scripts/outputs/face_clf.joblib"))
    t.add_argument("--device", default="mps")
    t.add_argument("--batch", type=int, default=32)
    t.set_defaults(func=cmd_train)

    a = sub.add_parser("apply")
    a.add_argument("--model-in", type=Path, required=True)
    a.add_argument("--images-dir", type=Path, required=True)
    a.add_argument("--out-dir", type=Path, required=True)
    a.add_argument("--thresh", type=float, default=0.5)
    a.add_argument("--device", default="mps")
    a.add_argument("--batch", type=int, default=32)
    a.set_defaults(func=cmd_apply)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
