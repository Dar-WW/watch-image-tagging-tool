# Label Studio Migration

This directory contains tools for migrating watch image annotation data to and from Label Studio.

## Quick Start

### 1. Start Label Studio

```bash
cd labelstudio
docker-compose up -d
```

Access the UI at http://localhost:8200

### 2. Create Admin User (First Time Only)

**Option A: Via Web UI (Recommended)**

1. Go to http://localhost:8200
2. Click "Sign up" on the login page
3. Fill in your email, password, and username
4. Complete the signup process

**Option B: Via Command Line**

```bash
docker-compose exec label-studio label-studio user --username admin --password YOUR_PASSWORD
```

Note: The command-line option doesn't support setting an email address directly.

### 3. Create a Project

1. Log in to Label Studio at http://localhost:8200
2. Click "Create Project"
3. Name your project (e.g., "Watch Keypoint Annotation")
4. Go to "Labeling Setup" tab
5. Choose "Custom template"
6. Paste the contents of `labeling_config.xml`
7. Click "Save"

### 3a. Configure Local File Storage

To enable local file serving:

1. Go to your project
2. Click "Settings" → "Cloud Storage"
3. Click "Add Source Storage"
4. Choose "Local Files"
5. Configure:
   - **Storage Title**: "Local Images"
   - **Absolute local path**: `/label-studio/media/images`
   - **File Filter Regex**: `.*\.jpg$` (or leave empty for all files)
   - Check "Treat every bucket object as a source file"
6. Click "Add Storage"
7. Click "Sync Storage" to load the images

### 4. Convert and Import Existing Annotations

```bash
# Convert internal annotations to Label Studio format
python convert_to_labelstudio.py \
    --input-dir ../alignment_labels \
    --output tasks.json \
    --image-base-url "/data/local-files/?d=images/"

# Import tasks into Label Studio via UI:
# 1. Go to your project
# 2. Click "Import"
# 3. Upload tasks.json
```

### 5. Export Annotations Back to Internal Format

```bash
# Export from Label Studio UI:
# 1. Go to your project
# 2. Click "Export"
# 3. Choose JSON format
# 4. Download the export file

# Convert back to internal format
python export_from_labelstudio.py \
    --input export.json \
    --output-dir ../alignment_labels \
    --merge  # Use --merge to update existing files
```

## Tools

### `convert_to_labelstudio.py`

Converts internal annotation format to Label Studio tasks with pre-annotations.

```bash
python convert_to_labelstudio.py --help
```

Options:
- `--input-dir`: Directory containing internal annotation JSON files
- `--output`: Output file for Label Studio tasks
- `--image-base-url`: Base URL for images in Label Studio

### `export_from_labelstudio.py`

Exports Label Studio annotations back to internal format.

```bash
python export_from_labelstudio.py --help
```

Options:
- `--input`: Label Studio export JSON file
- `--output-dir`: Output directory for internal annotation files
- `--merge`: Merge with existing annotations instead of overwriting

### `validate_annotations.py`

Validates annotation data for completeness and correctness.

```bash
# Validate internal annotations
python validate_annotations.py --input-dir ../alignment_labels --images-dir ../downloaded_images

# Validate Label Studio export
python validate_annotations.py --labelstudio-export export.json
```

Validation checks:
- All 5 keypoints exist (top, bottom, left, right, center)
- Keypoint coordinates are within [0, 1] bounds
- Crop ROI is within image bounds and non-empty
- No duplicate keypoint labels
- Image files are accessible

### `ml_predictions.py`

Entry point for ML-assisted pre-annotation (scaffolding for future use).

```bash
# Generate dummy predictions (placeholder for real ML model)
python ml_predictions.py generate \
    --images-dir ../downloaded_images \
    --output predictions.json

# Add predictions to existing tasks
python ml_predictions.py add-predictions \
    --tasks tasks.json \
    --predictions predictions.json \
    --output tasks_with_predictions.json
```

## Data Formats

### Internal Format

Each watch folder has a JSON file in `alignment_labels/`:

```json
{
  "PATEK_nab_001_01": {
    "image_size": [2046, 1720],
    "coords_norm": {
      "top": [0.232, 0.516],
      "left": [0.487, 0.819],
      "right": [0.486, 0.214],
      "bottom": [0.745, 0.519],
      "center": [0.488, 0.517]
    },
    "original_image_size": [2046, 2046],
    "crop_bbox": [0, 171, 2046, 1891],
    "full_image_name": "PATEK_nab_001_01_face_q3"
  }
}
```

### Label Studio Format

Tasks with pre-annotations:

```json
{
  "data": {
    "image": "/data/local-files/?d=PATEK_nab_001/PATEK_nab_001_01_face_q3.jpg",
    "image_key": "PATEK_nab_001_01"
  },
  "predictions": [{
    "result": [
      {
        "from_name": "keypoints",
        "to_name": "image",
        "type": "keypointlabels",
        "value": {
          "x": 23.2,
          "y": 51.6,
          "keypointlabels": ["Top"]
        }
      }
    ]
  }]
}
```

## Labeling Configuration

The `labeling_config.xml` defines:

- **Image**: Zoomable image display
- **RectangleLabels (crop_roi)**: Optional crop ROI rectangle (green)
- **KeyPointLabels (keypoints)**: 5 named keypoints
  - Top (red)
  - Bottom (blue)
  - Left (yellow)
  - Right (purple)
  - Center (orange)

## Directory Structure

```
labelstudio/
├── docker-compose.yml      # Label Studio Docker setup
├── labeling_config.xml     # Label Studio labeling configuration
├── convert_to_labelstudio.py  # Convert internal → Label Studio
├── export_from_labelstudio.py # Convert Label Studio → internal
├── validate_annotations.py    # QA/validation script
├── ml_predictions.py          # ML predictions entry point
├── data/                   # Label Studio data (created by Docker)
└── README.md               # This file
```

## Troubleshooting

### Images not loading in Label Studio

1. Ensure `LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true` is set
2. Check that `../downloaded_images` is mounted correctly
3. Verify image URL format: `/data/local-files/?d=FOLDER/IMAGE.jpg`

### Import errors

1. Validate your tasks file: `python validate_annotations.py --labelstudio-export tasks.json`
2. Check that image paths match the mounted directory structure

### Docker permissions

If Label Studio can't write to the data directory:
```bash
mkdir -p data
chmod 777 data
```
