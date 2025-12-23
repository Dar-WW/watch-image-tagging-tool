"""Internal pipeline result format (before conversion to Label Studio format)."""

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class KeypointCoords(BaseModel):
    """Keypoint coordinates in normalized format (0-1)."""

    top: Tuple[float, float] = Field(..., description="Top keypoint [x, y]")
    bottom: Tuple[float, float] = Field(..., description="Bottom keypoint [x, y]")
    left: Tuple[float, float] = Field(..., description="Left keypoint [x, y]")
    right: Tuple[float, float] = Field(..., description="Right keypoint [x, y]")
    center: Tuple[float, float] = Field(..., description="Center keypoint [x, y]")


class BoundingBox(BaseModel):
    """Bounding box in normalized format (0-1)."""

    x: float = Field(..., description="Top-left X (normalized)")
    y: float = Field(..., description="Top-left Y (normalized)")
    width: float = Field(..., description="Width (normalized)")
    height: float = Field(..., description="Height (normalized)")


class PipelineResult(BaseModel):
    """Internal result format from prediction pipeline.

    This is the normalized internal format that gets converted to
    Label Studio format for the API response.

    Coordinates are in normalized 0-1 range, not Label Studio's 0-100 percent.
    """

    success: bool = Field(..., description="Whether prediction succeeded")
    keypoints: Optional[KeypointCoords] = Field(default=None, description="Detected keypoints")
    roi: Optional[BoundingBox] = Field(default=None, description="Region of interest")
    confidence: float = Field(default=0.0, description="Overall confidence (0-1)")
    image_width: Optional[int] = Field(default=None, description="Original image width in pixels")
    image_height: Optional[int] = Field(default=None, description="Original image height in pixels")
    debug_info: Dict[str, Any] = Field(default_factory=dict, description="Debug metadata")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
