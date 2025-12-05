
# Migration Plan: Alignment Annotation Flow

## 1. Background & Goal

The existing **Watch Image Tagging Tool** (Streamlit) is used to:

- Browse watches under `downloaded_images/{watch_id}/`
- Tag **view type** (face / tiltface)
- Tag **details quality** (q1 – Bad, q2 – Partial, q3 – Full)
- Delete unwanted images (move them into `.trash`)
- Track progress and filter images by tags

We want to extend the app with an additional **alignment annotation flow** that lets users click 5 geometric keypoints on each image. These keypoints will later be used for watch-face alignment and possibly for training a custom model. In v1 this feature is **only a labeling tool** and is **not hooked into the main pipeline**.

## 2. Scope (v1)

### In Scope

- New **Alignment** page/tab in the Streamlit app.
- Annotating exactly **5 keypoints per image**:
  1. `top`
  2. `left`
  3. `right`
  4. `bottom`
  5. `center`
- Storing annotations as **normalized coordinates** plus image size.
- Saving and loading annotations in **per-watch JSON** files.
- Filters in the Alignment page:
  - By **quality** (q1/q2/q3)
  - By **annotation status**: All / Only unlabeled / Only labeled
- Supporting **all watch families** (any watch folder in `downloaded_images`).
- Re-annotating an image **overwrites** its previous annotation silently.

### Out of Scope (v1)

- Any changes to the existing **quality/view tagging** flow.
- Any integration with the training/preprocessing pipeline.
- Any ML/model training.
- Advanced annotation editing (dragging points, undo per point).
- Real-time alignment preview (just mentionable as a future enhancement).
- Alignment-specific statistics in the sidebar.

## 3. User Workflow – Alignment Page

### Entry Point

- The app should expose a **separate Alignment page/tab** (e.g., Streamlit multipage, or a top-level mode switch).
- Users can switch between:
  - **Tagging** (existing behavior)
  - **Alignment** (new behavior)

### Sidebar Controls (Alignment Page)

The Alignment page should reuse as much of the existing sidebar as possible and add these controls:

1. **Quality Filter**

   Checkboxes to select which images are eligible for annotation:

   - `Bad (q1)`
   - `Partial (q2)`
   - `Full (q3)`

   These map to the existing quality tags derived from filenames. Only images whose quality matches the selected filters should be shown.

2. **Annotation Status Filter**

   Radio/select to control which images appear:

   - `Show: All`
   - `Show: Only unlabeled`
   - `Show: Only labeled`

   An image is **labeled** if there is a corresponding entry in the alignment JSON file and all 5 keypoints are present.

3. **Watch Selection / Navigation**

   - Reuse the existing watch dropdown and Previous/Next watch navigation.
   - Alignment page should operate on the same set of watches as the Tagging page, respecting quality/status filters.

4. **Trash Handling**

   - Images located under `downloaded_images/.trash/{watch_id}/...` must **not** appear in the Alignment page.

### Main Content Layout

For the selected watch, the Alignment page should show **one large image per row** for precise clicking.

#### For Each Image

- Display the image at a comfortable size on its own row.
- Show a short status summary under the image, e.g.:

  - `Points: 0/5` (no annotation yet)
  - `Points: 5/5 (saved)` (annotation present)

- Provide a button under the image:

  - `Clear points` or `Re-annotate` – clears all points for this image and allows re-annotation.

#### Annotation Interaction

The per-image annotation flow is:

1. The annotator clicks directly on the image.
2. The system records clicks **in a fixed order**:

   1. `top`
   2. `left`
   3. `right`
   4. `bottom`
   5. `center`

3. The UI should indicate which point is currently expected, e.g.:

   - `Click TOP (1/5)`
   - `Click LEFT (2/5)`
   - …
   - `Click CENTER (5/5)`

