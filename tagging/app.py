"""Watch Image Tagging Tool - Streamlit Application

MVP version with core functionality:
- View images in grid
- Tag view_type (face/tiltface) and quality (1/2/3)
- Delete images
- Navigate between watches
"""

import streamlit as st
from PIL import Image
import os
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit.components.v1 as components
import base64
from io import BytesIO
from streamlit_image_coordinates import streamlit_image_coordinates

from image_manager import ImageManager
from filename_parser import ImageMetadata
from alignment_manager import AlignmentManager
from template_manager import TemplateManager
from typing import List, Optional


# Page configuration
st.set_page_config(
    page_title="Watch Image Tagging",
    page_icon="⌚",
    layout="wide"
)


def init_session_state():
    """Initialize Streamlit session state."""
    if 'manager' not in st.session_state:
        st.session_state.manager = ImageManager()
        st.session_state.manager.load_watches()

    if 'refresh_trigger' not in st.session_state:
        st.session_state.refresh_trigger = 0

    if 'view_mode' not in st.session_state:
        st.session_state.view_mode = "Tagging"

    # Alignment manager
    if 'alignment_manager' not in st.session_state:
        st.session_state.alignment_manager = AlignmentManager()

    # Template manager
    if 'template_manager' not in st.session_state:
        st.session_state.template_manager = TemplateManager()

    # Template annotation session
    if 'template_annotation_session' not in st.session_state:
        st.session_state.template_annotation_session = None
        # Structure: {"points": [[x,y], ...], "image_size": (w,h)} or None

    # Template clear counter
    if 'template_clear_counter' not in st.session_state:
        st.session_state.template_clear_counter = 0

    # Preview visibility state (per image)
    if 'preview_visible' not in st.session_state:
        st.session_state.preview_visible = {}
        # Structure: {filename: bool}

    # Alignment filters
    if 'alignment_quality_filter' not in st.session_state:
        st.session_state.alignment_quality_filter = [2, 3]  # Default: q2 and q3

    if 'alignment_status_filter' not in st.session_state:
        st.session_state.alignment_status_filter = "all"

    # Active annotation sessions (per image)
    if 'current_annotation_session' not in st.session_state:
        st.session_state.current_annotation_session = {}
        # Structure: {
        #   "PATEK_nab_001_05_face_q3.jpg": {
        #       "points": [[x1, y1], [x2, y2], ...],  # Up to 5 points in pixel coords
        #       "image_size": (width, height)
        #   }
        # }

    # Clear counter (per image) - incremented when clearing to reset component key
    if 'annotation_clear_counter' not in st.session_state:
        st.session_state.annotation_clear_counter = {}

    # Cross position counter (per image) - incremented when moving cross to reset component
    if 'cross_position_counter' not in st.session_state:
        st.session_state.cross_position_counter = {}

    # Cross helper settings (per image)
    if 'cross_helper_enabled' not in st.session_state:
        st.session_state.cross_helper_enabled = {}
        # Structure: {"image_filename.jpg": True/False}

    if 'cross_helper_settings' not in st.session_state:
        st.session_state.cross_helper_settings = {}
        # Structure: {
        #   "image_filename.jpg": {
        #       "x": 0.5,  # normalized position 0-1
        #       "y": 0.5,  # normalized position 0-1
        #       "rotation": 0,  # degrees
        #       "size": 0.3  # relative to image size
        #   }
        # }

    # Cross helper mode (per image): "annotate" or "position"
    if 'cross_helper_mode' not in st.session_state:
        st.session_state.cross_helper_mode = {}
        # Structure: {"image_filename.jpg": "annotate" or "position"}


