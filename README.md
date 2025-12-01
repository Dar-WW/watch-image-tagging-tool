# Watch Image Tagging Tool

A Streamlit-based web application for tagging and managing watch training images. This tool allows you to efficiently tag images with view types, quality ratings, zoom in to inspect details, and manage image datasets.

## Features

- 📸 **View images** in a 2-column grid layout with large, zoomable images
- 🏷️ **Tag view type**: face or tiltface
- ⭐ **Tag details quality**: Bad (q1), Partial (q2), or Full (q3)
- 🔍 **Interactive zoom**: Zoom in/out and pan to inspect specific parts of images
- 🗑️ **Delete images**: Move unwanted images to trash (recoverable)
- ⬅️➡️ **Navigate** between watch folders with Previous/Next buttons (top and bottom)
- 📊 **Statistics sidebar**: Real-time tracking of tagging progress, quality distribution, and deleted images
- 🎯 **Jump to watch**: Dropdown selector to quickly navigate to any watch folder
- 💾 **Auto-save**: Changes are saved immediately when you tag an image

## Prerequisites

- Python 3.9 or higher
- pip (Python package installer)

## Installation

### Option 1: Using pip (Recommended)

1. **Clone this repository:**
   ```bash
   git clone <your-repo-url>
   cd watch-image-tagging-tool
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Add your images:**
   Place your watch image folders in the `downloaded_images/` directory. Each watch should have its own folder (e.g., `PATEK_nab_001/`, `PATEK_nab_002/`, etc.).

   Expected structure:
   ```
   downloaded_images/
   ├── PATEK_nab_001/
   │   ├── PATEK_nab_001_01_face.jpg
   │   ├── PATEK_nab_001_02_face.jpg
   │   └── ...
   ├── PATEK_nab_002/
   │   └── ...
   └── ...
   ```

4. **Run the app:**
   ```bash
   ./run_app.sh
   ```

   Or directly:
   ```bash
   cd tagging
   streamlit run app.py
   ```

### Option 2: Using conda

1. **Clone this repository:**
   ```bash
   git clone <your-repo-url>
   cd watch-image-tagging-tool
   ```

2. **Create conda environment:**
   ```bash
   conda create -n watch-tagging python=3.9
   conda activate watch-tagging
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Add your images** (same as Option 1)

5. **Run the app:**
   ```bash
   ./run_app.sh
   ```

## Usage Guide

### Viewing and Zooming Images

- Images are displayed in a 2-column grid with **interactive zoom controls**
- All images are **directly zoomable** - no need to open a separate view
- Each image has a toolbar at the top with zoom/pan controls

**How to Zoom and Pan:**
- **Zoom In/Out**: Use your mouse scroll wheel OR click the zoom buttons in the toolbar
- **Pan**: Click and drag anywhere on the image to move around
- **Box Zoom**: Click and drag to select an area to zoom into
- **Reset View**: Click the home/reset button in the toolbar to return to original view

### Tagging Images

**View Type:**
- Select **face** for front-facing watch face views
- Select **tiltface** for angled/tilted views

**Details Quality:**
- **Bad** (q1): Low detail quality, blurry, or poor image
- **Partial** (q2): Medium detail quality, acceptable
- **Full** (q3): High detail quality, clear and sharp

Changes are saved immediately when you click a button.

### Deleting Images

1. Click the **"🗑️ Delete"** button below the image
2. Image is immediately moved to `downloaded_images/.trash/{watch_id}/`
3. Deleted images can be recovered from the trash folder if needed

### Navigation

- **Previous/Next** buttons at the top AND bottom to move between watch folders
- Progress indicator shows current watch number (e.g., "1/72")
- **Jump to Watch** dropdown in sidebar to select any watch directly

### Sidebar Features

**Statistics:**
- **Total Images**: Total count across all watches
- **Tagged/Untagged**: How many images have quality tags
- **Deleted**: Number of images moved to trash
- **Quality Distribution**: Count of Bad (q1), Partial (q2), and Full (q3) quality images

**Jump to Watch:**
- Dropdown showing all watches with their tagging progress
- Shows format: `PATEK_nab_001 (2/4)` = 2 out of 4 images tagged
- Checkmark (✓) appears when all images in a watch are tagged
- Click to instantly jump to any watch

**Refresh Statistics:**
- Statistics update automatically when you make changes
- Use "Refresh Statistics" button if needed

## Filename Format

Tagged images follow this format:
```
{WATCH_ID}_{VIEW_NUM}_{VIEW_TYPE}_q{QUALITY}.jpg
```

Examples:
- `PATEK_nab_042_04_face_q3.jpg` - face view, full quality
- `PATEK_nab_049_06_tiltface_q2.jpg` - tiltface view, partial quality
- `PATEK_nab_001_03_face_q1.jpg` - face view, bad quality

## Project Structure

```
watch-image-tagging-tool/
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── run_app.sh                  # Launch script
├── tagging/                    # Application code
│   ├── __init__.py
│   ├── app.py                  # Main Streamlit application
│   ├── image_manager.py        # Core business logic & file operations
│   ├── filename_parser.py      # Filename parsing/generation
│   └── README.md               # Detailed usage guide
└── downloaded_images/          # Your watch images (one folder per watch)
    ├── PATEK_nab_001/
    ├── PATEK_nab_002/
    ├── ...
    └── .trash/                 # Deleted images (organized by watch_id)
        ├── PATEK_nab_001/
        └── ...
```

## Tips

- Images are larger in the 2-column layout for better detail inspection
- Use the sidebar statistics to track your overall progress
- Jump to watch dropdown is useful for skipping to specific watches or reviewing completed ones
- Checkmarks (✓) in the watch dropdown indicate fully tagged watches
- Quality tags help filter training data by image clarity
- Deleted images can be recovered from the `.trash/` folder
- Statistics update automatically as you tag images
- Navigation buttons at both top and bottom save scrolling time

## Troubleshooting

### "No watch folders found in downloaded_images/"
- Make sure you have watch folders in the `downloaded_images/` directory
- Each folder should contain `.jpg` image files

### Port already in use
- Streamlit default port is 8501
- If it's already in use, Streamlit will automatically try the next port
- You can specify a different port: `streamlit run app.py --server.port 8502`

### Images not loading
- Check that image files are in `.jpg` format
- Ensure filenames match the expected pattern: `{WATCH_ID}_{VIEW_NUM}_{VIEW_TYPE}.jpg`

## Technical Details

- **UI Framework**: Streamlit
- **Image Processing**: Pillow (PIL)
- **Interactive Zoom**: Plotly
- **File Operations**: Python standard library (os, shutil)

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]