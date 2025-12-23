# Watch Keypoint Prediction Server

FastAPI-based ML backend for Label Studio, providing pre-annotations for watch image keypoint detection.

## Overview

This server generates predictions for 5 keypoints (top, bottom, left, right, center) on watch face images using a configurable pipeline architecture. The current implementation uses placeholder ML models (YOLO, LoFTR, Homography) that return dummy data in valid format.

## Quick Start

### Local Development

```bash
# Install dependencies
cd prediction_server
pip install -r requirements.txt

# Run server
python -m uvicorn prediction_server.main:app --reload --port 9090

# Or use the main.py directly
python main.py
```

Access the server at **http://localhost:9090**

### Docker Deployment

```bash
# Build and start
cd prediction_server
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## API Endpoints

### `GET /health`

Health check endpoint.

**Response:**
```json
{
  "status": "ok"
}
```

### `GET /version`

Get server and pipeline version information.

**Response:**
```json
{
  "version": "0.1.0",
  "pipeline": "homography_keypoints",
  "pipeline_version": "homography-v1.0-placeholder",
  "config": {
    "confidence_threshold": 0.7,
    "cache_enabled": true
  }
}
```

### `POST /predict`

Generate predictions for a single task.

**Request:**
```json
{
  "data": {
    "image": "/data/local-files/?d=images/PATEK_nab_001/image.jpg"
  },
  "meta": {
    "task_id": 123
  }
}
```

**Response:**
```json
{
  "predictions": [
    {
      "result": [
        {
          "id": "abc12345",
          "from_name": "crop_roi",
          "to_name": "image",
          "type": "rectanglelabels",
          "value": {
            "x": 10.0,
            "y": 10.0,
            "width": 80.0,
            "height": 80.0,
            "rectanglelabels": ["ROI"]
          }
        },
        {
          "id": "def67890",
          "from_name": "keypoints",
          "to_name": "image",
          "type": "keypointlabels",
          "value": {
            "x": 50.0,
            "y": 20.0,
            "keypointlabels": ["Top"]
          }
        }
        // ... 4 more keypoints
      ],
      "score": 0.85,
      "model_version": "homography-v1.0-placeholder",
      "debug": {
        "inliers": 45,
        "reprojection_error": 1.2,
        "method": "YOLO-LoFTR-Homography"
      }
    }
  ]
}
```

### `POST /predict_batch`

Generate predictions for multiple tasks (sequential processing).

**Request:**
```json
{
  "tasks": [
    {
      "data": {"image": "/data/local-files/?d=images/image1.jpg"}
    },
    {
      "data": {"image": "/data/local-files/?d=images/image2.jpg"}
    }
  ]
}
```

**Response:** Same as `/predict` but with predictions for all tasks.

## Configuration

Edit `config.yaml` to customize behavior:

```yaml
server:
  host: "0.0.0.0"
  port: 9090
  version: "0.1.0"

pipeline:
  type: "homography_keypoints"
  confidence_threshold: 0.7
  steps:
    - method: yolo
      model_path: models/yolo/best.pt
    - method: loftr
      model_path: models/loftr/weights.ckpt
    - method: homography
      ransac_thresh: 2.0
    - method: keypoint_project
      template_path: ../templates/nab/annotations.json

cache:
  enabled: true
  directory: cache/

paths:
  media_mount: /label-studio/media
  local_media: ../downloaded_images
```

## Architecture

### Directory Structure

```
prediction_server/
├── main.py                 # FastAPI application
├── config.yaml            # Configuration
├── pipelines/
│   ├── base.py           # Abstract pipeline interface
│   └── homography_keypoints.py  # Homography pipeline (placeholder)
├── models/
│   ├── request.py        # Pydantic request models
│   ├── response.py       # Pydantic response models
│   └── pipeline_result.py  # Internal result format
├── core/
│   ├── cache.py          # Disk caching
│   ├── config.py         # Config loading
│   ├── path_resolver.py  # Path resolution
│   └── template_loader.py  # Template loading
└── utils/
    ├── hashing.py        # Cache key generation
    └── formatters.py     # Output formatting
