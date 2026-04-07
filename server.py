"""
Demucs Stem Separator API Server

High-quality music stem separation using Demucs v4.
Designed for local use with the Music Stem Separator iOS app.
"""

import io
import os
import shutil
import tempfile
import time
import zipfile
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
import torch
import torchaudio
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("demucs-server")

AVAILABLE_MODELS = ["htdemucs", "htdemucs_ft", "mdx_extra"]
STEM_NAMES = ["drums", "bass", "other", "vocals"]
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "200"))
DEFAULT_MODEL = os.environ.get("DEMUCS_MODEL", "htdemucs")
PORT = int(os.environ.get("PORT", "8765"))

app = FastAPI(
    title="Demucs Stem Separator",
    description="High-quality music stem separation API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Model cache
_models: dict = {}
_device: Optional[str] = None


def get_device() -> str:
    global _device
    if _device is None:
        env_device = os.environ.get("DEMUCS_DEVICE")
        if env_device:
            _device = env_device
        elif torch.cuda.is_available():
            _device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            _device = "mps"
        else:
            _device = "cpu"
        logger.info(f"Using device: {_device}")
    return _device


def load_model(model_name: str):
    """Load and cache a Demucs model."""
    if model_name not in _models:
        if model_name not in AVAILABLE_MODELS:
            raise ValueError(f"Unknown model: {model_name}")

        logger.info(f"Loading model: {model_name}...")
        start = time.time()

        from demucs.pretrained import get_model
        from demucs.apply import BagOfModels

        model = get_model(model_name)
        if isinstance(model, BagOfModels):
            # BagOfModels wraps multiple models — use as-is
            pass

        device = get_device()
        if device != "cpu":
            model.to(device)

        _models[model_name] = model
        logger.info(f"Model {model_name} loaded in {time.time() - start:.1f}s")

    return _models[model_name]


def load_audio(file_path: str, sr: int = 44100) -> torch.Tensor:
    """Load audio file and return tensor [channels, samples] at target sample rate."""
    try:
        waveform, orig_sr = torchaudio.load(file_path)
    except Exception:
        # Fallback: try soundfile
        data, orig_sr = sf.read(file_path, dtype="float32")
        if data.ndim == 1:
            data = np.stack([data, data])
        else:
            data = data.T
        waveform = torch.from_numpy(data)

    # Resample if needed
    if orig_sr != sr:
        waveform = torchaudio.functional.resample(waveform, orig_sr, sr)

    # Ensure stereo
    if waveform.shape[0] == 1:
        waveform = waveform.repeat(2, 1)
    elif waveform.shape[0] > 2:
        waveform = waveform[:2]

    return waveform


def separate(waveform: torch.Tensor, model_name: str = DEFAULT_MODEL) -> dict[str, np.ndarray]:
    """
    Separate audio into stems using Demucs.

    Args:
        waveform: [2, samples] tensor at 44100 Hz
        model_name: Name of the Demucs model

    Returns:
        Dict mapping stem name to numpy array [2, samples]
    """
    from demucs.apply import apply_model

    model = load_model(model_name)
    device = get_device()

    # Add batch dimension: [1, 2, samples]
    ref = waveform.mean(0)
    waveform_input = (waveform - ref.mean()) / ref.std()
    waveform_input = waveform_input.unsqueeze(0)

    if device != "cpu":
        waveform_input = waveform_input.to(device)

    logger.info(f"Separating {waveform.shape[1] / 44100:.1f}s of audio with {model_name}...")
    start = time.time()

    with torch.no_grad():
        estimates = apply_model(model, waveform_input, device=device, progress=True)

    # estimates shape: [1, num_sources, 2, samples]
    estimates = estimates.squeeze(0)
    # Undo normalization
    estimates = estimates * ref.std() + ref.mean()

    elapsed = time.time() - start
    logger.info(f"Separation complete in {elapsed:.1f}s ({waveform.shape[1] / 44100 / elapsed:.1f}x realtime)")

    # Map to stem names
    source_names = model.sources if hasattr(model, "sources") else STEM_NAMES
    result = {}
    for i, name in enumerate(source_names):
        stem_np = estimates[i].cpu().numpy()
        result[name] = stem_np

    return result


def stems_to_zip(stems: dict[str, np.ndarray], sr: int = 44100, fmt: str = "wav") -> bytes:
    """Package stems into a ZIP file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in stems.items():
            stem_buf = io.BytesIO()
            # data is [2, samples], soundfile expects [samples, 2]
            sf.write(stem_buf, data.T, sr, format=fmt.upper())
            stem_buf.seek(0)
            ext = fmt.lower()
            zf.writestr(f"{name}.{ext}", stem_buf.read())
    buf.seek(0)
    return buf.read()


def stem_to_bytes(data: np.ndarray, sr: int = 44100, fmt: str = "wav") -> bytes:
    """Convert a single stem to audio bytes."""
    buf = io.BytesIO()
    sf.write(buf, data.T, sr, format=fmt.upper())
    buf.seek(0)
    return buf.read()


# ── Endpoints ──────────────────────────────────────────────


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": DEFAULT_MODEL,
        "device": get_device(),
    }


@app.get("/models")
async def list_models():
    return {
        "models": AVAILABLE_MODELS,
        "default": DEFAULT_MODEL,
        "loaded": list(_models.keys()),
    }


@app.post("/separate")
async def separate_endpoint(
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_MODEL),
    stems: Optional[str] = Form(None),
    format: str = Form("wav"),
):
    """Separate audio into stems, returned as a ZIP file."""
    if not file.filename:
        raise HTTPException(400, "No file provided")

    # Validate format
    fmt = format.lower()
    if fmt not in ("wav", "mp3", "flac"):
        raise HTTPException(400, f"Unsupported format: {fmt}")

    # Read upload
    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_MB}MB)")

    # Save to temp file
    suffix = Path(file.filename).suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        waveform = load_audio(tmp_path)
        result = separate(waveform, model)

        # Filter stems if requested
        if stems:
            requested = [s.strip() for s in stems.split(",")]
            result = {k: v for k, v in result.items() if k in requested}

        zip_bytes = stems_to_zip(result, fmt=fmt)

        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=stems.zip"},
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Separation failed: {e}", exc_info=True)
        raise HTTPException(500, f"Separation failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


@app.post("/separate/stream")
async def separate_stream_endpoint(
    file: UploadFile = File(...),
    stem: str = Form(...),
    model: str = Form(DEFAULT_MODEL),
    format: str = Form("wav"),
):
    """Separate audio and return a single stem."""
    if stem not in STEM_NAMES:
        raise HTTPException(400, f"Unknown stem: {stem}. Available: {STEM_NAMES}")

    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_MB}MB)")

    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        waveform = load_audio(tmp_path)
        result = separate(waveform, model)

        if stem not in result:
            raise HTTPException(400, f"Stem '{stem}' not in model output: {list(result.keys())}")

        fmt = format.lower()
        audio_bytes = stem_to_bytes(result[stem], fmt=fmt)

        mime = "audio/wav" if fmt == "wav" else f"audio/{fmt}"
        return Response(
            content=audio_bytes,
            media_type=mime,
            headers={"Content-Disposition": f"attachment; filename={stem}.{fmt}"},
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Separation failed: {e}", exc_info=True)
        raise HTTPException(500, f"Separation failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Demucs server on port {PORT}")
    logger.info(f"Default model: {DEFAULT_MODEL}")
    logger.info(f"Device: {get_device()}")

    # Pre-load default model
    try:
        load_model(DEFAULT_MODEL)
    except Exception as e:
        logger.warning(f"Failed to pre-load model: {e}")

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
