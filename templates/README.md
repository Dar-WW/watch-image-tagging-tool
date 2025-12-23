# Watch Templates

This directory contains template images and annotations for watch face alignment and keypoint prediction.

## Directory Structure

```
templates/
  └── nab/                    # Nautilus template
      ├── template.jpeg       # 832×832 template image
      └── annotations.json    # Keypoint annotations
```

## Template Format

### template.jpeg
- **Size**: 832×832 pixels (square)
- **Content**: Canonical watch face image with 12 o'clock at top
- **Source**: Main training codebase at `FPJ-WatchId-POC/data/templates/nab/`

### annotations.json
- **Format**: JSON with keypoint coordinates and metadata
- **Keypoints**: 5 points (top, bottom, left, right, center) at bezel edges
- **Coordinates**: Normalized [0, 1] range relative to image dimensions

Example:
```json
{
  "image_size": [832, 832],
  "coords_norm": {
    "top": [0.495, 0.002],      // 12 o'clock position
    "left": [0.001, 0.505],     // 9 o'clock position
    "right": [0.995, 0.507],    // 3 o'clock position
    "bottom": [0.498, 0.996],   // 6 o'clock position
    "center": [0.496, 0.501]    // Watch center
  }
}
```

## Keypoint Positions

The 5 keypoints are positioned at the **edges of the watch bezel**:

- **Top** (12 o'clock): Upper edge of bezel, ~2px from top
- **Bottom** (6 o'clock): Lower edge of bezel, ~829px (near bottom)
- **Left** (9 o'clock): Left edge of bezel, ~1px from left
- **Right** (3 o'clock): Right edge of bezel, ~828px (near right)
- **Center**: Geometric center of watch face, ~(413, 417)px

## Important Notes

⚠️ **DO NOT RESIZE** the template image without updating annotations!

The `image_size` field in `annotations.json` MUST match the actual pixel dimensions of `template.jpeg`. Mismatches cause incorrect keypoint positioning and prediction errors.

## Syncing with Main Codebase

The canonical template is maintained in the main training codebase:
- **Source**: `FPJ-WatchId-POC/data/templates/nab/` (832×832)
- **Copy**: `FPJ-WatchId-POC/alignment/templates/nab/` (annotations)

To sync templates to this directory:

```bash
# Copy template image (832×832)
cp ../FPJ-WatchId-POC/data/templates/nab/template.jpeg templates/nab/

# Copy annotations (832×832 coordinates)
cp ../FPJ-WatchId-POC/alignment/templates/nab/annotations.json templates/nab/
```

## Verification

To verify template consistency:

```bash
# Check image dimensions
sips -g pixelWidth -g pixelHeight templates/nab/template.jpeg

# Verify annotations match image size
python3 -c "
import json
with open('templates/nab/annotations.json') as f:
    data = json.load(f)
print(f'Annotation image_size: {data[\"image_size\"]}')
"
```

Both should report `832 × 832`.

