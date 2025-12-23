"""Homography-based keypoint prediction pipeline."""

import logging
from typing import Dict, Any, Tuple
from pathlib import Path
import numpy as np
import cv2

from .base import BasePipeline
from .yolo_utils import YOLODetector
from .loftr_utils import LoFTRMatcher
from ..core.template_loader import TemplateLoader
from ..models.pipeline_result import PipelineResult, KeypointCoords

logger = logging.getLogger(__name__)


class HomographyKeypointsPipeline(BasePipeline):
    """Pipeline using YOLO → LoFTR → Homography → Keypoint projection.

    Two-phase alignment pipeline:
    1. Phase 1 (YOLO): Detect oriented bounding box and de-rotate watch face
    2. Phase 2 (LoFTR): Dense feature matching for homography refinement
    3. Keypoint Projection: Transform template keypoints to query image
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize pipeline with configuration.

        Args:
            config: Pipeline configuration including:
                - yolo: YOLO configuration (checkpoint_path, conf_threshold, device)
                - loftr: LoFTR configuration (weights, device, match_threshold)
                - homography: Homography configuration (ransac_threshold, min_inliers)
                - template: Template configuration (templates_dir, model)
                - confidence_threshold: Minimum confidence for predictions
        """
        super().__init__(config)
        self.model_version = "yolo-loftr-homography-v1.0"

        # Initialize YOLO detector
        yolo_config = config.get('yolo', {})
        try:
            self.yolo_detector = YOLODetector(
                checkpoint_path=yolo_config.get('checkpoint_path', 'models/yolo_watch_face_best.pt'),
                conf_threshold=yolo_config.get('conf_threshold', 0.25),
                device=yolo_config.get('device', 'auto')
            )
        except Exception as e:
            logger.error(f"Failed to initialize YOLO detector: {e}")
            raise

        # Initialize LoFTR matcher
        loftr_config = config.get('loftr', {})
        try:
            self.loftr_matcher = LoFTRMatcher(
                weights=loftr_config.get('weights', 'outdoor'),
                device=loftr_config.get('device', 'auto')
            )
        except Exception as e:
            logger.error(f"Failed to initialize LoFTR matcher: {e}")
            raise

        # Load template
        template_config = config.get('template', {})
        templates_dir = template_config.get('templates_dir', '../templates')
        model_name = template_config.get('model', 'nab')

        try:
            # Resolve templates directory path
            templates_dir_path = Path(templates_dir)
            if not templates_dir_path.is_absolute():
                base_dir = Path(__file__).parent.parent
                templates_dir_path = base_dir / templates_dir_path

            template_loader = TemplateLoader(templates_dir_path)
            self.template_data = template_loader.load_template(model_name=model_name)
            logger.info(f"Loaded template: {model_name}")
        except Exception as e:
            logger.error(f"Failed to load template: {e}")
            raise

        # Configuration parameters
        self.padding_factor = yolo_config.get('padding_factor', 1.5)
        self.match_threshold = loftr_config.get('match_threshold', 0.2)
        self.ransac_threshold = config.get('homography', {}).get('ransac_threshold', 5.0)
        self.min_inliers = config.get('homography', {}).get('min_inliers', 10)
        self.confidence_threshold = config.get('confidence_threshold', 0.7)

    def _estimate_keypoints_from_obb(
        self,
        obb_data: Dict[str, Any],
        padding_percent: float = 0.15
    ) -> KeypointCoords:
        """Estimate keypoints from YOLO OBB using inverse transformation.

        This is the inverse of keypoints_to_obb_corners from the training pipeline.
        Given an OBB, we estimate where the canonical keypoints should be.

        Args:
            obb_data: Dict with center_x, center_y, width, height, rotation_deg, image_shape
            padding_percent: Padding used in OBB creation (default 0.15 = 15%)

        Returns:
            KeypointCoords: Estimated keypoints in normalized [0, 1] coordinates
        """
        # Extract OBB parameters
        center_x = obb_data["center_x"]
        center_y = obb_data["center_y"]
        obb_width = obb_data["width"]
        obb_height = obb_data["height"]
        rotation_deg = obb_data["rotation_deg"]
        img_h, img_w = obb_data["image_shape"]

        logger.info(
            f"OBB fallback: center=({center_x:.1f},{center_y:.1f}), "
            f"size=({obb_width:.1f}×{obb_height:.1f}), rot={rotation_deg:.1f}°, "
            f"img={img_w}×{img_h}"
        )

        # Convert rotation to radians
        rotation_rad = np.deg2rad(rotation_deg)

        # Remove padding to get the original keypoint ranges
        # OBB has padding: width = width_range * (1 + 2*padding_percent)
        # So: width_range = width / (1 + 2*padding_percent)
        padding_factor = 1.0 + 2 * padding_percent
        width_range = obb_width / padding_factor
        height_range = obb_height / padding_factor

        # Calculate primary axis (points from top to bottom after rotation)
        # In canonical orientation, this is the vertical axis [0, 1]
        # After rotation by rotation_deg, it becomes:
        primary_unit = np.array([
            np.sin(rotation_rad),
            np.cos(rotation_rad)
        ])

        # Secondary axis (perpendicular, points from left to right)
        # Perpendicular to primary, pointing right
        secondary_unit = np.array([
            np.cos(rotation_rad),
            -np.sin(rotation_rad)
        ])

        # Center point in pixel coordinates
        center = np.array([center_x, center_y])

        # Calculate keypoint positions based on canonical template layout
        # The template has keypoints at roughly:
        # - top/bottom: along primary axis
        # - left/right: along secondary axis
        # We position them at the edges of the non-padded range

        half_height = height_range / 2.0
        half_width = width_range / 2.0

        # Estimate keypoint positions in pixel coordinates
        keypoints_px = {
            "top": center - half_height * primary_unit,
            "bottom": center + half_height * primary_unit,
            "left": center - half_width * secondary_unit,
            "right": center + half_width * secondary_unit,
            "center": center
        }

        # Convert to normalized coordinates and clamp to [0, 1]
        keypoints_norm = {}
        for kp_name, kp_px in keypoints_px.items():
            x_norm = kp_px[0] / img_w
            y_norm = kp_px[1] / img_h

            # Clamp to valid range
            x_norm = max(0.0, min(1.0, x_norm))
            y_norm = max(0.0, min(1.0, y_norm))

            keypoints_norm[kp_name] = (x_norm, y_norm)
            logger.debug(f"  {kp_name}: px=({kp_px[0]:.1f},{kp_px[1]:.1f}) -> norm=({x_norm:.3f},{y_norm:.3f})")

        return KeypointCoords(**keypoints_norm)

    def predict(self, image_path: Path) -> PipelineResult:
        """Run prediction pipeline.

        Pipeline:
        1. Load the image
        2. Phase 1: YOLO detection and de-rotation
        3. Phase 2: LoFTR matching and homography estimation
        4. Project template keypoints to query image

        Args:
            image_path: Path to image file

        Returns:
            PipelineResult with keypoint predictions or error info
        """
        # 1. Load image
        query_img = cv2.imread(str(image_path))
        if query_img is None:
            logger.error(f"Failed to load image: {image_path}")
            return PipelineResult(
                success=False,
                keypoints=None,
                roi=None,
                confidence=0.0,
                image_width=None,
                image_height=None,
                debug_info={"reason": "image_load_failed", "path": str(image_path)},
                error_message=f"Image load failed: {image_path}",
            )

        # Get image dimensions (height, width, channels)
        img_h, img_w = query_img.shape[:2]
        logger.info(f"Loaded image: {img_w}×{img_h}")

        try:
            # 2. Phase 1: YOLO detection and alignment
            phase1_img, num_det, yolo_conf, reason, obb_data = self.yolo_detector.detect_and_align(
                query_img, self.padding_factor
            )

            if phase1_img is None:
                logger.warning(f"YOLO detection failed: {reason}")
                return PipelineResult(
                    success=False,
                    keypoints=None,
                    roi=None,
                    confidence=0.0,
                    image_width=img_w,
                    image_height=img_h,
                    debug_info={"phase": "yolo", "reason": reason},
                    error_message=f"YOLO detection failed: {reason}",
                )

            # 3. Phase 2: LoFTR matching
            mkpts0, mkpts1, mconf = self.loftr_matcher.find_correspondences(
                phase1_img, self.template_data.template_image, self.match_threshold
            )

            if len(mkpts0) < 4:
                # Not enough matches for homography - fall back to OBB estimation
                logger.warning(
                    f"Insufficient LoFTR matches ({len(mkpts0)} < 4), using OBB-based fallback"
                )

                if obb_data is None:
                    logger.error("No OBB data available for fallback")
                    return PipelineResult(
                        success=False,
                        keypoints=None,
                        roi=None,
                        confidence=0.0,
                        image_width=img_w,
                        image_height=img_h,
                        debug_info={
                            "phase": "loftr",
                            "reason": "insufficient_matches_no_obb_fallback",
                            "num_matches": len(mkpts0)
                        },
                        error_message=f"Insufficient LoFTR matches and no OBB data for fallback",
                    )

                # Use OBB-based estimation
                keypoints_norm = self._estimate_keypoints_from_obb(obb_data)

                return PipelineResult(
                    success=True,
                    keypoints=keypoints_norm,
                    roi=None,
                    confidence=yolo_conf,  # Use YOLO confidence as fallback
                    image_width=img_w,
                    image_height=img_h,
                    debug_info={
                        "yolo_detections": num_det,
                        "yolo_confidence": float(yolo_conf),
                        "yolo_used_whole_image": obb_data.get("used_whole_image", False),
                        "yolo_box_height_ratio": obb_data.get("box_height_ratio", None),
                        "loftr_matches": len(mkpts0),
                        "method": "YOLO-OBB-Fallback (insufficient LoFTR matches)",
                        "template_model": self.template_data.model_name,
                        "fallback_reason": f"insufficient_loftr_matches ({len(mkpts0)} < 4)"
                    },
                    error_message=None,
                )

            # 4. Homography estimation
            H, num_inliers, homography_conf = self.loftr_matcher.estimate_homography(
                mkpts0, mkpts1, self.ransac_threshold, self.min_inliers
            )

            if H is None:
                # Homography failed - fall back to OBB-based keypoint estimation
                logger.warning(
                    f"Homography failed ({num_inliers} inliers < {self.min_inliers}), "
                    f"using OBB-based fallback"
                )

                if obb_data is None:
                    logger.error("No OBB data available for fallback")
                    return PipelineResult(
                        success=False,
                        keypoints=None,
                        roi=None,
                        confidence=0.0,
                        image_width=img_w,
                        image_height=img_h,
                        debug_info={
                            "phase": "homography",
                            "reason": "homography_failed_no_obb_fallback",
                            "num_matches": len(mkpts0),
                            "inliers": num_inliers
                        },
                        error_message=f"Homography failed and no OBB data for fallback",
                    )

                # Use OBB-based estimation
                keypoints_norm = self._estimate_keypoints_from_obb(obb_data)

                return PipelineResult(
                    success=True,
                    keypoints=keypoints_norm,
                    roi=None,
                    confidence=yolo_conf,  # Use YOLO confidence as fallback
                    image_width=img_w,
                    image_height=img_h,
                    debug_info={
                        "yolo_detections": num_det,
                        "yolo_confidence": float(yolo_conf),
                        "yolo_used_whole_image": obb_data.get("used_whole_image", False),
                        "yolo_box_height_ratio": obb_data.get("box_height_ratio", None),
                        "loftr_matches": len(mkpts0),
                        "homography_inliers": num_inliers,
                        "method": "YOLO-OBB-Fallback (homography failed)",
                        "template_model": self.template_data.model_name,
                        "fallback_reason": f"insufficient_inliers ({num_inliers} < {self.min_inliers})"
                    },
                    error_message=None,
                )

            # 5. Project keypoints
            # Project from template → phase1 → original image space
            keypoints_norm = self._project_keypoints(
                H,
                phase1_shape=phase1_img.shape[:2],
                original_shape=(img_h, img_w),
                transform_params=obb_data.get("transform_params")
            )

            # Success!
            logger.info(f"Prediction successful: {num_inliers} inliers, conf={homography_conf:.3f}")
            return PipelineResult(
                success=True,
                keypoints=keypoints_norm,
                roi=None,  # Not computing ROI in this simplified pipeline
                confidence=homography_conf,
                image_width=img_w,
                image_height=img_h,
                debug_info={
                    "yolo_detections": num_det,
                    "yolo_confidence": float(yolo_conf),
                    "yolo_used_whole_image": obb_data.get("used_whole_image", False),
                    "yolo_box_height_ratio": obb_data.get("box_height_ratio", None),
                    "loftr_matches": len(mkpts0),
                    "homography_inliers": num_inliers,
                    "method": "YOLO-LoFTR-Homography",
                    "template_model": self.template_data.model_name
                },
                error_message=None,
            )

        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            return PipelineResult(
                success=False,
                keypoints=None,
                roi=None,
                confidence=0.0,
                image_width=img_w,
                image_height=img_h,
                debug_info={"reason": "pipeline_error", "error": str(e)},
                error_message=f"Pipeline error: {e}",
            )

    def _transform_phase1_to_original(
        self,
        x_phase1: float,
        y_phase1: float,
        transform_params: Dict[str, Any]
    ) -> Tuple[float, float]:
        """Transform coordinates from Phase1 image space to original image space.

        Args:
            x_phase1: X coordinate in Phase1 image (pixels)
            y_phase1: Y coordinate in Phase1 image (pixels)
            transform_params: Transformation parameters from obb_data

        Returns:
            (x_orig, y_orig): Coordinates in original image space (pixels)
        """
        if transform_params is None:
            # No transformation info - return as-is (shouldn't happen)
            logger.warning("No transform_params available, returning Phase1 coords as-is")
            return x_phase1, y_phase1

        transform_type = transform_params["type"]

        if transform_type == "resize_only":
            # Simple case: Phase1 is just resized original image
            # Inverse: divide by scale factors
            x_orig = x_phase1 / transform_params["scale_x"]
            y_orig = y_phase1 / transform_params["scale_y"]
            return x_orig, y_orig

        elif transform_type == "crop_rotate_resize":
            # Complex case: Phase1 = Resize(Rotate(Crop(Original)))
            # Inverse: UnResize → UnRotate → UnCrop

            # Step 1: UnResize (Phase1 → Rotated space)
            x_rotated = x_phase1 / transform_params["scale_x"]
            y_rotated = y_phase1 / transform_params["scale_y"]

            # Step 2: UnRotate (Rotated → Cropped space)
            # The forward rotation was around crop_center with angle -rotation_deg
            # So inverse is rotation around same center with angle +rotation_deg
            crop_center_x, crop_center_y = transform_params["crop_center"]
            rotation_deg = transform_params["rotation_deg"]

            # Translate to origin
            x_centered = x_rotated - crop_center_x
            y_centered = y_rotated - crop_center_y

            # Rotate by +rotation_deg (inverse of forward -rotation_deg)
            angle_rad = np.radians(rotation_deg)
            cos_a = np.cos(angle_rad)
            sin_a = np.sin(angle_rad)
            x_cropped = cos_a * x_centered - sin_a * y_centered + crop_center_x
            y_cropped = sin_a * x_centered + cos_a * y_centered + crop_center_y

            # Step 3: UnCrop (Cropped → Original space)
            x1, y1, x2, y2 = transform_params["crop_box"]
            x_orig = x_cropped + x1
            y_orig = y_cropped + y1

            return x_orig, y_orig
        else:
            logger.error(f"Unknown transform type: {transform_type}")
            return x_phase1, y_phase1

    def _project_keypoints(
        self,
        H: np.ndarray,
        phase1_shape: Tuple[int, int],
        original_shape: Tuple[int, int],
        transform_params: Dict[str, Any]
    ) -> KeypointCoords:
        """Project template keypoints to original query image using inverse homography.

        Args:
            H: 3×3 homography matrix (Phase1 → template)
            phase1_shape: (height, width) of Phase1 image (aligned, padded)
            original_shape: (height, width) of original query image
            transform_params: Transformation parameters from obb_data

        Returns:
            KeypointCoords: Projected keypoints in normalized [0, 1] coordinates
                           relative to ORIGINAL image dimensions
        """
        template_keypoints = self.template_data.keypoints_norm
        template_size = self.template_data.image_size  # (width, height)
        phase1_h, phase1_w = phase1_shape
        orig_h, orig_w = original_shape

        logger.info(f"Projecting keypoints: template={template_size}, phase1=({phase1_w}×{phase1_h}), original=({orig_w}×{orig_h})")

        # Invert homography (H maps query→template, need template→query)
        try:
            H_inv = np.linalg.inv(H)
        except np.linalg.LinAlgError:
            logger.warning("Singular homography matrix, using center fallback keypoints")
            # Singular matrix - return center keypoints as fallback
            return KeypointCoords(
                top=(0.5, 0.2), bottom=(0.5, 0.8),
                left=(0.2, 0.5), right=(0.8, 0.5),
                center=(0.5, 0.5)
            )

        # Project each keypoint
        projected = {}
        for kp_name, (x_norm, y_norm) in template_keypoints.items():
            # Convert template normalized → template pixels
            x_t_px = x_norm * template_size[0]
            y_t_px = y_norm * template_size[1]

            # Apply inverse homography (template → Phase1 pixels)
            pt_h = np.array([[x_t_px], [y_t_px], [1.0]])
            pt_phase1_h = H_inv @ pt_h
            x_phase1_px = pt_phase1_h[0, 0] / pt_phase1_h[2, 0]  # Dehomogenize
            y_phase1_px = pt_phase1_h[1, 0] / pt_phase1_h[2, 0]

            # Transform from Phase1 space to Original image space
            x_orig_px, y_orig_px = self._transform_phase1_to_original(
                x_phase1_px, y_phase1_px, transform_params
            )

            # Convert original pixels → normalized by original dimensions
            x_orig_norm = x_orig_px / orig_w
            y_orig_norm = y_orig_px / orig_h

            # Clamp to valid range [0, 1]
            x_orig_norm = max(0.0, min(1.0, x_orig_norm))
            y_orig_norm = max(0.0, min(1.0, y_orig_norm))

            projected[kp_name] = (x_orig_norm, y_orig_norm)
            logger.debug(f"  {kp_name}: template=({x_t_px:.1f},{y_t_px:.1f}) → phase1=({x_phase1_px:.1f},{y_phase1_px:.1f}) → orig=({x_orig_px:.1f},{y_orig_px:.1f}) → norm=({x_orig_norm:.3f},{y_orig_norm:.3f})")

        return KeypointCoords(**projected)

    def get_version(self) -> str:
        """Get pipeline version string.

        Returns:
            str: Version identifier
        """
        return self.model_version

    def get_info(self) -> Dict[str, Any]:
        """Get pipeline information.

        Returns:
            dict: Pipeline metadata
        """
        return {
            "type": "homography_keypoints",
            "version": self.model_version,
            "description": "YOLO + LoFTR + Homography pipeline for watch keypoint detection",
            "confidence_threshold": self.confidence_threshold,
            "template_model": self.template_data.model_name,
            "steps": ["yolo_obb_detection", "loftr_matching", "ransac_homography", "keypoint_projection"],
            "config": {
                "yolo_conf_threshold": self.yolo_detector.conf_threshold,
                "loftr_match_threshold": self.match_threshold,
                "ransac_threshold": self.ransac_threshold,
                "min_inliers": self.min_inliers,
                "padding_factor": self.padding_factor,
            }
        }
