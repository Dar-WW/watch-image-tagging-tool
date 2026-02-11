"""FastAPI server implementing the SageMaker inference contract.

Endpoints:
    GET  /ping         - Health check (returns 200 when ready)
    POST /invocations  - Run predictions or warmup
"""

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.pipeline.predictor import Predictor
from app.pipeline.config import PipelineConfig

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Watch Keypoint Inference", version="1.0.0")

# Global predictor singleton (lazy-initialized)
_predictor: Optional[Predictor] = None


def get_predictor() -> Predictor:
    """Get or create the global predictor singleton."""
    global _predictor
    if _predictor is None:
        logger.info("Initializing predictor singleton...")
        config = PipelineConfig()
        _predictor = Predictor(config)
        logger.info("Predictor singleton ready")
    return _predictor


# --- Request/Response Models ---


class ImageRef(BaseModel):
    """Reference to an image in S3."""

    s3_bucket: str = Field(..., description="S3 bucket name")
    s3_key: str = Field(..., description="S3 object key")


class InvocationRequest(BaseModel):
    """Request body for /invocations."""

    warmup: bool = Field(default=False, description="If true, run warmup only (no prediction)")
    images: List[ImageRef] = Field(default_factory=list, description="List of S3 image references")
    job_id: Optional[str] = Field(default=None, description="Optional job identifier")


class KeypointResult(BaseModel):
    """Keypoints in normalized [0,1] coordinates."""

    top: List[float]
    bottom: List[float]
    left: List[float]
    right: List[float]
    center: List[float]


class PredictionResult(BaseModel):
    """Result for a single image prediction."""

    filename: str
    s3_bucket: str
    s3_key: str
    success: bool
    confidence: Optional[float] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    keypoints: Optional[KeypointResult] = None
    error: Optional[str] = None
    debug_info: Optional[Dict[str, Any]] = None


class InvocationResponse(BaseModel):
    """Response body for /invocations."""

    job_id: Optional[str] = None
    total: Optional[int] = None
    successful: Optional[int] = None
    predictions: Optional[List[PredictionResult]] = None
    warmup: Optional[Dict[str, Any]] = None


# --- Endpoints ---


@app.get("/ping")
def ping():
    """SageMaker health check endpoint.

    Returns 200 when the container is healthy and ready to serve.
    Initializes the predictor on first call if not already done.
    """
    try:
        get_predictor()
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return Response(status_code=503)


@app.post("/invocations", response_model=InvocationResponse)
def invocations(request: InvocationRequest):
    """SageMaker inference endpoint.

    Accepts either a warmup request or a batch of S3 image references.
    """
    predictor = get_predictor()

    # Handle warmup
    if request.warmup:
        logger.info("Running warmup...")
        result = predictor.warmup()
        return InvocationResponse(warmup=result)

    # Validate images
    if not request.images:
        raise HTTPException(
            status_code=400,
            detail="Either 'warmup: true' or a non-empty 'images' list is required",
        )

    # Run batch prediction
    logger.info(f"Running prediction on {len(request.images)} images...")
    result = predictor.predict_batch(
        images=[img.model_dump() for img in request.images],
        job_id=request.job_id,
    )

    return InvocationResponse(
        job_id=result["job_id"],
        total=result["total"],
        successful=result["successful"],
        predictions=result["predictions"],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080, workers=1)
