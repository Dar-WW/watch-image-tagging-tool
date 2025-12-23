# Batch Prediction Script

Offline batch processing script for generating keypoint predictions for all unlabeled watch images using MPS (Metal Performance Shaders) GPU acceleration on Mac.

## Overview

The `batch_predict.py` script processes images using the YOLO + LoFTR + Homography pipeline and saves predictions to JSON files in the same format as manual annotations.

**Key Features:**
- ✅ **MPS GPU acceleration** for 10x speedup on Mac (1-3s per image vs 10-30s on CPU)
- ✅ **Resumable processing** with automatic progress tracking
- ✅ **Three-tier fallback** strategy (full → pipeline → geometric)
- ✅ **Comprehensive logging** and error handling
- ✅ **Separate output directory** for easy review before merging

## Quick Start

### 1. Install Dependencies

```bash
# From project root
cd prediction_server
pip install -r requirements.txt
cd ..
```

### 2. Run Batch Prediction

```bash
# Test on single watch model first (recommended)
python scripts/batch_predict.py --watch-id PATEK_nab_001

# Process all unlabeled images
python scripts/batch_predict.py

# See all options
python scripts/batch_predict.py --help
```

That's it! The script will:
- Use MPS GPU acceleration by default
- Skip images already in `alignment_labels/`
- Save predictions to `alignment_labels_predicted/`
- Auto-save progress every 10 images
- Resume automatically if interrupted

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--images-dir` | Directory containing images | `downloaded_images` |
| `--output-dir` | Directory to save predictions | `alignment_labels_predicted` |
| `--labels-dir` | Directory with existing annotations | `alignment_labels` |
| `--config` | Pipeline config file | `prediction_server/config.yaml` |
| `--device` | Device to use (mps/cpu/cuda/auto) | `mps` |
| `--resume` | Resume from progress file | `True` |
| `--no-resume` | Don't resume, start fresh | - |
| `--force` | Reprocess all images, ignore existing | `False` |
| `--watch-id` | Only process this watch ID | - |
| `--checkpoint-freq` | Save progress every N images | `10` |

## Usage Examples

### Basic Usage

```bash
# Process all new images with MPS acceleration
python scripts/batch_predict.py
```

### Test on Single Watch

```bash
# Process just one watch model to verify everything works
python scripts/batch_predict.py --watch-id PATEK_nab_001
```

### Resume After Interruption

The script automatically saves progress every 10 images. If interrupted (Ctrl+C), just run again:

```bash
# Resumes automatically from last checkpoint
python scripts/batch_predict.py --resume
```

Or to start completely fresh:

```bash
# Clear progress and start over
rm .batch_predict_progress.json
python scripts/batch_predict.py --no-resume
```

### Force Reprocess

To regenerate predictions for images that already have them:

```bash
python scripts/batch_predict.py --force
```

### Use CPU Instead of MPS

If you encounter issues with MPS or want to test:

```bash
python scripts/batch_predict.py --device cpu
```

## Output Format

Predictions are saved to `alignment_labels_predicted/{WATCH_ID}.json` in the same format as `alignment_labels/`:

```json
{
  "PATEK_nab_001_03": {
    "image_size": [2228, 2066],
    "coords_norm": {
      "top": [0.442, 0.184],
      "bottom": [0.591, 0.736],
      "left": [0.163, 0.444],
      "right": [0.841, 0.434],
      "center": [0.510, 0.436]
    },
    "full_image_name": "PATEK_nab_001_03_tiltface_q1.jpg",
    "annotator": "ml-model-v1.0",
    "confidence": 0.289,
    "timestamp": "2024-12-22T11:42:58.831796",
    "debug_info": {
      "yolo_detections": 1,
      "yolo_confidence": 0.864,
      "loftr_matches": 571,
      "homography_inliers": 165,
      "method": "YOLO-LoFTR-Homography",
      "template_model": "nab"
    }
  }
}
```

**Key fields:**
- `coords_norm`: Normalized [0,1] keypoint coordinates
- `annotator`: Type of prediction (see Fallback Strategy below)
- `confidence`: Overall prediction confidence
- `debug_info`: Full pipeline diagnostics

## Three-Tier Fallback Strategy

The script automatically uses the best available method for each image:

### 1. Full Pipeline Success (`ml-model-v1.0`)

**Best case** - High accuracy, high confidence
- YOLO detects watch → LoFTR matches → Homography succeeds
- Returns precise keypoint coordinates
- Expected: ~70-80% of images

### 2. Pipeline Fallback (`ml-model-v1.0-pipeline-fallback`)

**Good case** - Moderate accuracy
- YOLO detects watch → LoFTR/Homography fails
- Estimates keypoints from oriented bounding box geometry
- Expected: ~10-20% of images

### 3. Geometric Fallback (`ml-model-v1.0-geometric-fallback`)

**Fallback case** - Low accuracy, needs human review
- YOLO fails or exception occurs
- Uses center-based default keypoints:
  - center: (0.5, 0.5)
  - top: (0.5, 0.1)
  - bottom: (0.5, 0.9)
  - left: (0.1, 0.5)
  - right: (0.9, 0.5)
- Expected: ~5-10% of images

**All predictions are saved** regardless of fallback level, making it easy to identify which ones need human review.

## Progress Tracking

Progress is automatically saved to `.batch_predict_progress.json`.

### View Current Progress

```bash
# View progress file
cat .batch_predict_progress.json | python3 -m json.tool

