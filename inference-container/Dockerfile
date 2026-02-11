FROM python:3.11-slim

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ml

# Install PyTorch CPU-only (separate layer for caching)
RUN pip install --no-cache-dir \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
