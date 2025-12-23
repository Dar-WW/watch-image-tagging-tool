# Watch Image Tagging Tool - Unified Setup Guide

Complete setup for Label Studio annotation UI with ML-powered prediction server.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Docker Network                        │
│                                                         │
│  ┌──────────────────┐         ┌────────────────────┐  │
│  │  Label Studio    │◄───────►│ Prediction Server  │  │
│  │  Port: 8200      │         │ Port: 9090         │  │
│  │                  │         │                    │  │
│  │  - Annotation UI │         │ - YOLO Detection   │  │
│  │  - Task Mgmt     │         │ - LoFTR Matching   │  │
│  │  - Data Storage  │         │ - Homography       │  │
│  │                  │         │ - Keypoint Predict │  │
│  └──────────────────┘         └────────────────────┘  │
│                                                         │
│           ▲                           ▲                │
│           │                           │                │
│           ▼                           ▼                │
│  ┌─────────────────────────────────────────────────┐  │
│  │         Shared Volumes                          │  │
│  │  - downloaded_images/  (watch images)           │  │
│  │  - templates/          (nab template)           │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Docker Desktop installed and running
- ~3 GB free disk space (for Docker images and ML models)
- macOS, Linux, or Windows with WSL2

### Start Everything

```bash
# From project root
./start.sh
```

This will:
1. Build the prediction server Docker image (~5-10 minutes first time)
2. Start both Label Studio and Prediction Server
3. Show health check status

**Access points:**
- Label Studio: http://localhost:8200
- Prediction Server API: http://localhost:9090
- API Docs: http://localhost:9090/docs

### Stop Everything

```bash
./stop.sh
```

## 📋 Manual Docker Commands

If you prefer manual control:

```bash
# Build and start all services
docker-compose up -d

# Build only prediction server (after code changes)
docker-compose build prediction-server

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f prediction-server
docker-compose logs -f label-studio

# Restart services
docker-compose restart

# Stop all services
docker-compose down

# Rebuild and restart
docker-compose up -d --build
```

## 🔧 Configuration

### Prediction Server Config

Edit `prediction_server/config.yaml`:

```yaml
pipeline:
  yolo:
    conf_threshold: 0.25    # Lower = more detections

  loftr:
    match_threshold: 0.2    # Lower = stricter matching

  homography:
    min_inliers: 10         # Lower = more permissive
```

After changing config:
```bash
docker-compose restart prediction-server
```

### Adding ML Backend to Label Studio

1. Open Label Studio: http://localhost:8200
2. Create/Open your project
3. Go to **Settings** → **Machine Learning**
4. Click **Add Model**
5. Enter URL: `http://prediction-server:9090`
6. Click **Validate and Save**

✅ Predictions will now appear automatically when you open tasks!

## 📊 Pipeline Details

### Phase 1: YOLO Detection
- Detects oriented watch face bounding box
- De-rotates image to canonical orientation
- Output: 1536×1536 aligned image

### Phase 2: LoFTR Matching
- Dense feature matching with template
- RANSAC homography estimation
- Validates with inlier count

### Phase 3: Keypoint Projection
- Projects template keypoints via homography
- Returns 5 keypoints: top, bottom, left, right, center
- Coordinates in Label Studio format (0-100%)

## 📂 Project Structure

```
watch-image-tagging-tool/
├── docker-compose.yml          # ⭐ Unified orchestration
├── start.sh                    # ⭐ Easy startup
├── stop.sh                     # ⭐ Easy shutdown
│
├── labelstudio/
│   ├── data/                   # Label Studio database
│   ├── docker-compose.yml      # (superseded by root)
│   └── nginx-local-files.conf
│
├── prediction_server/
│   ├── config.yaml             # Pipeline configuration
│   ├── Dockerfile              # Server image definition
│   ├── requirements.txt        # Python dependencies
│   ├── main.py                 # FastAPI server
│   ├── pipelines/
│   │   ├── yolo_utils.py       # YOLO detector
│   │   ├── loftr_utils.py      # LoFTR matcher
│   │   └── homography_keypoints.py  # Main pipeline
│   ├── core/
│   │   └── template_loader.py  # Template management
│   ├── models/
│   │   └── yolo_watch_face_best.pt  # 51 MB (gitignored)
│   └── cache/                  # Prediction cache
│
├── templates/
│   └── nab/
│       ├── annotations.json    # Template keypoints
│       └── template.jpeg       # Reference image
│
└── downloaded_images/          # Watch images (shared)
    └── PATEK_nab_*/
```

## 🐛 Troubleshooting

### Services won't start

```bash
# Check Docker is running
docker info

# View detailed logs
docker-compose logs

# Remove old containers and rebuild
docker-compose down
docker-compose up -d --build
```

### Prediction server fails

```bash
# Check logs for detailed error
docker-compose logs prediction-server

# Common issues:
# 1. YOLO weights missing
ls prediction_server/models/yolo_watch_face_best.pt

# 2. Templates missing
ls templates/nab/annotations.json

# 3. Port conflict (9090 already in use)
lsof -i :9090
```

### LoFTR download issues

On first prediction, LoFTR weights (~200 MB) auto-download. If this fails:

```bash
# Restart server to retry
docker-compose restart prediction-server

# Check network inside container
docker-compose exec prediction-server curl -I https://google.com
```

### Low accuracy / many failures

Adjust thresholds in `prediction_server/config.yaml`:

```yaml
pipeline:
  yolo:
    conf_threshold: 0.15  # Lower from 0.25

  homography:
    min_inliers: 5        # Lower from 10
```

### Out of memory

Docker Desktop settings → Resources → Increase memory to 8 GB

## 📈 Performance

**First Build:**
- Time: 5-10 minutes
- Size: ~1.5 GB

**First Prediction:**
- Time: ~10-15 seconds (LoFTR download)
- After: ~3-5 seconds per image (CPU)

**With GPU (optional):**
- Install nvidia-docker2
- Uncomment GPU settings in docker-compose.yml
- Speed: ~0.7-1.6 seconds per image

## 🔄 Development Workflow

### Local Development (without Docker)

```bash
cd prediction_server
pip install -r requirements.txt
python -m uvicorn prediction_server.main:app --reload --port 9090
```

### After Code Changes

```bash
# Rebuild and restart prediction server only
docker-compose up -d --build prediction-server

# Or use no-cache to force fresh build
docker-compose build --no-cache prediction-server
docker-compose up -d prediction-server
```

## 📚 API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:9090/docs
- **ReDoc**: http://localhost:9090/redoc

## 🎯 Next Steps

1. ✅ Start services with `./start.sh`
2. ✅ Open Label Studio at http://localhost:8200
3. ✅ Create a project and import tasks
4. ✅ Add ML backend: `http://prediction-server:9090`
5. ✅ Start annotating with automatic predictions!

## 📞 Support

Check logs for errors:
```bash
docker-compose logs -f
```

Common log locations:
- Prediction server: Docker logs (see above)
- Label Studio: `labelstudio/data/logs/`
