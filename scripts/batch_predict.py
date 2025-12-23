#!/usr/bin/env python3
"""Batch prediction script for watch keypoint detection.

Processes all unlabeled images in downloaded_images/ directory using the
YOLO + LoFTR + Homography pipeline, and saves predictions to
alignment_labels_predicted/ directory in the same format as alignment_labels/.

Features:
- Resumable processing with progress tracking
- Three-tier fallback strategy (full → pipeline → geometric)
- Serial processing to avoid CPU overload
- Comprehensive logging and error handling

Usage:
    # Basic usage - process all new images
    python scripts/batch_predict.py

    # Test on single watch model
    python scripts/batch_predict.py --watch-id PATEK_nab_001

    # Resume after interruption
    python scripts/batch_predict.py --resume

    # Force reprocess all images
    python scripts/batch_predict.py --force
"""

import argparse
import json
import logging
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from prediction_server.pipelines.homography_keypoints import HomographyKeypointsPipeline
from prediction_server.models.pipeline_result import PipelineResult, KeypointCoords
from utils.filename_parser import get_image_id, extract_watch_id, parse_filename

# Constants
PROGRESS_FILE = ".batch_predict_progress.json"
LOG_FILE = "batch_predict.log"
DEFAULT_IMAGES_DIR = Path("downloaded_images")
DEFAULT_OUTPUT_DIR = Path("alignment_labels_predicted")
DEFAULT_LABELS_DIR = Path("alignment_labels")
DEFAULT_CONFIG = Path("prediction_server/config.yaml")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ProgressManager:
    """Manage progress tracking for resumable batch processing."""

    def __init__(self, progress_file: Path = Path(PROGRESS_FILE)):
        """Initialize progress manager.

        Args:
            progress_file: Path to progress JSON file
        """
        self.progress_file = progress_file
        self.data = self._init_progress_data()

    def _init_progress_data(self) -> dict:
        """Initialize or load progress data."""
        default_data = {
            "version": "1.0",
            "last_updated": None,
            "processed_images": [],
            "failed_images": {},
            "stats": {
                "total_images": 0,
                "processed": 0,
                "successful": 0,
                "pipeline_fallback": 0,
                "geometric_fallback": 0,
                "skipped_existing": 0,
                "errors": {}
            }
        }

        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    loaded_data = json.load(f)
                logger.info(f"Loaded progress from {self.progress_file}")
                return loaded_data
            except Exception as e:
                logger.warning(f"Failed to load progress file: {e}, starting fresh")
                return default_data
        else:
            return default_data

    def save(self):
        """Save current progress to file."""
        self.data["last_updated"] = datetime.now().isoformat()
        try:
            with open(self.progress_file, 'w') as f:
                json.dump(self.data, f, indent=2)
            logger.debug(f"Progress saved to {self.progress_file}")
        except Exception as e:
            logger.error(f"Failed to save progress: {e}")

    def is_processed(self, image_id: str) -> bool:
        """Check if image has been processed.

        Args:
            image_id: Quality-agnostic image ID

        Returns:
            True if image already processed
        """
        return image_id in self.data["processed_images"]

    def mark_processed(self, image_id: str, success: bool, error: str = None,
                      annotator: str = "ml-model-v1.0"):
        """Mark image as processed and update stats.

        Args:
            image_id: Quality-agnostic image ID
            success: Whether prediction succeeded
            error: Error message if failed
            annotator: Type of prediction (ml-model-v1.0, -pipeline-fallback, -geometric-fallback)
        """
        if image_id not in self.data["processed_images"]:
            self.data["processed_images"].append(image_id)

        self.data["stats"]["processed"] += 1

        if success:
            self.data["stats"]["successful"] += 1
            if "pipeline-fallback" in annotator:
                self.data["stats"]["pipeline_fallback"] += 1
            elif "geometric-fallback" in annotator:
                self.data["stats"]["geometric_fallback"] += 1
        else:
            self.data["failed_images"][image_id] = error or "unknown_error"
            # Track error types
            error_key = error or "unknown_error"
            self.data["stats"]["errors"][error_key] = \
                self.data["stats"]["errors"].get(error_key, 0) + 1

    def set_total_images(self, total: int):
        """Set total number of images to process."""
        self.data["stats"]["total_images"] = total

    def set_skipped_existing(self, count: int):
        """Set number of images skipped (already annotated)."""
        self.data["stats"]["skipped_existing"] = count

    def get_stats(self) -> dict:
        """Get current statistics."""
        return self.data["stats"].copy()


