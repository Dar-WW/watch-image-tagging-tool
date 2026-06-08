#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import time
from urllib.parse import urlsplit
import argparse

import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0 Safari/537.36"
)


def get_next_folder_name(base_out_dir: str, brand: str, model: str) -> str:
    """
    Compute the next folder name like BRAND_model_001, BRAND_model_002, ...
    by scanning existing subdirectories in base_out_dir.

    Args:
        base_out_dir: Base directory to scan for existing folders
        brand: Brand name in uppercase (e.g., "PATEK", "ROLEX")
        model: Model identifier in lowercase (e.g., "nab", "nam", "sub")

    Returns:
        Next folder name (e.g., "PATEK_nam_001")

    Examples:
        >>> get_next_folder_name("downloaded_images", "PATEK", "nab")
        "PATEK_nab_086"  # if PATEK_nab_085 exists
        >>> get_next_folder_name("downloaded_images", "PATEK", "nam")
        "PATEK_nam_001"  # if no PATEK_nam_* exists yet
    """
    prefix = f"{brand}_{model}_"
    os.makedirs(base_out_dir, exist_ok=True)
    max_num = 0
    try:
        for name in os.listdir(base_out_dir):
            if not name.startswith(prefix):
                continue
            suffix = name[len(prefix):]
            if len(suffix) != 3 or not suffix.isdigit():
                continue
            num = int(suffix)
            if num > max_num:
                max_num = num
    except FileNotFoundError:
        # base_out_dir does not exist yet; we'll create it above anyway
        max_num = 0

    next_num = max_num + 1
    return f"{prefix}{next_num:03d}"


def download_image(img_url: str, dest_dir: str, cookies: dict[str, str], filename: str | None = None) -> None:
    os.makedirs(dest_dir, exist_ok=True)
    if filename is None:
        filename = urlsplit(img_url).path.rsplit("/", 1)[-1]
    dest_path = os.path.join(dest_dir, filename)

    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.chrono24.com",
    }

    resp = requests.get(
        img_url,
        headers=headers,
        cookies=cookies,
        stream=True,
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"  ! Failed {img_url} (status {resp.status_code})")
        return

    total = 0
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                continue
            f.write(chunk)
            total += len(chunk)

    print(f"  ✓ Saved {filename} ({total} bytes)")


