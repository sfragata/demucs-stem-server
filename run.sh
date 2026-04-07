#!/bin/bash
set -e

IMAGE_NAME="demucs-stem-server"
CONTAINER_NAME="demucs-server"
PORT="${PORT:-8765}"

# Check for --gpu flag
GPU_FLAGS=""
if [[ "$1" == "--gpu" ]]; then
    GPU_FLAGS="--gpus all"
    echo "🎮 GPU mode enabled"
fi

# Stop existing container
if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
    echo "⏹  Stopping existing container..."
    docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
    docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
fi

# Build if needed
if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    echo "🔨 Building Docker image (this takes a few minutes the first time)..."
    docker build -t "$IMAGE_NAME" .
fi

echo "🚀 Starting Demucs server on port $PORT..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -p "$PORT:8765" \
    $GPU_FLAGS \
    "$IMAGE_NAME"

echo ""
echo "✅ Server running at http://localhost:$PORT"
echo ""
echo "Test it:"
echo "  curl http://localhost:$PORT/health"
echo ""
echo "Separate a song:"
echo "  curl -X POST http://localhost:$PORT/separate \\"
echo "    -F 'file=@song.mp3' -o stems.zip"
echo ""
echo "Logs:  docker logs -f $CONTAINER_NAME"
echo "Stop:  docker stop $CONTAINER_NAME"
