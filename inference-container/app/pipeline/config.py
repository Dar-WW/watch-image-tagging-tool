"""Pipeline configuration for SageMaker inference container."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any


@dataclass
class PipelineConfig:
    """Configuration for the keypoint prediction pipeline.

    All defaults are set for CPU-only SageMaker Serverless inference.
    """

    # YOLO configuration
    yolo_checkpoint_path: str = "models/yolo_watch_face_best.pt"
    yolo_conf_threshold: float = 0.05
    yolo_padding_factor: float = 1.5
    yolo_device: str = "cpu"

    # LoFTR configuration
    loftr_weights: str = "outdoor"
    loftr_device: str = "cpu"
    loftr_match_threshold: float = 0.2

    # Homography configuration
    ransac_threshold: float = 5.0
    min_inliers: int = 10

    # Template configuration
    templates_dir: str = "templates"
    default_model: str = "nab"

    # Pipeline confidence threshold
    confidence_threshold: float = 0.7

    def to_pipeline_dict(self) -> Dict[str, Any]:
        """Convert to the dictionary format expected by HomographyKeypointsPipeline.

        Returns:
            Configuration dictionary matching the pipeline's expected format.
        """
        # Resolve paths relative to the app directory
        app_dir = Path(__file__).parent.parent

        yolo_path = Path(self.yolo_checkpoint_path)
        if not yolo_path.is_absolute():
            yolo_path = app_dir / yolo_path

        templates_path = Path(self.templates_dir)
        if not templates_path.is_absolute():
            templates_path = app_dir / templates_path

        return {
            "yolo": {
                "checkpoint_path": str(yolo_path),
                "conf_threshold": self.yolo_conf_threshold,
                "padding_factor": self.yolo_padding_factor,
                "device": self.yolo_device,
            },
            "loftr": {
                "weights": self.loftr_weights,
                "device": self.loftr_device,
                "match_threshold": self.loftr_match_threshold,
            },
            "homography": {
                "ransac_threshold": self.ransac_threshold,
                "min_inliers": self.min_inliers,
            },
            "template": {
                "templates_dir": str(templates_path),
                "model": self.default_model,
            },
            "confidence_threshold": self.confidence_threshold,
        }
