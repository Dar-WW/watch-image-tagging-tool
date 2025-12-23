"""LoFTR-based feature matching for watch image alignment.

Adapted from FPJ-WatchId-POC/src/preprocess/loftr_alignment.py
"""

from typing import Optional, Tuple
import numpy as np
import cv2
import torch

try:
    from kornia.feature import LoFTR
    LOFTR_AVAILABLE = True
except ImportError:
    LOFTR_AVAILABLE = False
    LoFTR = None


class LoFTRMatcher:
    """
    LoFTR matcher for dense feature correspondence finding.

    Uses transformer-based deep learning to find dense correspondences
    between query and template images for accurate homography estimation.
    """

    def __init__(self, weights: str = "outdoor", device: Optional[str] = None):
        """
        Initialize LoFTR matcher.

        Args:
            weights: Pretrained weights to use ("outdoor" or "indoor")
            device: Device to use ("cuda", "mps", "cpu", or None for auto-detect)

        Raises:
            ImportError: If kornia is not installed
        """
        if not LOFTR_AVAILABLE:
            raise ImportError(
                "kornia is required for LoFTR alignment. "
                "Install with: pip install kornia kornia-moons"
            )

        # Determine device
        if device is None or device == "auto":
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"

        self.device = torch.device(device)
        self.weights = weights

        # Load LoFTR model
        print(f"Loading LoFTR model (weights={weights}, device={device})...")
        self.matcher = LoFTR(pretrained=weights).to(self.device).eval()
        print("LoFTR model loaded successfully")

    def preprocess_image(self, image_bgr: np.ndarray) -> torch.Tensor:
        """
        Preprocess image for LoFTR.

        LoFTR expects:
        - Grayscale image
        - Shape: (1, 1, H, W)
        - Values: [0, 1]

        Args:
            image_bgr: Input image in BGR format

        Returns:
            Preprocessed tensor on device
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

        # Normalize to [0, 1]
        gray_norm = gray.astype(np.float32) / 255.0

        # Convert to tensor (1, 1, H, W)
        tensor = torch.from_numpy(gray_norm)[None, None].to(self.device)

        return tensor

    def find_correspondences(
        self,
        query_bgr: np.ndarray,
        template_bgr: np.ndarray,
        match_threshold: float = 0.2
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Find dense correspondences between query and template.

        Args:
            query_bgr: Query image (BGR)
            template_bgr: Template image (BGR)
            match_threshold: Confidence threshold for filtering matches

        Returns:
            Tuple of (query_keypoints, template_keypoints, match_confidences)
            Each is an array of shape (N, 2) or (N,)
        """
        # Preprocess
        query_tensor = self.preprocess_image(query_bgr)
        template_tensor = self.preprocess_image(template_bgr)

        # Run LoFTR
        with torch.no_grad():
            input_dict = {
                'image0': query_tensor,
                'image1': template_tensor
            }
            correspondences = self.matcher(input_dict)

        # Extract matches
        mkpts0 = correspondences['keypoints0'].cpu().numpy()  # Query keypoints
        mkpts1 = correspondences['keypoints1'].cpu().numpy()  # Template keypoints
        mconf = correspondences['confidence'].cpu().numpy()   # Match confidence

        # Filter by confidence
        mask = mconf > match_threshold
        mkpts0 = mkpts0[mask]
        mkpts1 = mkpts1[mask]
        mconf = mconf[mask]

        return mkpts0, mkpts1, mconf

    def estimate_homography(
        self,
        mkpts0: np.ndarray,
        mkpts1: np.ndarray,
        ransac_threshold: float = 5.0,
        min_inliers: int = 10
    ) -> Tuple[Optional[np.ndarray], int, float]:
        """
        Estimate homography from correspondences using RANSAC.

        Args:
            mkpts0: Query keypoints (N, 2)
            mkpts1: Template keypoints (N, 2)
            ransac_threshold: RANSAC reprojection error threshold (pixels)
            min_inliers: Minimum RANSAC inliers required for success

        Returns:
            Tuple of (H, num_inliers, confidence):
                H: 3×3 homography matrix (query → template), or None if failed
                num_inliers: Number of RANSAC inliers
                confidence: Inlier ratio (inliers / total_matches)
        """
        num_matches = len(mkpts0)

        # Check minimum matches for homography
        if num_matches < 4:
            return None, 0, 0.0

        # Estimate homography with RANSAC
        H, inlier_mask = cv2.findHomography(
            mkpts0, mkpts1,
            cv2.RANSAC,
            ransac_threshold
        )

        if H is None:
            return None, 0, 0.0

        # Count inliers
        num_inliers = int(np.sum(inlier_mask)) if inlier_mask is not None else 0
        confidence = num_inliers / num_matches if num_matches > 0 else 0.0

        # Validate minimum inliers
        if num_inliers < min_inliers:
            return None, num_inliers, confidence

        return H, num_inliers, confidence


def create_loftr_matcher(
    weights: str = "outdoor",
    device: Optional[str] = None
) -> Optional[LoFTRMatcher]:
    """
    Convenience function to create a LoFTR matcher.

    Args:
        weights: Pretrained weights ("outdoor" or "indoor")
        device: Device to use (None for auto-detect)

    Returns:
        LoFTRMatcher instance or None if kornia not available
    """
    if not LOFTR_AVAILABLE:
        print("⚠ LoFTR not available. Install kornia: pip install kornia kornia-moons")
        return None

    try:
        return LoFTRMatcher(weights=weights, device=device)
    except Exception as e:
        print(f"⚠ Failed to create LoFTR matcher: {e}")
        return None