def create_zoomable_image(img: Image.Image, filename: str = ""):
    """Create an interactive zoomable image using Plotly.

    Args:
        img: PIL Image object
        filename: Filename to display

    Returns:
        Plotly figure with zoom/pan controls
    """
    # Convert PIL image to numpy array
    img_array = np.array(img)

    # Create plotly figure
    fig = px.imshow(img_array)

    # Update layout for better zoom/pan experience
    fig.update_layout(
        xaxis=dict(
            showgrid=False,
            showticklabels=False,
            zeroline=False,
        ),
        yaxis=dict(
            showgrid=False,
            showticklabels=False,
            zeroline=False,
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        hovermode=False,
        dragmode='pan',  # Default to pan mode
        height=600,  # Bigger height for 2-column layout
    )

    # Configure modebar (toolbar)
    config = {
        'displayModeBar': True,
        'displaylogo': False,
        'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
        'toImageButtonOptions': {
            'format': 'png',
            'filename': filename or 'watch_image',
        }
    }

    return fig, config


def calculate_statistics(manager):
    """Calculate tagging statistics across all watches.

    Args:
        manager: ImageManager instance

    Returns:
        Dictionary with statistics
    """
    stats = {
        'total_images': 0,
        'tagged_images': 0,
        'untagged_images': 0,
        'quality_counts': {1: 0, 2: 0, 3: 0},
        'deleted_images': 0,
        'watch_progress': {}
    }

    # Count deleted images
    if os.path.exists(manager.trash_dir):
        for watch_id in manager.watches:
            trash_watch_dir = os.path.join(manager.trash_dir, watch_id)
            if os.path.exists(trash_watch_dir):
                deleted_count = len([f for f in os.listdir(trash_watch_dir) if f.endswith('.jpg')])
                stats['deleted_images'] += deleted_count

    # Calculate per-watch statistics
    for watch_id in manager.watches:
        images = manager.load_images(watch_id)
        total = len(images)
        tagged = sum(1 for img in images if img.quality is not None)

        stats['total_images'] += total
        stats['tagged_images'] += tagged
        stats['untagged_images'] += (total - tagged)

        # Count quality distribution
        for img in images:
            if img.quality:
                stats['quality_counts'][img.quality] += 1

        # Store per-watch progress
        stats['watch_progress'][watch_id] = {
            'total': total,
            'tagged': tagged,
            'percentage': (tagged / total * 100) if total > 0 else 0
        }

    return stats


def calculate_filtered_watches(manager, quality_filters, view_type_filter, min_images=1):
    """Calculate which watches meet the specified quality and view type criteria.

    Args:
        manager: ImageManager instance
        quality_filters: List of quality values to include (e.g., [2, 3] for q2 and q3)
        view_type_filter: "face" for face only, "both" for face + tiltface
        min_images: Minimum number of matching images required per watch

    Returns:
        Dictionary with filtered results
    """
    results = {
        'matching_watches': [],
        'total_matching_images': 0,
        'watch_details': {}
    }

    for watch_id in manager.watches:
        images = manager.load_images(watch_id)

        # Filter images based on criteria
        matching_images = []
        for img in images:
            # Check quality
            if img.quality not in quality_filters:
                continue

            # Check view type
            if view_type_filter == "face" and img.view_type != "face":
                continue

            matching_images.append(img)

        # Only include watch if it has at least min_images matching images
        if len(matching_images) >= min_images:
            results['matching_watches'].append(watch_id)
            results['total_matching_images'] += len(matching_images)
            results['watch_details'][watch_id] = {
                'count': len(matching_images),
                'images': matching_images
            }

    return results


def render_image_card(image_meta: ImageMetadata, idx: int):
    """Render a single image card with tagging controls.

    Args:
        image_meta: Image metadata
        idx: Index for unique widget keys
    """
    try:
        # Load image
        img = Image.open(image_meta.full_path)

        # Display interactive zoomable image directly
        fig, config = create_zoomable_image(img, filename=image_meta.filename)
        st.plotly_chart(fig, width='stretch', config=config, key=f"plot_{idx}")

        # Show filename
        st.caption(f"**{image_meta.filename}**")
        st.caption("💡 Use toolbar to zoom/pan | Scroll to zoom | Click & drag to pan")

        # View type selector
        current_view = image_meta.view_type if image_meta.view_type else "face"
        view_type = st.radio(
            "View type:",
            options=["face", "tiltface"],
            index=0 if current_view == "face" else 1,
            key=f"view_{idx}",
            horizontal=True,
            label_visibility="collapsed"
        )

        # Details Quality selector
        st.write("**Details Quality:**")
        quality_cols = st.columns(3)
        quality = None

        # Map quality values to labels
        quality_labels = {1: "Bad", 2: "Partial", 3: "Full"}

        for i, q in enumerate([1, 2, 3]):
            with quality_cols[i]:
                button_type = "primary" if image_meta.quality == q else "secondary"
                if st.button(quality_labels[q], key=f"qual_{idx}_{q}", type=button_type, width='stretch'):
                    quality = q

        # If quality button clicked or view type changed, rename file
        if quality is not None or view_type != current_view:
            new_quality = quality if quality is not None else image_meta.quality
            success, message = st.session_state.manager.rename_image(
                image_meta, view_type, new_quality
            )
            if success:
                st.success(message, icon="✅")
                st.session_state.refresh_trigger += 1
                st.rerun()
            else:
                st.error(message, icon="❌")

        # Delete button - direct deletion without confirmation
        if st.button("🗑️ Delete", key=f"del_{idx}", type="secondary", width='stretch'):
            success, message = st.session_state.manager.delete_image(image_meta)
            if success:
                st.success(message, icon="✅")
                st.session_state.refresh_trigger += 1
                st.rerun()
            else:
                st.error(message, icon="❌")

    except Exception as e:
        st.error(f"Error loading image: {e}")


def render_navigation(manager, current_num, total_watches, key_suffix=""):
    """Render navigation buttons.

    Args:
        manager: ImageManager instance
        current_num: Current watch number (1-based)
        total_watches: Total number of watches
        key_suffix: Suffix for button keys to avoid duplicates
    """
    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        if st.button("◀ Previous", disabled=(current_num == 1), width='stretch', key=f"prev_{key_suffix}"):
            manager.prev_watch()
            st.rerun()

    with col3:
        if st.button("Next ▶", disabled=(current_num == total_watches), width='stretch', key=f"next_{key_suffix}"):
            manager.next_watch()
            st.rerun()


def render_trash_view(manager):
    """Render the trash view showing deleted images with restore option.

    Args:
        manager: ImageManager instance
    """
    from datetime import datetime

    st.title("🗑️ Recently Deleted")
    st.write("View and restore deleted images")

    # Load trash images
    trash_images = manager.load_trash_images()

    if not trash_images:
        st.info("No deleted images found. Deleted images will appear here.")
        return

    # Count total deleted images
    total_deleted = sum(len(images) for images in trash_images.values())
    st.write(f"**{total_deleted} deleted images across {len(trash_images)} watches**")

    st.divider()

    # Display by watch
    for watch_id in sorted(trash_images.keys()):
        images = trash_images[watch_id]

        st.subheader(f"📁 {watch_id}")
        st.write(f"{len(images)} deleted images")

        # Display images in 3-column grid
        num_cols = 3
        cols = st.columns(num_cols)

        for idx, (image_meta, deleted_time) in enumerate(images):
            with cols[idx % num_cols]:
                try:
                    # Load and display image (smaller for grid view)
                    img = Image.open(image_meta.full_path)
                    st.image(img, width='stretch')

                    # Show details
                    st.caption(f"**{image_meta.filename}**")
                    deleted_str = datetime.fromtimestamp(deleted_time).strftime("%Y-%m-%d %H:%M:%S")
                    st.caption(f"🕒 Deleted: {deleted_str}")

                    # Restore button
                    if st.button("↩️ Restore", key=f"restore_{watch_id}_{idx}", width='stretch'):
                        success, message = manager.restore_image(image_meta)
                        if success:
                            st.success(message, icon="✅")
                            st.session_state.refresh_trigger += 1
                            st.rerun()
                        else:
                            st.error(message, icon="❌")

                except Exception as e:
                    st.error(f"Error loading image: {e}")

        st.divider()


def pil_to_base64(img: Image.Image) -> str:
    """Convert PIL Image to base64 data URL.

    Args:
        img: PIL Image

    Returns:
        Base64 data URL string
    """
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"


def draw_cross_helper(img: Image.Image, x_norm: float, y_norm: float, rotation: float, size: float) -> Image.Image:
    """Draw a rotatable cross helper on the image.

    Args:
        img: PIL Image to draw on (will be copied)
        x_norm: X position normalized to [0, 1]
        y_norm: Y position normalized to [0, 1]
        rotation: Rotation angle in degrees
        size: Size relative to image (0-1, where 0.3 means 30% of image width)

    Returns:
        New PIL Image with cross overlay
    """
    from PIL import ImageDraw
    import math

    # Create a copy to avoid modifying original
    img_copy = img.copy()
    draw = ImageDraw.Draw(img_copy)

    # Get image dimensions
    width, height = img.size

    # Calculate center point in pixels
    cx = int(x_norm * width)
    cy = int(y_norm * height)

    # Calculate cross arm length based on size parameter
    arm_length = int(min(width, height) * size)

    # Convert rotation to radians
    angle_rad = math.radians(rotation)

    # Calculate endpoints for both lines of the cross
    # Horizontal line (rotated)
    h_dx = int(arm_length * math.cos(angle_rad))
    h_dy = int(arm_length * math.sin(angle_rad))

    # Vertical line (rotated 90 degrees from horizontal)
    v_dx = int(arm_length * math.cos(angle_rad + math.pi/2))
    v_dy = int(arm_length * math.sin(angle_rad + math.pi/2))

    # Draw the cross with semi-transparent lines
    # Horizontal line
    draw.line(
        [(cx - h_dx, cy - h_dy), (cx + h_dx, cy + h_dy)],
        fill=(255, 255, 0, 200),  # Yellow
        width=3
    )

    # Vertical line
    draw.line(
        [(cx - v_dx, cy - v_dy), (cx + v_dx, cy + v_dy)],
        fill=(255, 255, 0, 200),  # Yellow
        width=3
    )

    # Draw center circle
    circle_radius = 5
    draw.ellipse(
        [(cx - circle_radius, cy - circle_radius),
         (cx + circle_radius, cy + circle_radius)],
        outline=(255, 255, 0, 255),
        fill=(255, 255, 0, 128),
        width=2
    )

    return img_copy


def create_clickable_image(img: Image.Image, existing_points: list, key: str,
                          cross_helper_settings: dict = None):
    """Create a clickable image using streamlit-image-coordinates.

    Args:
        img: PIL Image to display
        existing_points: List of [x, y] coordinates of existing points (in original image coordinates)
        key: Unique key for this component
        cross_helper_settings: Optional dict with cross helper settings
                              {"x": float, "y": float, "rotation": float, "size": float}

    Returns:
        Dictionary with 'x' and 'y' keys if clicked (in original image coordinates), None otherwise
    """
    from PIL import ImageDraw, ImageFont

    # Get original image dimensions
    orig_width, orig_height = img.size

    # Apply cross helper if settings provided
    if cross_helper_settings:
        img = draw_cross_helper(
            img,
            cross_helper_settings['x'],
            cross_helper_settings['y'],
            cross_helper_settings['rotation'],
            cross_helper_settings['size']
        )

    # Scale to a reasonable display width (larger than before but not overflowing)
    display_width = 1100

    # Calculate scale factor
    scale = display_width / orig_width
    display_height = int(orig_height * scale)

    # Resize image for display
    img_display = img.resize((display_width, display_height), Image.Resampling.LANCZOS)

    # Draw existing points on the display-sized image
    draw = ImageDraw.Draw(img_display)

    if existing_points:
        point_labels = ['T', 'B', 'L', 'R', 'C']
        for i, (x_orig, y_orig) in enumerate(existing_points):
            label = point_labels[i] if i < len(point_labels) else str(i+1)

            # Scale coordinates to display size
            x = int(x_orig * scale)
            y = int(y_orig * scale)

            # Draw a red X marker (scaled size)
            marker_size = int(20 * scale)
            draw.line([(x - marker_size, y - marker_size), (x + marker_size, y + marker_size)],
                     fill='red', width=max(2, int(4 * scale)))
            draw.line([(x - marker_size, y + marker_size), (x + marker_size, y - marker_size)],
                     fill='red', width=max(2, int(4 * scale)))

            # Draw white outline for text
            text_y = y - int(30 * scale)
            for offset_x in [-1, 0, 1]:
                for offset_y in [-1, 0, 1]:
                    draw.text((x + offset_x, text_y + offset_y), label, fill='black')

            # Draw label text in white
            draw.text((x, text_y), label, fill='white')

    # Display image and capture clicks
    value = streamlit_image_coordinates(
        img_display,
        key=key
    )

    # Process click - scale back to original image coordinates
    if value is not None:
        x_display = value.get('x')
        y_display = value.get('y')

        if x_display is not None and y_display is not None:
            # Scale coordinates back to original image size
            x_orig = int(x_display / scale)
            y_orig = int(y_display / scale)

            # Make sure coordinates are within original image bounds
            x_orig = max(0, min(x_orig, orig_width - 1))
            y_orig = max(0, min(y_orig, orig_height - 1))

            return {'x': x_orig, 'y': y_orig}

    return None


def compute_homography_preview(
    image: Image.Image,
    image_coords_norm: dict,
    template_coords_norm: dict,
    template_size: tuple
) -> Optional[Image.Image]:
    """Compute homography and warp image to align with template.

    Args:
        image: PIL Image to warp
        image_coords_norm: Normalized coordinates dict from image annotation
                          Format: {"top": [x, y], "left": [x, y], ...}
        template_coords_norm: Normalized coordinates dict from template annotation
        template_size: (width, height) of template in pixels

    Returns:
        Warped PIL Image, or None if computation fails
    """
    import cv2
    import numpy as np

    # Convert normalized coords to pixel coordinates
    img_width, img_height = image.size
    template_width, template_height = template_size

    # Use only the 4 edge points for homography (exclude center)
    point_keys = ["top", "left", "right", "bottom"]

    # Build source points (from image)
    src_points = []
    for key in point_keys:
        x_norm, y_norm = image_coords_norm[key]
        x_pixel = x_norm * img_width
        y_pixel = y_norm * img_height
        src_points.append([x_pixel, y_pixel])

    # Build destination points (from template)
    dst_points = []
    for key in point_keys:
        x_norm, y_norm = template_coords_norm[key]
        x_pixel = x_norm * template_width
        y_pixel = y_norm * template_height
        dst_points.append([x_pixel, y_pixel])

    # Convert to numpy arrays
    src_points = np.array(src_points, dtype=np.float32)
    dst_points = np.array(dst_points, dtype=np.float32)

    try:
        # Compute homography matrix
        H, status = cv2.findHomography(src_points, dst_points, cv2.RANSAC, 5.0)

        if H is None:
            return None

        # Convert PIL Image to numpy array
        img_array = np.array(image)

        # Warp image
        warped = cv2.warpPerspective(
            img_array,
            H,
            (template_width, template_height),
            flags=cv2.INTER_LINEAR
        )

        # Convert back to PIL Image
        warped_pil = Image.fromarray(warped)
        return warped_pil

    except Exception as e:
        print(f"Error computing homography: {e}")
        return None


def filter_images_for_alignment(
    images: List[ImageMetadata],
    watch_id: str,
    alignment_manager: AlignmentManager,
    quality_filter: List[int],
    status_filter: str
) -> List[ImageMetadata]:
    """Filter images based on quality and annotation status.

    Args:
        images: List of image metadata
        watch_id: Current watch ID
        alignment_manager: AlignmentManager instance
        quality_filter: List of quality values to include (e.g., [2, 3])
        status_filter: "all", "unlabeled", or "labeled"

    Returns:
        Filtered list of images
    """
    filtered = []

    for img in images:
        # Skip images without quality tags
        if img.quality is None:
            continue

        # Apply quality filter
        if img.quality not in quality_filter:
            continue

        # Apply status filter
        is_labeled = alignment_manager.is_image_labeled(watch_id, img.filename)

        if status_filter == "unlabeled" and is_labeled:
            continue
        if status_filter == "labeled" and not is_labeled:
            continue

        filtered.append(img)

    return filtered


def render_template_annotation_section(template_manager: TemplateManager, template_name: str = "nab"):
    """Render expandable section for annotating template image.

    Args:
        template_manager: TemplateManager instance
        template_name: Template name (default: "nab")
    """
    with st.expander("📐 Template Annotation", expanded=False):
        st.write("**Annotate the template image with 5 keypoints**")
        st.caption("This is done once and used for all alignment previews.")

        # Load template image
        template_path = template_manager.get_template_path(template_name)

        if not os.path.exists(template_path):
            st.error(f"Template image not found: {template_path}")
            return

        try:
            template_img = Image.open(template_path)
            template_size = template_img.size

            # Check if template is already labeled
            is_labeled = template_manager.is_template_labeled(template_name)

            # Initialize or load session state
            if st.session_state.template_annotation_session is None:
                if is_labeled:
                    # Already labeled - no active session
                    st.session_state.template_annotation_session = None
                else:
                    # Start new session
                    st.session_state.template_annotation_session = {
                        "points": [],
                        "image_size": template_size
                    }

            session = st.session_state.template_annotation_session

            # Determine display state
            if session is None and is_labeled:
                # Show saved annotation
                annotation = template_manager.load_template_annotations(template_name)
                display_points = []
                if annotation:
                    coords = annotation["coords_norm"]
                    for key in ["top", "left", "right", "bottom", "center"]:
                        x_norm, y_norm = coords[key]
                        display_points.append([x_norm * template_size[0], y_norm * template_size[1]])

                num_points = 5
                st.success("✅ Template annotated (5/5 points)", icon="✅")

            elif session is not None:
                # Active annotation
                display_points = session["points"]
                num_points = len(display_points)

                if num_points < 5:
                    point_names = ["TOP", "BOTTOM", "LEFT", "RIGHT", "CENTER"]
                    current_point = point_names[num_points]
                    st.info(f"📍 Click {current_point} ({num_points + 1}/5)", icon="📍")
                st.caption(f"Points: {num_points}/5")
            else:
                # No session and not labeled (shouldn't happen)
                display_points = []
                num_points = 0

            # Display clickable image
            clear_counter = st.session_state.template_clear_counter
            click_result = create_clickable_image(
                template_img,
                display_points,
                f"template_{template_name}_{clear_counter}"
            )

            # Handle click event
            if session is not None and click_result:
                if isinstance(click_result, dict) and 'x' in click_result and 'y' in click_result:
                    click_x = click_result['x']
                    click_y = click_result['y']

                    if len(session["points"]) < 5:
                        # Check if new point (avoid duplicates)
                        is_new_point = True
                        if session["points"]:
                            last_x, last_y = session["points"][-1]
                            if abs(click_x - last_x) < 5 and abs(click_y - last_y) < 5:
                                is_new_point = False

                        if is_new_point:
                            session["points"].append([click_x, click_y])

                            # Check if complete
                            if len(session["points"]) == 5:
                                # Build coords dict
                                coords_pixel = {
                                    "top": session["points"][0],
                                    "bottom": session["points"][1],
                                    "left": session["points"][2],
                                    "right": session["points"][3],
                                    "center": session["points"][4]
                                }

                                # Save annotation
                                success, message = template_manager.save_template_annotations(
                                    template_name,
                                    coords_pixel,
                                    template_size
                                )

                                if success:
                                    st.success("✅ Template annotation saved!", icon="✅")
                                    st.session_state.template_annotation_session = None
                                    st.rerun()
                                else:
                                    st.error(f"❌ Failed to save: {message}", icon="❌")
                            else:
                                st.rerun()

            # Undo and Clear buttons side by side
            col1, col2 = st.columns([1, 1])

            with col1:
                # Undo button - only show if there are points to undo
                has_points = session is not None and len(session.get("points", [])) > 0
                if has_points:
                    if st.button("↩️ Undo Last Point", key="undo_template", use_container_width=True):
                        # Remove last point from session
                        session["points"].pop()
                        st.session_state.template_clear_counter += 1
                        st.rerun()

            with col2:
                # Clear button
                if st.button("🔄 Clear & Re-annotate Template", key="clear_template", use_container_width=True):
                    st.session_state.template_annotation_session = {
                        "points": [],
                        "image_size": template_size
                    }
                    st.session_state.template_clear_counter += 1
                    template_manager.clear_template_annotations(template_name)
                    st.rerun()

        except Exception as e:
            st.error(f"❌ Error loading template: {e}")


def create_alignment_image(img: Image.Image, filename: str, points: list, num_points: int):
    """Create interactive image for alignment annotation with point overlays.

    Args:
        img: PIL Image
        filename: Image filename
        points: List of [x, y] pixel coordinates
        num_points: Number of points (for coloring next expected point)

    Returns:
        Plotly figure and config
    """
    img_array = np.array(img)

    # Create base image
    fig = px.imshow(img_array)

    # Add existing points as scatter markers
    if points:
        x_coords = [p[0] for p in points]
        y_coords = [p[1] for p in points]
        point_labels = ['T', 'B', 'L', 'R', 'C'][:len(points)]

        fig.add_trace(go.Scatter(
            x=x_coords,
            y=y_coords,
            mode='markers+text',
            marker=dict(size=20, color='red', symbol='cross', line=dict(width=2, color='white')),
            text=point_labels,
            textposition="top center",
            textfont=dict(size=14, color='white', family='Arial Black'),
            name='Keypoints',
            hoverinfo='text',
            hovertext=[f"{label}: ({int(x)}, {int(y)})" for label, x, y in zip(point_labels, x_coords, y_coords)]
        ))

    # Update layout - disable all interactions except clicking
    fig.update_layout(
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, fixedrange=True),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, fixedrange=True),
        margin=dict(l=0, r=0, t=0, b=0),
        hovermode=False,  # Disable hover
        dragmode=False,  # Disable drag
        height=700,  # Taller for precise clicking
        showlegend=False
    )

    # Config - hide modebar completely for click-only interaction
    config = {
        'displayModeBar': False,  # Hide toolbar completely
        'displaylogo': False,
        'staticPlot': False,  # Keep interactive for clicks
    }

    return fig, config


