#!/usr/bin/env python3
"""
ML Predictions entry point for Label Studio integration.

This module provides utilities for generating and loading ML predictions
in Label Studio format. It's designed as an entry point for future
ML-assisted pre-annotation workflows.

Usage:
    # As a library
    from ml_predictions import create_predictions_from_model, load_predictions_to_tasks

    # Generate predictions for new images
    python ml_predictions.py generate --images-dir ../downloaded_images --output predictions.json

    # Add predictions to existing tasks
    python ml_predictions.py add-predictions --tasks tasks.json --predictions predictions.json --output tasks_with_predictions.json

Note: The actual ML model integration is OUT OF SCOPE for now.
      This module provides the scaffolding and data format utilities.
"""

import argparse
import json
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple


class KeypointPredictor(Protocol):
    """Protocol for keypoint prediction models."""

    def predict(self, image_path: Path) -> Dict[str, Tuple[float, float]]:
        """
        Predict keypoints for an image.

        Args:
            image_path: Path to the image file

        Returns:
            Dict mapping keypoint name to (x, y) normalized coordinates (0-1)
        """
        ...


class CropROIPredictor(Protocol):
    """Protocol for crop ROI prediction models."""

    def predict(self, image_path: Path) -> Optional[Tuple[float, float, float, float]]:
        """
        Predict crop ROI for an image.

        Args:
            image_path: Path to the image file

        Returns:
            Tuple of (x, y, width, height) as normalized values (0-1),
            or None if no ROI predicted
        """
        ...


def generate_result_id() -> str:
    """Generate a unique result ID for Label Studio annotations."""
    return str(uuid.uuid4())[:8]


def create_keypoint_prediction(
    keypoint_name: str,
    x_norm: float,
    y_norm: float,
    score: float = 1.0,
) -> dict[str, Any]:
    """
    Create a Label Studio keypoint prediction result.

    Args:
        keypoint_name: Name of the keypoint (top, bottom, left, right, center)
        x_norm: X coordinate, normalized 0-1
        y_norm: Y coordinate, normalized 0-1
        score: Confidence score 0-1

    Returns:
        Label Studio prediction result dict
    """
    return {
        "id": generate_result_id(),
        "from_name": "keypoints",
        "to_name": "image",
        "type": "keypointlabels",
        "score": score,
        "value": {
            "x": x_norm * 100,  # Convert to percentage
            "y": y_norm * 100,
            "width": 0.75,
            "keypointlabels": [keypoint_name.capitalize()],
        },
    }


def create_roi_prediction(
    x_norm: float,
    y_norm: float,
    width_norm: float,
    height_norm: float,
    score: float = 1.0,
) -> Dict[str, Any]:
    """
    Create a Label Studio rectangle ROI prediction result.

    Args:
        x_norm: X coordinate of top-left, normalized 0-1
        y_norm: Y coordinate of top-left, normalized 0-1
        width_norm: Width, normalized 0-1
        height_norm: Height, normalized 0-1
        score: Confidence score 0-1

    Returns:
        Label Studio prediction result dict
    """
    return {
        "id": generate_result_id(),
        "from_name": "crop_roi",
        "to_name": "image",
        "type": "rectanglelabels",
        "score": score,
        "value": {
            "x": x_norm * 100,  # Convert to percentage
            "y": y_norm * 100,
            "width": width_norm * 100,
            "height": height_norm * 100,
            "rectanglelabels": ["Crop ROI"],
        },
    }


def create_prediction_for_image(
    image_path: Path,
    keypoint_predictor: Optional[KeypointPredictor] = None,
    roi_predictor: Optional[CropROIPredictor] = None,
) -> Dict[str, Any]:
    """
    Create a complete prediction for an image.

    Args:
        image_path: Path to the image
        keypoint_predictor: Optional keypoint prediction model
        roi_predictor: Optional ROI prediction model

    Returns:
        Label Studio prediction dict with results
    """
    results = []

    if keypoint_predictor:
        keypoints = keypoint_predictor.predict(image_path)
        for name, (x, y) in keypoints.items():
            results.append(create_keypoint_prediction(name, x, y))

    if roi_predictor:
        roi = roi_predictor.predict(image_path)
        if roi:
            x, y, w, h = roi
            results.append(create_roi_prediction(x, y, w, h))

    return {"result": results}