def process_listing(driver, url: str, base_out_dir: str, brand: str, model: str,
                    max_per_listing: int | None = None):
    """
    Process a Chrono24 listing and download all high-res images.

    Args:
        driver: Selenium WebDriver instance
        url: Chrono24 listing URL
        base_out_dir: Base directory for downloads
        brand: Brand name in uppercase (e.g., "PATEK")
        model: Model identifier in lowercase (e.g., "nab", "nam")
    """
    print(f"\nProcessing {url}")
    print(f"Brand: {brand}, Model: {model}")
    driver.get(url)

    # Wait for the main image area to load (tweak selector if needed)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-zoom-image], img"))
        )
    except Exception:
        print("  ! Page did not load images in time")
        return

    time.sleep(2)  # small extra buffer if gallery is lazy-loaded

    # Collect zoom image URLs
    zoom_urls = set()

    # Preferred: explicit data-zoom-image attribute
    for el in driver.find_elements(By.CSS_SELECTOR, "[data-zoom-image]"):
        z = el.get_attribute("data-zoom-image")
        if z:
            zoom_urls.add(z)

    # Fallback: any image src ending with -Zoom.jpg, or patterns we can map to zoom
    if not zoom_urls:
        for el in driver.find_elements(By.TAG_NAME, "img"):
            src = el.get_attribute("src")
            if not src:
                continue
            # Existing Chrono24 zoom pattern
            if "-Zoom.jpg" in src:
                zoom_urls.add(src)
            # Pattern: ...-ExtraLarge.jpg -> ...-Zoom.jpg
            elif "-ExtraLarge" in src:
                zoom_src = src.replace("-ExtraLarge", "-Zoom")
                zoom_urls.add(zoom_src)
            # New pattern: ..._xxl_... -> ..._zoom_...
            elif "_xxl_" in src:
                zoom_src = src.replace("_xxl_", "_zoom_")
                zoom_urls.add(zoom_src)

    if not zoom_urls:
        print("  ! No high-res URLs found in DOM")
        return

    # Normalise URLs a bit
    normalised = []
    for u in zoom_urls:
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = "https://img.chrono24.com" + u
        normalised.append(u)

    normalised = sorted(set(normalised))

    # Cap images per listing to favour cross-instance breadth over redundant
    # near-duplicate shots of the same watch. The downstream face filter
    # discards ~50% anyway, so pull a few extra above the desired net.
    if max_per_listing is not None and len(normalised) > max_per_listing:
        print(f"  Capping {len(normalised)} → {max_per_listing} images for this listing")
        normalised = normalised[:max_per_listing]

    # Build a cookies dict from the browser session
    cookie_dict = {c["name"]: c["value"] for c in driver.get_cookies()}

    folder = get_next_folder_name(base_out_dir, brand, model)
    dest_dir = os.path.join(base_out_dir, folder)
    print(f"  Found {len(normalised)} image(s); saving into {dest_dir}")

    # Print folder name in parseable format for batch script
    print(f"DOWNLOAD_FOLDER: {folder}")

    for idx, img_url in enumerate(normalised, start=1):
        # Preserve original extension if possible (default to .jpg)
        path = urlsplit(img_url).path
        _, ext = os.path.splitext(path)
        if not ext:
            ext = ".jpg"
        # Filename format: {BRAND}_{model}_{watch_num}_{view_num}_face.jpg
        filename = f"{folder}_{idx:02d}_face{ext}"
        download_image(img_url, dest_dir, cookie_dict, filename=filename)


def main():
    parser = argparse.ArgumentParser(
        description="Download high-res Chrono24 images for a single listing using Selenium.",
        epilog="""
Examples:
  # Download Patek Philippe Nautilus
  python download_images_script.py <url> --brand PATEK --model nab

  # Download Patek Philippe Nautilus Moonphase
  python download_images_script.py <url> --brand PATEK --model nam

  # Download Rolex Submariner (future)
  python download_images_script.py <url> --brand ROLEX --model sub

  # Use custom output directory
  python download_images_script.py <url> --brand PATEK --model nam -o /path/to/output
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "url",
        help="Chrono24 listing URL (e.g. https://www.chrono24.com/...--id14920047.htm)",
    )
    parser.add_argument(
        "--brand",
        type=str,
        default="PATEK",
        help="Brand name in uppercase (default: PATEK). Examples: PATEK, ROLEX, AP",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Model identifier in lowercase. Examples: nab (Nautilus), nam (Nautilus Moonphase), sub (Submariner)",
    )
    parser.add_argument(
        "-o",
        "--out-dir",
        default=None,
        help="Base output directory (default: scripts/outputs/downloaded_images_{model})",
    )
    parser.add_argument(
        "--max-per-listing",
        type=int,
        default=None,
        help="Cap images downloaded per listing (default: unlimited). Favours breadth.",
    )
    args = parser.parse_args()

    # Validate and normalize inputs
    brand = args.brand.upper()  # Ensure uppercase
    model = args.model.lower()  # Ensure lowercase

    # Set default output directory if not specified
    if args.out_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        args.out_dir = os.path.join(script_dir, "outputs", f"downloaded_images_{model}")

    print(f"Download configuration:")
    print(f"  Brand: {brand}")
    print(f"  Model: {model}")
    print(f"  Output directory: {args.out_dir}")
    print()

    chrome_options = webdriver.ChromeOptions()
    # Optional headless:
    # chrome_options.add_argument("--headless=new")
    chrome_options.add_argument(f"user-agent={USER_AGENT}")
    chrome_options.add_argument("--window-size=1400,900")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options,
    )

    try:
        process_listing(driver, args.url, args.out_dir, brand, model,
                        max_per_listing=args.max_per_listing)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()