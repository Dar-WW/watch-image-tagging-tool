# CVAT Local Setup for Watch Annotation

This directory contains everything needed to run CVAT locally for annotating watch images with keypoints.

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Python 3.8+

### 1. Start CVAT

```bash
cd cvat
./run_cvat_local.sh start
```

### 2. Create Admin User (first time only)

```bash
./run_cvat_local.sh create-superuser
```

### 3. Access CVAT

Open http://localhost:8080 and login with your admin credentials.

### 4. Create Project and Tasks

Follow the guide:
```bash
python scripts/create_task.py --guide
```

## Directory Structure

```
cvat/
├── docker-compose.yml      # Docker configuration
├── nginx.conf              # Nginx proxy config
├── run_cvat_local.sh       # Management script
├── label_schema.json       # Annotation schema definition
├── README.md               # This file
└── scripts/
    ├── config.py                    # Configuration settings
    ├── convert_internal_to_cvat.py  # Internal → CVAT conversion
    ├── convert_cvat_to_internal.py  # CVAT → Internal conversion
    ├── import_into_cvat.py          # API-based import
    ├── export_from_cvat.py          # API-based export
    ├── validate_annotations.py      # Annotation validation
    └── create_task.py               # Task creation guide
```

## Management Commands

```bash
# Start CVAT
./run_cvat_local.sh start

# Stop CVAT
./run_cvat_local.sh stop

# View logs
./run_cvat_local.sh logs

# View logs for specific service
./run_cvat_local.sh logs cvat_server

# Open shell in server container
./run_cvat_local.sh shell

# Check status
./run_cvat_local.sh status
```

## Annotation Schema

### Label: `watch_landmarks` (Skeleton)

A skeleton with 5 keypoints representing watch dial landmarks:

| Keypoint | Description | Position |
|----------|-------------|----------|
| `top` | 12 o'clock marker | Top of dial |
| `bottom` | 6 o'clock marker | Bottom of dial |
| `left` | 9 o'clock marker | Left side of dial |
| `right` | 3 o'clock marker | Right side of dial |
| `center` | Dial center | Center of watch face |

### Attributes

- **quality**: `bad`, `partial`, `full` - Image quality rating
- **view_type**: `face`, `tiltface` - Camera angle type

### Label: `crop_roi` (Rectangle)

Optional bounding box for crop region:
- **crop_type**: `watch_face`, `dial`, `custom`

## Migration Workflow

### Migrating Existing Annotations to CVAT

1. **Convert to CVAT format:**
   ```bash
   python scripts/convert_internal_to_cvat.py --all --output ./cvat_exports
   ```

2. **Import via API:**
   ```bash
   export CVAT_PASSWORD=your_password
   python scripts/import_into_cvat.py --all --annotations-dir ./cvat_exports
   ```

   Or import via UI:
   - Open task → Actions → Upload annotations
   - Format: "CVAT for images 1.1"
   - Select XML file

### Exporting from CVAT

1. **Export via API:**
   ```bash
   python scripts/export_from_cvat.py --project "Watch Annotations" --output ./cvat_exports/
   ```

2. **Convert back to internal format:**
   ```bash
   python scripts/convert_cvat_to_internal.py --input ./cvat_exports/ --output ../alignment_labels/
   ```

### Round-Trip Validation

Test that annotations survive the round-trip:

```bash
# 1. Export current internal annotations
python scripts/convert_internal_to_cvat.py --watch PATEK_nab_001 --output ./test_export

# 2. Convert back to internal
python scripts/convert_cvat_to_internal.py --input ./test_export/ --output ./test_internal/

# 3. Compare (should be equivalent within rounding tolerance)
diff -q ../alignment_labels/PATEK_nab_001.json ./test_internal/PATEK_nab_001.json
```

## Validation

Check annotation quality:

```bash
# Validate all watches
python scripts/validate_annotations.py --all

# Validate specific watch
python scripts/validate_annotations.py --watch PATEK_nab_001

# Show summary only
python scripts/validate_annotations.py --summary

# Verbose output
python scripts/validate_annotations.py --all --verbose
```

Validation checks:
- ✅ All 5 keypoints present
- ✅ Coordinates within bounds (0-1)
- ✅ Points not duplicated
- ✅ Center roughly between edges
- ✅ Image file exists
- ✅ Image size matches annotation

## Annotation Hotkeys (in CVAT)

| Key | Action |
|-----|--------|
| N | Next image |
| P | Previous image |
| Ctrl+S | Save |
| Space | Play/Pause |
| D | Delete selected |
| Ctrl+Z | Undo |

## Troubleshooting

### CVAT won't start

```bash
# Check Docker is running
docker ps

# Check logs
./run_cvat_local.sh logs

# Restart from scratch
./run_cvat_local.sh stop
docker volume rm cvat_cvat_db cvat_cvat_data  # Warning: deletes data!
./run_cvat_local.sh start
```

### Can't see images in CVAT

The `downloaded_images` directory is mounted read-only at `/home/django/share` in CVAT.

1. Check mount in docker-compose.yml
2. Verify images are in the correct location
3. In CVAT, use "Connected file share" when creating tasks

### API authentication errors

```bash
# Set credentials
export CVAT_HOST=http://localhost:8080
export CVAT_USERNAME=admin
export CVAT_PASSWORD=your_password

# Test connection
python scripts/export_from_cvat.py --list-projects
```

### Import fails

1. Ensure task has images uploaded first
2. Check XML format is "CVAT for images 1.1"
3. Verify image filenames match between XML and task

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CVAT_HOST` | http://localhost:8080 | CVAT server URL |
| `CVAT_USERNAME` | admin | API username |
| `CVAT_PASSWORD` | (required) | API password |
| `CVAT_SHARE_DIR` | ../downloaded_images | Path to image directory |

## Data Persistence

CVAT data is persisted in Docker volumes:
- `cvat_db` - PostgreSQL database
- `cvat_data` - Uploaded files and exports
- `cvat_keys` - Authentication keys
- `cvat_logs` - Server logs

To backup:
```bash
docker run --rm -v cvat_cvat_db:/data -v $(pwd):/backup busybox tar cvf /backup/cvat_db_backup.tar /data
```

## ML-Assisted Annotation (Placeholder)

Future enhancement: Pre-populate annotations using ML predictions.

```python
# TODO: Implement predict_keypoints.py
# python scripts/predict_keypoints.py --watch PATEK_nab_001 --output ./predictions/
# python scripts/import_into_cvat.py --watch PATEK_nab_001 --annotations-dir ./predictions/
```

This will:
1. Run watch keypoint detection model on images
2. Generate CVAT XML with predicted points
3. Import as initial annotations for human correction