class ImageScanner:
    """Scan and filter images to process."""

    def __init__(self, images_dir: Path, labels_dir: Path, output_dir: Path):
        """Initialize image scanner.

        Args:
            images_dir: Directory containing downloaded images
            labels_dir: Directory containing existing annotations
            output_dir: Directory containing predicted annotations
        """
        self.images_dir = images_dir
        self.labels_dir = labels_dir
        self.output_dir = output_dir

    def scan_images(self, skip_existing: bool = True, watch_id_filter: Optional[str] = None) \
            -> List[Tuple[Path, str, str]]:
        """Scan for images to process.

        Args:
            skip_existing: Skip images already in labels_dir or output_dir
            watch_id_filter: Only process this watch ID (for testing)

        Returns:
            List of (image_path, image_id, watch_id) tuples
        """
        logger.info(f"Scanning images in {self.images_dir}")

        if not self.images_dir.exists():
            logger.error(f"Images directory not found: {self.images_dir}")
            return []

        # Load existing annotations
        existing_ids = set()
        if skip_existing:
            existing_ids = self._load_existing_image_ids()
            logger.info(f"Found {len(existing_ids)} already annotated images")

        # Scan for images
        images_to_process = []

        for watch_dir in sorted(self.images_dir.iterdir()):
            if not watch_dir.is_dir():
                continue

            watch_id = watch_dir.name

            # Apply watch_id filter if specified
            if watch_id_filter and watch_id != watch_id_filter:
                continue

            for image_file in sorted(watch_dir.glob("*.jpg")):
                # Check if face or tiltface image
                if not self._is_face_or_tiltface(image_file.name):
                    continue

                # Get quality-agnostic image ID
                try:
                    image_id = get_image_id(image_file.name)
                except Exception as e:
                    logger.warning(f"Failed to parse filename {image_file.name}: {e}")
                    continue

                # Skip if already annotated
                if image_id in existing_ids:
                    continue

                images_to_process.append((image_file, image_id, watch_id))

        logger.info(f"Found {len(images_to_process)} images to process")
        return images_to_process

    def _is_face_or_tiltface(self, filename: str) -> bool:
        """Check if filename is face or tiltface view.

        Args:
            filename: Image filename

        Returns:
            True if face or tiltface view
        """
        try:
            metadata = parse_filename(filename)
            return metadata.view_type in ["face", "tiltface"]
        except Exception:
            return False

    def _load_existing_image_ids(self) -> set:
        """Load image IDs from existing annotation files.

        Returns:
            Set of image IDs that already have annotations
        """
        existing_ids = set()

        # Check labels_dir (human annotations)
        if self.labels_dir.exists():
            for json_file in self.labels_dir.glob("*.json"):
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                    existing_ids.update(data.keys())
                except Exception as e:
                    logger.warning(f"Failed to read {json_file}: {e}")

        # Check output_dir (predicted annotations)
        if self.output_dir.exists():
            for json_file in self.output_dir.glob("*.json"):
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                    existing_ids.update(data.keys())
                except Exception as e:
                    logger.warning(f"Failed to read {json_file}: {e}")

        return existing_ids