4. After the 5th point is clicked:

   - Convert pixel coordinates to normalized coordinates in `[0, 1]`, using the image width/height.
   - Save/update the annotation in the per-watch JSON (see Data Model).
   - Update the status label to show that the image is labeled (e.g. `✅ 5/5 points annotated`).

5. **Re-annotating**:

   - When the user presses `Clear points`, the annotations for that image are cleared from the in-memory state and the JSON file is updated accordingly (either remove the entry or reset it).
   - New clicks start over from `top` (1/5).
   - When the 5 points are re-clicked, they overwrite the previous values in the JSON.

6. **No advanced editing in v1**:

   - No dragging points.
   - No “undo last point”.
   - No per-point modification – re-annotate by clearing and clicking again.

## 4. Data Model & Storage

### Directory Structure

Add a new directory for alignment labels:

```text
alignment_labels/
├── PATEK_nab_001.json
├── PATEK_nab_002.json
└── ...
```

Location can be at project root (recommended) so both the Streamlit app and offline scripts can access it easily.

### JSON Schema (Per Watch)

Each JSON file contains annotations for one watch, keyed by **image filename**.

```jsonc
{
  "PATEK_nab_001_05_face_q3.jpg": {
    "image_size": [1024, 768],
    "coords_norm": {
      "top":    [0.50, 0.10],
      "left":   [0.20, 0.45],
      "right":  [0.80, 0.45],
      "bottom": [0.50, 0.80],
      "center": [0.50, 0.50]
    },
    "annotator": "user_id_or_initials",
    "timestamp": "2025-12-03T10:15:00Z"
  },

  "PATEK_nab_001_06_tiltface_q1.jpg": {
    "image_size": [1024, 768],
    "coords_norm": {
      "top":    [0.50, 0.08],
      "left":   [0.18, 0.40],
      "right":  [0.82, 0.42],
      "bottom": [0.52, 0.78],
      "center": [0.50, 0.50]
    },
    "annotator": "user_id_or_initials",
    "timestamp": "2025-12-03T10:20:00Z"
  }
}
```

Notes:

- `image_size` is `[width, height]` of the image in pixels at the time of annotation.
- All coordinates in `coords_norm` are normalized:

  - `x_norm = x_pixel / width`
  - `y_norm = y_pixel / height`

- `coords_norm` **must contain all 5 keys**: `top`, `left`, `right`, `bottom`, `center` for an image to be considered fully labeled.
- `annotator` can reuse any available user ID/initials (if no user system exists, `"unknown"` is acceptable).
- `timestamp` is ISO8601 in UTC.

### Read/Write Behavior

- On loading the Alignment page for a given watch:

  - Attempt to open `alignment_labels/{watch_id}.json`.
  - If it doesn’t exist, treat as empty (`{}`).

- When saving an annotation for an image:

  - Update or insert the corresponding entry.
  - Write the updated JSON file back to disk.

- Re-annotating an image:

  - The new annotation **overwrites** the previous one for that image.
  - No version history is maintained.

- An image is considered **labeled** if:

  - It has an entry in the watch’s JSON, and
  - `coords_norm` has all 5 keys.

## 5. Integration With Existing Code

### Image Enumeration and Filtering

- Reuse existing image enumeration logic (`downloaded_images/{watch_id}/`).
- Exclude any images under `downloaded_images/.trash/`.
- Use existing filename parsing logic to determine:

  - `watch_id`
  - quality (`q1`, `q2`, `q3`)
  - view type (face / tiltface), if needed for filtering.

### Quality Filter

- The Alignment page’s quality filter should leverage the same quality tags (q1/q2/q3) as the Tagging page.
- Only display images whose quality matches the selected checkboxes.

### Annotation Status Filter

- Before rendering images for a watch:

  - Load the watch’s JSON labels.
  - For each image, determine if it is “labeled” (5 points present).
  - Apply the status filter:
    - `All`: show all images passing quality filter.
    - `Only unlabeled`: show only images with 0 or incomplete annotations.
    - `Only labeled`: show only fully annotated images.

