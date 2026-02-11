"""YOLO-OBB detector for watch face detection and alignment.

Adapted from FPJ-WatchId-POC/src/preprocess/alignment.py
"""

from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import cv2


class YOLODetector:
    """
    YOLO-OBB detector for oriented watch face detection.

    Detects watches with oriented bounding boxes and performs rotation correction
    to align watches to canonical orientation before Phase 2 (LoFTR) refinement.
    """

    def __init__(
        self,
        checkpoint_path: str,
        conf_threshold: float = 0.25,
        device: str = "auto"
    ):
        """
        Initialize YOLO detector.

        Args:
            checkpoint_path: Path to trained YOLO-OBB model (.pt file)
            conf_threshold: Confidence threshold for detection (0-1)
            device: Device to use ("auto", "cuda", "mps", "cpu")

        Raises:
            ImportError: If ultralytics is not installed
            FileNotFoundError: If checkpoint path doesn't exist
        """
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError(
                "ultralytics is required for YOLO detection. "
                "Install with: pip install ultralytics"
            )

        # Resolve checkpoint path
        checkpoint_path = Path(checkpoint_path)
        if not checkpoint_path.is_absolute():
            # Try to resolve from prediction_server directory
            base_dir = Path(__file__).parent.parent
            checkpoint_path = base_dir / checkpoint_path

        if not checkpoint_path.exists():
            raise FileNotFoundError(
                f"YOLO checkpoint not found: {checkpoint_path}"
            )

        # Auto-detect device
        if device == "auto":
            import torch
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"

        self.device = device
        self.conf_threshold = conf_threshold

        # Load YOLO model
        self.model = YOLO(str(checkpoint_path))
        print(f"Loaded YOLO model from {checkpoint_path} on device: {device}")

    def detect_and_align(
        self,
        image_bgr: np.ndarray,
        padding_factor: float = 1.5,
        template_size: Tuple[int, int] = (1024, 1024)
    ) -> Tuple[Optional[np.ndarray], int, float, str, Optional[dict]]:
        """
        Detect watch face with OBB and align to canonical orientation.

        Pipeline:
        1. Run YOLO-OBB inference to detect watch
        2. Extract oriented bounding box (center, size, rotation)
        3. Crop region around OBB with margin
        4. De-rotate using inverse rotation matrix
        5. Resize to padded canvas size

        Args:
            image_bgr: Input image in BGR format
            padding_factor: Canvas size multiplier (1.5 = 1536×1536 for 1024 template)
            template_size: (height, width) of target template

        Returns:
            Tuple of (aligned_image, num_detections, confidence, reason, obb_data):
                aligned_image: BGR image on padded canvas (template_size * padding_factor)
                num_detections: Number of watches detected
                confidence: YOLO detection confidence (0-1)
                reason: Empty string on success, error description on failure
                obb_data: Dict with OBB parameters (center_x, center_y, width, height, rotation_deg, image_shape)
        """
        try:
            # Run YOLO inference
            # imgsz=640 is the default YOLO training resolution
            results = self.model.predict(
                source=image_bgr,
                conf=self.conf_threshold,
                iou=0.45,  # IoU threshold for NMS
                imgsz=640,  # Image size for inference (must match training size)
                device=self.device,
                verbose=False
            )

            result = results[0]

            # Check if any watches were detected
            if result.obb is None or len(result.obb) == 0:
                # No detection - fall back to whole image
                print(f"YOLO detected no watches, using whole image as fallback")
                img_h, img_w = image_bgr.shape[:2]

                # Resize whole image to padded template size
                template_h, template_w = template_size
                padded_w = int(template_w * padding_factor)
                padded_h = int(template_h * padding_factor)

                aligned_phase1 = cv2.resize(
                    image_bgr,
                    (padded_w, padded_h),
                    interpolation=cv2.INTER_LINEAR
                )

                # Calculate resize scale factors
                scale_x = padded_w / img_w
                scale_y = padded_h / img_h

                # Create minimal obb_data for whole image fallback
                obb_data = {
                    "center_x": float(img_w / 2),
                    "center_y": float(img_h / 2),
                    "width": float(img_w),
                    "height": float(img_h),
                    "rotation_deg": 0.0,
                    "image_shape": (img_h, img_w),
                    "used_whole_image": True,
                    "box_height_ratio": 1.0,  # 100% - entire image
                    "transform_params": {
                        "type": "resize_only",
                        "scale_x": float(scale_x),
                        "scale_y": float(scale_y),
                        "phase1_size": (padded_w, padded_h)
                    }
                }

                return aligned_phase1, 0, 0.0, "", obb_data

            num_detections = len(result.obb)

            # Use the first detection (highest confidence)
            obb = result.obb[0]
            confidence = float(obb.conf[0])

            # Get oriented bounding box info
            # xywhr: [center_x, center_y, width, height, rotation_degrees]
            xywhr = obb.xywhr[0].cpu().numpy()
            center_x, center_y, obb_width, obb_height, rotation_deg = xywhr

            # Strategy: Extract rotated rectangle, then de-rotate it
            img_h, img_w = image_bgr.shape[:2]

            # Store OBB data for potential fallback keypoint estimation
            obb_data = {
                "center_x": float(center_x),
                "center_y": float(center_y),
                "width": float(obb_width),
                "height": float(obb_height),
                "rotation_deg": float(rotation_deg),
                "image_shape": (img_h, img_w),  # Original image shape
                # Transformation parameters (will be filled in below)
                "transform_params": None
            }

            # Check if detected box is too small (< 10% of image height)
            # If box is tiny, it's likely a false detection - use whole image instead
            box_height_ratio = max(obb_width, obb_height) / img_h
            MIN_BOX_SIZE_RATIO = 0.10

            if box_height_ratio < MIN_BOX_SIZE_RATIO:
                print(f"YOLO box too small ({box_height_ratio:.1%} of image), using whole image instead")
                # Resize whole image to padded template size without crop/rotate
                template_h, template_w = template_size
                padded_w = int(template_w * padding_factor)
                padded_h = int(template_h * padding_factor)

                aligned_phase1 = cv2.resize(
                    image_bgr,
                    (padded_w, padded_h),
                    interpolation=cv2.INTER_LINEAR
                )

                # Calculate resize scale factors
                scale_x = padded_w / img_w
                scale_y = padded_h / img_h

                # Store transformation: Original → Phase1 (just resize, no crop/rotate)
                obb_data["used_whole_image"] = True
                obb_data["box_height_ratio"] = float(box_height_ratio)
                obb_data["transform_params"] = {
                    "type": "resize_only",
                    "scale_x": float(scale_x),
                    "scale_y": float(scale_y),
                    "phase1_size": (padded_w, padded_h)
                }

                return aligned_phase1, num_detections, confidence, "", obb_data

            # Calculate crop size with 30% margin
            crop_w = int(max(obb_width, obb_height) * 1.3)
            crop_h = int(max(obb_width, obb_height) * 1.3)

            # Ensure we don't exceed image bounds
            x1 = max(0, int(center_x - crop_w // 2))
            y1 = max(0, int(center_y - crop_h // 2))
            x2 = min(img_w, int(center_x + crop_w // 2))
            y2 = min(img_h, int(center_y + crop_h // 2))

            # Crop region around OBB
            cropped_region = image_bgr[y1:y2, x1:x2].copy()

            # Calculate new center in cropped coordinates
            crop_center_x = center_x - x1
            crop_center_y = center_y - y1

            # Rotate the cropped region to align watch to canonical orientation
            # If YOLO says watch is rotated X degrees, rotate by -X to make it upright
            rotation_matrix = cv2.getRotationMatrix2D(
                (crop_center_x, crop_center_y),
                -rotation_deg,  # Negative to undo rotation
                1.0  # No scaling
            )

            # Apply rotation
            rotated_region = cv2.warpAffine(
                cropped_region,
                rotation_matrix,
                (cropped_region.shape[1], cropped_region.shape[0]),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0)
            )

            # Resize to padded template size
            template_h, template_w = template_size
            padded_w = int(template_w * padding_factor)
            padded_h = int(template_h * padding_factor)

            aligned_phase1 = cv2.resize(
                rotated_region,
                (padded_w, padded_h),
                interpolation=cv2.INTER_LINEAR
            )

            # Calculate resize scale factors
            crop_shape_h, crop_shape_w = rotated_region.shape[:2]
            scale_x = padded_w / crop_shape_w
            scale_y = padded_h / crop_shape_h

            # Store transformation: Original → Crop → Rotate → Resize → Phase1
            obb_data["used_whole_image"] = False
            obb_data["box_height_ratio"] = float(box_height_ratio)
            obb_data["transform_params"] = {
                "type": "crop_rotate_resize",
                "crop_box": (int(x1), int(y1), int(x2), int(y2)),  # Original image crop bounds
                "crop_center": (float(crop_center_x), float(crop_center_y)),  # Center in cropped space
                "rotation_deg": float(rotation_deg),  # Applied rotation
                "rotation_matrix": rotation_matrix.tolist(),  # 2×3 affine matrix
                "crop_shape": (crop_shape_w, crop_shape_h),  # Cropped/rotated size before resize
                "scale_x": float(scale_x),
                "scale_y": float(scale_y),
                "phase1_size": (padded_w, padded_h)
            }

            return aligned_phase1, num_detections, confidence, "", obb_data

        except Exception as e:
            return None, 0, 0.0, f"yolo_error: {str(e)}", None
