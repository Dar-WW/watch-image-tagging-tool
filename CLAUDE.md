# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Streamlit-based web application for annotating watch training images. It serves two primary functions:

1. **Tagging Mode**: Tag images with view types (face/tiltface) and quality ratings (q1/q2/q3)
2. **Alignment Mode**: Annotate 5 keypoints on watch images for geometric alignment tasks

The tool manages a dataset of watch images organized by watch ID, with support for image deletion (trash), navigation between watches, and real-time statistics tracking.

## Running the Application

```bash
# First-time setup
./setup.sh

# Run the app
./run_app.sh

# Or manually (from the tagging/ directory)
cd tagging
streamlit run app.py
```

The app runs on `http://localhost:8501` by default.

## Architecture

### Core Components

The application follows a manager-based architecture with clear separation of concerns:

- **`app.py`**: Streamlit UI with three view modes (Tagging, Trash, Alignment). Manages session state and renders interactive components.
- **`image_manager.py`**: Handles watch folder discovery, image loading, file operations (rename, delete, restore), and navigation between watches.
- **`alignment_manager.py`**: Manages alignment keypoint annotations stored as JSON files per watch.
- **`template_manager.py`**: Manages template image annotations (5 keypoints per template) used for homography computation.
- **`filename_parser.py`**: Parses and generates filenames following the pattern: `{WATCH_ID}_{VIEW_NUM}_{VIEW_TYPE}_q{QUALITY}.jpg`

### Data Flow

1. **Image Discovery**: `ImageManager.load_watches()` scans `downloaded_images/` for watch folders
2. **Image Loading**: `ImageManager.load_images(watch_id)` parses filenames and creates `ImageMetadata` objects
3. **Tag Changes**: User interactions trigger `ImageManager.rename_image()` which renames files on disk
4. **Alignment Annotations**: Click events on images are captured, converted to normalized coordinates, and saved via `AlignmentManager.save_image_annotation()`
5. **Template Alignment**: Template keypoints + image keypoints enable homography-based preview warping

### Session State Management

Streamlit's session state is heavily used to maintain:
- Current watch index and loaded images
- Active annotation sessions (per image, stored by filename)
- Cross helper settings (position, rotation, size) per image
- Preview visibility toggles per image
- Quality and status filters for alignment mode

**Important**: Always check if session state keys exist before accessing them. Use `st.session_state.get(key, default)` or initialize in `init_session_state()`.

### Filename Convention

All image filenames follow this strict pattern:
- Tagged: `PATEK_nab_042_04_face_q3.jpg`
- Untagged: `PATEK_nab_042_04_face.jpg`

Components:
- `WATCH_ID`: e.g., `PATEK_nab_042`
- `VIEW_NUM`: 2-digit zero-padded number (e.g., `04`)
- `VIEW_TYPE`: `face` or `tiltface`
- `QUALITY`: Optional `q1`, `q2`, or `q3`

**Critical**: When modifying filename parsing/generation, ensure backward compatibility with both formats.

### Annotation Storage

**Alignment Annotations** (`alignment_labels/{watch_id}.json`):
```json
{
  "PATEK_nab_001_05": {
    "image_size": [1024, 768],
    "coords_norm": {
      "top": [0.50, 0.10],
      "bottom": [0.50, 0.80],
      "left": [0.20, 0.45],
      "right": [0.80, 0.45],
      "center": [0.50, 0.50]
    },
    "annotator": "unknown",
    "timestamp": "2025-12-03T10:15:00Z"
  }
}
```

**Key Design Decisions**:
- Keys use quality-agnostic image IDs (without `_qX` suffix) so annotations persist across quality changes
- Coordinates are normalized to [0, 1] for resolution independence
- One JSON file per watch (not per image) for easier management

**Template Annotations** (`templates/{template_name}/annotations.json`):
- Same format as image annotations
- Used as target coordinates for homography computation
- Template names extracted from watch IDs (e.g., "nab" from "PATEK_nab_042")

### Image Display Components

**Tagging Mode**: Uses Plotly for zoomable/pannable image display with toolbar controls

**Alignment Mode**: Uses `streamlit-image-coordinates` for click-based point placement:
- Displays image at fixed width (1100px) with scaling
- Captures clicks and converts display coordinates back to original image coordinates
- Overlays existing points as red X markers with labels (T/B/L/R/C)
- Optional cross helper overlay (rotatable yellow cross) for precise center identification

### Cross Helper Feature

The cross helper is a sophisticated annotation aid:
- Two modes: "Position Cross" (click to move) and "Annotate Points" (click to place keypoints)
- Settings stored per image: position (x, y normalized), rotation (0-359°), size (0-1)
- Fine-tune controls: sliders + increment/decrement buttons for rotation
- Component reset via counters: `clear_counter` and `cross_position_counter` force re-render with new keys

## Common Workflows

### Adding a New View Mode

1. Add mode to sidebar radio options in `main()`
2. Create render function (e.g., `render_new_view()`)
3. Add conditional in `main()` to call render function
4. Initialize any required session state in `init_session_state()`

### Modifying Alignment Annotation

Key files to modify:
- `render_alignment_card()` in app.py: UI and click handling
- `alignment_manager.py`: JSON persistence logic
- Always preserve the quality-agnostic ID system

### Changing Filename Format

**Warning**: This impacts all file operations and should be done carefully:
1. Update regex patterns in `filename_parser.py`
2. Update `generate_filename()` to match new format
3. Test with both legacy and new formats
4. Consider migration script for existing files

## Important Constraints

- **No selectbox with None values**: Always check `if selected_value is not None:` before calling `.index()` on options list (see app.py:1424, 1496)
- **Image coordinates**: Display size != original size. Always scale coordinates when converting between display and original image dimensions
- **Component keys**: Streamlit components with state need unique, stable keys. Use counters (e.g., `clear_counter`) to force re-renders
- **Trash recovery**: Deleted images in `.trash/` preserve original folder structure for restoration

## Data Directories

- `downloaded_images/`: Watch images organized by watch ID (one folder per watch)
- `downloaded_images/.trash/`: Deleted images preserving folder structure
- `alignment_labels/`: JSON files with keypoint annotations (one per watch)
- `templates/{template_name}/`: Template images and annotations

## Dependencies

Key libraries and their usage:
- **streamlit**: Web UI framework
- **plotly**: Interactive zoomable images (tagging mode)
- **streamlit-image-coordinates**: Click coordinate capture (alignment mode)
- **PIL/Pillow**: Image loading and manipulation
- **opencv-python**: Homography computation for alignment preview
- **numpy**: Array operations for image processing

## Debugging Tips

- Check browser console for Streamlit component errors
- Use `st.write()` to inspect session state during development
- Streamlit reruns on every interaction - be mindful of expensive operations
- Session state persists across reruns but not across server restarts
