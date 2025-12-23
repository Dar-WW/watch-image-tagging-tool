"""Pydantic models for Label Studio request payloads."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LabelStudioTaskData(BaseModel):
    """Data field of a Label Studio task."""

    class Config:
        extra = "allow"  # Allow extra fields from Label Studio

    image: str = Field(..., description="Image path or URL")


class LabelStudioTask(BaseModel):
    """Label Studio task format for predictions.

    Example:
        {
            "data": {
                "image": "/data/local-files/?d=images/PATEK_nab_001/image.jpg"
            },
            "meta": {
                "task_id": 123
            }
        }
    """

    class Config:
        extra = "allow"  # Allow extra fields from Label Studio

    data: LabelStudioTaskData
    meta: Optional[Dict[str, Any]] = Field(default=None, description="Optional metadata")


class LabelStudioBatchRequest(BaseModel):
    """Batch prediction request from Label Studio."""

    class Config:
        extra = "allow"  # Allow extra fields like project, label_config, params

    tasks: List[LabelStudioTask] = Field(..., description="List of tasks to predict")
