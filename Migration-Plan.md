# Migration Plan for Label Studio (Local/Self-Hosted)

## Goal
- Migrate from current annotation tooling to Label Studio for watch image keypoint and ROI annotation.
- Enable efficient manual labeling with optional ML-assisted pre-annotation.
- Ensure reproducible local deployment, consistent data formats, and streamlined export/import workflows.

## Scope
- Annotate 5 fixed keypoints per watch image: top, bottom, left, right, center.
- Optional rectangular crop ROI annotation.
- Support image input from local files or URLs.
- Utilize ML-assisted pre-annotation to speed up manual labeling.
- Enable cropping and keypoint annotation in a single interface.

## Local Setup (Docker Compose)

Create `docker-compose.yml`:
```yaml
version: '3'
services:
  label-studio:
    image: heartexlabs/label-studio:latest
    ports:
      - "8200:8200"
    volumes:
      - <LABEL_STUDIO_DATA_DIR>:/label-studio/data
      - <PATH_TO_IMAGES>:/label-studio/media:ro
```
Run:
```bash
docker-compose up -d
```
Create admin user:
```bash
docker-compose exec label-studio label-studio user create --username admin --password <password> --email admin@example.com
```
Access UI at `http://localhost:8200`.

## Project + Labeling Configuration

### Label Studio labeling config XML (copy-paste ready)
```xml
<View>
  <Image name="image" value="$image" zoom="true" />
  <RectangleLabels name="crop_roi" toName="image" maxUsages="1" strokeWidth="2">
    <Label value="Crop ROI" background="green" />
  </RectangleLabels>
  <KeyPointLabels name="keypoints" toName="image" pointSize="10" strokeWidth="2">
    <Label value="Top" background="red" />
    <Label value="Bottom" background="blue" />
    <Label value="Left" background="yellow" />
    <Label value="Right" background="purple" />
    <Label value="Center" background="orange" />
  </KeyPointLabels>
</View>
```
- Assumes each task JSON includes an `image` field with local path or URL.
- `RectangleLabels` for optional crop ROI.
- `KeyPointLabels` for 5 named keypoints.

## Data Organization Strategy
- One task per watch folder, grouping all images per watch into a single task for contextual annotation.
- Store images locally under `<PATH_TO_IMAGES>`, mounted inside the container at `/label-studio/media`.
- Each task JSON references images via relative or absolute paths accessible inside Label Studio container.

## Migration of Existing Annotations

### Internal JSON schema example
```json
{
  "task_id": "watch123",
  "image": "media/watch123/front.jpg",
  "crop_roi": {
    "x": 0.1,
    "y": 0.1,
    "width": 0.8,
    "height": 0.8
  },
  "keypoints": {
    "top": {"x": 0.5, "y": 0.05},
    "bottom": {"x": 0.5, "y": 0.95},
    "left": {"x": 0.1, "y": 0.5},
    "right": {"x": 0.9, "y": 0.5},
    "center": {"x": 0.5, "y": 0.5}
  }
}
```

### Conversion steps internal → Label Studio preannotations
- Convert each internal task JSON to Label Studio task JSON with fields:
  - `image`: local path or URL.
  - `predictions`: array with one object containing:
    - `result`: array of annotations:
      - Rectangle ROI:
        ```json
        {
          "from_name": "crop_roi",
          "to_name": "image",
          "type": "rectanglelabels",
          "origin": "manual",
          "value": {
            "x": crop_roi.x * 100,
            "y": crop_roi.y * 100,
            "width": crop_roi.width * 100,
            "height": crop_roi.height * 100,
            "rectanglelabels": ["Crop ROI"]
          }
        }
        ```
      - Keypoints (for each named point):
        ```json
        {
          "from_name": "keypoints",
          "to_name": "image",
          "type": "keypointlabels",
          "origin": "manual",
          "value": {
            "x": keypoints.<name>.x * 100,
            "y": keypoints.<name>.y * 100,
            "keypointlabels": ["<Name>"]
          }
        }
        ```
- Note: Label Studio expects `x` and `y` in percentages (0–100), so multiply internal normalized coordinates by 100.
- Store these preannotations as `predictions` in Label Studio tasks for ML-assisted labeling.

## Export Back to Internal JSON
- Export annotations from Label Studio as JSON via UI or API.
- Parse `result` array:
  - Extract rectangle ROI coordinates, convert from percent to normalized float [0.0–1.0].
  - Extract each keypoint by label name, convert coordinates similarly.
- Rebuild internal JSON format for downstream use.
- Automate conversion with a script to ensure consistency.

## ML “Guess Points” Workflow (Offline) - OUT OF SCOPE FOR NOW - just prepare an entry point to load predictions.
- Use exported Label Studio annotations as training data.
- Train ML model offline to predict keypoints and crop ROI.
- Generate model predictions in Label Studio prediction format.
- Upload predictions back to Label Studio tasks as preannotations.
- Annotators review and correct ML guesses, improving speed and consistency.

## QA / Validation Script Checklist
- Validate all keypoints exist and are within [0,1] normalized bounds.
- Ensure crop ROI rectangle is within image bounds and non-empty.
- Confirm each task has exactly one image field.
- Check no duplicate keypoint labels per task.
- Verify consistency of image paths and accessibility.
- Confirm exported JSON matches internal schema exactly.
- Automate these checks as part of CI/CD or pre-import validation.

## Milestones
1. Set up Label Studio local environment via Docker Compose.
2. Create initial project with labeling config.
3. Convert existing data and annotations to Label Studio format.
4. Import tasks and preannotations into Label Studio.
5. Train ML model and integrate offline predictions.
6. Validate annotation quality and export pipeline.
7. Document workflows and train annotators on Label Studio UI.
8. Full migration and decommission legacy tooling.