class PredictionRunner:
    """Run predictions with three-tier fallback strategy."""

    def __init__(self, config_path: Path, device: str = "auto"):
        """Initialize prediction runner.

        Args:
            config_path: Path to pipeline config YAML
            device: Device to use (auto/cpu/mps/cuda)
        """
        self.config_path = config_path
        self.device = device
        self.pipeline = None

    def initialize(self):
        """Initialize the prediction pipeline."""
        logger.info(f"Loading config from {self.config_path}")

        # Load config
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Override device if specified
        if self.device != "auto":
            if "yolo" in config.get("pipeline", {}):
                config["pipeline"]["yolo"]["device"] = self.device
            if "loftr" in config.get("pipeline", {}):
                config["pipeline"]["loftr"]["device"] = self.device

        # Initialize pipeline
        logger.info(f"Initializing pipeline (device: {self.device})")
        pipeline_config = config.get("pipeline", {})
        self.pipeline = HomographyKeypointsPipeline(pipeline_config)

        logger.info(f"Pipeline initialized: {self.pipeline.get_version()}")

    def predict(self, image_path: Path) -> Tuple[dict, str]:
        """Run prediction on image with fallback strategy.

        Args:
            image_path: Path to image file

        Returns:
            Tuple of (annotation_dict, annotator_type)
        """
        if self.pipeline is None:
            raise RuntimeError("Pipeline not initialized. Call initialize() first.")

        # Load image to get dimensions
        img = cv2.imread(str(image_path))
        if img is None:
            logger.error(f"Failed to load image: {image_path}")
            # Use geometric fallback
            annotation = self._generate_geometric_fallback((2048, 2048), image_path.name)
            return annotation, "ml-model-v1.0-geometric-fallback"

        img_h, img_w = img.shape[:2]

        try:
            # Run pipeline
            result: PipelineResult = self.pipeline.predict(image_path)

            if result.success and result.keypoints is not None:
                # Extract keypoints from result
                annotation = self._extract_keypoints(result, img_w, img_h, image_path.name)

                # Determine annotator type based on debug info
                debug_info = result.debug_info or {}
                if "pipeline_fallback" in debug_info.get("method", "").lower() or \
                   "obb" in debug_info.get("method", "").lower():
                    annotator = "ml-model-v1.0-pipeline-fallback"
                else:
                    annotator = "ml-model-v1.0"

                return annotation, annotator
            else:
                # Pipeline failed, use geometric fallback
                logger.warning(f"Pipeline failed for {image_path.name}: {result.error_message}")
                annotation = self._generate_geometric_fallback((img_w, img_h), image_path.name)
                return annotation, "ml-model-v1.0-geometric-fallback"

        except Exception as e:
            logger.error(f"Exception during prediction for {image_path.name}: {e}")
            annotation = self._generate_geometric_fallback((img_w, img_h), image_path.name)
            return annotation, "ml-model-v1.0-geometric-fallback"

    def _extract_keypoints(self, result: PipelineResult, img_w: int, img_h: int,
                          filename: str) -> dict:
        """Extract keypoints from pipeline result.

        Args:
            result: Pipeline result
            img_w: Image width
            img_h: Image height
            filename: Image filename

        Returns:
            Annotation dict in internal format
        """
        keypoints_norm = {
            "top": list(result.keypoints.top),
            "bottom": list(result.keypoints.bottom),
            "left": list(result.keypoints.left),
            "right": list(result.keypoints.right),
            "center": list(result.keypoints.center)
        }

        annotation = {
            "image_size": [img_w, img_h],
            "coords_norm": keypoints_norm,
            "full_image_name": filename,
            "confidence": round(result.confidence, 3),
            "timestamp": datetime.now().isoformat(),
            "debug_info": result.debug_info or {}
        }

        return annotation

    def _generate_geometric_fallback(self, image_size: Tuple[int, int],
                                     filename: str) -> dict:
        """Generate geometric fallback keypoints.

        Args:
            image_size: (width, height) tuple
            filename: Image filename

        Returns:
            Annotation dict with center-based geometric keypoints
        """
        annotation = {
            "image_size": list(image_size),
            "coords_norm": {
                "center": [0.5, 0.5],
                "top": [0.5, 0.1],
                "bottom": [0.5, 0.9],
                "left": [0.1, 0.5],
                "right": [0.9, 0.5]
            },
            "full_image_name": filename,
            "confidence": 0.0,
            "timestamp": datetime.now().isoformat(),
            "debug_info": {"method": "geometric_fallback"}
        }

        return annotation


