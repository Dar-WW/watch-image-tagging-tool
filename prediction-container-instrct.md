
SageMaker Serverless Inference Container — Engineering Instructions

0) Context: what you’re building

We’re building the ML inference backend for the Kairos WatchId Demo web app.

The user flow:
	•	User uploads verification images to S3 (Zurich) via pre-signed URLs.
	•	The backend (Lambda worker) triggers inference.
	•	Inference runs a pipeline:

YOLO OBB detection → LoFTR alignment → keypoints derivation (template-based)

This inference will be hosted as a SageMaker Serverless Inference Endpoint.

Design choice

We will implement the inference container to accept S3 object references (URIs or bucket+key), not raw image bytes, because:
	•	payload is small and fast
	•	uploads already exist in S3
	•	data stays in Zurich and doesn’t pass through other regions/services
	•	avoids API Gateway/AppSync payload limits and client encoding overhead

⸻

1) Expected inputs/outputs

1.1 Request format (HTTP POST /invocations)

Your container must accept JSON like:

{
  "jobId": "uuid",
  "projectId": "uuid",
  "modelVersion": "v1",
  "watchModel": "mil",
  "images": [
    { "bucket": "kairos-watchid", "key": "uploads/verify/<projectId>/<jobId>/img1.jpg" },
    { "bucket": "kairos-watchid", "key": "uploads/verify/<projectId>/<jobId>/img2.jpg" }
  ],
  "template": {
    "templateModel": "mil",
    "templateVersion": "v1"
  },
  "params": {
    "yoloConfThreshold": 0.25,
    "minLoftrMatches": 50,
    "minHomographyInliers": 10
  }
}

Notes:
	•	watchModel / template.templateModel tells the pipeline which template configuration to use.
	•	params can be optional; defaults should come from config.

1.2 Response format

Return one JSON response with:
	•	normalized keypoints (coords_norm) for each image
	•	pipeline metadata / debug info
	•	per-image confidence
	•	a top-level success flag

Example response:

{
  "jobId": "uuid",
  "success": true,
  "predictions": {
    "img1.jpg": {
      "image_size": [2228, 2066],
      "coords_norm": {
        "top": [0.442, 0.184],
        "bottom": [0.591, 0.736],
        "left": [0.163, 0.444],
        "right": [0.841, 0.434],
        "center": [0.510, 0.436]
      },
      "confidence": 0.289,
      "debug_info": {
        "yolo_detections": 1,
        "yolo_confidence": 0.864,
        "loftr_matches": 571,
        "homography_inliers": 165,
        "method": "YOLO-LoFTR-Homography",
        "template_model": "mil"
      }
    }
  },
  "errors": []
}

Important: This output should match our existing annotation format as closely as possible (see watch-image-tagging-tool/scripts/README.md).

⸻

2) Container requirements (SageMaker inference contract)

SageMaker expects the container to implement:
	•	GET /ping → returns 200 OK if healthy
	•	POST /invocations → accepts JSON body and returns JSON

You can implement this using:
	•	FastAPI + uvicorn (simple)
	•	Flask + gunicorn (also fine)

⸻

3) Folder layout we want in the repo

Create a new folder (suggestion):

inference-container/
  Dockerfile
  requirements.txt
  app/
    server.py
    pipeline/
      predictor.py
      loaders.py
      templates.py
      config.py
  tests/
    test_local_invocations.py

Keep it self-contained.

⸻

4) Pipeline implementation notes

4.1 Download images from S3
	•	Use boto3 inside the container.
	•	Use the IAM role attached to the SageMaker endpoint (no hardcoded keys).
	•	Download each image to /tmp/<jobId>/<imageName>.jpg.

Implementation detail
	•	Use boto3.client("s3").download_file(bucket, key, local_path)
	•	Add basic retry (3 retries) for transient errors.

4.2 Run pipeline on local files

Reuse the same logic as the existing offline script:
	•	YOLO detection
	•	LoFTR matching/alignment
	•	homography
	•	template-based keypoint derivation
	•	fallback modes (full → pipeline fallback → geometric fallback)

This should match the semantics described in:
	•	watch-image-tagging-tool/scripts/README.md

4.3 Return predictions per image

Use image filename (or original key basename) as the dict key so it’s stable.

⸻

5) Model files & configs strategy (manual deployment friendly)

We need a clean way to ship:
	•	YOLO weights
	•	LoFTR weights
	•	template assets/config

Preferred approach (V1): bake weights into image
	•	Put weights under inference-container/app/models/
	•	Bake into Docker image

Pros: simplest, fewer moving parts
Cons: larger image, redeploy needed for new weights

Alternative (later): weights in S3
	•	Store weights in S3 with versioning, e.g.
	•	s3://.../models/yolo/<version>/best.pt
	•	Pass version via env vars or request
	•	Download on startup and cache to /tmp/models/

We can start with “baked-in” for V1 and migrate later.

⸻

6) Performance & warm-up considerations

Cold starts

This is serverless: cold starts can happen.

Add a “warmup path”:
	•	If request contains { "warmup": true }:
	•	load models
	•	run a tiny no-op check
	•	return quickly

This allows:
	•	backend to pre-warm near user action
	•	future option to run a scheduled warm-up for demos

⸻

7) Dockerfile guidance (high level)
	•	Use a Python base image compatible with Torch/CPU (unless you are using GPU later).
	•	Install system deps required by OpenCV (if needed).
	•	Install Python deps from requirements.txt
	•	Copy app code
	•	Expose port 8080 (typical SageMaker container convention)
	•	Start server on 0.0.0.0:8080

⸻

8) Local testing workflow (required)

Before we push to ECR, we must be able to test locally.

Local run
	•	Run container with AWS creds available (for S3 download) OR use local test images.
	•	Example test request includes bucket+key.

Output checks
	•	Validate:
	•	response JSON matches expected schema
	•	coords are normalized [0..1]
	•	fallback behavior matches the “three-tier strategy”
	•	debug_info fields are present

Add a simple tests/test_local_invocations.py script that:
	•	sends a local HTTP request to localhost:8080/invocations
	•	prints response and validates minimal schema

⸻

9) ECR push + SageMaker setup (next step after container works)

Once container works locally:
	1.	Create ECR repo (CDK or manual)
	2.	docker build -t <repo>:<tag> .
	3.	docker push ...
	4.	Create SageMaker model referencing:
	•	ECR image
	•	execution role with S3 access
	5.	Create Serverless EndpointConfig (memory + concurrency)
	6.	Create endpoint

Lambda will call InvokeEndpoint with the request payload above.

⸻

10) Definition of done
	•	Container responds to /ping and /invocations
	•	Given S3 image references, returns predictions in expected annotation format
	•	Works locally
	•	Image built & pushed to ECR
	•	Endpoint can be created in SageMaker Serverless and invoked successfully