```

### Data Flow

1. **Request** → FastAPI endpoint receives Label Studio task
2. **Path Resolution** → Convert Label Studio URL to local file path
3. **Cache Check** → Check if prediction exists in cache
4. **Pipeline** → Run prediction pipeline (YOLO → LoFTR → Homography → Keypoints)
5. **Format** → Convert internal format to Label Studio format
6. **Cache Save** → Save result to cache
7. **Response** → Return predictions to Label Studio

### Coordinate Systems

- **Internal Format**: Normalized coordinates (0-1 range)
- **Label Studio Format**: Percent coordinates (0-100 range)
- **Conversion**: `percent = normalized * 100`

### Caching Strategy

Predictions are cached using a key derived from:
- Image file hash (SHA256)
- Pipeline version string
- Configuration hash

Cache files are stored as JSON in `cache/` directory.

## Extending the Server

### Adding a New Pipeline

1. Create a new class inheriting from `BasePipeline`:

```python
# pipelines/my_pipeline.py
from .base import BasePipeline
from ..models.pipeline_result import PipelineResult

class MyPipeline(BasePipeline):
    def predict(self, image_path: Path) -> PipelineResult:
        # Your implementation
        pass

    def get_version(self) -> str:
        return "my-pipeline-v1.0"

    def get_info(self) -> Dict[str, Any]:
        return {"type": "my_pipeline", "version": self.get_version()}
```

2. Update `config.yaml`:

```yaml
pipeline:
  type: "my_pipeline"
  # ... your config
```

3. Update `main.py` to instantiate your pipeline based on `config.pipeline.type`.

### Implementing Real ML Models

Replace placeholder methods in `pipelines/homography_keypoints.py`:

1. **`_yolo_detect()`**: Load YOLO model and detect watch face ROI
2. **`_loftr_match()`**: Run LoFTR to find feature correspondences
3. **`_compute_homography()`**: Use OpenCV to compute homography from matches
4. **`_project_keypoints()`**: Load template and project keypoints via homography

Required dependencies (add to `requirements.txt`):
- `torch` (for YOLO, LoFTR)
- `opencv-python` (for homography)
- Model-specific packages

## Label Studio Integration

### Setup

1. Start the prediction server:
```bash
docker-compose up -d
```

2. In Label Studio, go to your project → Settings → Machine Learning

3. Add ML backend:
   - **URL**: `http://localhost:9090` (or `http://prediction-server:9090` if on same Docker network)
   - Click **Validate and Save**

4. Enable pre-annotations in the labeling interface

### Supported Label Types

This server generates:
- **RectangleLabels** (crop_roi): Watch face bounding box
- **KeyPointLabels** (keypoints): 5 keypoints (Top, Bottom, Left, Right, Center)

Ensure your Label Studio labeling config includes these tools.

## Troubleshooting

### Server won't start

- Check `config.yaml` exists and is valid YAML
- Verify Python version >= 3.9
- Install all dependencies: `pip install -r requirements.txt`

### Images not found

- Check `paths.local_media` in `config.yaml` points to correct directory
- For Docker: verify volume mounts in `docker-compose.yml`
- Test path resolution: Check server logs for resolved paths

### Predictions are empty

- Check server logs for errors
- Verify image file exists and is readable
- Current implementation returns dummy predictions - this is expected

### Cache not working

- Set `cache.enabled: true` in `config.yaml`
- Check `cache/` directory exists and is writable
- Clear cache: `rm -rf cache/*.json`

## Development

### Running Tests

```bash
# TODO: Add tests
pytest tests/
```

### API Documentation

FastAPI provides interactive docs:
- **Swagger UI**: http://localhost:9090/docs
- **ReDoc**: http://localhost:9090/redoc

### Hot Reload

For development with auto-reload:
```bash
uvicorn prediction_server.main:app --reload --port 9090
```

## Current Limitations (Placeholder Implementation)

- ✅ Complete API structure and validation
- ✅ Caching system functional
- ✅ Configuration system working
- ⚠️ ML models are placeholders (return dummy data)
- ⚠️ No actual YOLO, LoFTR, or homography computation
- ⚠️ Template loading implemented but not used in pipeline

## Next Steps

1. Integrate real YOLO model for ROI detection
2. Add LoFTR feature matching
3. Implement homography computation with OpenCV
4. Use actual template keypoints for projection
5. Add unit tests
6. Add batch processing optimization
7. Add Prometheus metrics
8. Add authentication

## License

Internal tool for watch image annotation.
