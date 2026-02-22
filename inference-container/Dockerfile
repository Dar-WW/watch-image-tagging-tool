FROM python:3.11-slim

# Install system dependencies for OpenCV headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ml

# Install PyTorch CPU-only (separate layer for caching)
RUN pip install --no-cache-dir \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python dependencies
# ultralytics pulls in opencv-python (full), so we uninstall it and
# force-reinstall opencv-python-headless which provides the same cv2 module
# without requiring libGL.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip uninstall -y opencv-python 2>/dev/null; true
RUN pip install --no-cache-dir --force-reinstall opencv-python-headless

# Pre-download LoFTR weights so they're cached in the image
COPY build_scripts/ build_scripts/
RUN python build_scripts/download_loftr_weights.py

# Copy YOLO model weights
COPY app/models/ app/models/

# Copy templates
COPY app/templates/ app/templates/

# Copy application code
COPY app/__init__.py app/__init__.py
COPY app/server.py app/server.py
COPY app/utils/ app/utils/
COPY app/pipeline/ app/pipeline/

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

EXPOSE 8080

# SageMaker invokes the container with `docker run <image> serve`
# Use an entrypoint script that accepts "serve" and starts uvicorn
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