def add_predictions_to_tasks(
    tasks: List[Dict[str, Any]],
    predictions: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Add predictions to existing tasks.

    Args:
        tasks: List of Label Studio task dicts
        predictions: Dict mapping image_key to prediction dict

    Returns:
        Tasks with predictions added
    """
    updated_tasks = []

    for task in tasks:
        task_copy = dict(task)
        image_key = task.get("data", {}).get("image_key")

        if image_key and image_key in predictions:
            pred = predictions[image_key]
            # Add to existing predictions or create new list
            if "predictions" not in task_copy:
                task_copy["predictions"] = []
            task_copy["predictions"].append(pred)

        updated_tasks.append(task_copy)

    return updated_tasks


def create_dummy_predictions(
    images_dir: Path,
    output_file: Path,
) -> None:
    """
    Create dummy predictions for all images in a directory.

    This is a placeholder for actual ML model predictions.
    It generates centered default keypoints and a full-image ROI.

    Args:
        images_dir: Directory containing image folders
        output_file: Output file for predictions
    """
    predictions = {}

    for watch_folder in sorted(images_dir.iterdir()):
        if not watch_folder.is_dir():
            continue

        for image_file in watch_folder.glob("*.jpg"):
            # Extract image key (e.g., "PATEK_nab_001_01" from "PATEK_nab_001_01_face_q3.jpg")
            filename = image_file.stem
            parts = filename.split("_")
            if len(parts) >= 4:
                image_key = "_".join(parts[:4])
            else:
                image_key = filename

            # Create dummy centered predictions
            # In a real implementation, these would come from an ML model
            results = [
                create_keypoint_prediction("top", 0.5, 0.1),
                create_keypoint_prediction("bottom", 0.5, 0.9),
                create_keypoint_prediction("left", 0.1, 0.5),
                create_keypoint_prediction("right", 0.9, 0.5),
                create_keypoint_prediction("center", 0.5, 0.5),
                create_roi_prediction(0.05, 0.05, 0.9, 0.9),
            ]

            predictions[image_key] = {
                "result": results,
                "model_version": "dummy-v1.0",
            }

    with open(output_file, "w") as f:
        json.dump(predictions, f, indent=2)

    print(f"Generated {len(predictions)} dummy predictions to {output_file}")


def load_predictions(predictions_file: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load predictions from a JSON file.

    Args:
        predictions_file: Path to predictions JSON file

    Returns:
        Dict mapping image_key to prediction dict
    """
    with open(predictions_file) as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="ML predictions for Label Studio"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Generate command
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate predictions for images"
    )
    gen_parser.add_argument(
        "--images-dir",
        type=Path,
        default=Path("../downloaded_images"),
        help="Directory containing image folders",
    )
    gen_parser.add_argument(
        "--output",
        type=Path,
        default=Path("predictions.json"),
        help="Output file for predictions",
    )

    # Add predictions command
    add_parser = subparsers.add_parser(
        "add-predictions",
        help="Add predictions to existing tasks"
    )
    add_parser.add_argument(
        "--tasks",
        type=Path,
        required=True,
        help="Input tasks JSON file",
    )
    add_parser.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="Predictions JSON file",
    )
    add_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output tasks JSON file with predictions",
    )

    args = parser.parse_args()

    if args.command == "generate":
        images_dir = args.images_dir.resolve()
        if not images_dir.exists():
            print(f"Error: Images directory not found: {images_dir}")
            return 1

        print(f"Generating predictions for images in: {images_dir}")
        print("Note: Using dummy predictions. Replace with actual ML model.")
        create_dummy_predictions(images_dir, args.output)

    elif args.command == "add-predictions":
        if not args.tasks.exists():
            print(f"Error: Tasks file not found: {args.tasks}")
            return 1
        if not args.predictions.exists():
            print(f"Error: Predictions file not found: {args.predictions}")
            return 1

        with open(args.tasks) as f:
            tasks = json.load(f)

        predictions = load_predictions(args.predictions)

        updated_tasks = add_predictions_to_tasks(tasks, predictions)

        with open(args.output, "w") as f:
            json.dump(updated_tasks, f, indent=2)

        print(f"Added predictions to {len(updated_tasks)} tasks")
        print(f"Output written to: {args.output}")

    return 0


if __name__ == "__main__":
    exit(main())
