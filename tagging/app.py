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

from image_manager import ImageManager
from filename_parser import ImageMetadata


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
        st.plotly_chart(fig, use_container_width=True, config=config, key=f"plot_{idx}")

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
                if st.button(quality_labels[q], key=f"qual_{idx}_{q}", type=button_type, use_container_width=True):
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
        if st.button("🗑️ Delete", key=f"del_{idx}", type="secondary", use_container_width=True):
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
        if st.button("◀ Previous", disabled=(current_num == 1), use_container_width=True, key=f"prev_{key_suffix}"):
            manager.prev_watch()
            st.rerun()

    with col3:
        if st.button("Next ▶", disabled=(current_num == total_watches), use_container_width=True, key=f"next_{key_suffix}"):
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
                    st.image(img, use_container_width=True)

                    # Show details
                    st.caption(f"**{image_meta.filename}**")
                    deleted_str = datetime.fromtimestamp(deleted_time).strftime("%Y-%m-%d %H:%M:%S")
                    st.caption(f"🕒 Deleted: {deleted_str}")

                    # Restore button
                    if st.button("↩️ Restore", key=f"restore_{watch_id}_{idx}", use_container_width=True):
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


def main():
    """Main application."""
    init_session_state()

    manager = st.session_state.manager

    # Sidebar - Mode selector at the top
    with st.sidebar:
        st.header("🎛️ View Mode")
        view_mode = st.radio(
            "Select view:",
            options=["Tagging", "Trash"],
            index=0 if st.session_state.view_mode == "Tagging" else 1,
            label_visibility="collapsed"
        )

        # Update mode if changed
        if view_mode != st.session_state.view_mode:
            st.session_state.view_mode = view_mode
            st.rerun()

        st.divider()

    # Render appropriate view based on mode
    if st.session_state.view_mode == "Trash":
        render_trash_view(manager)
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
            if st.button("🔄 Refresh Statistics", use_container_width=True):
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
