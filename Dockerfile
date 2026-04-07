FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application
COPY server.py .

# Pre-download the default model during build
RUN python -c "from demucs.pretrained import get_model; get_model('htdemucs')"

EXPOSE 8765

CMD ["python", "server.py"]