## 6. Implementation Notes (High-Level)

The following is an optional guideline for structure; you can adapt it based on the existing codebase.

### Backend Helpers

Create a helper module, e.g. `tagging/alignment_manager.py`, with functions like:

- `load_alignment_labels(watch_id) -> dict`
- `save_alignment_labels(watch_id, labels_dict) -> None`
- `get_annotation_for_image(watch_id, image_name, labels_dict) -> dict | None`
- `is_image_labeled(annotation_entry) -> bool`

These helpers encapsulate JSON I/O and make it easy for the Streamlit app to use.

### Frontend Logic (Streamlit)

- Add a new Alignment page via Streamlit’s multipage pattern or a top-level mode switch.
- For the selected watch and filters, build the list of images to display.
- For each image:
  - Render the image.
  - Capture mouse clicks and map them to pixel coordinates.
  - Maintain state per image (e.g. in `st.session_state`) with:
    - list of collected points,
    - current step index (0–4),
    - whether it’s been saved.
  - After 5 points:
    - Normalize the coordinates,
    - Save via `alignment_manager`,
    - Mark as labeled in the UI.

Implementation detail of capturing clicks (Plotly, Streamlit custom component, etc.) is left to the engineer’s choice; the requirement is only that the user can click precise locations in order.

## 7. Future Enhancements (Not in v1)

These are useful to keep in mind but are explicitly **out of scope** for the first migration:

- **Alignment preview**:
  - Using the 5 keypoints and a reference template to compute a homography and show an aligned image side-by-side.
- **Advanced editing tools**:
  - Drag/move existing points.
  - Undo last click.
  - Per-point editing instead of full clear & re-annotate.
- **Alignment statistics**:
  - Progress per watch.
  - Global completion percentage for alignment annotations.
- **Pipeline integration**:
  - Scripts or notebook to generate aligned crops from these annotations for training.
- **Model training utilities**:
  - Export labels to a format suitable for training keypoint regression / alignment models.

## 8. Implementation Notes (Final)

### Click Capture Approach - Final Implementation

**Original Plan**: Use Plotly's `on_select` click events to capture point coordinates.

**Issue Encountered**: Plotly's `on_select` is designed to select existing data points in traces (scatter plots, etc.), not to capture arbitrary clicks on the underlying image. Testing revealed that clicks on the image background returned empty point arrays.

**Attempted Solutions**:
1. Plotly with `on_select` - didn't capture background clicks
2. `streamlit-drawable-canvas` - incompatibility with Streamlit 1.50.0
3. `streamlit-plotly-events` - component registration issues, image display problems

**Final Solution**: Switched to `streamlit-image-coordinates` library.
- **Why**: Purpose-built for capturing click coordinates on images in Streamlit
- **Benefit**: Simple API, captures exact pixel coordinates on any click
- **Implementation**: Draw existing points directly on the image using PIL's `ImageDraw`
- **Result**: Clean, reliable click capture with visual feedback

### Updated Dependencies

Added to `requirements.txt`:
```
streamlit-image-coordinates
```

The library provides:
- Direct click coordinate capture on images
- Automatic scaling and coordinate normalization
- Simple integration with Streamlit
- Reliable cross-browser compatibility

## 9. Definition of Done

The Alignment migration is considered complete when:

1. The app exposes a **separate Alignment page/tab**.
2. For any watch, a user can:
   - Filter images by quality and annotation status.
   - See eligible images (excluding `.trash`) as one large image per row.
   - Click the 5 keypoints in order (top, left, right, bottom, center) for each image.
   - Clear and re-annotate any image.
3. Annotations are persisted per watch in `alignment_labels/{watch_id}.json` using the agreed schema.
4. Re-opening the app restores the annotation state correctly (labeled vs unlabeled).
5. Existing quality/view tagging functionality continues to work unchanged.