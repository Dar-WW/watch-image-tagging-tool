#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import json
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode

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

# Valid Chrono24 sort order values
VALID_SORTORDERS = [0, 1, 11, 5, 15]


def canonicalize_url_drop_query_fragment(url: str) -> str:
    """Drop query params + fragment; keep scheme/host/path."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme or "https", parts.netloc, parts.path, "", ""))


def set_sortorder_in_url(url: str, sortorder: int) -> str:
    """Return a new URL with the sortorder parameter set to the specified value."""
    parts = urlsplit(url)
    query_params = parse_qs(parts.query, keep_blank_values=True)

    # Update sortorder parameter
    query_params["sortorder"] = [str(sortorder)]

    # Rebuild query string
    new_query = urlencode(query_params, doseq=True)

    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def default_index_path(out_dir: str, brand: str, model: str) -> str:
    """Return a stable per brand/model index file path."""
    safe_brand = brand.upper()
    safe_model = model.lower()
    return os.path.join(out_dir, f"_index_{safe_brand}_{safe_model}.jsonl")


def load_index(index_path: str) -> dict[str, str]:
    """Load a JSONL index file mapping canonical_url -> instance_name."""
    index: dict[str, str] = {}
    if not os.path.exists(index_path):
        return index

    with open(index_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = obj.get("url")
            instance = obj.get("instance")
            if isinstance(url, str) and isinstance(instance, str):
                index[url] = instance
    return index


def append_index(index_path: str, url: str, instance: str) -> None:
    """Append one entry to the JSONL index."""
    os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
    with open(index_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"url": url, "instance": instance}, ensure_ascii=False) + "\n")


def read_urls_file(path: str) -> list[str]:
    """Read listing URLs (one per line) from a file or stdin (path == '-')."""
    lines: list[str]
    if path == "-":
        lines = sys.stdin.read().splitlines()
    else:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

    urls: list[str] = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        urls.append(s)
    return urls


def _canonicalize_chrono24_listing_url(href: str) -> str | None:
    """Return a canonical Chrono24 listing URL ending with .htm (drop query/fragment)."""
    if not href:
        return None

    # Handle protocol-relative URLs
    if href.startswith("//"):
        href = "https:" + href

    # Handle relative URLs
    if href.startswith("/"):
        href = "https://www.chrono24.com" + href

    parts = urlsplit(href)
    if parts.netloc and "chrono24.com" not in parts.netloc:
        return None

    # Chrono24 listings generally end with .htm
    if not parts.path.endswith(".htm"):
        return None

    # Must contain an --id123... token somewhere to avoid navigation/other pages
    if "--id" not in parts.path:
        return None

    # Remove query + fragment for canonical identity
    clean = urlunsplit((parts.scheme or "https", parts.netloc or "www.chrono24.com", parts.path, "", ""))
    return clean


def extract_listing_urls_from_search_page(driver: webdriver.Chrome, search_url: str, timeout_s: int = 20) -> list[str]:
    """Open a Chrono24 search page and return unique listing URLs found on it."""
    driver.get(search_url)

    # Wait for results area / links to appear
    WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href]"))
    )

    # Collect links likely to be listing detail pages
    urls: set[str] = set()
    anchors = driver.find_elements(By.CSS_SELECTOR, "a[href]")
    for a in anchors:
        href = a.get_attribute("href")
        canon = _canonicalize_chrono24_listing_url(href)
        if canon:
            urls.add(canon)

    return sorted(urls)


def run_downloader_for_listing(
    script_path: str,
    url: str,
    brand: str,
    model: str,
    out_dir: str,
    instance: str | None = None,
    max_per_listing: int | None = None,
) -> tuple[int, str | None]:
    """
    Invoke download_images_script.py as a subprocess for a single listing.

    Returns:
        Tuple of (return_code, folder_name). folder_name is None if not found in output.
    """
    cmd = [
        sys.executable,
        script_path,
        url,
        "--brand",
        brand,
        "--model",
        model,
        "-o",
        out_dir,
    ]
    if instance:
        cmd.extend(["--instance", instance])
    if max_per_listing is not None:
        cmd.extend(["--max-per-listing", str(max_per_listing)])

    print(f"\n=== Downloading listing ===\n{url}\nCommand: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)

    # Print stdout/stderr for visibility
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)

    # Parse folder name from output
    folder_name = None
    for line in proc.stdout.splitlines():
        if line.startswith("DOWNLOAD_FOLDER:"):
            folder_name = line.split(":", 1)[1].strip()
            break

    return proc.returncode, folder_name


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Batch-download Chrono24 listing images by scanning a Chrono24 search page and "
            "calling download_images_script.py for each listing."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Single sortorder (use URL as-is, default output: scripts/outputs/downloaded_images_datj)\n"
            "  python batch_download_images.py \\\n"
            "    'https://www.chrono24.com/search/index.htm?...&sortorder=0&showpage=1' \\\n"
            "    --brand ROLEX --model datj --delay 2\n\n"
            "  # Try all sortorders to maximize discovery\n"
            "  python batch_download_images.py \\\n"
            "    'https://www.chrono24.com/search/index.htm?...&showpage=1' \\\n"
            "    --brand ROLEX --model datj --delay 2 \\\n"
            "    --try-all-sortorders\n\n"
            "  # Custom output directory\n"
            "  python batch_download_images.py \\\n"
            "    'https://www.chrono24.com/search/index.htm?...&showpage=1' \\\n"
            "    --brand PATEK --model nab -o /path/to/custom/dir --delay 2\n"
        ),
    )

    parser.add_argument(
        "search_url",
        help="Chrono24 search URL (filtered page) containing listings.",
    )
    parser.add_argument(
        "--urls-file",
        default=None,
        help=(
            "Path to a text file containing Chrono24 listing URLs (one per line). "
            "If set, the script will NOT open the search page with Selenium and will use these URLs instead. "
            "Use '-' to read from stdin."
        ),
    )
    parser.add_argument(
        "--brand",
        type=str,
        default="PATEK",
        help="Brand name in uppercase (default: PATEK).",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Model identifier in lowercase (e.g., nab, nam).",
    )
    parser.add_argument(
        "-o",
        "--out-dir",
        default=None,
        help="Base output directory passed through to the downloader (default: scripts/outputs/downloaded_images_{model}).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay (seconds) between runs (default: 2.0).",
    )
    parser.add_argument(
        "--script",
        default=os.path.join(os.path.dirname(__file__), "download_images_script.py"),
        help="Path to download_images_script.py (default: ./download_images_script.py).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the search-page browser in headless mode.",
    )
    parser.add_argument(
        "--index",
        default=None,
        help="Path to housekeeping index JSONL file. Default: <out-dir>/_index_<BRAND>_<model>.jsonl",
    )
    parser.add_argument(
        "--try-all-sortorders",
        action="store_true",
        help="Try all valid sortorder values (0, 1, 11, 5, 15) to maximize listing discovery.",
    )
    parser.add_argument(
        "--max-per-listing",
        type=int,
        default=None,
        help="Cap images downloaded per listing (default: unlimited). Favours cross-instance breadth.",
    )
    args = parser.parse_args()

    brand = args.brand.upper()
    model = args.model.lower()

    # Set default output directory if not specified
    if args.out_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        args.out_dir = os.path.join(script_dir, "outputs", f"downloaded_images_{model}")

    index_path = args.index or default_index_path(args.out_dir, brand, model)
    index = load_index(index_path)

    # Determine which sortorders to try
    if args.try_all_sortorders:
        sortorders_to_try = VALID_SORTORDERS
        print(f"Will try all valid sortorders: {sortorders_to_try}")
    else:
        sortorders_to_try = [None]  # Use URL as-is

    print("Batch configuration:")
    print(f"  Base search URL: {args.search_url}")
    print(f"  URLs file: {args.urls_file}")
    print(f"  Brand: {brand}")
    print(f"  Model: {model}")
    print(f"  Output directory: {args.out_dir}")
    print(f"  Delay between runs: {args.delay}s")
    print(f"  Downloader script: {args.script}")
    print(f"  Index file: {index_path}")
    print(f"  Already downloaded (from index): {len(index)}")
    print(f"  Try all sortorders: {args.try_all_sortorders}")

    if not os.path.exists(args.script):
        raise FileNotFoundError(f"Downloader script not found: {args.script}")

    all_listing_urls: set[str] = set()

    if args.urls_file:
        raw_urls = read_urls_file(args.urls_file)
        if not raw_urls:
            print("No URLs provided in --urls-file.")
            sys.exit(1)

        for u in raw_urls:
            # Drop query/fragment and keep only valid listing URLs
            cu = canonicalize_url_drop_query_fragment(u)
            canon = _canonicalize_chrono24_listing_url(cu)
            if canon:
                all_listing_urls.add(canon)

        print(f"Loaded {len(all_listing_urls)} unique listing URL(s) from {args.urls_file}.")

    else:
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument(f"user-agent={USER_AGENT}")
        chrome_options.add_argument("--window-size=1400,900")
        if args.headless:
            chrome_options.add_argument("--headless=new")

        for sortorder_idx, sortorder in enumerate(sortorders_to_try, start=1):
            # Modify URL with current sortorder if trying multiple
            if sortorder is not None:
                current_search_url = set_sortorder_in_url(args.search_url, sortorder)
                print(f"\n{'='*60}")
                print(f"Sortorder [{sortorder_idx}/{len(sortorders_to_try)}]: {sortorder}")
                print(f"URL: {current_search_url}")
                print(f"{'='*60}")
            else:
                current_search_url = args.search_url
                print(f"\n{'='*60}")
                print(f"Using original URL (no sortorder modification)")
                print(f"{'='*60}")

            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options,
            )

            try:
                listing_urls = extract_listing_urls_from_search_page(driver, current_search_url)
                print(f"Found {len(listing_urls)} listing(s) on this page (sortorder={sortorder})")

                # Add to cumulative set
                before_count = len(all_listing_urls)
                all_listing_urls.update(listing_urls)
                new_count = len(all_listing_urls) - before_count
                print(f"Added {new_count} new unique listing(s) (total unique: {len(all_listing_urls)})")

            finally:
                driver.quit()

    if not all_listing_urls:
        print("\nNo listing URLs found across all sortorders.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Total unique listings found across all sortorders: {len(all_listing_urls)}")
    print(f"{'='*60}")

    # Canonicalize + skip already-downloaded URLs
    canonical_listing_urls: list[str] = []
    for u in all_listing_urls:
        cu = canonicalize_url_drop_query_fragment(u)
        if cu in index:
            continue
        canonical_listing_urls.append(cu)

    if not canonical_listing_urls:
        print("All listings are already downloaded (per index).")
        sys.exit(0)

    print(f"After skipping already-downloaded: {len(canonical_listing_urls)} listing(s) remaining.\n")

    # Run downloader sequentially with delay
    failures: list[tuple[str, int]] = []
    for i, url in enumerate(canonical_listing_urls, start=1):
        print(f"\n[{i}/{len(canonical_listing_urls)}] Starting...")

        rc, folder_name = run_downloader_for_listing(
            script_path=args.script,
            url=url,
            brand=brand,
            model=model,
            out_dir=args.out_dir,
            instance=None,
            max_per_listing=args.max_per_listing,
        )

        if rc == 0:
            # Use actual folder name from downloader, or fallback to placeholder
            instance_name = folder_name if folder_name else f"{brand}_{model}_UNKNOWN"
            append_index(index_path, url, instance_name)
            index[url] = instance_name
            print(f"  ✓ Recorded in index: {instance_name}")
        else:
            failures.append((url, rc))

        # Delay between runs
        if i != len(canonical_listing_urls):
            time.sleep(args.delay)

    if failures:
        print("\nDone with failures:")
        for url, rc in failures:
            print(f"  - rc={rc}: {url}")
        sys.exit(2)

    print("\nDone. All listings processed successfully.")


if __name__ == "__main__":
    main()