class PredictionSaver:
    """Save predictions to JSON files grouped by watch model."""

    def __init__(self, output_dir: Path):
        """Initialize prediction saver.

        Args:
            output_dir: Directory to save prediction JSON files
        """
        self.output_dir = output_dir
        self.predictions = defaultdict(dict)  # watch_id -> {image_id: annotation}

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def add_prediction(self, watch_id: str, image_id: str, annotation: dict,
                      annotator: str):
        """Add a prediction to the batch.

        Args:
            watch_id: Watch model ID
            image_id: Quality-agnostic image ID
            annotation: Annotation dict
            annotator: Annotator type string
        """
        # Add annotator field
        annotation["annotator"] = annotator

        # Store in memory
        self.predictions[watch_id][image_id] = annotation

    def save_all(self) -> bool:
        """Save all predictions to JSON files.

        Returns:
            True if successful
        """
        if not self.predictions:
            logger.info("No predictions to save")
            return True

        success = True
        for watch_id, annotations in self.predictions.items():
            if not self._save_watch_file(watch_id, annotations):
                success = False

        return success

    def _save_watch_file(self, watch_id: str, new_annotations: dict) -> bool:
        """Save or merge annotations for a watch model.

        Args:
            watch_id: Watch model ID
            new_annotations: Dict of {image_id: annotation}

        Returns:
            True if successful
        """
        json_file = self.output_dir / f"{watch_id}.json"

        # Load existing annotations if file exists
        existing_annotations = {}
        if json_file.exists():
            try:
                with open(json_file, 'r') as f:
                    existing_annotations = json.load(f)
                logger.debug(f"Loaded {len(existing_annotations)} existing annotations from {json_file}")
            except Exception as e:
                logger.warning(f"Failed to load existing annotations from {json_file}: {e}")

        # Merge (new annotations override existing)
        merged_annotations = {**existing_annotations, **new_annotations}

        # Save
        try:
            with open(json_file, 'w') as f:
                json.dump(merged_annotations, f, indent=2)
            logger.info(f"Saved {len(new_annotations)} predictions to {json_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save predictions to {json_file}: {e}")
            return False


