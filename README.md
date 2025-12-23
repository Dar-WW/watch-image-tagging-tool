# Watch Image Annotation Tool

A Label Studio-based annotation tool for watch image keypoint labeling with ML-powered predictions. This tool enables efficient annotation of 5 keypoints (top, bottom, left, right, center) on watch face images using a two-phase YOLO + LoFTR + Homography pipeline.

## ✨ Features

- 🎯 **Automated Keypoint Prediction** - YOLO-OBB + LoFTR + Homography pipeline
- 🏷️ **Label Studio Integration** - Professional annotation UI with pre-annotations
- 🐳 **Docker Setup** - One command to start everything
- 💾 **Smart Caching** - Fast predictions with disk-based cache
- 📊 **Template-based** - Uses reference template for consistent alignment

## 🚀 Quick Start (Unified Docker Setup)

### Prerequisites
- Docker Desktop installed and running
- ~3 GB free disk space

### Start Everything

```bash
# One command to start both Label Studio and Prediction Server
./start.sh
```

**Access points:**
- Label Studio UI: http://localhost:8200
- Prediction Server: http://localhost:9090
- API Docs: http://localhost:9090/docs

**Stop everything:**
```bash
./stop.sh
```

📖 **For detailed setup and troubleshooting, see [SETUP.md](SETUP.md)**

---

## 🔧 Alternative: Manual Setup

### 1. Start Services Separately

**Label Studio:**
```bash
cd labelstudio
docker-compose up -d
```

Access the UI at **http://localhost:8200**

**Prediction Server:**
```bash
cd prediction_server
docker-compose up -d
```

Access at **http://localhost:9090**

### 2. Create Admin User (First Time Only)

Go to http://localhost:8200 and sign up with your email and password.

### 3. Create a Project

1. Log in and click "Create Project"
2. Name it (e.g., "Watch Keypoint Annotation")
3. Go to **Labeling Setup** → **Custom template**
4. Paste contents from `labelstudio/labeling_config.xml`
5. Click **Save**

### 4. Configure Local File Storage

1. Go to **Settings** → **Cloud Storage** → **Add Source Storage**
2. Choose **Local Files**
3. Configure:
   - **Absolute local path**: `/label-studio/media/images`
   - **File Filter Regex**: `.*\.jpg$`
   - Check "Treat every bucket object as a source file"
4. Click **Add Storage** → **Sync Storage**

### 5. Import Existing Annotations (Optional)

```bash
cd labelstudio

# Convert existing annotations to Label Studio format
python convert_to_labelstudio.py \
    --input-dir ../alignment_labels \
    --output tasks.json \
    --image-base-url "/data/local-files/?d=images/"

# Import via UI: Project → Import → Upload tasks.json
```

## 📁 Project Structure

```
watch-image-tagging-tool/
├── labelstudio/              # Label Studio setup and tools
│   ├── docker-compose.yml    # Docker configuration
│   ├── labeling_config.xml   # Keypoint labeling interface
│   ├── convert_to_labelstudio.py   # Import converter
│   ├── export_from_labelstudio.py  # Export converter
│   ├── validate_annotations.py     # QA/validation
│   └── README.md             # Detailed Label Studio documentation
├── downloaded_images/        # Watch images organized by model
├── alignment_labels/         # Annotation data (internal format)
├── templates/                # Template images for alignment
└── utils/                    # Utility modules
    ├── filename_parser.py    # Parse watch image filenames
    ├── image_manager.py      # File operations
    ├── alignment_manager.py  # Annotation management
    └── template_manager.py   # Template handling
```

## 🏷️ Annotation Workflow

### Keypoint Labeling

Annotate 5 keypoints on each watch face image:

1. **Top** (red) - Top center of watch face
2. **Bottom** (blue) - Bottom center of watch face
3. **Left** (yellow) - Leftmost point of watch face
4. **Right** (purple) - Rightmost point of watch face
5. **Center** (orange) - Center point of watch face

### Tips
- Use zoom to precisely place keypoints
- Follow consistent keypoint placement across all images
- Mark crop ROI if needed for alignment

## 🔄 Data Conversion

### Export Annotations

```bash
cd labelstudio

# Export from Label Studio UI:
# Project → Export → JSON format → Download

# Convert back to internal format
python export_from_labelstudio.py \
    --input export.json \
    --output-dir ../alignment_labels \
    --merge
```

### Validate Annotations

```bash
cd labelstudio

# Validate internal annotations
python validate_annotations.py \
    --input-dir ../alignment_labels \
    --images-dir ../downloaded_images

# Validate Label Studio export
python validate_annotations.py \
    --labelstudio-export export.json
```

## 📊 Data Formats

### Internal Format
JSON files in `alignment_labels/` with normalized coordinates (0-1):

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
    "crop_bbox": [0, 171, 2046, 1891]
  }
}
```

### Label Studio Format
Tasks with pre-annotations for import/export. See `labelstudio/README.md` for details.

## 🛠️ Tools

| Script | Purpose |
|--------|---------|
| `convert_to_labelstudio.py` | Convert internal annotations to Label Studio tasks |
| `export_from_labelstudio.py` | Convert Label Studio export back to internal format |
| `validate_annotations.py` | Validate annotation completeness and correctness |
| `ml_predictions.py` | ML-assisted pre-annotation (future) |

## 🔍 Troubleshooting

### Images not loading
1. Check `LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true` in docker-compose.yml
2. Verify `../downloaded_images` is mounted correctly
3. Ensure image URL format: `/data/local-files/?d=FOLDER/IMAGE.jpg`

### Import errors
1. Validate tasks file: `python validate_annotations.py --labelstudio-export tasks.json`
2. Check image paths match mounted directory structure

### Docker permissions
```bash
cd labelstudio
mkdir -p data
chmod 777 data
```

## 📚 Documentation

- **Detailed Label Studio setup**: See `labelstudio/README.md`
- **Migration plan**: See `Migration-Plan.md`

## 🤝 Contributing

When adding new annotations:
1. Export from Label Studio (JSON format)
2. Validate: `python validate_annotations.py --labelstudio-export export.json`
3. Convert to internal format: `python export_from_labelstudio.py --input export.json --output-dir ../alignment_labels --merge`
4. Commit annotation JSON files to git

## 📝 License

Internal tool for watch image annotation.
