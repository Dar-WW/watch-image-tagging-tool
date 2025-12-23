"""Abstract base class for prediction pipelines."""

from abc import ABC, abstractmethod
from typing import Dict, Any
from pathlib import Path


class BasePipeline(ABC):
    """Abstract base class for prediction pipelines.

    All pipeline implementations must inherit from this class and implement
    the abstract methods.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize pipeline with configuration.

        Args:
            config: Pipeline configuration dictionary
        """
        self.config = config
        self.model_version = "unknown"

    @abstractmethod
    def predict(self, image_path: Path) -> "PipelineResult":
        """Run prediction on an image.

        Args:
            image_path: Path to the image file

        Returns:
            PipelineResult: Internal prediction result format
        """
        pass

    @abstractmethod
    def get_version(self) -> str:
        """Get pipeline version string.

        Returns:
            str: Version identifier for this pipeline
        """
        pass

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """Get pipeline information and metadata.

        Returns:
            dict: Pipeline metadata (type, version, config, etc.)
        """
        pass
