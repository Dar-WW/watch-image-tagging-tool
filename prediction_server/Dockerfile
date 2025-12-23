# Dockerfile for Watch Keypoint Prediction Server

FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies for OpenCV and ML libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1 \
    libglib2.0-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code as a package
COPY . /app/prediction_server

# Create cache directory
RUN mkdir -p /app/prediction_server/cache

# Expose port
EXPOSE 9090

# Set Python to run in unbuffered mode and add /app to Python path
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Run the server with single worker to prevent concurrent CPU-intensive predictions
CMD ["uvicorn", "prediction_server.main:app", "--host", "0.0.0.0", "--port", "9090", "--workers", "1", "--timeout-keep-alive", "300"]