class BatchProcessor:
    """Main orchestrator for batch prediction processing."""

    def __init__(self, images_dir: Path, output_dir: Path, labels_dir: Path,
                 config_path: Path, device: str = "auto", resume: bool = True,
                 force: bool = False, watch_id: Optional[str] = None,
                 checkpoint_freq: int = 10):
        """Initialize batch processor.

        Args:
            images_dir: Directory containing images
            output_dir: Directory to save predictions
            labels_dir: Directory containing existing annotations
            config_path: Path to pipeline config
            device: Device to use (auto/cpu/mps/cuda)
            resume: Resume from progress file
            force: Force reprocess all images (ignore existing)
            watch_id: Only process this watch ID (optional)
            checkpoint_freq: Save progress every N images
        """
        self.images_dir = images_dir
        self.output_dir = output_dir
        self.labels_dir = labels_dir
        self.config_path = config_path
        self.device = device
        self.resume = resume
        self.force = force
        self.watch_id = watch_id
        self.checkpoint_freq = checkpoint_freq

        # Components
        self.progress = ProgressManager()
        self.scanner = ImageScanner(images_dir, labels_dir, output_dir)
        self.runner = PredictionRunner(config_path, device)
        self.saver = PredictionSaver(output_dir)

        # State
        self.interrupted = False
        self.start_time = None

    def run(self):
        """Run batch prediction process."""
        # Register signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)

        logger.info("=" * 80)
        logger.info("Starting batch prediction")
        logger.info("=" * 80)

        self.start_time = time.time()

        # Scan for images to process
        skip_existing = not self.force
        images_to_process = self.scanner.scan_images(
            skip_existing=skip_existing,
            watch_id_filter=self.watch_id
        )

        if not images_to_process:
            logger.info("No images to process")
            return

        # Filter out already processed images if resuming (but not if force is set)
        if self.resume and not self.force:
            images_to_process = [
                (path, img_id, watch_id) for path, img_id, watch_id in images_to_process
                if not self.progress.is_processed(img_id)
            ]
            logger.info(f"Resuming: {len(images_to_process)} images remaining")
        elif self.force:
            # Force reprocess: clear progress and start fresh
            logger.info(f"Force mode: Reprocessing all {len(images_to_process)} images")
            self.progress = ProgressManager()  # Clear progress

        # Update progress stats
        total_images = len(images_to_process)
        self.progress.set_total_images(total_images)

        if total_images == 0:
            logger.info("All images already processed")
            return

        # Initialize pipeline
        try:
            self.runner.initialize()
        except Exception as e:
            logger.error(f"Failed to initialize pipeline: {e}")
            return

        # Process images
        logger.info(f"Processing {total_images} images...")
        logger.info("-" * 80)

        for idx, (image_path, image_id, watch_id) in enumerate(images_to_process, 1):
            if self.interrupted:
                logger.info("Processing interrupted by user")
                break

            logger.info(f"[{idx}/{total_images}] Processing {image_path.name}")

            try:
                # Run prediction
                annotation, annotator = self.runner.predict(image_path)

                # Save prediction
                self.saver.add_prediction(watch_id, image_id, annotation, annotator)

                # Update progress
                success = annotator == "ml-model-v1.0"  # Full pipeline success
                self.progress.mark_processed(image_id, success, None, annotator)

                # Log result
                confidence = annotation.get("confidence", 0.0)
                logger.info(f"[{idx}/{total_images}] {annotator} (confidence: {confidence:.3f})")

            except Exception as e:
                logger.error(f"[{idx}/{total_images}] Failed to process {image_path.name}: {e}")
                self.progress.mark_processed(image_id, False, str(e))

            # Checkpoint progress
            if idx % self.checkpoint_freq == 0:
                self.progress.save()
                self.saver.save_all()
                logger.info(f"Checkpoint saved ({idx} images processed)")
                self._print_progress(idx, total_images, self.progress.get_stats())

        # Final save
        logger.info("-" * 80)
        logger.info("Saving final predictions...")
        self.saver.save_all()
        self.progress.save()

        # Print summary
        elapsed_time = time.time() - self.start_time
        self._print_final_summary(self.progress.get_stats(), elapsed_time)

    def _signal_handler(self, sig, frame):
        """Handle Ctrl+C gracefully."""
        logger.info("\nReceived interrupt signal, saving progress...")
        self.interrupted = True
        self.progress.save()
        self.saver.save_all()
        logger.info("Progress saved. You can resume with --resume flag.")
        sys.exit(0)

    def _print_progress(self, current: int, total: int, stats: dict):
        """Print progress bar."""
        pct = (current / total) * 100 if total > 0 else 0
        successful = stats.get("successful", 0)
        pipeline_fb = stats.get("pipeline_fallback", 0)
        geometric_fb = stats.get("geometric_fallback", 0)
        failed = len(self.progress.data.get("failed_images", {}))

        elapsed = time.time() - self.start_time
        avg_time = elapsed / current if current > 0 else 0
        eta = avg_time * (total - current)

        print("\n" + "=" * 80)
        print("Batch Prediction Progress")
        print("=" * 80)
        print(f"Processed: {current}/{total} ({pct:.1f}%)")
        print(f"Success:   {successful} ({successful/current*100:.1f}%)" if current > 0 else "Success:   0")
        print(f"Pipeline Fallback: {pipeline_fb}")
        print(f"Geometric Fallback: {geometric_fb}")
        print(f"Failed:    {failed}")
        print(f"Elapsed:   {self._format_time(elapsed)}")
        print(f"ETA:       {self._format_time(eta)}")
        print("=" * 80 + "\n")

    def _print_final_summary(self, stats: dict, elapsed_time: float):
        """Print final summary."""
        total = stats.get("processed", 0)
        successful = stats.get("successful", 0)
        pipeline_fb = stats.get("pipeline_fallback", 0)
        geometric_fb = stats.get("geometric_fallback", 0)
        errors = stats.get("errors", {})

        print("\n" + "=" * 80)
        print("BATCH PREDICTION COMPLETE")
        print("=" * 80)
        print(f"Total processed:     {total}")
        print(f"Successful:          {successful} ({successful/total*100:.1f}%)" if total > 0 else "Successful:          0")
        print(f"Pipeline fallback:   {pipeline_fb}")
        print(f"Geometric fallback:  {geometric_fb}")
        print(f"Total time:          {self._format_time(elapsed_time)}")
        print(f"Avg time per image:  {elapsed_time/total:.1f}s" if total > 0 else "Avg time per image:  N/A")

        if errors:
            print("\nError Summary:")
            for error_type, count in sorted(errors.items(), key=lambda x: x[1], reverse=True):
                print(f"  {error_type}: {count}")

        print("=" * 80)
        print(f"Predictions saved to: {self.output_dir}")
        print("\nNext steps:")
        print("  1. Validate predictions:")
        print(f"     python labelstudio/validate_annotations.py --input-dir {self.output_dir}")
        print("  2. Convert to Label Studio format:")
        print(f"     cd labelstudio && python convert_to_labelstudio.py --input-dir ../{self.output_dir}")
        print("=" * 80 + "\n")

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Batch prediction for watch keypoint detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all new images
  python scripts/batch_predict.py

  # Test on single watch model
  python scripts/batch_predict.py --watch-id PATEK_nab_001

  # Resume after interruption
  python scripts/batch_predict.py --resume

  # Force reprocess all images
  python scripts/batch_predict.py --force

  # Use CPU explicitly
  python scripts/batch_predict.py --device cpu
        """
    )

    parser.add_argument(
        "--images-dir",
        type=Path,
        default=DEFAULT_IMAGES_DIR,
        help=f"Directory containing images (default: {DEFAULT_IMAGES_DIR})"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to save predictions (default: {DEFAULT_OUTPUT_DIR})"
    )
    parser.add_argument(
        "--labels-dir",
        type=Path,
        default=DEFAULT_LABELS_DIR,
        help=f"Directory with existing annotations (default: {DEFAULT_LABELS_DIR})"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Pipeline config file (default: {DEFAULT_CONFIG})"
    )
    parser.add_argument(
        "--device",
        type=str,
        default="mps",
        choices=["auto", "cpu", "mps", "cuda"],
        help="Device to use (default: mps for Mac GPU acceleration)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume from progress file (default: True)"
    )
    parser.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="Don't resume, start fresh"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reprocess all images, ignore existing annotations"
    )
    parser.add_argument(
        "--watch-id",
        type=str,
        help="Only process this watch ID (for testing)"
    )
    parser.add_argument(
        "--checkpoint-freq",
        type=int,
        default=10,
        help="Save progress every N images (default: 10)"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Validate paths
    if not args.images_dir.exists():
        logger.error(f"Images directory not found: {args.images_dir}")
        return 1

    if not args.config.exists():
        logger.error(f"Config file not found: {args.config}")
        return 1

    # Create batch processor
    processor = BatchProcessor(
        images_dir=args.images_dir,
        output_dir=args.output_dir,
        labels_dir=args.labels_dir,
        config_path=args.config,
        device=args.device,
        resume=args.resume,
        force=args.force,
        watch_id=args.watch_id,
        checkpoint_freq=args.checkpoint_freq
    )

    # Run batch processing
    try:
        processor.run()
        return 0
    except Exception as e:
        logger.error(f"Batch processing failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
