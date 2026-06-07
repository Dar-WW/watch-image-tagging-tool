# Watch-Domain Pretrain Corpus — Migration to Another Mac

This doc walks through resuming the [013-watch-domain-pretrain-design](../../FPJ-WatchId-POC/experiments/013-watch-domain-pretrain-design.md)
corpus build on a different Mac.

## TL;DR

| Asset | Where | Transport |
|---|---|---|
| Scripts (`yolo_split.py`, `face_classifier.py`, `process_scrape.py`, …) | this repo, branch `feat/watch-domain-pretrain-corpus` | git pull |
| Trained face classifier (`face_clf.joblib`, 22 KB) | `scripts/outputs/face_clf.joblib` in branch | git pull |
| Hand labels manifest (`labels_manifest.json`, 377 labels) | `scripts/outputs/labels_manifest.json` in branch | git pull |
| YOLO-OBB weights (`yolo_obb_best.pt`, 53 MB) | `s3://watchid-fpj-ml-data/pretrain-corpus/v1/yolo_obb_best.pt` | `aws s3 cp` |
| Raw scraped images (~736 MB, 7 refs) | `s3://watchid-fpj-ml-data/pretrain-corpus/v1/pretrain_*` | `aws s3 sync` |
| Derived dirs (`*_split/`, `*_dino/`) | not transferred — regenerate via `process_scrape.py` | recompute (~3-5 min) |

## Step-by-step on the new Mac

### 1. Pull the branch + sync submodules

```bash
cd ~/ww-repos/Kairos-Workspace
git submodule update --init --recursive

# Pull the latest agent-tools so the new ml-experiments skill is present
git submodule update --remote agent-tools

# Reinstall skills so ml-experiments lands in ~/.claude/skills/
./agent-tools/scripts/setup.sh

# Switch the tagging-tool submodule to the corpus branch
cd WatchMLProjects/watch-image-tagging-tool
git fetch origin
git checkout feat/watch-domain-pretrain-corpus
git pull
```

### 1b. Pull the 013 design spec from S3

The FPJ-WatchId-POC repo has `*.md` in `.gitignore` (experiments are
intentionally local-only), so the design spec for this work is
distributed via S3 rather than git:

```bash
aws s3 cp \
  s3://watchid-fpj-ml-data/pretrain-corpus/v1/experiments/013-watch-domain-pretrain-design.md \
  ~/ww-repos/Kairos-Workspace/WatchMLProjects/FPJ-WatchId-POC/experiments/
```

### 2. Set up the conda env

```bash
# Assumes miniforge / miniconda is installed and there is no fpj-watchid-poc env yet.
# Create the env. If it already exists from the FPJ-WatchId-POC setup, just install the extra deps below.
conda env create -f ../FPJ-WatchId-POC/environment.yml  # if not already
conda activate fpj-watchid-poc

# Scrape pipeline (selenium-based)
pip install selenium webdriver_manager requests

# YOLO-OBB detector
pip install ultralytics

# DINOv2 feature extractor + face classifier
pip install scikit-learn joblib timm
```

Make sure Google Chrome is installed (Selenium drives it via `webdriver_manager`).

### 3. Pull raw data + YOLO weights from S3

```bash
cd ~/ww-repos/Kairos-Workspace/WatchMLProjects/watch-image-tagging-tool

# YOLO weights → the same path the source Mac used
aws s3 cp s3://watchid-fpj-ml-data/pretrain-corpus/v1/yolo_obb_best.pt \
  ../FPJ-WatchId-POC/models/yolo_obb_best.pt

# Raw scrapes (~736 MB across 7 refs)
aws s3 sync s3://watchid-fpj-ml-data/pretrain-corpus/v1/scrapes/ \
  scripts/outputs/ \
  --exclude "*" --include "pretrain_*"
```

### 4. Regenerate YOLO + DINOv2 splits per ref

The filtered `*_split/` and `*_dino/` directories were intentionally NOT
transferred — they're symlink trees, and symlinks don't survive a rsync /
s3 sync cleanly. Recreate them on the new Mac in a few minutes per ref:

```bash
# example: Submariner
python scripts/process_scrape.py \
  --scrape-dir scripts/outputs/pretrain_sub_116610LN \
  --brand ROLEX --model sub --reference 116610LN

# example: Aquanaut
python scripts/process_scrape.py \
  --scrape-dir scripts/outputs/pretrain_aqua_5167-1A-001 \
  --brand PATEK --model aqua --reference 5167/1A-001
```

`process_scrape.py` defaults look for the YOLO weights at
`../FPJ-WatchId-POC/models/yolo_obb_best.pt` and the classifier at
`scripts/outputs/face_clf.joblib` — both already in place after step 3.

Each ref takes ~1-3 min on MPS (DINOv2 first-call also auto-downloads
~330 MB of timm weights from HuggingFace; cached for subsequent runs).

### 5. Optional — restore the labels_staging/ dirs

