# demucs-stem-server

A FastAPI server for high-quality music stem separation using [Demucs v4](https://github.com/facebookresearch/demucs). Upload an audio file and get back individual stems — **drums**, **bass**, **other** (instruments), and **vocals** — as WAV, MP3, or FLAC files.

Originally designed for use with the **Music Stem Separator iOS app**, but works great as a standalone local API.

---

## Features

- 🎵 Separates audio into 4 stems: drums, bass, other, vocals
- 📦 Returns all stems as a ZIP archive, or streams a single stem directly
- 🤖 Supports multiple Demucs models: `htdemucs`, `htdemucs_ft`, `mdx_extra`
- 🎛️ Output in WAV, MP3, or FLAC format
- ⚡ Automatic GPU detection (CUDA → MPS → CPU)
- 🐳 Docker-first setup with a single command

---

## Requirements

### Local (without Docker)

- Python 3.11+
- [FFmpeg](https://ffmpeg.org/download.html) installed on your system
- 8 GB+ RAM recommended
- GPU optional but recommended (NVIDIA CUDA or Apple MPS)

### Docker

- [Docker](https://docs.docker.com/get-docker/) installed

---

## Installation & Running

### Option 1 — Docker (Recommended)

```bash
# CPU mode
./run.sh

# GPU mode (requires NVIDIA Docker runtime)
./run.sh --gpu
```

The script builds the image on first run (downloads the default model during build) and starts the container on port **8765**.

### Option 2 — Python directly

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python server.py
```

The server starts on `http://localhost:8765`.

---

## Configuration

All configuration is done via environment variables:

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8765` | Port the server listens on |
| `MAX_UPLOAD_MB` | `200` | Maximum upload file size in MB |
| `DEMUCS_MODEL` | `htdemucs` | Default model loaded at startup |
| `DEMUCS_DEVICE` | *(auto)* | Force device: `cpu`, `cuda`, or `mps` |

Example:

```bash
PORT=3000 DEMUCS_MODEL=htdemucs_ft python server.py
```

---

## API Reference

### `GET /health`

Returns server status, active model, and compute device.

```bash
curl http://localhost:8765/health
```

**Response:**

```json
{
  "status": "ok",
  "model": "htdemucs",
  "device": "cpu"
}
```

---

### `GET /models`

Lists available models, the default, and which are currently loaded in memory.

```bash
curl http://localhost:8765/models
```

**Response:**

```json
{
  "models": ["htdemucs", "htdemucs_ft", "mdx_extra"],
  "default": "htdemucs",
  "loaded": ["htdemucs"]
}
```

---

### `POST /separate`

Separates an audio file into stems and returns them bundled in a ZIP archive.

**Form parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `file` | file | ✓ | — | Audio file (mp3, wav, flac, …) |
| `model` | string | | `htdemucs` | Model: `htdemucs`, `htdemucs_ft`, `mdx_extra` |
| `stems` | string | | all | Comma-separated subset of stems to include |
| `format` | string | | `wav` | Output format: `wav`, `mp3`, `flac` |

**Returns:** `application/zip` containing one audio file per stem.

#### Examples

Separate all stems (default WAV output):

```bash
curl -X POST http://localhost:8765/separate \
  -F 'file=@song.mp3' \
  -o stems.zip
```

Separate into MP3 stems using a fine-tuned model:

```bash
curl -X POST http://localhost:8765/separate \
  -F 'file=@song.mp3' \
  -F 'model=htdemucs_ft' \
  -F 'format=mp3' \
  -o stems.zip
```

Get only vocals and drums (skip bass and other):

```bash
curl -X POST http://localhost:8765/separate \
  -F 'file=@song.mp3' \
  -F 'stems=vocals,drums' \
  -o stems.zip
```

Unzip the result:

```bash
unzip stems.zip -d ./stems/
# → ./stems/vocals.wav
# → ./stems/drums.wav
# → ./stems/bass.wav
# → ./stems/other.wav
```

---

### `POST /separate/stream`

Separates an audio file and returns a **single stem** directly as an audio file (no ZIP).

**Form parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `file` | file | ✓ | — | Audio file (mp3, wav, flac, …) |
| `stem` | string | ✓ | — | Stem to return: `drums`, `bass`, `other`, `vocals` |
| `model` | string | | `htdemucs` | Model: `htdemucs`, `htdemucs_ft`, `mdx_extra` |
| `format` | string | | `wav` | Output format: `wav`, `mp3`, `flac` |

**Returns:** Single audio file (`audio/wav`, `audio/mp3`, or `audio/flac`).

#### Examples

Extract vocals:

```bash
curl -X POST http://localhost:8765/separate/stream \
  -F 'file=@song.mp3' \
  -F 'stem=vocals' \
  -o vocals.wav
```

Extract drums in MP3 format using the fine-tuned model:

```bash
curl -X POST http://localhost:8765/separate/stream \
  -F 'file=@song.mp3' \
  -F 'stem=drums' \
  -F 'model=htdemucs_ft' \
  -F 'format=mp3' \
  -o drums.mp3
```

Extract bass as FLAC:

```bash
curl -X POST http://localhost:8765/separate/stream \
  -F 'file=@song.flac' \
  -F 'stem=bass' \
  -F 'format=flac' \
  -o bass.flac
```

---

## Interactive API Docs

FastAPI provides automatic interactive documentation:

- **Swagger UI:** [http://localhost:8765/docs](http://localhost:8765/docs)
- **ReDoc:** [http://localhost:8765/redoc](http://localhost:8765/redoc)

---

## Available Models

| Model | Description |
|---|---|
| `htdemucs` | Default hybrid transformer model. Good balance of quality and speed. |
| `htdemucs_ft` | Fine-tuned version of `htdemucs`. Higher quality, slower. |
| `mdx_extra` | MDX-Net based model. Alternative architecture for different mixes. |

---

## Docker Management

```bash
# View logs
docker logs -f demucs-server

# Stop the container
docker stop demucs-server

# Force rebuild the image
docker rmi demucs-stem-server && ./run.sh
```

---

## License

See [LICENSE](LICENSE).