def render_alignment_card(
    image_meta: ImageMetadata,
    idx: int,
    watch_id: str,
    alignment_manager: AlignmentManager
):
    """Render a single image card for alignment annotation.

    Displays image with click-to-annotate functionality.
    Shows progress (Points: X/5) and Clear button.
    """
    try:
        # Load image
        img = Image.open(image_meta.full_path)
        img_size = img.size  # (width, height)

        # Session key for this image
        session_key = image_meta.filename

        # Initialize or load session state for this image
        if session_key not in st.session_state.current_annotation_session:
            # Check if already labeled
            existing = alignment_manager.get_image_annotation(watch_id, image_meta.filename)
            if existing and alignment_manager.is_image_labeled(watch_id, image_meta.filename):
                # Fully labeled - no active session
                st.session_state.current_annotation_session[session_key] = None
            else:
                # New or incomplete - start fresh session
                st.session_state.current_annotation_session[session_key] = {
                    "points": [],
                    "image_size": img_size
                }

        session = st.session_state.current_annotation_session[session_key]

        # Determine display state
        if session is None:
            # Already fully annotated
            is_labeled = True
            num_points = 5
            # Load saved points for display
            existing = alignment_manager.get_image_annotation(watch_id, image_meta.filename)
            display_points = []
            if existing:
                coords = existing["coords_norm"]
                # Convert normalized back to pixels for overlay
                for key in ["top", "left", "right", "bottom", "center"]:
                    x_norm, y_norm = coords[key]
                    display_points.append([x_norm * img_size[0], y_norm * img_size[1]])
        else:
            # Active annotation session
            is_labeled = False
            num_points = len(session["points"])
            display_points = session["points"]

        # Display filename and cross helper toggle
        col_filename, col_helper = st.columns([3, 1])
        with col_filename:
            st.caption(f"**{image_meta.filename}**")
        with col_helper:
            # Toggle button for cross helper
            is_helper_enabled = st.session_state.cross_helper_enabled.get(session_key, False)
            if st.button("✛ Helper" if not is_helper_enabled else "✛ Hide",
                        key=f"helper_toggle_{idx}",
                        type="primary" if is_helper_enabled else "secondary",
                        width='stretch'):
                st.session_state.cross_helper_enabled[session_key] = not is_helper_enabled
                st.rerun()

        # Cross helper controls (if enabled)
        cross_settings = None
        helper_enabled = st.session_state.cross_helper_enabled.get(session_key, False)

        if helper_enabled:
            # Initialize default settings if not present
            if session_key not in st.session_state.cross_helper_settings:
                st.session_state.cross_helper_settings[session_key] = {
                    "x": 0.5,
                    "y": 0.5,
                    "rotation": 0,
                    "size": 0.45
                }

            # Initialize mode if not present
            if session_key not in st.session_state.cross_helper_mode:
                st.session_state.cross_helper_mode[session_key] = "position"

            # Mode toggle (only show if not fully labeled)
            if not is_labeled:
                current_mode = st.session_state.cross_helper_mode.get(session_key, "position")
                mode_col1, mode_col2 = st.columns(2)

                with mode_col1:
                    if st.button("📍 Annotate Points",
                                key=f"mode_annotate_{idx}",
                                type="primary" if current_mode == "annotate" else "secondary",
                                width='stretch'):
                        st.session_state.cross_helper_mode[session_key] = "annotate"
                        st.rerun()

                with mode_col2:
                    if st.button("🎯 Position Cross",
                                key=f"mode_position_{idx}",
                                type="primary" if current_mode == "position" else "secondary",
                                width='stretch'):
                        st.session_state.cross_helper_mode[session_key] = "position"
                        st.rerun()

                # Show instruction based on mode
                point_names = ["TOP", "BOTTOM", "LEFT", "RIGHT", "CENTER"]
                if current_mode == "annotate":
                    if num_points < 5:
                        current_point = point_names[num_points]
                        st.info(f"📍 Click {current_point} ({num_points + 1}/5)", icon="📍")
                    st.caption(f"Points: {num_points}/5")
                else:
                    st.warning("🎯 POSITION MODE: Click anywhere on the image to move the cross", icon="🎯")
                    current_settings = st.session_state.cross_helper_settings[session_key]
                    st.caption(f"Cross at: ({current_settings['x']:.2f}, {current_settings['y']:.2f}) | Rotation: {current_settings['rotation']}°")
            else:
                st.caption(f"Points: {num_points}/5")

            # Cross helper fine-tune controls in expander
            with st.expander("🎛️ Fine-tune Controls", expanded=False):
                current_settings = st.session_state.cross_helper_settings[session_key]

                col1, col2 = st.columns(2)
                with col1:
                    x_pos = st.slider("X Position", 0.0, 1.0, current_settings["x"],
                                     0.01, key=f"cross_x_{idx}")
                    rotation = st.slider("Rotation (°)", 0, 359, current_settings["rotation"],
                                        1, key=f"cross_rot_{idx}")
                with col2:
                    y_pos = st.slider("Y Position", 0.0, 1.0, current_settings["y"],
                                     0.01, key=f"cross_y_{idx}")
                    size = st.slider("Size", 0.1, 0.6, current_settings["size"],
                                    0.05, key=f"cross_size_{idx}")

                # Update settings
                st.session_state.cross_helper_settings[session_key] = {
                    "x": x_pos,
                    "y": y_pos,
                    "rotation": rotation,
                    "size": size
                }

            cross_settings = st.session_state.cross_helper_settings[session_key]
        else:
            # Helper not enabled - show normal instruction for unlabeled images
            if not is_labeled:
                point_names = ["TOP", "BOTTOM", "LEFT", "RIGHT", "CENTER"]
                if num_points < 5:
                    current_point = point_names[num_points]
                    st.info(f"📍 Click {current_point} ({num_points + 1}/5)", icon="📍")
                st.caption(f"Points: {num_points}/5")

        # Get clear counter for this image (used to reset component state)
        clear_counter = st.session_state.annotation_clear_counter.get(session_key, 0)
        # Get cross position counter (used to reset component when cross moves)
        cross_counter = st.session_state.cross_position_counter.get(session_key, 0)

        # Display clickable image with existing points
        # Include both counters in key to force component reset when cleared or cross moved
        click_result = create_clickable_image(
            img,
            display_points,
            f"click_{idx}_{clear_counter}_{cross_counter}",
            cross_helper_settings=cross_settings
        )

        # Handle click event
        if click_result and isinstance(click_result, dict) and 'x' in click_result and 'y' in click_result:
            click_x = click_result['x']
            click_y = click_result['y']

            # Check current mode
            current_mode = st.session_state.cross_helper_mode.get(session_key, "position")

            # Mode 1: Position Cross - move the cross to clicked position
            if helper_enabled and current_mode == "position":
                # Convert pixel coordinates to normalized [0, 1]
                x_norm = click_x / img_size[0]
                y_norm = click_y / img_size[1]

                # Update cross position
                if session_key in st.session_state.cross_helper_settings:
                    st.session_state.cross_helper_settings[session_key]["x"] = x_norm
                    st.session_state.cross_helper_settings[session_key]["y"] = y_norm
                    # Increment counter to reset component
                    current_cross_counter = st.session_state.cross_position_counter.get(session_key, 0)
                    st.session_state.cross_position_counter[session_key] = current_cross_counter + 1
                    st.success(f"✅ Cross moved to ({x_norm:.2f}, {y_norm:.2f})", icon="🎯")
                    st.rerun()
                else:
                    st.error("Debug: Settings not found", icon="⚠️")

            # Mode 2: Annotate Points - place keypoints
            elif not is_labeled and session is not None:
                # Check if this is a new point (not already in session)
                if len(session["points"]) < 5:
                    # Check if this point is different from the last one (avoid duplicates from re-renders)
                    is_new_point = True
                    if session["points"]:
                        last_x, last_y = session["points"][-1]
                        if abs(click_x - last_x) < 5 and abs(click_y - last_y) < 5:
                            is_new_point = False

                    if is_new_point:
                        # Add point to session
                        session["points"].append([click_x, click_y])

                        # Check if complete (5 points)
                        if len(session["points"]) == 5:
                            # Build coords dict
                            coords_pixel = {
                                "top": session["points"][0],
                                "bottom": session["points"][1],
                                "left": session["points"][2],
                                "right": session["points"][3],
                                "center": session["points"][4]
                            }

                            # Save annotation
                            success, message = alignment_manager.save_image_annotation(
                                watch_id,
                                image_meta.filename,
                                coords_pixel,
                                img_size
                            )

                            if success:
                                st.success(f"✅ Annotation saved!", icon="✅")
                                # Clear session - mark as complete
                                st.session_state.current_annotation_session[session_key] = None
                                st.rerun()
                            else:
                                st.error(f"❌ Failed to save: {message}", icon="❌")
                        else:
                            # Continue to next point
                            st.rerun()

        # Display status for labeled images
        if is_labeled:
            st.success(f"✅ 5/5 points annotated", icon="✅")

        # Undo and Clear buttons side by side
        col1, col2 = st.columns([1, 1])

        with col1:
            # Undo button - only show if there are points to undo
            has_points = session is not None and len(session.get("points", [])) > 0
            if has_points:
                if st.button("↩️ Undo Last Point", key=f"undo_{idx}", use_container_width=True):
                    # Remove last point from session
                    session["points"].pop()
                    # Increment clear counter to force component reset with new key
                    current_counter = st.session_state.annotation_clear_counter.get(session_key, 0)
                    st.session_state.annotation_clear_counter[session_key] = current_counter + 1
                    st.rerun()

        with col2:
            # Clear/Re-annotate button
            if st.button("🔄 Clear & Re-annotate", key=f"clear_{idx}", use_container_width=True):
                # Reset session
                st.session_state.current_annotation_session[session_key] = {
                    "points": [],
                    "image_size": img_size
                }
                # Increment clear counter to force component reset with new key
                current_counter = st.session_state.annotation_clear_counter.get(session_key, 0)
                st.session_state.annotation_clear_counter[session_key] = current_counter + 1
                # Clear from JSON
                alignment_manager.clear_image_annotation(watch_id, image_meta.filename)
                st.rerun()

        # Preview Alignment button (only if fully annotated)
        if is_labeled:
            st.divider()

            template_manager = st.session_state.template_manager
            template_name = "nab"

            # Check if template is annotated
            if not template_manager.is_template_labeled(template_name):
                st.warning("⚠️ Template not annotated. Annotate template above to enable preview.")
            else:
                # Toggle preview button
                preview_key = image_meta.filename
                is_preview_visible = st.session_state.preview_visible.get(preview_key, False)

                button_label = "👁️ Hide Preview" if is_preview_visible else "👁️ Preview Alignment"

                if st.button(button_label, key=f"preview_{idx}", width='stretch'):
                    st.session_state.preview_visible[preview_key] = not is_preview_visible
                    st.rerun()

                # Show preview if visible
                if st.session_state.preview_visible.get(preview_key, False):
                    st.write("**Alignment Preview:**")

                    # Load annotations
                    template_annotation = template_manager.load_template_annotations(template_name)
                    template_path = template_manager.get_template_path(template_name)
                    template_img = Image.open(template_path)
                    template_size = template_img.size

                    image_annotation = alignment_manager.get_image_annotation(watch_id, image_meta.filename)

                    if template_annotation and image_annotation:
                        # Compute homography and warp
                        warped_img = compute_homography_preview(
                            img,
                            image_annotation["coords_norm"],
                            template_annotation["coords_norm"],
                            template_size
                        )

                        if warped_img:
                            # Display side-by-side
                            col1, col2 = st.columns([1, 1])

                            with col1:
                                st.caption("**Original Image**")
                                st.image(img, width='stretch')

                            with col2:
                                st.caption("**Warped to Template**")
                                st.image(warped_img, width='stretch')

                            st.caption("💡 The warped image shows how the watch aligns with the template")
                        else:
                            st.error("❌ Failed to compute alignment preview")

    except Exception as e:
        st.error(f"❌ Error rendering alignment card: {e}")