# Quick stats
python3 -c "
import json
with open('.batch_predict_progress.json') as f:
    data = json.load(f)
    stats = data['stats']
    print(f\"Processed: {stats['processed']}/{stats['total_images']}\")
    if stats['processed'] > 0:
        print(f\"Success: {stats['successful']} ({stats['successful']/stats['processed']*100:.1f}%)\")
        print(f\"Pipeline fallback: {stats.get('pipeline_fallback', 0)}\")
        print(f\"Geometric fallback: {stats.get('geometric_fallback', 0)}\")
"
```

### Clear Progress

```bash
# Start fresh (will reprocess all images)
rm .batch_predict_progress.json
```

## Monitoring

### Live Progress

The script prints progress every 10 images and at the end:

```
================================================================================
Batch Prediction Progress
================================================================================
Processed: 40/402 (10.0%)
Success:   32 (80.0%)
Pipeline Fallback: 6
Geometric Fallback: 2
Elapsed:   00:02:15
ETA:       00:20:20
================================================================================
```

### View Logs

```bash
# View log file
tail -f batch_predict.log

# Search for errors
grep ERROR batch_predict.log

# Search for warnings
grep WARNING batch_predict.log
```

### Monitor System Resources

```bash
# Watch CPU/memory usage
top -pid $(pgrep -f batch_predict.py)

# Or use Activity Monitor.app and search for "Python"
```

## Workflow: From Predictions to Final Annotations

### 1. Run Batch Prediction

```bash
python scripts/batch_predict.py
```

**Output**: `alignment_labels_predicted/*.json` files

### 2. Validate Predictions

```bash
python labelstudio/validate_annotations.py \
  --input-dir alignment_labels_predicted/
```

**Checks**: Coordinate ranges, required keypoints, image references

### 3. Convert to Label Studio Format

```bash
cd labelstudio
python convert_to_labelstudio.py \
  --input-dir ../alignment_labels_predicted \
  --output tasks_predicted.json \
  --image-base-url "/data/local-files/?d=images/"
cd ..
```

**Output**: `labelstudio/tasks_predicted.json`

### 4. Import to Label Studio

- Start Label Studio: `cd labelstudio && docker-compose up -d`
- Open http://localhost:8200
- Create project: "Watch Keypoints - ML Predictions"
- Upload labeling config: `labelstudio/labeling_config.xml`
- Import tasks: Upload `tasks_predicted.json`

**Result**: Tasks with ML predictions as pre-annotations

### 5. Review & Correct in Label Studio

- Open tasks in Label Studio UI
- ML predictions appear as colored keypoints
- **Accept** good predictions (click Submit)
- **Correct** bad predictions (drag keypoints, then Submit)
- Focus on `geometric-fallback` predictions (lowest confidence)

### 6. Export Corrected Annotations

- In Label Studio: Export → JSON format
- Download `export.json`

### 7. Merge Back to alignment_labels

```bash
python labelstudio/export_from_labelstudio.py \
  --input export.json \
  --output-dir alignment_labels \
  --merge
```

**Result**: Final human-corrected annotations in `alignment_labels/`

## Troubleshooting

### MPS Not Available

If you get "MPS device not found" error:

```bash
# Check if MPS is available
python3 -c "import torch; print(f'MPS available: {torch.backends.mps.is_available()}')"

# If not available, use CPU instead
python scripts/batch_predict.py --device cpu
```

MPS requires:
- macOS 12.3+
- Apple Silicon (M1/M2/M3) or AMD GPUs
- PyTorch 1.12+

### Import Errors

If you get "No module named 'torch'" or similar:

```bash
# Install dependencies
cd prediction_server
pip install -r requirements.txt
cd ..
```

### Out of Memory

If processing crashes with OOM errors:

```bash
# Use CPU instead (uses less memory)
python scripts/batch_predict.py --device cpu

# Or process one watch at a time
python scripts/batch_predict.py --watch-id PATEK_nab_001
python scripts/batch_predict.py --watch-id PATEK_nab_002
# ... etc
```

### Low Success Rate

If many predictions use geometric fallback:

1. Check YOLO model weights exist:
   ```bash
   ls -lh prediction_server/models/yolo_watch_face_best.pt
   ```

2. Check config thresholds:
   ```bash
   cat prediction_server/config.yaml
   ```

3. Try lowering thresholds in `config.yaml`:
   ```yaml
   yolo:
     conf_threshold: 0.15  # Lower from 0.25
   homography:
     min_inliers: 5  # Lower from 10
   ```

### Slow Processing

- **Normal on CPU**: 10-30s per image
- **Should be fast on MPS**: 1-3s per image

If slow on MPS:
```bash
# Verify MPS is actually being used
python3 -c "
import torch
print(f'MPS available: {torch.backends.mps.is_available()}')
print(f'MPS built: {torch.backends.mps.is_built()}')
"
```

### Model Files Missing

If YOLO model not found:

```bash
# Check if model exists
ls prediction_server/models/

# If missing, copy from FPJ-WatchId-POC project
cp /path/to/FPJ-WatchId-POC/yolo/outputs/watch_face_detection/weights/best.pt \
   prediction_server/models/yolo_watch_face_best.pt
```

## Files Created

Running the batch script creates:

- `.batch_predict_progress.json` - Progress tracking (resumable)
- `batch_predict.log` - Complete execution log
- `alignment_labels_predicted/*.json` - Prediction output files (one per watch model)

All can be safely deleted to start fresh.

## Tips

**For testing:**
- Always test on one watch first: `--watch-id PATEK_nab_001`
- Verify output format before running full batch

**For production:**
- Run on all images overnight: `python scripts/batch_predict.py`
- Monitor progress with `tail -f batch_predict.log`
- Let it run unattended (auto-saves progress every 10 images)

**For debugging:**
- Check `debug_info` field in output JSON for pipeline details
- Look for patterns in failures (specific watch models, view types)
- Compare confidence scores across predictions

## Support

For issues or questions:
- Implementation plan: `.claude/plans/robust-rolling-brook.md`
- Pipeline details: `prediction_server/pipelines/homography_keypoints.py`
- Data format: `labelstudio/convert_to_labelstudio.py`
