

# Migration Plan: Streamlit Tagging App → Self‑Hosted CVAT (Local)

## Goal
Replace the current Streamlit image tagging/annotation app with a smoother, purpose‑built local annotation UI (CVAT Community) while:
- Preserving the existing dataset folder structure.
- Migrating existing annotations.
- Keeping downstream consumers compatible (export back to our internal JSON format).
- Enabling new actions: crop ROI annotation, point adjustment via drag, and ML-assisted “guess points”.

---

## Scope (What we will support)
### Annotation types
- **Keypoints**: 5 landmarks per image
  - `top`, `bottom`, `left`, `right`, `center`
- **Crop ROI (optional but planned)**: rectangle/polygon region representing the desired crop

### ML assistance
- Offline **pre-annotation**: run our model to predict points → import into CVAT → human correct.

---

## 1) Local CVAT Setup (Community, self-hosted)
### Deliverables
- A local CVAT deployment using Docker, with persistent volumes.
- A small wrapper script to start/stop CVAT and a README snippet for engineers.

### Steps
1. Install prerequisites (Docker + Docker Compose).
2. Deploy CVAT locally following the official community installation guide.
3. Configure persistence:
   - Persist CVAT DB and media volumes (so tasks/labels survive restarts).
4. Configure dataset access:
   - Mount our local image root directory into the CVAT container (read-only preferred).

### Output
- `cvat/` folder (or dedicated repo section) containing:
  - Docker compose configuration (and optional override file)
  - `run_cvat_local.sh` (or equivalent)

---

## 2) Define the Annotation Schema (Labels)
 Skeleton label
- Create a single label: **`watch_landmarks`** with a skeleton of 5 named nodes:
  - `top`, `bottom`, `left`, `right`, `center`

---

## 3) Data Organization in CVAT (Tasks / Jobs)
We currently store images under a watch-centric folder structure (e.g., one folder per watch instance / shoot).

### Recommended structure
- **Task per watch folder**
  - Each task contains all images for that watch folder.
  - Benefits: mirrors how we review and how downstream data is grouped.

### Deliverables
- A small “task creator” script OR documented manual steps:
  - Create task
  - Upload/mount images for that watch folder
  - Apply label schema

---

## 4) Migrate Existing Annotations into CVAT
We already have internal JSON annotations (normalized keypoints).

### Deliverables
- `convert_internal_to_cvat.py` (one-time migration script)
  - Reads our internal JSON for each image.
  - Converts normalized coords → absolute pixel coords.
  - Produces a CVAT-importable annotation payload (matching chosen schema).
- `import_into_cvat.py` (optional)
  - Uses CVAT API to attach annotations to tasks (preferred for reproducibility).

### Validation
- Run migration on a small sample (e.g., 10–20 images across multiple watches).
- Visually verify:
  - Correct orientation (x increases right, y increases down).
  - Correct scaling and image-size consistency.
  - All 5 points land in expected locations.

---

## 5) Export from CVAT Back to Our Internal JSON
Even if CVAT is the UI, we keep our downstream pipeline unchanged.

### Deliverables
- `export_from_cvat.py`
  - Exports annotations for tasks (via CVAT API or UI export).
- `convert_cvat_to_internal.py`
  - Converts CVAT output → our internal JSON schema:
    - keypoints normalized to `[0, 1]` relative to image width/height
    - consistent naming and file placement

### Acceptance criteria
- Round-trip test passes:
  - internal → CVAT → internal yields equivalent points (within expected rounding tolerance).

---

## 6) Add ML-Assisted “Guess Points”
Start with the simplest, highest-ROI workflow:
### We won't implement this part this time, we should just leave a placeholder where we'll add predicted points the user will be able to edit. (edit points should be possible anyway) ###

---

## 7) Cropping Support
CVAT is an annotation tool; we should store cropping intent as annotation metadata.

### Plan
- Add a `crop_roi` label:
  - rectangle (preferred) or polygon
- Export crop ROI alongside keypoints.
- Apply cropping downstream in our preprocessing/training pipeline.

### Deliverables
- Updated schema
- Updated conversion scripts to include crop ROI

---

## 8) QA / Ergonomics (Make It Better Than Streamlit)
### Minimum usability checklist
- Hotkeys for navigation (next/prev).
- A clear “done/reviewed” workflow (use CVAT stages/tags/attributes).
- Enforce 5 points per image:
  - via skeleton schema OR via review checklist + script validation.

### Deliverables
- `validate_annotations.py`
  - Flags missing points, out-of-bounds points, or suspicious placements.

---
---

## Notes / Decisions Log
- Start with the simplest schema that unblocks round-trip (separate point labels), then upgrade to skeleton if needed.
- Keep downstream stable by always converting CVAT exports to our internal JSON.
- Prefer API-based import/export for reproducibility (UI export acceptable for early validation).