def render_alignment_view(manager: ImageManager, alignment_manager: AlignmentManager):
    """Render the alignment annotation view."""
    st.title("📍 Watch Image Alignment")

    # Get current watch
    current_watch = manager.get_current_watch()
    current_num, total_watches = manager.get_progress()

    if not current_watch:
        st.warning("No watch folders found in downloaded_images/")
        return

    st.subheader(f"Watch: {current_watch}")
    st.write(f"Progress: {current_num}/{total_watches}")

    # Top navigation
    render_navigation(manager, current_num, total_watches, key_suffix="align_top")
    st.divider()

    # Template annotation section
    render_template_annotation_section(st.session_state.template_manager)
    st.divider()

    # Load images for current watch
    images = manager.load_images()

    if not images:
        st.info("No images found in this watch folder.")
        return

    # Apply filters
    filtered_images = filter_images_for_alignment(
        images,
        current_watch,
        alignment_manager,
        st.session_state.alignment_quality_filter,
        st.session_state.alignment_status_filter
    )

    if not filtered_images:
        st.info("No images match the current filters.")
        return

    st.write(f"**{len(filtered_images)} images matching filters**")

    # Render each image in its own row
    for idx, image_meta in enumerate(filtered_images):
        render_alignment_card(image_meta, idx, current_watch, alignment_manager)
        if idx < len(filtered_images) - 1:  # Don't add divider after last image
            st.divider()

    # Bottom navigation
    st.divider()
    render_navigation(manager, current_num, total_watches, key_suffix="align_bottom")


