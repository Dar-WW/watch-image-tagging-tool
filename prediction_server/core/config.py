"""Configuration loading and validation."""

import yaml
from pathlib import Path
from typing import Dict, Any, List
from pydantic import BaseModel, Field


class ServerSettings(BaseModel):
    """Server configuration settings."""

    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=9090, description="Server port")
    version: str = Field(default="0.1.0", description="Server version")


class PipelineStep(BaseModel):
    """Single pipeline step configuration."""

    method: str = Field(..., description="Method name (yolo, loftr, etc.)")
    model_path: str = Field(default="", description="Path to model weights")
    ransac_thresh: float = Field(default=2.0, description="RANSAC threshold (for homography)")
    template_path: str = Field(default="", description="Path to template file")


class PipelineSettings(BaseModel):
    """Pipeline configuration settings."""

    class Config:
        extra = "allow"  # Allow extra fields from YAML (yolo, loftr, homography, template)

    type: str = Field(default="homography_keypoints", description="Pipeline type")
    confidence_threshold: float = Field(default=0.7, description="Minimum confidence")
    steps: List[PipelineStep] = Field(default_factory=list, description="Pipeline steps")


class CacheSettings(BaseModel):
    """Cache configuration settings."""

    enabled: bool = Field(default=True, description="Enable caching")
    directory: str = Field(default="cache/", description="Cache directory")


class PathSettings(BaseModel):
    """Path configuration settings."""

    media_mount: str = Field(
        default="/label-studio/media", description="Docker media mount point"
    )
    local_media: str = Field(
        default="../downloaded_images", description="Local media directory"
    )


class ServerConfig(BaseModel):
    """Complete server configuration."""

    server: ServerSettings = Field(default_factory=ServerSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    paths: PathSettings = Field(default_factory=PathSettings)


def load_config(config_path: Path) -> ServerConfig:
    """Load and validate configuration from YAML file.

    Args:
        config_path: Path to config.yaml file

    Returns:
        ServerConfig: Validated configuration object

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML is invalid
        ValidationError: If config doesn't match schema
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)

    # Convert steps list to PipelineStep objects
    if "pipeline" in config_data and "steps" in config_data["pipeline"]:
        steps_data = config_data["pipeline"]["steps"]
        config_data["pipeline"]["steps"] = [
            PipelineStep(**step) for step in steps_data
        ]

    return ServerConfig(**config_data)


def get_default_config() -> ServerConfig:
    """Get default configuration.

    Returns:
        ServerConfig: Default configuration
    """
    return ServerConfig()
