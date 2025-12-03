# Watch Image Tagging Tool

A Streamlit-based web application for tagging and managing watch training images. This tool allows you to efficiently tag images with view types, quality ratings, zoom in to inspect details, and manage image datasets.

## 🚀 Quick Start (TL;DR)

**For teammates with Python already installed:**
```bash
git clone <your-repo-url>
cd watch-image-tagging-tool
./setup.sh
./run_app.sh
```

**Don't have Python?** See [Prerequisites](#prerequisites) below for installation instructions.

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

### Check if Python is Already Installed

Before starting, check if you have Python installed:

```bash
python3 --version
```

If you see something like `Python 3.9.x` or higher, you're good to go! Skip to [Installation](#installation).

If you get an error or have an older version, follow the installation instructions below.

---

### Installing Python

**Required**: Python 3.9 or higher

#### macOS

**Option 1: Using Homebrew (Recommended)**
```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python@3.9
```

**Option 2: Download from python.org**
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download the macOS installer (3.9 or higher)
3. Run the installer and follow the instructions

#### Windows

**Option 1: Download from python.org (Recommended)**
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download the Windows installer (3.9 or higher)
3. **Important**: Check "Add Python to PATH" during installation
4. Run the installer and follow the instructions

**Option 2: Using Microsoft Store**
1. Open Microsoft Store
2. Search for "Python 3.9" or higher
3. Click "Get" to install

#### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install python3.9 python3.9-venv python3-pip
```

#### Linux (Fedora/RedHat)

```bash
sudo dnf install python39 python39-pip
```

---

### Verify Installation

After installing Python, verify it works:

```bash
# Check Python version
python3 --version

# Check pip (package installer) is available
pip3 --version
```

You should see version numbers for both commands.

---

## Installation

### Quick Start (Recommended - with Virtual Environment)

1. **Clone this repository:**
   ```bash
   git clone <your-repo-url>
   cd watch-image-tagging-tool
   ```

2. **Run the setup script:**
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

   This will:
   - Create a Python virtual environment (`venv/`)
   - Install all required dependencies
   - Prepare the app for use

3. **Run the app:**
   ```bash
   ./run_app.sh
   ```

   The launch script automatically activates the virtual environment and starts the app.

---

### Manual Setup Options

#### Option 1: Using Virtual Environment (Manual)

1. **Clone this repository:**
   ```bash
   git clone <your-repo-url>
   cd watch-image-tagging-tool
   ```

2. **Create virtual environment:**
   ```bash
   python3 -m venv venv
   ```

3. **Activate virtual environment:**

   On macOS/Linux:
   ```bash
   source venv/bin/activate
   ```

   On Windows:
   ```bash
   venv\Scripts\activate
   ```

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Run the app:**
   ```bash
   ./run_app.sh
   ```

   Or manually:
   ```bash
   cd tagging
   streamlit run app.py
   ```

#### Option 2: Using conda

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

4. **Run the app:**
   ```bash
   ./run_app.sh
   ```

#### Option 3: System Python (Not Recommended)

Only use this if you understand Python dependency management:

```bash
git clone <your-repo-url>
cd watch-image-tagging-tool
pip install -r requirements.txt
./run_app.sh
```

---

### Image Data

The repository includes all watch images in the `downloaded_images/` directory. The expected structure is:

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

If you need to add more images, place them in the appropriate watch folder following the naming convention.

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

### Alignment Annotation Mode

The Alignment mode allows you to annotate 5 keypoints on each watch image for geometric alignment tasks. Uses an interactive canvas for precise point placement.

**How to Use:**

1. Switch to "Alignment" mode in the sidebar
2. Select quality filters (which images to annotate)
   - Bad (q1): Low detail quality images
   - Partial (q2): Medium detail quality images
   - Full (q3): High detail quality images
3. Select annotation status filter
   - All images: Show all images matching quality filter
   - Only unlabeled: Show images without complete annotations
   - Only labeled: Show images with all 5 keypoints annotated
4. For each image, **click directly on the image** to place 5 points in order:
   - **TOP**: Topmost point of watch face
   - **LEFT**: Leftmost point of watch face
   - **RIGHT**: Rightmost point of watch face
   - **BOTTOM**: Bottommost point of watch face
   - **CENTER**: Center point of watch face
5. Annotations save automatically after the 5th point is clicked
6. Use "Clear & Re-annotate" to redo any image

**Visual Feedback:**
- Each clicked point appears as a red dot on the image
- Progress indicator shows which point to click next (e.g., "Click TOP (1/5)")
- Status shows completion: "Points: 3/5" or "✅ 5/5 points annotated"
- Previously placed points remain visible on the canvas

**Annotation Storage:**
- Annotations stored in `alignment_labels/{watch_id}.json`
- Coordinates normalized to [0, 1] range for resolution independence
- Each annotation includes:
  - Normalized coordinates for all 5 keypoints
  - Original image size (width, height)
  - Timestamp (ISO8601 format)
  - Annotator identifier

**JSON Format Example:**
```json
{
  "PATEK_nab_001_05_face_q3.jpg": {
    "image_size": [1024, 768],
    "coords_norm": {
      "top": [0.50, 0.10],
      "left": [0.20, 0.45],
      "right": [0.80, 0.45],
      "bottom": [0.50, 0.80],
      "center": [0.50, 0.50]
    },
    "annotator": "unknown",
    "timestamp": "2025-12-03T10:15:00Z"
  }
}
```

**Tips:**
- Click precisely on the watch face boundaries for accurate keypoints
- The canvas is in "point" mode - just click to place dots
- Annotations persist across sessions - you can close and reopen the app
- Re-annotating an image overwrites the previous annotation (no version history)
- If you make a mistake, use "Clear & Re-annotate" to start over

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
│   ├── alignment_manager.py    # Alignment annotation management
│   └── README.md               # Detailed usage guide
├── alignment_labels/           # Alignment annotations (JSON files)
│   ├── PATEK_nab_001.json
│   ├── PATEK_nab_002.json
│   └── ...
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
- **Interactive Zoom**: Plotly (for tagging mode)
- **Alignment Annotation**: streamlit-drawable-canvas (for precise point placement)
- **File Operations**: Python standard library (os, shutil)
- **Data Storage**: JSON files for alignment annotations

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]