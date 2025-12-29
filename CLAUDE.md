# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Label Studio-based annotation tool for watch image keypoint labeling. The tool enables annotation of 5 keypoints (top, bottom, left, right, center) on watch face images for alignment model training. The project has migrated from a legacy Streamlit-based tool to a Label Studio setup with Docker deployment.

**Multi-Model Support:** The system now supports multiple watch models with different face shapes. Templates are automatically selected based on the watch model identifier in the filename (e.g., "nab" for Nautilus, "nam" for Nautilus Moonphase).

## Key Commands

### Label Studio Operations

```bash
# Start Label Studio
cd labelstudio
docker-compose up -d

# Stop Label Studio
docker-compose down

# View logs
docker-compose logs -f
```

Access Label Studio UI at http://localhost:8200

### Data Conversion

```bash
# Convert internal annotations to Label Studio format
cd labelstudio
python convert_to_labelstudio.py \
    --input-dir ../alignment_labels \
    --output tasks.json

# Export from Label Studio back to internal format
python export_from_labelstudio.py \
    --input export.json \
    --output-dir ../alignment_labels \
    --merge

# Validate annotations
python validate_annotations.py \
    --input-dir ../alignment_labels \
    --images-dir ../downloaded_images

# Validate Label Studio export
python validate_annotations.py --labelstudio-export export.json
```

## Architecture

### Data Flow

1. **Source Images**: Located in `downloaded_images/` organized by watch model (e.g., `PATEK_nab_001/`)
2. **Internal Annotations**: JSON files in `alignment_labels/` (one file per watch model)
3. **Label Studio**: Docker-based annotation interface with local file serving
4. **Conversion Scripts**: Bidirectional conversion between internal format and Label Studio format

### Image Naming Convention

Images follow the pattern: `{BRAND}_{MODEL}_{WATCH_NUM}_{VIEW_NUM}_{VIEW_TYPE}_q{QUALITY}.jpg`

Examples:
- `PATEK_nab_042_04_face_q3.jpg` (Nautilus, face view, quality 3)
- `PATEK_nam_001_01_face_q2.jpg` (Nautilus Moonphase, face view, quality 2)
- `PATEK_nab_049_06_tiltface_q2.jpg` (Nautilus, tiltface view, quality 2)
- `PATEK_nab_001_03_face.jpg` (legacy format without quality)

Components:
- `BRAND`: All caps brand name (e.g., "PATEK", "ROLEX")
- `MODEL`: Lowercase model identifier (e.g., "nab", "nam") - **used for template selection**
- `WATCH_NUM`: Three-digit watch number (e.g., "042", "001")
- `WATCH_ID`: Combined `{BRAND}_{MODEL}_{WATCH_NUM}` (e.g., "PATEK_nab_042")
- `VIEW_NUM`: Two-digit view number (e.g., "04")
- `VIEW_TYPE`: "face" or "tiltface"
- `QUALITY`: 1, 2, or 3 (optional in legacy format)

**Important:** The `MODEL` identifier determines which template is used for keypoint prediction. Supported models are defined in `utils/model_mapper.py`.

### Annotation Data Format

#### Internal Format (JSON in alignment_labels/)

