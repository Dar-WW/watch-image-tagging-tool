#!/usr/bin/env python3
"""FastAPI prediction server for Label Studio ML backend.

This server provides pre-annotation predictions for watch image keypoint detection.
"""

import json
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .models.request import LabelStudioTask, LabelStudioBatchRequest
from .models.response import (
    PredictionResponse,
    HealthResponse,
    VersionInfo,
    Prediction,
)
from .core.config import load_config, ServerConfig
from .core.cache import PredictionCache
from .core.path_resolver import PathResolver
from .pipelines.homography_keypoints import HomographyKeypointsPipeline
from .utils.hashing import hash_file, hash_config
from .utils.formatters import (
    pipeline_result_to_prediction,
    create_empty_prediction,
    create_prediction_response,
)

# Global server state
app = FastAPI(
    title="Watch Keypoint Prediction Server",
    description="ML backend for Label Studio watch image annotation",
    version="0.1.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors with request body for debugging."""
    body = await request.body()
    print(f"Validation error on {request.url}")
    print(f"Request body: {body.decode()}")
    print(f"Validation errors: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body.decode()},
    )


# Will be initialized on startup
config: ServerConfig = None
cache: PredictionCache = None
path_resolver: PathResolver = None
pipeline: HomographyKeypointsPipeline = None


@app.on_event("startup")
async def startup_event():
    """Initialize server on startup."""
    global config, cache, path_resolver, pipeline

    # Load configuration
    config_path = Path(__file__).parent / "config.yaml"
    try:
        config = load_config(config_path)
        print(f"Loaded configuration from: {config_path}")
    except Exception as e:
        print(f"Error loading config: {e}")
        print("Using default configuration")
        from .core.config import get_default_config

        config = get_default_config()

    # Initialize cache
    cache_dir = Path(__file__).parent / config.cache.directory
    cache = PredictionCache(cache_dir, enabled=config.cache.enabled)
    print(f"Cache initialized: enabled={config.cache.enabled}, dir={cache_dir}")

    # Initialize path resolver
    path_resolver = PathResolver(
        media_mount=config.paths.media_mount, local_media=config.paths.local_media
    )
    print(f"Path resolver initialized: mount={config.paths.media_mount}")

    # Initialize pipeline
    pipeline_config = config.pipeline.dict()
    pipeline = HomographyKeypointsPipeline(pipeline_config)
    print(f"Pipeline initialized: {pipeline.get_version()}")

    print("Server startup complete")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for Label Studio ML backend.

    Label Studio expects this endpoint to return {"status": "UP"}.

    Returns:
        HealthResponse: Server status
    """
    return HealthResponse(
        status="UP",
        model_class="HomographyKeypointsPipeline"
    )


@app.get("/version", response_model=VersionInfo)
async def version_info():
    """Get server and pipeline version information.

    Returns:
        VersionInfo: Version and configuration details
    """
    if pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline not initialized",
        )

    pipeline_info = pipeline.get_info()

    return VersionInfo(
        version=config.server.version,
        pipeline=pipeline_info["type"],
        pipeline_version=pipeline_info["version"],
        config={
            "confidence_threshold": config.pipeline.confidence_threshold,
            "cache_enabled": config.cache.enabled,
        },
    )


@app.post("/predict")
async def predict(request: LabelStudioBatchRequest):
    """Generate predictions for tasks (Label Studio sends batch format).

    Args:
        request: Batch request with tasks array

    Returns:
        Dict with "results" key containing list of predictions (Label Studio ML backend format)

    Raises:
        HTTPException: If image path is invalid or prediction fails
    """
    if pipeline is None or path_resolver is None or cache is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server not fully initialized",
        )

    predictions = []

    # Process each task in the batch
    for task in request.tasks:
        # Log incoming request for debugging
        print(f"Received predict request: image={task.data.image}")

        # Resolve image path
        image_path = path_resolver.resolve(task.data.image)

        if image_path is None or not path_resolver.validate_path(image_path):
            # Return empty prediction for invalid path
            prediction = create_empty_prediction(
                model_version=pipeline.get_version(),
                reason="invalid_image_path",
                error_message=f"Image not found: {task.data.image}",
            )
            predictions.append(prediction)
            continue

        # Generate cache key
        try:
            image_hash = hash_file(image_path)
            config_hash = hash_config(config.pipeline.dict())
            cache_key = cache.make_key(
                image_hash, pipeline.get_version(), config_hash
            )
        except Exception as e:
            print(f"Error generating cache key: {e}")
            cache_key = None

        # Check cache
        if cache_key and cache.enabled:
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                print(f"Cache hit for: {image_path.name}")
                # Use cached prediction
                predictions.append(Prediction(**cached_result))
                continue

        # Run pipeline
        try:
            print(f"Running prediction for: {image_path.name}")
            result = pipeline.predict(image_path)

            # Convert to Label Studio format
            prediction = pipeline_result_to_prediction(result, pipeline.get_version())

            # Cache result if successful
            if cache_key and cache.enabled and result.success:
                cache.set(cache_key, prediction.dict())

            predictions.append(prediction)

        except Exception as e:
            print(f"Prediction error: {e}")
            # Return empty prediction with error
            prediction = create_empty_prediction(
                model_version=pipeline.get_version(),
                reason="pipeline_error",
                error_message=str(e),
            )
            predictions.append(prediction)

    # Return dict with "results" key (Label Studio ML backend format)
    # NOTE: Label Studio expects "results" key, not "predictions"
    # See: https://github.com/HumanSignal/label-studio/issues/7630
    response = {"results": [pred.dict() for pred in predictions]}

    # Log the prediction response for debugging
    print(f"\n{'='*80}")
    print(f"PREDICTION RESPONSE ({len(predictions)} predictions):")
    print(f"{'='*80}")
    for i, pred in enumerate(predictions):
        pred_dict = pred.dict()
        print(f"\nPrediction {i+1}:")
        print(f"  Model version: {pred_dict.get('model_version', 'N/A')}")
        print(f"  Score: {pred_dict.get('score', 0):.3f}")

        if pred_dict.get('result'):
            print(f"  Keypoints ({len(pred_dict['result'])} points):")
            for kp in pred_dict['result']:
                label = kp['value']['keypointlabels'][0] if kp['value'].get('keypointlabels') else 'Unknown'
                x = kp['value'].get('x', 0)
                y = kp['value'].get('y', 0)
                print(f"    - {label:8s}: x={x:6.2f}%, y={y:6.2f}%")
        else:
            print(f"  No keypoints (empty result)")
    print(f"{'='*80}\n")

    # Log the exact JSON response being sent to Label Studio
    print(f"RAW JSON RESPONSE:")
    print(json.dumps(response, indent=2))
    print(f"{'='*80}\n")

    return response


@app.post("/predict_batch", response_model=PredictionResponse)
async def predict_batch(request: LabelStudioBatchRequest):
    """Generate predictions for multiple tasks (optional endpoint).

    Args:
        request: Batch request with multiple tasks

    Returns:
        PredictionResponse: Predictions for all tasks

    Note:
        This is a simple sequential implementation.
        For production, consider async processing or task queue.
    """
    if pipeline is None or path_resolver is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server not fully initialized",
        )

    predictions = []

    for task in request.tasks:
        # Run prediction for each task
        response = await predict(task)
        predictions.extend(response.predictions)

    return create_prediction_response(predictions)


@app.post("/setup")
async def setup(request: Dict[str, Any]):
    """Label Studio ML backend setup endpoint.

    This endpoint is called by Label Studio to validate the ML backend
    and provide the labeling configuration.

    Args:
        request: Setup request from Label Studio with project info

    Returns:
        dict: Model information and capabilities
    """
    if pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline not initialized",
        )

    # Label Studio sends project info including labeling config
    # We acknowledge receipt but don't need to do anything with it
    # since our pipeline is pre-configured

    pipeline_info = pipeline.get_info()

    return {
        "model_version": pipeline.get_version(),
        "model_type": pipeline_info["type"],
        "description": pipeline_info["description"],
        "config": pipeline_info.get("config", {}),
        "setup_complete": True,
        "supports_preannotations": True,
        "supports_training": False,  # We use pre-trained models
    }


@app.post("/train")
async def train(request: Dict[str, Any]):
    """Label Studio ML backend training endpoint.

    This endpoint is called when Label Studio wants to train/update the model.
    Since we use pre-trained models (YOLO, LoFTR), we don't support training.

    Args:
        request: Training request from Label Studio

    Returns:
        dict: Training status (not supported)
    """
    return {
        "status": "skipped",
        "message": "Training not supported - using pre-trained YOLO and LoFTR models",
        "model_version": pipeline.get_version() if pipeline else "unknown",
    }


@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - acts as health check for Label Studio.

    Label Studio can use either / or /health for health checks.
    """
    return HealthResponse(
        status="UP",
        model_class="HomographyKeypointsPipeline"
    )


@app.get("/info")
async def server_info():
    """Server information endpoint."""
    return {
        "name": "Watch Keypoint Prediction Server",
        "version": "0.1.0" if config is None else config.server.version,
        "endpoints": {
            "health": "/health",
            "version": "/version",
            "setup": "/setup",
            "predict": "/predict",
            "predict_batch": "/predict_batch",
            "train": "/train",
            "info": "/info",
        },
    }


if __name__ == "__main__":
    import uvicorn

    # For local development
    uvicorn.run(
        "prediction_server.main:app",
        host="0.0.0.0",
        port=9090,
        reload=True,
        log_level="info",
    )
