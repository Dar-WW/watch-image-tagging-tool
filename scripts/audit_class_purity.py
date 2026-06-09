#!/usr/bin/env python3
"""Audit intra-class purity of the pretrain corpus.

Each scraped class (a `*_dino/dino_keep/` dir) is labeled by one intended
(brand, model, reference), but Chrono24 query results mix sub-references
(e.g. a "cartier tank" search returns Louis / Française / Must / Solo).
This tool quantifies that mixing from DINOv2 embeddings — no manual review —
and renders montages for the most-mixed classes so they can be eyeballed.

Impurity = 1 - mean cosine similarity of each image to its class centroid
(higher = more internal visual spread = more likely mixed references).
A KMeans silhouette is reported alongside as a multi-modality signal.

Outputs:
  <audit-dir>/purity_ranking.json   full ranking
  <audit-dir>/<rank>_<class>.png    montage for each flagged class
  <audit-dir>/index.html            browsable gallery of the flagged classes
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import timm
import torch
from PIL import Image, UnidentifiedImageError
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from timm.data import create_transform, resolve_data_config

MODEL_NAME = "vit_base_patch14_dinov2.lvd142m"


def load_model(device: str, img_size: int = 224):
    model = timm.create_model(MODEL_NAME, pretrained=True, num_classes=0,
                              dynamic_img_size=True)
    cfg = resolve_data_config({}, model=model)
    # Override DINOv2's 518px native input — for clustering, 224px embeddings
    # are plenty and ~5x faster on MPS.
    cfg["input_size"] = (3, img_size, img_size)
    cfg["crop_pct"] = 1.0
    transform = create_transform(**cfg, is_training=False)
    return model.to(device).eval(), transform


def collect(dino_keep: Path) -> list[Path]:
    return sorted(
        p for p in dino_keep.rglob("*")
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )


def embed(model, transform, paths: list[Path], device: str, batch: int = 32) -> np.ndarray:
    feats: list[np.ndarray] = []
    with torch.no_grad():
        for i in range(0, len(paths), batch):
            tensors, ok = [], []
            for p in paths[i : i + batch]:
                try:
                    tensors.append(transform(Image.open(p).convert("RGB")))
                    ok.append(True)
                except (UnidentifiedImageError, OSError):
                    ok.append(False)
            if not any(ok):
                continue
            out = model(torch.stack(tensors).to(device)).detach().float().cpu().numpy()
            feats.append(out)
    if not feats:
        return np.zeros((0, model.num_features), dtype=np.float32)
    x = np.concatenate(feats, axis=0)
    return x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-9)


def montage(paths: list[Path], labels: np.ndarray, out: Path, grid: int = 4, cell: int = 224) -> None:
    """Sample grid*grid images spread proportionally across clusters."""
    rng = random.Random(0)
    picks: list[Path] = []
    if labels is not None and len(set(labels)) > 1:
        by_cluster: dict[int, list[int]] = {}
        for idx, c in enumerate(labels):
            by_cluster.setdefault(int(c), []).append(idx)
        slots = grid * grid
        per = max(1, slots // len(by_cluster))
        for c, idxs in sorted(by_cluster.items()):
            picks += [paths[j] for j in rng.sample(idxs, min(per, len(idxs)))]
        picks = picks[:slots]
    else:
        picks = rng.sample(paths, min(grid * grid, len(paths)))
    canvas = Image.new("RGB", (grid * cell, grid * cell), (20, 24, 32))
    for k, p in enumerate(picks):
        try:
            im = Image.open(p).convert("RGB")
        except (UnidentifiedImageError, OSError):
            continue
        im.thumbnail((cell, cell))
        x = (k % grid) * cell + (cell - im.width) // 2
        y = (k // grid) * cell + (cell - im.height) // 2
        canvas.paste(im, (x, y))
    canvas.save(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outputs-root", type=Path, default=Path("scripts/outputs"))
    ap.add_argument("--audit-dir", type=Path, default=Path("scripts/outputs/_purity_audit"))
    ap.add_argument("--cap", type=int, default=100, help="max images/class to embed")
    ap.add_argument("--top", type=int, default=999, help="how many classes to render montages for")
    ap.add_argument("--img-size", type=int, default=224, help="embed resolution (224 fast, 518 native)")
    ap.add_argument("--cropped-root", type=Path, default=None,
                    help="if set, audit class-foldered crops here instead of the dino_keep trees")
    ap.add_argument("--device", default="mps")
    args = ap.parse_args()
    args.audit_dir.mkdir(parents=True, exist_ok=True)
    prog = args.audit_dir / "progress.log"

    def log(msg: str) -> None:
        print(msg, flush=True)
        with prog.open("a") as fh:
            fh.write(msg + "\n")

    prog.write_text("")
    if args.cropped_root:
        sources = [(d.name, d) for d in sorted(args.cropped_root.iterdir()) if d.is_dir()]
    else:
        sources = [(kp.parent.name.replace("pretrain_", "").replace("_dino", ""), kp)
                   for kp in sorted(args.outputs_root.glob("pretrain_*_dino/dino_keep"))]
    log(f"found {len(sources)} classes")
    model, transform = load_model(args.device, args.img_size)
    log(f"loaded {MODEL_NAME} @ {args.img_size}px on {args.device}")

    rng = random.Random(42)
    rows = []
    cache: dict[str, tuple[list[Path], np.ndarray]] = {}
    for cls, src in sources:
        allp = collect(src)
        if len(allp) < 10:
            print(f"  {cls}: only {len(allp)} imgs, skipping"); continue
        paths = rng.sample(allp, min(args.cap, len(allp)))
        emb = embed(model, transform, paths, args.device)
        if emb.shape[0] < 10:
            continue
        centroid = emb.mean(0); centroid /= (np.linalg.norm(centroid) + 1e-9)
        impurity = float(1.0 - (emb @ centroid).mean())
        sil, klabels = 0.0, None
        if emb.shape[0] >= 30:
            klabels = KMeans(n_clusters=3, n_init=5, random_state=0).fit_predict(emb)
            try:
                sil = float(silhouette_score(emb, klabels, metric="cosine"))
            except ValueError:
                sil = 0.0
        rows.append({"cls": cls, "n_total": len(allp), "n_sampled": len(paths),
                     "impurity": round(impurity, 4), "silhouette": round(sil, 4)})
        cache[cls] = (paths, klabels)
        log(f"  [{len(rows)}/{len(sources)}] {cls}: n={len(allp)} impurity={impurity:.3f} sil={sil:.3f}")

    rows.sort(key=lambda r: r["impurity"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    (args.audit_dir / "purity_ranking.json").write_text(json.dumps(rows, indent=2))

    flagged = rows[: args.top]
    html = ["<html><head><meta charset=utf-8><style>body{background:#0f172a;color:#e2e8f0;"
            "font-family:system-ui;padding:20px}h2{margin-top:32px}img{border:1px solid #334155}"
            "td{vertical-align:top;padding:8px}</style></head><body>",
            f"<h1>Class-purity audit — {len(flagged)} most-mixed classes</h1>",
            "<p>Impurity = internal visual spread (higher = more mixed references). "
            "Montage samples across sub-clusters.</p><table>"]
    for r in flagged:
        cls = r["cls"]
        paths, klabels = cache[cls]
        png = args.audit_dir / f"{r['rank']:02d}_{cls}.png"
        montage(paths, klabels, png)
        html.append(f"<tr><td><b>#{r['rank']} {cls}</b><br>n={r['n_total']}<br>"
                    f"impurity={r['impurity']}<br>silhouette={r['silhouette']}</td>"
                    f"<td><img src='{png.name}' width=700></td></tr>")
    html.append("</table></body></html>")
    (args.audit_dir / "index.html").write_text("\n".join(html))

    print("\n=== TOP MIXED CLASSES (by impurity) ===")
    for r in flagged:
        print(f"  #{r['rank']:>2} {r['cls']:<14} n={r['n_total']:>4} "
              f"impurity={r['impurity']:.3f} silhouette={r['silhouette']:.3f}")
    print(f"\nmontages + index.html in {args.audit_dir}")


if __name__ == "__main__":
    main()