If you want to re-label, audit, or retrain the classifier, restore the
hand-labeled face/ and not_face/ symlink dirs from the manifest:

```bash
python scripts/restore_labels_from_manifest.py \
  --manifest scripts/outputs/labels_manifest.json \
  --outputs-root scripts/outputs \
  --out-dir scripts/outputs/labels_staging
```

Then either:

- Re-run training: `python scripts/face_classifier.py train --base-dir scripts/outputs/labels_staging`
- Add more labels: `python scripts/label_server.py scripts/outputs/labels_staging`
  (open http://127.0.0.1:8088 after sampling fresh images via `sample_for_labeling.py`)

## State of the corpus at handoff

Captured 2026-06-07. End-to-end yield = raw → YOLO-kept → DINO face-only.

| Ref | Raw | YOLO (~85%) | DINO face-only (~50% e2e) |
|---|---:|---:|---:|
| PATEK aqua 5167/1A-001 | 125 | 101 | 67 |
| ROLEX sub 116610LN | 958 | 793 | 456 |
| AP roak 15400ST | 582 | 501 | 296 |
| PATEK nchr 5980/1A-019 | 690 | 599 | 374 |
| **Sub-total (round 1)** | **2,355** | **1,994** | **1,193** |

Round-2 scrapes were **stopped mid-flight**. Partial data is on S3 but is
incomplete (~10-15 listings per ref vs the ~60-75 a full scrape produces):

| Ref | Partial raw | Status |
|---|---:|---|
| ROLEX dayt 116500LN | 80 | partial — resume via batch_download_images.py with same `-o` |
| OMEGA spdm 310.30.42.50.01.001 | 66 | partial — resume |
| ROLEX gmt 126710BLNR (Batman) | 83 | partial — resume |

The scraper's dedup index files (`_index_<BRAND>_<model>.jsonl` inside each
output dir) make `batch_download_images.py` idempotent — re-running the
same command with the same `-o` path picks up where it left off, skipping
already-downloaded listings.

## Resuming the corpus build

Round-2 resume commands (from `watch-image-tagging-tool/`):

```bash
# Daytona
python scripts/batch_download_images.py \
  'https://www.chrono24.com/search/index.htm?query=rolex+daytona+116500LN&dosearch=true' \
  --brand ROLEX --model dayt \
  -o scripts/outputs/pretrain_dayt_116500LN \
  --delay 3 --headless --try-all-sortorders

# Speedmaster
python scripts/batch_download_images.py \
  'https://www.chrono24.com/search/index.htm?query=omega+speedmaster+310.30.42.50.01.001&dosearch=true' \
  --brand OMEGA --model spdm \
  -o scripts/outputs/pretrain_spdm_31030 \
  --delay 3 --headless --try-all-sortorders

# GMT-Master II "Batman"
python scripts/batch_download_images.py \
  'https://www.chrono24.com/search/index.htm?query=rolex+gmt-master+ii+126710BLNR&dosearch=true' \
  --brand ROLEX --model gmt \
  -o scripts/outputs/pretrain_gmt_126710BLNR \
  --delay 3 --headless --try-all-sortorders
```

After each scrape finishes, run the post-processor:

```bash
python scripts/process_scrape.py \
  --scrape-dir scripts/outputs/pretrain_dayt_116500LN \
  --brand ROLEX --model dayt --reference 116500LN
```

## Scaling up — round 3+

To hit 013's ~30 K image target we need ~50-60 more refs. Add a ref via:

1. Pick a brand + model + reference (e.g., Rolex GMT-Master 116710BLNR Pepsi)
2. Scrape with `batch_download_images.py` (one ref per output dir)
3. Post-process with `process_scrape.py`
4. Outputs land at `scripts/outputs/<scrape-dir>_dino/dino_keep/`

Pretraining (015 / 016 in the experiment ledger) consumes
`scripts/outputs/pretrain_*_dino/dino_keep/` symlinks as the training set,
labeled by `(brand, model, reference)` from the per-ref manifest.

## Files at a glance

| Path | Purpose |
|---|---|
| `scripts/yolo_split.py` | Stage 1 filter — YOLO-OBB detects "is there a watch here" |
| `scripts/face_classifier.py {train,apply}` | Stage 2 filter — DINOv2 + sklearn LogReg face/not-face head |
| `scripts/sample_for_labeling.py` | Sample N images per source for hand-labeling |
| `scripts/label_server.py` | Local web labeler — `http://127.0.0.1:8088/` |
| `scripts/process_scrape.py` | Turnkey: YOLO → DINO → manifest in one command |
| `scripts/dump_labels_manifest.py` | Serialize labels_staging/ to JSON |
| `scripts/restore_labels_from_manifest.py` | Inverse — restore from JSON |
| `scripts/outputs/face_clf.joblib` | Trained binary face classifier (96.8 % CV) |
| `scripts/outputs/labels_manifest.json` | 377 hand labels (211 face / 166 not_face) |