def main():
    """Main application."""
    init_session_state()

    manager = st.session_state.manager

    # Sidebar - Mode selector at the top
    with st.sidebar:
        st.header("🎛️ View Mode")
        view_mode = st.radio(
            "Select view:",
            options=["Tagging", "Trash", "Alignment"],
            index=0 if st.session_state.view_mode == "Tagging"
                  else (1 if st.session_state.view_mode == "Trash" else 2),
            label_visibility="collapsed"
        )

        # Update mode if changed
        if view_mode != st.session_state.view_mode:
            st.session_state.view_mode = view_mode
            st.rerun()

        st.divider()

        # Alignment-specific sidebar filters
        if st.session_state.view_mode == "Alignment":
            st.header("📊 Alignment Filters")

            # Quality filter checkboxes
            st.write("**Quality:**")
            q1_check = st.checkbox("Bad (q1)", value=False, key="align_q1")
            q2_check = st.checkbox("Partial (q2)", value=True, key="align_q2")
            q3_check = st.checkbox("Full (q3)", value=True, key="align_q3")

            # Update session state
            quality_filter = []
            if q1_check:
                quality_filter.append(1)
            if q2_check:
                quality_filter.append(2)
            if q3_check:
                quality_filter.append(3)
            st.session_state.alignment_quality_filter = quality_filter

            # Annotation status filter
            st.write("**Annotation Status:**")
            status_options = ["all", "unlabeled", "labeled"]
            status_labels = {
                "all": "All images",
                "unlabeled": "Only unlabeled",
                "labeled": "Only labeled"
            }
            status_filter = st.radio(
                "Show:",
                options=status_options,
                format_func=lambda x: status_labels[x],
                key="align_status",
                label_visibility="collapsed"
            )
            st.session_state.alignment_status_filter = status_filter

            st.divider()

            # Jump to watch selector (reuse from Tagging mode pattern)
            st.subheader("🎯 Jump to Watch")

            # Create watch options
            watch_options = []
            for i, watch_id in enumerate(manager.watches):
                # Simple format without annotation progress for v1
                watch_options.append(watch_id)

            selected_watch = st.selectbox(
                "Select watch:",
                options=watch_options,
                index=manager.current_watch_index
            )

            # Update watch if selection changed
            new_index = watch_options.index(selected_watch)
            if new_index != manager.current_watch_index:
                manager.set_watch_index(new_index)
                st.rerun()

            st.divider()

    # Render appropriate view based on mode
    if st.session_state.view_mode == "Trash":
        render_trash_view(manager)
        return
    elif st.session_state.view_mode == "Alignment":
        render_alignment_view(manager, st.session_state.alignment_manager)
        return

    # Main content - Tagging mode
    st.title("⌚ Watch Image Tagging Tool")

    # Get current watch info
    current_watch = manager.get_current_watch()
    current_num, total_watches = manager.get_progress()

    # Sidebar - Only show statistics and navigation in Tagging mode
    if st.session_state.view_mode == "Tagging":
        with st.sidebar:
            st.header("📊 Statistics")

            # Calculate statistics (cached to avoid recalculating on every interaction)
            if 'stats' not in st.session_state or st.session_state.refresh_trigger > st.session_state.get('last_stats_refresh', -1):
                st.session_state.stats = calculate_statistics(manager)
                st.session_state.last_stats_refresh = st.session_state.refresh_trigger

            stats = st.session_state.stats

            # Overall statistics
            st.metric("Total Images", stats['total_images'])
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Tagged", stats['tagged_images'])
            with col2:
                st.metric("Untagged", stats['untagged_images'])

            st.metric("Deleted", stats['deleted_images'])

            # Quality distribution
            st.subheader("Quality Distribution")
            st.write(f"🔴 Bad (q1): {stats['quality_counts'][1]}")
            st.write(f"🟡 Partial (q2): {stats['quality_counts'][2]}")
            st.write(f"🟢 Full (q3): {stats['quality_counts'][3]}")

            st.divider()

            # Jump to watch
            st.subheader("🎯 Jump to Watch")

            # Create watch options with progress
            watch_options = []
            for i, watch_id in enumerate(manager.watches):
                progress = stats['watch_progress'].get(watch_id, {'tagged': 0, 'total': 0})
                label = f"{watch_id} ({progress['tagged']}/{progress['total']})"
                if progress['tagged'] == progress['total'] and progress['total'] > 0:
                    label += " ✓"
                watch_options.append(label)

            selected_label = st.selectbox(
                "Select watch:",
                options=watch_options,
                index=manager.current_watch_index
            )

            # Update watch if selection changed
            new_index = watch_options.index(selected_label)
            if new_index != manager.current_watch_index:
                manager.set_watch_index(new_index)
                st.rerun()

            st.divider()

            # Refresh statistics button
            if st.button("🔄 Refresh Statistics", width='stretch'):
                st.session_state.stats = calculate_statistics(manager)
                st.rerun()

            st.divider()

            # Advanced Info - Filter criteria
            with st.expander("🔍 Advanced Info", expanded=False):
                st.write("**Filter Criteria**")
                st.caption("Set requirements to see which watches qualify")

                # Quality filters
                st.write("**Quality Levels:**")
                q1_check = st.checkbox("Bad (q1)", value=False, key="filter_q1")
                q2_check = st.checkbox("Partial (q2)", value=False, key="filter_q2")
                q3_check = st.checkbox("Full (q3)", value=True, key="filter_q3")

                # Build quality filter list
                quality_filters = []
                if q1_check:
                    quality_filters.append(1)
                if q2_check:
                    quality_filters.append(2)
                if q3_check:
                    quality_filters.append(3)

                st.write("**View Type:**")
                view_type_filter = st.radio(
                    "Include:",
                    options=["face", "both"],
                    format_func=lambda x: "Face only" if x == "face" else "Face + Tiltface",
                    key="filter_view_type"
                )

                st.write("**Minimum Images per Watch:**")
                min_images = st.number_input(
                    "At least:",
                    min_value=1,
                    max_value=20,
                    value=2,
                    step=1,
                    key="filter_min_images",
                    help="Watches must have at least this many images matching the criteria"
                )

                # Only calculate if at least one quality is selected
                if quality_filters:
                    st.divider()

                    # Calculate filtered results
                    filtered = calculate_filtered_watches(manager, quality_filters, view_type_filter, min_images)

                    st.write("**Results:**")
                    st.metric("Watches Meeting Criteria", len(filtered['matching_watches']))
                    st.metric("Total Matching Images", filtered['total_matching_images'])

                    # Show list of matching watches
                    if filtered['matching_watches']:
                        st.write("**Qualifying Watches:**")
                        for watch_id in filtered['matching_watches']:
                            count = filtered['watch_details'][watch_id]['count']
                            st.write(f"• {watch_id} ({count} images)")
                else:
                    st.info("Select at least one quality level")

    if not current_watch:
        st.warning("No watch folders found in downloaded_images/")
        return

    st.subheader(f"Watch: {current_watch}")
    st.write(f"Progress: {current_num}/{total_watches}")

    # Navigation at top
    render_navigation(manager, current_num, total_watches, key_suffix="top")

    st.divider()

    # Load and display images
    images = manager.load_images()

    if not images:
        st.info("No images found in this watch folder.")
        return

    st.write(f"**{len(images)} images**")

    # Display images in 2-column grid (bigger images)
    num_cols = 2
    cols = st.columns(num_cols)

    for idx, image_meta in enumerate(images):
        with cols[idx % num_cols]:
            render_image_card(image_meta, idx)
            st.divider()

    # Navigation at bottom
    st.divider()
    render_navigation(manager, current_num, total_watches, key_suffix="bottom")


if __name__ == "__main__":
    main()
