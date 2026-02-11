"""Predictor orchestrator: S3 download -> pipeline predict -> format response."""

import logging
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import PipelineConfig
from .homography_keypoints import HomographyKeypointsPipeline
from .loaders import S3ImageLoader
from .pipeline_result import PipelineResult

logger = logging.getLogger(__name__)

# Temp directory for downloaded images
TEMP_DIR = Path("/tmp/inference")


class Predictor:
    """Orchestrates S3 image download, pipeline prediction, and response formatting.

    Loads the pipeline once and reuses it across requests. Templates are
    switched per-request via the pipeline's load_template() method.
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        """Initialize the predictor with pipeline and S3 loader.

        Args:
            config: Pipeline configuration. Uses defaults if not provided.
        """
        self.config = config or PipelineConfig()
        logger.info("Initializing prediction pipeline...")

        pipeline_dict = self.config.to_pipeline_dict()
        self.pipeline = HomographyKeypointsPipeline(pipeline_dict)
        self.s3_loader = S3ImageLoader()

        logger.info("Predictor initialized successfully")

    def predict_batch(
        self,
        images: List[Dict[str, str]],
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run predictions on a batch of S3 images.

        Args:
            images: List of dicts with "s3_bucket" and "s3_key" fields.
            job_id: Optional job identifier for temp directory isolation.

        Returns:
            Response dict with predictions list and metadata.
        """
        if job_id is None:
            job_id = uuid.uuid4().hex[:12]

        job_dir = TEMP_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        predictions = []

        try:
            for i, image_ref in enumerate(images):
                bucket = image_ref["s3_bucket"]
                key = image_ref["s3_key"]
                filename = Path(key).name

                logger.info(f"Processing image {i + 1}/{len(images)}: s3://{bucket}/{key}")

                try:
                    result = self._predict_single(bucket, key, job_dir)
                    predictions.append(result)
                except FileNotFoundError as e:
                    logger.error(f"Image not found: {e}")
                    predictions.append({
                        "filename": filename,
                        "s3_bucket": bucket,
                        "s3_key": key,
                        "success": False,
                        "error": str(e),
                    })
                except Exception as e:
                    logger.error(f"Prediction failed for {filename}: {e}", exc_info=True)
                    predictions.append({
                        "filename": filename,
                        "s3_bucket": bucket,
                        "s3_key": key,
                        "success": False,
                        "error": str(e),
                    })

        finally:
            # Clean up temp files
            if job_dir.exists():
                shutil.rmtree(job_dir, ignore_errors=True)
                logger.debug(f"Cleaned up temp directory: {job_dir}")

        return {
            "job_id": job_id,
            "total": len(images),
            "successful": sum(1 for p in predictions if p.get("success")),
            "predictions": predictions,
        }

    def _predict_single(
        self, bucket: str, key: str, job_dir: Path
    ) -> Dict[str, Any]:
        """Download and predict a single image.

        Args:
            bucket: S3 bucket name.
            key: S3 object key.
            job_dir: Temp directory for this job.

        Returns:
            Prediction result dict.
        """
        # Download from S3
        local_path = self.s3_loader.download(bucket, key, job_dir)
        filename = local_path.name

        # Run pipeline prediction
        result: PipelineResult = self.pipeline.predict(local_path)

        # Format response
        response = {
            "filename": filename,
            "s3_bucket": bucket,
            "s3_key": key,
            "success": result.success,
            "confidence": result.confidence,
            "image_width": result.image_width,
            "image_height": result.image_height,
            "debug_info": result.debug_info,
        }

        if result.success and result.keypoints:
            response["keypoints"] = {
                "top": list(result.keypoints.top),
                "bottom": list(result.keypoints.bottom),
                "left": list(result.keypoints.left),
                "right": list(result.keypoints.right),
                "center": list(result.keypoints.center),
            }
        else:
            response["keypoints"] = None
            response["error"] = result.error_message

        return response

    def warmup(self) -> Dict[str, Any]:
        """Run a warmup pass to ensure models are loaded and ready.

        Returns:
            Warmup status dict.
        """
        info = self.pipeline.get_info()
        return {
            "status": "ok",
            "pipeline": info,
        }
