"""S3 image loader with retry logic for SageMaker inference."""

import logging
import time
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3ImageLoader:
    """Downloads images from S3 with retry and exponential backoff."""

    def __init__(self, max_retries: int = 3, base_delay: float = 0.5):
        """Initialize S3 loader.

        Args:
            max_retries: Maximum number of retry attempts.
            base_delay: Base delay in seconds for exponential backoff.
        """
        self.s3_client = boto3.client("s3")
        self.max_retries = max_retries
        self.base_delay = base_delay

    def download(self, bucket: str, key: str, local_dir: Path) -> Path:
        """Download an image from S3 to a local directory.

        Args:
            bucket: S3 bucket name.
            key: S3 object key (e.g., "images/PATEK_nab_001/img.jpg").
            local_dir: Local directory to save the file.

        Returns:
            Path to the downloaded file.

        Raises:
            FileNotFoundError: If the S3 object does not exist (404).
            RuntimeError: If download fails after all retries.
        """
        filename = Path(key).name
        local_path = local_dir / filename
        local_dir.mkdir(parents=True, exist_ok=True)

        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Downloading s3://{bucket}/{key} (attempt {attempt}/{self.max_retries})")
                self.s3_client.download_file(bucket, key, str(local_path))
                logger.info(f"Downloaded to {local_path}")
                return local_path

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code in ("404", "NoSuchKey"):
                    raise FileNotFoundError(
                        f"S3 object not found: s3://{bucket}/{key}"
                    ) from e

                last_error = e
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"S3 download failed (attempt {attempt}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)

            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"Download failed (attempt {attempt}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)

        raise RuntimeError(
            f"Failed to download s3://{bucket}/{key} after {self.max_retries} attempts: {last_error}"
        )
