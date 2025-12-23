"""Pydantic models for Label Studio response payloads."""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class KeypointValue(BaseModel):
    """Keypoint annotation value in Label Studio format."""

    x: float = Field(..., description="X coordinate in percent (0-100)")
    y: float = Field(..., description="Y coordinate in percent (0-100)")
    width: float = Field(default=1.5, description="Keypoint size in percent (0-100)")
    keypointlabels: List[str] = Field(..., description="Keypoint label(s)")


class RectangleValue(BaseModel):
    """Rectangle annotation value in Label Studio format."""

    x: float = Field(..., description="Top-left X in percent (0-100)")
    y: float = Field(..., description="Top-left Y in percent (0-100)")
    width: float = Field(..., description="Width in percent (0-100)")
    height: float = Field(..., description="Height in percent (0-100)")
    rectanglelabels: List[str] = Field(..., description="Rectangle label(s)")


class ResultItem(BaseModel):
    """Single result item (keypoint or rectangle) in Label Studio format."""

    id: Optional[str] = Field(default=None, description="Unique ID for this annotation")
    from_name: str = Field(..., description="Name of the labeling tool")
    to_name: str = Field(..., description="Name of the data field")
    type: str = Field(..., description="Type of annotation (keypointlabels or rectanglelabels)")
    original_width: Optional[int] = Field(default=None, description="Original image width in pixels")
    original_height: Optional[int] = Field(default=None, description="Original image height in pixels")
    image_rotation: Optional[int] = Field(default=0, description="Image rotation in degrees")
    value: Union[KeypointValue, RectangleValue] = Field(..., description="Annotation value")
    score: Optional[float] = Field(default=None, description="Confidence score for this item")


class Prediction(BaseModel):
    """Single prediction with results and metadata."""

    result: List[ResultItem] = Field(default_factory=list, description="List of annotations")
    score: float = Field(default=0.0, description="Overall confidence score (0-1)")
    model_version: str = Field(default="unknown", description="Model version identifier")
    debug: Optional[Dict[str, Any]] = Field(default=None, description="Debug information")


class PredictionResponse(BaseModel):
    """Response format for Label Studio ML backend.

    Example:
        {
            "predictions": [{
                "result": [
                    {
                        "from_name": "keypoints",
                        "to_name": "image",
                        "type": "keypointlabels",
                        "value": {"x": 50.0, "y": 50.0, "keypointlabels": ["Center"]}
                    }
                ],
                "score": 0.95,
                "model_version": "homography-v1.0",
                "debug": {"method": "YOLO-LoFTR-Homography"}
            }]
        }
    """

    predictions: List[Prediction] = Field(default_factory=list, description="List of predictions")


class HealthResponse(BaseModel):
    """Health check response for Label Studio ML backend."""

    status: str = Field(default="UP", description="Server status (Label Studio expects 'UP')")
    model_class: Optional[str] = Field(default=None, description="Model class name (optional)")


class VersionInfo(BaseModel):
    """Version information response."""

    version: str = Field(..., description="Server version")
    pipeline: str = Field(..., description="Pipeline type")
    pipeline_version: str = Field(..., description="Pipeline version")
    config: Optional[Dict[str, Any]] = Field(default=None, description="Configuration info")
