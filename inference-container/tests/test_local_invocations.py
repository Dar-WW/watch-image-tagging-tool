"""Integration tests for the SageMaker inference container.

Usage:
    # Start container first:
    #   docker run -p 8080:8080 watch-inference
    #
    # Then run tests:
    #   python tests/test_local_invocations.py
    #   python tests/test_local_invocations.py --with-s3  # requires AWS creds
"""

import argparse
import json
import sys
import requests

BASE_URL = "http://localhost:8080"


def test_ping():
    """Test /ping returns 200."""
    resp = requests.get(f"{BASE_URL}/ping")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    print("PASS: /ping -> 200")


def test_warmup():
    """Test warmup invocation."""
    resp = requests.post(
        f"{BASE_URL}/invocations",
        json={"warmup": True},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    data = resp.json()
    assert "warmup" in data, f"Missing 'warmup' key in response: {data}"
    assert data["warmup"]["status"] == "ok", f"Warmup status not ok: {data}"

    pipeline_info = data["warmup"]["pipeline"]
    assert pipeline_info["type"] == "homography_keypoints"
    print(f"PASS: warmup -> pipeline={pipeline_info['type']}, version={pipeline_info['version']}")


def test_empty_images_400():
    """Test that empty images list returns 400."""
    resp = requests.post(
        f"{BASE_URL}/invocations",
        json={"images": []},
    )
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    print("PASS: empty images -> 400")


def test_invocation_schema(s3_bucket: str, s3_key: str):
    """Test full invocation with a real S3 image and validate response schema.

    Args:
        s3_bucket: S3 bucket containing the test image.
        s3_key: S3 key for the test image.
    """
    resp = requests.post(
        f"{BASE_URL}/invocations",
        json={
            "images": [{"s3_bucket": s3_bucket, "s3_key": s3_key}],
            "job_id": "test-run",
        },
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    data = resp.json()
    assert data["total"] == 1, f"Expected total=1, got {data['total']}"
    assert "predictions" in data
    assert len(data["predictions"]) == 1

    pred = data["predictions"][0]
    assert "filename" in pred
    assert "s3_bucket" in pred
    assert "s3_key" in pred
    assert "success" in pred
    assert "confidence" in pred

    if pred["success"]:
        kp = pred["keypoints"]
        assert kp is not None, "Keypoints missing on successful prediction"
        for name in ("top", "bottom", "left", "right", "center"):
            assert name in kp, f"Missing keypoint: {name}"
            assert len(kp[name]) == 2, f"Keypoint {name} should have 2 coords, got {len(kp[name])}"
            x, y = kp[name]
            assert 0.0 <= x <= 1.0, f"Keypoint {name} x={x} out of [0,1]"
            assert 0.0 <= y <= 1.0, f"Keypoint {name} y={y} out of [0,1]"
        print(f"PASS: invocation -> success, confidence={pred['confidence']:.3f}")
        print(f"  keypoints: { {k: [round(v, 3) for v in vals] for k, vals in kp.items()} }")
    else:
        print(f"WARN: prediction failed (expected if test image is not a watch): {pred.get('error')}")

    print(f"  job_id={data['job_id']}, total={data['total']}, successful={data['successful']}")


def main():
    parser = argparse.ArgumentParser(description="Test inference container locally")
    parser.add_argument("--with-s3", action="store_true", help="Run S3 integration test")
    parser.add_argument("--s3-bucket", default="", help="S3 bucket for test image")
    parser.add_argument("--s3-key", default="", help="S3 key for test image")
    parser.add_argument("--url", default=BASE_URL, help="Base URL of inference server")
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.url

    print(f"Testing inference container at {BASE_URL}\n")

    try:
        test_ping()
        test_warmup()
        test_empty_images_400()

        if args.with_s3:
            if not args.s3_bucket or not args.s3_key:
                print("\nERROR: --s3-bucket and --s3-key required with --with-s3")
                sys.exit(1)
            test_invocation_schema(args.s3_bucket, args.s3_key)

        print("\nAll tests passed!")

    except requests.ConnectionError:
        print(f"\nERROR: Could not connect to {BASE_URL}")
        print("Make sure the container is running: docker run -p 8080:8080 watch-inference")
        sys.exit(1)
    except AssertionError as e:
        print(f"\nFAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
