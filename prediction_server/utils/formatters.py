"""Format prediction results to Label Studio schema."""

import uuid
from typing import Dict, List, Tuple, Optional, Any

from ..models.response import (
    ResultItem,
    KeypointValue,
    RectangleValue,
    Prediction,
    PredictionResponse,
)
from ..models.pipeline_result import PipelineResult, KeypointCoords, BoundingBox


def format_keypoint(
    coords_norm: Tuple[float, float],
    label: str,
    image_width: int,
    image_height: int,
    from_name: str = "keypoints",
    to_name: str = "image",
) -> ResultItem:
    """Convert normalized keypoint to Label Studio format.

    Args:
        coords_norm: Normalized coordinates (0-1) as (x, y)
        label: Keypoint label (e.g., "Top", "Center")
        image_width: Original image width in pixels
        image_height: Original image height in pixels
        from_name: Label Studio labeling tool name
        to_name: Label Studio data field name

    Returns:
        ResultItem: Label Studio keypoint annotation with image dimensions
    """
    x_norm, y_norm = coords_norm

    # Convert from normalized (0-1) to percent (0-100)
    x_percent = x_norm * 100.0
    y_percent = y_norm * 100.0

    return ResultItem(
        id=_generate_id(),
        from_name=from_name,
        to_name=to_name,
        type="keypointlabels",
        original_width=image_width,
        original_height=image_height,
        image_rotation=0,
        value=KeypointValue(
            x=round(x_percent, 2),
            y=round(y_percent, 2),
            width=1.5,
            keypointlabels=[label]
        ),
    )


def format_rectangle(
    bbox: BoundingBox,
    label: str = "ROI",
    from_name: str = "crop_roi",
    to_name: str = "image",
) -> ResultItem:
    """Convert normalized bounding box to Label Studio format.

    Args:
        bbox: Bounding box with normalized coordinates (0-1)
        label: Rectangle label
        from_name: Label Studio labeling tool name
        to_name: Label Studio data field name

    Returns:
        ResultItem: Label Studio rectangle annotation
    """
    # Convert from normalized (0-1) to percent (0-100)
    x_percent = bbox.x * 100.0
    y_percent = bbox.y * 100.0
    width_percent = bbox.width * 100.0
    height_percent = bbox.height * 100.0

    return ResultItem(
        id=_generate_id(),
        from_name=from_name,
        to_name=to_name,
        type="rectanglelabels",
        value=RectangleValue(
            x=round(x_percent, 2),
            y=round(y_percent, 2),
            width=round(width_percent, 2),
            height=round(height_percent, 2),
            rectanglelabels=[label],
        ),
    )


def format_keypoints_all(
    keypoints: KeypointCoords,
    image_width: int,
    image_height: int,
    from_name: str = "keypoints",
    to_name: str = "image"
) -> List[ResultItem]:
    """Convert all 5 keypoints to Label Studio format.

    Args:
        keypoints: KeypointCoords with all 5 points
        image_width: Original image width in pixels
        image_height: Original image height in pixels
        from_name: Label Studio labeling tool name
        to_name: Label Studio data field name

    Returns:
        list: List of 5 ResultItem objects (one per keypoint)
    """
    # Map keypoint names to Label Studio labels
    keypoint_labels = {
        "top": "Top",
        "bottom": "Bottom",
        "left": "Left",
        "right": "Right",
        "center": "Center",
    }

    results = []

    for key, label in keypoint_labels.items():
        coords = getattr(keypoints, key)
        result_item = format_keypoint(coords, label, image_width, image_height, from_name, to_name)
        results.append(result_item)

    return results


def pipeline_result_to_prediction(
    result: PipelineResult, model_version: str = "unknown"
) -> Prediction:
    """Convert internal PipelineResult to Label Studio Prediction format.

    Args:
        result: Internal pipeline result
        model_version: Model version string

    Returns:
        Prediction: Label Studio prediction object
    """
    result_items = []

    # Get image dimensions (use defaults if not available)
    image_width = result.image_width or 2048
    image_height = result.image_height or 2048

    # Add ROI if present
    if result.roi is not None:
        roi_item = format_rectangle(result.roi)
        result_items.append(roi_item)

    # Add keypoints if present
    if result.keypoints is not None:
        keypoint_items = format_keypoints_all(result.keypoints, image_width, image_height)
        result_items.extend(keypoint_items)

    # Build debug info
    debug_info = result.debug_info.copy() if result.debug_info else {}
    if result.error_message:
        debug_info["error"] = result.error_message
    if not result.success:
        debug_info["reason"] = debug_info.get("reason", "prediction_failed")

    return Prediction(
        result=result_items,
        score=round(result.confidence, 3),
        model_version=model_version,
        debug=debug_info if debug_info else None,
    )


def create_empty_prediction(
    model_version: str = "unknown",
    reason: str = "prediction_failed",
    error_message: Optional[str] = None,
) -> Prediction:
    """Create empty prediction for failure cases.

    Args:
        model_version: Model version string
        reason: Failure reason code
        error_message: Human-readable error message

    Returns:
        Prediction: Empty prediction with debug info
    """
    debug_info = {"reason": reason}
    if error_message:
        debug_info["error"] = error_message

    return Prediction(
        result=[],
        score=0.0,
        model_version=model_version,
        debug=debug_info,
    )


def create_prediction_response(predictions: List[Prediction]) -> PredictionResponse:
    """Wrap predictions in response format.

    Args:
        predictions: List of predictions

    Returns:
        PredictionResponse: Complete response object
    """
    return PredictionResponse(predictions=predictions)


def _generate_id() -> str:
    """Generate unique ID for annotations.

    Returns:
        str: 8-character unique ID
    """
    return str(uuid.uuid4())[:8]