Annotations are stored per watch model with normalized coordinates (0-1 range):

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
    "crop_bbox": [0, 171, 2046, 1891],
    "annotator": "user@example.com",
    "timestamp": "2024-12-01T12:00:00Z"
  }
}
```

Key points:
- Keys use quality-agnostic image IDs (e.g., "PATEK_nab_041_05" without quality tag)
- Coordinates are normalized to [0, 1] range relative to image dimensions
- All 5 keypoints required: top, bottom, left, right, center
- Optional crop_bbox in pixel coordinates [x, y, width, height]

#### Label Studio Format

Tasks with pre-annotations for import/export. Coordinates are in percent (0-100):

```json
{
  "data": {
    "image": "/data/local-files/?d=images/PATEK_nab_001/PATEK_nab_001_01_face_q3.jpg",
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

### Utility Modules

Located in `utils/`:

- **filename_parser.py**: Parse and validate image filenames, extract metadata
  - `parse_filename()`: Extract watch_id, view_number, view_type, quality, model_identifier
  - `get_image_id()`: Get quality-agnostic image ID (e.g., "PATEK_nab_041_05")
  - `extract_watch_id()`: Extract just the watch ID
  - `extract_model_identifier()`: Extract model code (e.g., "nab", "nam") from filename

- **model_mapper.py**: Map watch IDs to template models (multi-model support)
  - `get_template_for_watch_id(watch_id)`: Map watch ID to template name
  - `get_template_from_filename(filename)`: Get template from image filename
  - `extract_model_identifier(watch_id)`: Extract model identifier from watch ID
  - `register_model(model_id, template_name)`: Dynamically register new models
  - `MODEL_TEMPLATE_MAP`: Central registry of model identifier → template mappings

- **alignment_manager.py**: Manage annotation CRUD operations
  - `load_annotations(watch_id)`: Load all annotations for a watch
  - `save_image_annotation()`: Save annotation with automatic normalization
  - `is_image_labeled()`: Check if image has complete 5-keypoint annotation
  - Keys in JSON files use quality-agnostic image IDs from `get_image_id()`

- **image_manager.py**: File operations and image loading
- **template_manager.py**: Template image handling for alignment

### Label Studio Configuration

The annotation interface (`labelstudio/labeling_config.xml`) defines:
- Zoomable image display
- RectangleLabels for optional crop ROI (green)
- KeyPointLabels with 5 color-coded points:
  - Top (red)
  - Bottom (blue)
  - Left (yellow)
  - Right (purple)
  - Center (orange)

### Docker Setup

Label Studio runs in Docker with:
- Port mapping: 8200:8080
- Local file serving enabled (`LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true`)
- Volume mounts:
  - `./labelstudio/data` → Label Studio database
  - `./downloaded_images` → `/label-studio/media/images` (read-only)
  - Custom nginx config for local file serving

**Important**: Images are mounted at `/label-studio/media/images/` inside the container, so all image URLs must include the `images/` prefix. The conversion script automatically adds this prefix. For example:
- Container path: `/label-studio/media/images/PATEK_nab_001/PATEK_nab_001_01_face_q3.jpg`
- Label Studio URL: `/data/local-files/?d=images/PATEK_nab_001/PATEK_nab_001_01_face_q3.jpg`

### Future: ML Prediction Server

See `Migration-Plan.md` for planned prediction server architecture:
- FastAPI-based local HTTP server
- YOLO → LoFTR → Homography → Keypoint projection pipeline
- Disk-based caching strategy
- Label Studio ML backend integration
- All coordinates in percent (0-100) for Label Studio compatibility

## Development Notes

### When Working with Annotations

1. Always use `get_image_id()` from filename_parser to generate annotation keys (quality-agnostic)
2. Coordinate conversion:
   - Internal format uses normalized [0, 1] range
   - Label Studio uses percent [0, 100] range
   - Convert: `percent = normalized * 100`
3. All 5 keypoints must be present for a complete annotation
4. Image dimensions stored as `[width, height]`

### When Adding New Scripts

1. Place conversion/validation scripts in `labelstudio/`
2. Place utility modules in `utils/`
3. Import utilities with relative imports handling both cases:
   ```python
   try:
       from .filename_parser import get_image_id
   except ImportError:
       from filename_parser import get_image_id
   ```

### When Modifying Data Formats

1. Update both conversion scripts: `convert_to_labelstudio.py` and `export_from_labelstudio.py`
2. Update validation script: `validate_annotations.py`
3. Test round-trip conversion to ensure no data loss
4. Update `labelstudio/labeling_config.xml` if annotation interface changes

### Adding a New Watch Model

To add support for a new watch model:

1. **Register model**: Add to `MODEL_TEMPLATE_MAP` in `utils/model_mapper.py`:
   ```python
   MODEL_TEMPLATE_MAP = {
       "nab": "nab",   # Nautilus
       "nam": "nam",   # Nautilus Moonphase
       "newmodel": "newmodel",  # Your new model
   }
   ```

2. **Create template directory**:
   - `templates/{model}/template.jpeg` - Reference image
   - `templates/{model}/annotations.json` - 5 keypoints in normalized coords [0,1]

3. **Use the model**: Images named `BRAND_{model}_XXX_YY_face_qZ.jpg` will automatically use the correct template

## Common Workflows

### Importing Existing Annotations

1. Convert internal format to Label Studio tasks
2. Import tasks.json via Label Studio UI
3. Existing annotations appear as pre-annotations for review

### Exporting New Annotations

1. Export from Label Studio UI (JSON format)
2. Convert back to internal format with `--merge` flag
3. Validate converted annotations
4. Commit updated JSON files to git

### Quality Control

1. Use `validate_annotations.py` to check for:
   - Missing keypoints
   - Out-of-bounds coordinates
   - Duplicate labels
   - Missing image files
2. Fix issues in Label Studio UI
3. Re-export and validate
