import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Literal, Dict, Any

# Ensure backend directory is in sys.path for local module imports
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, status, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import yt_dlp
from faster_whisper import WhisperModel
from google import genai
from google.genai import types

from audio_analyzer import compute_loudness_per_second, apply_audio_excitement_bonus
from captions import generate_ass_subtitles, CAPTION_STYLES
from reframe import (
    sample_clip_faces,
    detect_voice_activity_ffmpeg,
    compute_smart_reframe_path,
    render_smart_reframe_video,
)
from clip_enhancer import (
    plan_cuts_and_keep_segments,
    execute_trim_and_concat,
    apply_background_music,
    detect_sfx_moments_gemini,
    apply_sound_effects,
    pick_broll_cues_gemini,
    overlay_broll_clips,
)
from thumbnail_generator import (
    sample_and_score_frames,
    pick_top_diverse_frames,
    generate_punchy_text_hooks_gemini,
    render_thumbnail,
)

# Load environment variables
load_dotenv()
ROOT_DIR = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == "backend" else Path(__file__).resolve().parent
if (ROOT_DIR / ".env").exists():
    load_dotenv(ROOT_DIR / ".env")

def clean_model_name(name: Optional[str]) -> str:
    """
    Clean model name:
    - Strip whitespace and surrounding quotes (' or ")
    - Remove leading 'models/' prefix
    """
    if not name:
        return ""
    cleaned = str(name).strip().strip("'\"").strip()
    if cleaned.startswith("models/"):
        cleaned = cleaned[len("models/"):].strip()
    return cleaned

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Read GEMINI_MODEL and fallbacks, cleaned of whitespace, quotes, and 'models/'
GEMINI_MODEL = clean_model_name(os.getenv("GEMINI_MODEL", "gemini-2.5-flash")) or "gemini-2.5-flash"
GEMINI_FALLBACK_MODELS_RAW = os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash,gemini-3.5-flash-lite")

# Whisper model configuration: "tiny", "base", "small", "medium", "large-v3"
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "small")

# Ensure storage directories exist
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(ROOT_DIR / "storage")))
VIDEOS_DIR = STORAGE_DIR / "videos"
EXPORTS_DIR = STORAGE_DIR / "exports"
THUMBNAILS_DIR = STORAGE_DIR / "thumbnails"
HIGHLIGHTS_CACHE_DIR = STORAGE_DIR / "cache"

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
if not PROMPTS_DIR.exists():
    PROMPTS_DIR = ROOT_DIR / "prompts"

VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
HIGHLIGHTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

def get_highlights_cache_file(video_id: str, prompt: Optional[str], min_sec: int, max_sec: int) -> Path:
    prompt_clean = (prompt or "").strip().lower()
    raw_key = f"{video_id}::{prompt_clean}::{min_sec}::{max_sec}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]
    return HIGHLIGHTS_CACHE_DIR / f"highlights_{video_id}_{key_hash}.json"

# Frontend distribution directory
DIST_DIR = ROOT_DIR / "dist"

# Test benchmark logger
TEST_LOG_PATH = STORAGE_DIR / "test_log.json"

def format_bytes(b: Optional[int]) -> str:
    """Format bytes into readable string."""
    if b is None or b < 0:
        return "-"
    if b < 1024:
        return f"{b} B"
    elif b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    elif b < 1024 * 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    else:
        return f"{b / (1024 * 1024 * 1024):.2f} GB"

def log_test_step(step: str, duration_sec: float, file_size: Optional[int], result: str, details: Optional[str] = None):
    """
    Log test execution metrics to storage/test_log.json:
    - step name (import-file, import-url, transcribe, highlights, export)
    - duration in seconds
    - file size in bytes and human-readable string
    - result ("ok" or "error")
    - details (optional message, filename, or clip counts)
    """
    try:
        entries = []
        if TEST_LOG_PATH.exists():
            try:
                with open(TEST_LOG_PATH, "r", encoding="utf-8") as f:
                    entries = json.load(f)
                    if not isinstance(entries, list):
                        entries = []
            except Exception:
                entries = []

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        entry = {
            "timestamp": now_str,
            "step": step,
            "duration_sec": round(duration_sec, 2),
            "file_size_bytes": file_size,
            "file_size": format_bytes(file_size),
            "result": "ok" if result.lower() == "ok" else "error",
            "details": details or "",
        }
        entries.append(entry)
        if len(entries) > 200:
            entries = entries[-200:]

        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        with open(TEST_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
    except Exception as e:
        print(f"[test_log warning]: {e}")

# In-memory progress tracking for transcription
transcribe_progress: Dict[str, int] = {}

# Lazy-loaded singleton Whisper model instance
_whisper_model: Optional[WhisperModel] = None

app = FastAPI(
    title="ClipSnap API",
    description="Backend API for personal YouTube video clipper",
    version="1.0.0"
)

# Enable CORS for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# Helpers & Utilities
# ==========================================

_SELECTED_VIDEO_ENCODER: Optional[str] = None
_GEMINI_STARTUP_STATUS: Dict[str, Any] = {
    "status": "pending",
    "details": "Startup test not run yet"
}


@app.on_event("startup")
def startup_event():
    """Run hardware encoder detection and Gemini self-test on app startup."""
    try:
        detect_best_video_encoder()
    except Exception as e:
        print(f"[Startup] Encoder detection error: {e}")
    try:
        run_gemini_startup_test()
    except Exception as e:
        print(f"[Startup] Gemini self-test error: {e}")



def get_gemini_http_options(timeout_ms: int = 60000) -> Optional[types.HttpOptions]:
    """
    Construct HttpOptions disabling hidden SDK retries.
    Uses HttpOptions(timeout=timeout_ms, retry_options=types.HttpRetryOptions(attempts=1)),
    or falls back to HttpOptions(timeout=timeout_ms) if retry_options is rejected.
    """
    try:
        if hasattr(types, "HttpRetryOptions"):
            return types.HttpOptions(timeout=timeout_ms, retry_options=types.HttpRetryOptions(attempts=1))
        return types.HttpOptions(timeout=timeout_ms)
    except Exception:
        try:
            return types.HttpOptions(timeout=timeout_ms)
        except Exception:
            return None


def run_gemini_startup_test():
    """Run a tiny startup self-test call with Gemini and store status for /diagnostics."""
    global _GEMINI_STARTUP_STATUS
    if not GEMINI_API_KEY or GEMINI_API_KEY in ("YOUR_GEMINI_API_KEY_HERE", "MY_GEMINI_API_KEY"):
        _GEMINI_STARTUP_STATUS = {
            "status": "error",
            "details": "GEMINI_API_KEY not configured"
        }
        print("[Gemini Startup Test] GEMINI_API_KEY not configured.")
        return

    t0 = time.time()
    cleaned_model = clean_model_name(GEMINI_MODEL) or "gemini-2.5-flash"
    try:
        http_opts = get_gemini_http_options(timeout_ms=10000)
        client = genai.Client(api_key=GEMINI_API_KEY, http_options=http_opts) if http_opts else genai.Client(api_key=GEMINI_API_KEY)
        res = client.models.generate_content(
            model=cleaned_model,
            contents="Say hi in 1 word.",
            config=types.GenerateContentConfig(temperature=0.1)
        )
        duration = time.time() - t0
        if res and res.text:
            msg = f"Gemini OK ({cleaned_model}, {duration:.2f}s)"
            _GEMINI_STARTUP_STATUS = {
                "status": "ok",
                "details": msg,
                "model": cleaned_model,
                "duration_sec": round(duration, 2)
            }
            print(f"[Gemini Startup Test] {msg}")
        else:
            raise ValueError("Empty response from Gemini")
    except Exception as e:
        duration = time.time() - t0
        err_msg = str(e)
        _GEMINI_STARTUP_STATUS = {
            "status": "error",
            "details": f"Gemini Error ({cleaned_model}): {err_msg}",
            "model": cleaned_model,
            "duration_sec": round(duration, 2)
        }
        print(f"[Gemini Startup Test Error] {err_msg}")


def detect_best_video_encoder() -> str:
    """
    Test hardware acceleration encoders (h264_nvenc, h264_qsv, h264_amf)
    with a 1-second synthetic test encode at startup.
    Returns the first working encoder or falls back to 'libx264'.
    """
    global _SELECTED_VIDEO_ENCODER
    if _SELECTED_VIDEO_ENCODER is not None:
        return _SELECTED_VIDEO_ENCODER

    candidates = ["h264_nvenc", "h264_qsv", "h264_amf"]
    for candidate in candidates:
        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "testsrc=duration=1:size=320x240:rate=1",
                "-c:v", candidate,
                "-f", "null", "-"
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
            if res.returncode == 0:
                print(f"[FFmpeg Encoder] Selected hardware encoder: '{candidate}'")
                _SELECTED_VIDEO_ENCODER = candidate
                return candidate
        except Exception:
            pass

    print("[FFmpeg Encoder] Using software encoder 'libx264'")
    _SELECTED_VIDEO_ENCODER = "libx264"
    return _SELECTED_VIDEO_ENCODER


def get_encoder_args(crf: int = 24) -> List[str]:
    """Return optimal FFmpeg encoder flags with strict quality targets to keep files small."""
    enc = detect_best_video_encoder()
    if enc == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-cq", "28", "-preset", "veryfast"]
    elif enc == "h264_qsv":
        return ["-c:v", "h264_qsv", "-global_quality", "26", "-look_ahead", "0", "-preset", "veryfast"]
    elif enc == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "26", "-qp_p", "28"]
    else:
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf)]


def probe_video_codecs(file_path: Path) -> Dict[str, str]:
    """Use ffprobe to inspect video and audio codecs."""
    v_codec, a_codec = "", ""
    try:
        res_v = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        if res_v.returncode == 0:
            v_codec = res_v.stdout.strip().lower()

        res_a = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        if res_a.returncode == 0:
            a_codec = res_a.stdout.strip().lower()
    except Exception as e:
        print(f"[ffprobe probe error]: {e}")
    return {"vcodec": v_codec, "acodec": a_codec, "video": v_codec, "audio": a_codec}


def get_whisper_model() -> WhisperModel:
    """Lazy-load faster-whisper model on CPU using int8 quantization and all CPU cores."""
    global _whisper_model
    if _whisper_model is None:
        threads = os.cpu_count() or 4
        print(f"[Whisper] Initializing WhisperModel('{WHISPER_MODEL_NAME}', compute_type='int8', cpu_threads={threads})...")
        _whisper_model = WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8", cpu_threads=threads)
    return _whisper_model


def generate_video_id() -> str:
    """Generate a short 8-character random string ID."""
    return secrets.token_hex(4)


def get_video_duration(file_path: Path) -> float:
    """Use ffprobe to get precise video duration in seconds."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path)
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0 or not result.stdout.strip():
            raise ValueError("ffprobe returned an empty result.")
        return round(float(result.stdout.strip()), 2)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="FFmpeg/ffprobe is not installed on your system. Please install FFmpeg to continue."
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read video duration. Please verify the file is a valid video."
        )


def extract_audio_wav(video_path: Path, wav_path: Path) -> Tuple[float, int, str]:
    """
    Extract 16kHz mono 16-bit PCM WAV audio from video with exact FFmpeg command:
    ffmpeg -y -nostdin -i <video> -vn -sn -dn -map 0:a:0 -ac 1 -ar 16000 -c:a pcm_s16le <video_id>.temp.wav
    Runs with 10 minute timeout, capturing stderr.
    Returns (duration_seconds, output_file_size_bytes, exact_cmd_string).
    """
    cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", str(video_path),
        "-vn", "-sn", "-dn",
        "-map", "0:a:0",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(wav_path)
    ]
    cmd_str = " ".join(cmd)
    t0 = time.time()
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600
        )
        duration = time.time() - t0
        if res.returncode != 0:
            stderr_text = (res.stderr or "").strip()
            if "matches no streams" in stderr_text or "Stream map '0:a:0' matches no streams" in stderr_text or "Output file #0 does not contain any stream" in stderr_text:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This video has no sound, so I can't find clips."
                )
            raise RuntimeError(f"Audio extraction failed: {stderr_text if stderr_text else 'FFmpeg code ' + str(res.returncode)}")

        if not wav_path.exists():
            raise RuntimeError("Audio extraction output file was not created.")

        file_size = wav_path.stat().st_size
        return duration, file_size, cmd_str

    except subprocess.TimeoutExpired as te:
        duration = time.time() - t0
        stderr_text = te.stderr.decode("utf-8", errors="ignore") if isinstance(te.stderr, bytes) else (te.stderr or "")
        raise RuntimeError(f"Audio extraction timed out after 10 minutes: {stderr_text.strip()}")
    except HTTPException:
        raise
    except Exception as e:
        err_str = str(e)
        if "matches no streams" in err_str or "no sound" in err_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This video has no sound, so I can't find clips."
            )
        raise RuntimeError(f"Audio extraction error: {err_str}")


def convert_or_save_as_mp4(temp_input_path: Path, output_mp4_path: Path, is_mov: bool):
    """Save or remux video to standard MP4 container."""
    if not is_mov:
        shutil.move(str(temp_input_path), str(output_mp4_path))
        return

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(temp_input_path),
        "-c", "copy",
        str(output_mp4_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            cmd_reencode = [
                "ffmpeg",
                "-y",
                "-i", str(temp_input_path),
                "-c:v", "libx264",
                "-c:a", "aac",
                str(output_mp4_path)
            ]
            subprocess.run(cmd_reencode, check=True)
    except Exception:
        shutil.copyfile(str(temp_input_path), str(output_mp4_path))
    finally:
        if temp_input_path.exists():
            temp_input_path.unlink()


def group_words_into_lines(words: List[Dict[str, Any]]) -> str:
    """Group words into timestamped sentence-like lines for Gemini."""
    lines = []
    current_words = []
    line_start = 0.0

    for i, w in enumerate(words):
        word_text = str(w.get("word", "")).strip()
        if not word_text:
            continue
        if not current_words:
            line_start = float(w.get("start", 0.0))

        current_words.append(word_text)

        ends_sentence = word_text.endswith((".", "?", "!", "…"))
        pause_after = False
        if i < len(words) - 1:
            pause_after = (float(words[i + 1].get("start", 0.0)) - float(w.get("end", 0.0))) > 0.8

        if ends_sentence or pause_after or len(current_words) >= 15:
            line_end = float(w.get("end", 0.0))
            lines.append(f"[{line_start:.1f}s - {line_end:.1f}s] {' '.join(current_words)}")
            current_words = []

    if current_words:
        last_end = float(words[-1].get("end", 0.0))
        lines.append(f"[{line_start:.1f}s - {last_end:.1f}s] {' '.join(current_words)}")

    return "\n".join(lines)


def snap_to_word_boundary(t: float, words: List[Dict[str, Any]], is_start: bool) -> float:
    """Snap a timestamp to the closest spoken word boundary."""
    if not words:
        return round(t, 2)
    if is_start:
        closest = min(words, key=lambda w: abs(float(w.get("start", 0.0)) - t))
        return round(float(closest.get("start", t)), 2)
    else:
        closest = min(words, key=lambda w: abs(float(w.get("end", 0.0)) - t))
        return round(float(closest.get("end", t)), 2)


def build_export_ffmpeg_command(
    input_video: Path,
    output_video: Path,
    start_sec: float,
    end_sec: float,
    format_type: str,
    options: Optional[Dict[str, Any]] = None,
    ass_subtitle_path: Optional[Path] = None,
) -> List[str]:
    """
    Builds the FFmpeg command to cut, center-crop, burn animated captions,
    and re-encode a video clip.
    Can be extended with background music and B-roll overlays in the future.
    """
    duration = max(0.5, end_sec - start_sec)

    # 9:16 = 1080x1920 center crop
    # 1:1 = 1080x1080 center crop
    # 4:3 = 1440x1080 center crop
    if format_type == "9:16":
        target_w, target_h = 1080, 1920
    elif format_type == "1:1":
        target_w, target_h = 1080, 1080
    elif format_type == "4:3":
        target_w, target_h = 1440, 1080
    else:
        target_w, target_h = 1080, 1920

    vf_filters = [
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase",
        f"crop={target_w}:{target_h}:(in_w-{target_w})/2:(in_h-{target_h})/2"
    ]

    # Burn in ASS animated subtitles if provided
    if ass_subtitle_path and ass_subtitle_path.exists():
        escaped_ass_path = str(ass_subtitle_path.resolve()).replace("\\", "/").replace(":", r"\:")
        fonts_dir = Path("./fonts").resolve()
        if fonts_dir.exists():
            escaped_fonts_dir = str(fonts_dir).replace("\\", "/").replace(":", r"\:")
            vf_filters.append(f"ass='{escaped_ass_path}':fontsdir='{escaped_fonts_dir}'")
        else:
            vf_filters.append(f"ass='{escaped_ass_path}'")

    filter_str = ",".join(vf_filters)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", f"{start_sec:.2f}",
        "-t", f"{duration:.2f}",
        "-i", str(input_video),
        "-vf", filter_str,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_video)
    ]
    return cmd


# ==========================================
# Pydantic Request & Response Models
# ==========================================

class ImportUrlRequest(BaseModel):
    url: str

class VideoImportResponse(BaseModel):
    video_id: str
    duration: float
    title: str

class TranscribeRequest(BaseModel):
    video_id: str

class WordTiming(BaseModel):
    word: str
    start: float
    end: float

class TranscribeResponse(BaseModel):
    words: List[WordTiming]

class TranscribeStatusResponse(BaseModel):
    progress: int

class ClipScores(BaseModel):
    hook: int = Field(..., ge=0, le=100)
    pacing: int = Field(..., ge=0, le=100)
    trend: int = Field(..., ge=0, le=100)
    total: int = Field(..., ge=0, le=100)

class Clip(BaseModel):
    id: str
    start: float
    end: float
    title: str
    reason: str
    scores: ClipScores

class GeminiClipsOutput(BaseModel):
    clips: List[Clip]

class HighlightsRequest(BaseModel):
    video_id: str
    prompt: Optional[str] = None
    min_sec: float = 15.0
    max_sec: float = 60.0

class HighlightsResponse(BaseModel):
    clips: List[Clip]

class ExportRequest(BaseModel):
    video_id: str
    clip: Clip
    format: Literal["9:16", "1:1", "4:3"]
    options: Dict[str, Any] = {}

class ExportResponse(BaseModel):
    file_url: str
    duration: Optional[float] = None
    credits: Optional[List[str]] = None

class MetadataRequest(BaseModel):
    video_id: str
    clip: Clip
    source_url: Optional[str] = None

class MetadataResponse(BaseModel):
    titles: List[str]
    description: str
    hashtags: List[str]

class ThumbnailsRequest(BaseModel):
    video_id: str
    clip: Clip

class ThumbnailsResponse(BaseModel):
    images: List[str]


# ==========================================
# Endpoints
# ==========================================

@app.get("/health")
def health_check():
    """Health check endpoint to verify backend status and configuration."""
    return {
        "status": "ok",
        "gemini_configured": bool(GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE"),
        "whisper_model": WHISPER_MODEL_NAME
    }


@app.post("/import-file", response_model=VideoImportResponse)
async def import_file(file: UploadFile = File(...)):
    """
    Accept MP4/MOV upload, extract clean title, probe codecs with ffprobe.
    Runs video remux/re-encode and exact 16kHz mono audio extraction concurrently in background threads.
    Logs exact FFmpeg audio extraction command, duration, and output WAV file size in test report.
    """
    filename = file.filename or "uploaded_video.mp4"
    title = Path(filename).stem.replace("_", " ").replace("-", " ").strip() or "Uploaded Video"

    filename_lower = filename.lower()
    content_type = (file.content_type or "").lower()
    is_mp4 = filename_lower.endswith(".mp4") or "mp4" in content_type
    is_mov = filename_lower.endswith(".mov") or "quicktime" in content_type

    if not (is_mp4 or is_mov):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Please upload an MP4 or MOV video file."
        )

    video_id = generate_video_id()
    temp_upload_path = VIDEOS_DIR / f"temp_{video_id}_{filename}"
    dest_path = VIDEOS_DIR / f"{video_id}.mp4"
    wav_path = VIDEOS_DIR / f"{video_id}.temp.wav"

    t0 = time.time()
    try:
        t_recv = time.time()
        print(f"[import-file] Step 1: Receiving and saving uploaded file: {filename}")
        with open(temp_upload_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        recv_time = time.time() - t_recv

        t_probe = time.time()
        print(f"[import-file] Step 2: Measuring source duration & probing codecs via ffprobe...")
        source_duration = get_video_duration(temp_upload_path)
        codecs = probe_video_codecs(temp_upload_path)
        vcodec, acodec = codecs.get("vcodec", ""), codecs.get("acodec", "")
        probe_time = time.time() - t_probe

        if not acodec:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This video has no sound, so I can't find clips."
            )

        used_encoder = detect_best_video_encoder()

        is_h264 = ("h264" in vcodec.lower() or "avc1" in vcodec.lower())
        is_aac = ("aac" in acodec.lower() or "mp4a" in acodec.lower())

        if is_h264 and is_aac:
            decision = "remux"
            decision_reason = f"video is H.264 ({vcodec}) and audio is AAC ({acodec})"
        else:
            decision = f"re-encode ({used_encoder})"
            decision_reason = f"codecs video={vcodec}, audio={acodec} require conversion to H.264/AAC"

        print(f"[import-file] Codecs found: video='{vcodec}', audio='{acodec}'. Decision: {decision} ({decision_reason})")

        def process_video_task():
            t_proc = time.time()
            if is_h264 and is_aac:
                print(f"[import-file] Step 3a: Fast REMUXING H.264 + AAC video in seconds (-c copy)...")
                remux_cmd = [
                    "ffmpeg", "-y", "-nostdin",
                    "-i", str(temp_upload_path),
                    "-c", "copy",
                    "-movflags", "+faststart",
                    str(dest_path)
                ]
                res = subprocess.run(remux_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
                if res.returncode != 0 or not dest_path.exists():
                    print(f"[import-file] FFmpeg remux failed: {res.stderr}")
                    raise RuntimeError(f"FFmpeg remuxing failed: {res.stderr[-300:] if res.stderr else 'unknown error'}")
            else:
                print(f"[import-file] Step 3a: Re-encoding video with '{used_encoder}' scaled to max 720p height...")
                enc_args = get_encoder_args(crf=24)
                reencode_cmd = [
                    "ffmpeg", "-y", "-nostdin",
                    "-i", str(temp_upload_path),
                    *enc_args,
                    "-vf", "scale=-2:'min(720,ih)'",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(dest_path)
                ]
                res = subprocess.run(reencode_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
                if res.returncode != 0 or not dest_path.exists():
                    print(f"[import-file] FFmpeg re-encode failed: {res.stderr}")
                    raise RuntimeError(f"FFmpeg re-encoding failed: {res.stderr[-300:] if res.stderr else 'unknown error'}")
            return decision, time.time() - t_proc

        def process_audio_task():
            print(f"[import-file] Step 3b: Extracting mono 16 kHz audio concurrently...")
            return extract_audio_wav(temp_upload_path, wav_path)

        print(f"[import-file] Step 3: Running video remux/encode and audio extraction concurrently...")
        input_file_size = temp_upload_path.stat().st_size if temp_upload_path.exists() else 0
        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_video = executor.submit(process_video_task)
            fut_audio = executor.submit(process_audio_task)

            used_action, process_time = fut_video.result()
            audio_time, audio_file_size, audio_cmd_str = fut_audio.result()

        print(f"[import-file] Step 4: Verifying final file duration with ffprobe...")
        final_duration = get_video_duration(dest_path)
        if source_duration > 0 and final_duration < (0.95 * source_duration):
            if dest_path.exists():
                dest_path.unlink()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transcoded video duration ({final_duration}s) is under 95% of source duration ({source_duration}s)."
            )

        # Save metadata info.json
        info_json_path = VIDEOS_DIR / f"{video_id}.info.json"
        with open(info_json_path, "w", encoding="utf-8") as f:
            json.dump({
                "video_id": video_id,
                "title": title,
                "duration": final_duration,
                "original_filename": filename,
            }, f, indent=2)

        file_size = dest_path.stat().st_size if dest_path.exists() else None
        elapsed = time.time() - t0
        details = (
            f"Uploaded: {filename} ({final_duration:.1f}s) | Codecs found: video={vcodec}, audio={acodec} | "
            f"Decision: {decision} ({decision_reason}) | "
            f"Input size: {format_bytes(input_file_size)} ({input_file_size} B), Output size: {format_bytes(file_size)} ({file_size} B) | "
            f"Timings -> receive: {recv_time:.2f}s, probe: {probe_time:.2f}s, {decision}: {process_time:.2f}s, audio_extract: {audio_time:.2f}s | "
            f"Audio extract WAV size: {format_bytes(audio_file_size)}"
        )
        log_test_step("import-file", elapsed, file_size, "ok", details)

        print(f"[import-file] Success: video_id={video_id}, duration={final_duration}s, title='{title}' ({elapsed:.2f}s)")
        return {
            "video_id": video_id,
            "duration": final_duration,
            "title": title
        }
    except HTTPException as he:
        if dest_path.exists():
            dest_path.unlink()
        log_test_step("import-file", time.time() - t0, None, "error", str(he.detail))
        raise
    except Exception as e:
        if dest_path.exists():
            dest_path.unlink()
        elapsed = time.time() - t0
        log_test_step("import-file", elapsed, None, "error", str(e))
        print(f"[import-file] Processing error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process uploaded video: {str(e)}"
        )
    finally:
        if temp_upload_path.exists():
            try:
                temp_upload_path.unlink()
            except Exception:
                pass


@app.post("/import-url", response_model=VideoImportResponse)
def import_url(payload: ImportUrlRequest):
    """
    Download max 720p video via yt-dlp with concurrent fragments, probe codecs with ffprobe.
    Runs video remux/re-encode and exact 16kHz mono audio extraction concurrently in background threads.
    Logs exact FFmpeg audio extraction command, duration, and output WAV file size in test report.
    """
    url = payload.url.strip()
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid video URL."
        )

    t0 = time.time()
    video_id = generate_video_id()
    raw_download_path = VIDEOS_DIR / f"raw_{video_id}.mp4"
    dest_path = VIDEOS_DIR / f"{video_id}.mp4"
    wav_path = VIDEOS_DIR / f"{video_id}.temp.wav"

    print(f"[import-url] Step 1: Extracting metadata via yt-dlp for URL: {url}")
    info_opts = {
        "quiet": True,
        "no_warnings": True,
    }

    try:
        t_dl_meta = time.time()
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError("Could not extract video metadata.")
            
            source_duration = float(info.get("duration") or 0.0)
            title = str(info.get("title") or "Imported Video")
            print(f"[import-url] Metadata fetched: title='{title}', source_duration={source_duration}s")

            if source_duration and source_duration > 5400:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This video is too long (> 90 minutes). Please choose a shorter video."
                )

        print(f"[import-url] Step 2: Downloading <=720p video (H.264+AAC preferred, 4 concurrent fragments)...")
        download_opts = {
            "format": "bv*[height<=720][vcodec^=avc1]+ba[acodec^=mp4a]/b[height<=720][vcodec^=avc1][acodec^=mp4a]/bv*[height<=720]+ba/b[height<=720]",
            "concurrent_fragment_downloads": 4,
            "outtmpl": str(raw_download_path),
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(download_opts) as ydl:
            ydl.download([url])

        if not raw_download_path.exists():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Downloaded video file could not be found."
            )
        download_time = time.time() - t_dl_meta
        input_file_size = raw_download_path.stat().st_size if raw_download_path.exists() else 0

        t_probe = time.time()
        print(f"[import-url] Step 3: Measuring source duration & probing codecs via ffprobe...")
        codecs = probe_video_codecs(raw_download_path)
        vcodec, acodec = codecs.get("vcodec", ""), codecs.get("acodec", "")
        probe_time = time.time() - t_probe

        if not acodec:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This video has no sound, so I can't find clips."
            )

        used_encoder = detect_best_video_encoder()

        is_h264 = ("h264" in vcodec.lower() or "avc1" in vcodec.lower())
        is_aac = ("aac" in acodec.lower() or "mp4a" in acodec.lower())

        if is_h264 and is_aac:
            decision = "remux"
            decision_reason = f"video is H.264 ({vcodec}) and audio is AAC ({acodec})"
        else:
            decision = f"re-encode ({used_encoder})"
            decision_reason = f"codecs video={vcodec}, audio={acodec} require conversion to H.264/AAC"

        print(f"[import-url] Codecs found: video='{vcodec}', audio='{acodec}'. Decision: {decision} ({decision_reason})")

        def process_video_task():
            t_proc = time.time()
            if is_h264 and is_aac:
                print(f"[import-url] Step 4a: Fast REMUXING H.264 + AAC video in seconds (-c copy)...")
                remux_cmd = [
                    "ffmpeg", "-y", "-nostdin",
                    "-i", str(raw_download_path),
                    "-c", "copy",
                    "-movflags", "+faststart",
                    str(dest_path)
                ]
                res = subprocess.run(remux_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
                if res.returncode != 0 or not dest_path.exists():
                    print(f"[import-url] FFmpeg remux failed: {res.stderr}")
                    raise RuntimeError(f"FFmpeg remuxing failed: {res.stderr[-300:] if res.stderr else 'unknown error'}")
            else:
                print(f"[import-url] Step 4a: Re-encoding video with '{used_encoder}' scaled to max 720p height...")
                enc_args = get_encoder_args(crf=24)
                reencode_cmd = [
                    "ffmpeg", "-y", "-nostdin",
                    "-i", str(raw_download_path),
                    *enc_args,
                    "-vf", "scale=-2:'min(720,ih)'",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(dest_path)
                ]
                res = subprocess.run(reencode_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
                if res.returncode != 0 or not dest_path.exists():
                    print(f"[import-url] FFmpeg re-encode failed: {res.stderr}")
                    raise RuntimeError(f"FFmpeg re-encoding failed: {res.stderr[-300:] if res.stderr else 'unknown error'}")
            return decision, time.time() - t_proc

        def process_audio_task():
            print(f"[import-url] Step 4b: Extracting mono 16 kHz audio concurrently...")
            return extract_audio_wav(raw_download_path, wav_path)

        print(f"[import-url] Step 4: Running video remux/encode and audio extraction concurrently...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_video = executor.submit(process_video_task)
            fut_audio = executor.submit(process_audio_task)

            used_action, process_time = fut_video.result()
            audio_time, audio_file_size, audio_cmd_str = fut_audio.result()

        print(f"[import-url] Step 5: Verifying final file duration with ffprobe...")
        final_duration = get_video_duration(dest_path)
        if source_duration > 0 and final_duration < (0.95 * source_duration):
            if dest_path.exists():
                dest_path.unlink()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transcoded video duration ({final_duration}s) is under 95% of source duration ({source_duration}s)."
            )

        # Save metadata info.json
        info_json_path = VIDEOS_DIR / f"{video_id}.info.json"
        with open(info_json_path, "w", encoding="utf-8") as f:
            json.dump({
                "video_id": video_id,
                "title": title,
                "duration": final_duration,
                "source_url": url,
            }, f, indent=2)

        file_size = dest_path.stat().st_size if dest_path.exists() else None
        elapsed = time.time() - t0
        details = (
            f"URL video: {title[:40]} ({final_duration:.1f}s) | Codecs found: video={vcodec}, audio={acodec} | "
            f"Decision: {decision} ({decision_reason}) | "
            f"Input size: {format_bytes(input_file_size)} ({input_file_size} B), Output size: {format_bytes(file_size)} ({file_size} B) | "
            f"Timings -> download: {download_time:.2f}s, probe: {probe_time:.2f}s, {decision}: {process_time:.2f}s, audio_extract: {audio_time:.2f}s | "
            f"Audio extract WAV size: {format_bytes(audio_file_size)}"
        )
        log_test_step("import-url", elapsed, file_size, "ok", details)

        print(f"[import-url] Success: video_id={video_id}, duration={final_duration}s, title='{title}' ({elapsed:.2f}s)")
        return {
            "video_id": video_id,
            "duration": final_duration,
            "title": title
        }
    except HTTPException as he:
        if dest_path.exists():
            dest_path.unlink()
        log_test_step("import-url", time.time() - t0, None, "error", str(he.detail))
        raise
    except Exception as e:
        if dest_path.exists():
            dest_path.unlink()
        elapsed = time.time() - t0
        log_test_step("import-url", elapsed, None, "error", str(e))
        print(f"[import-url] Download/processing error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download and process video: {str(e)}"
        )
    finally:
        if raw_download_path.exists():
            try:
                raw_download_path.unlink()
            except Exception:
                pass


@app.get("/video/{video_id}")
def stream_video(video_id: str, request: Request):
    """
    Stream video with full HTTP Range request support (Accept-Ranges: bytes, 206 Partial Content),
    media_type video/mp4, so seeking works smoothly in all browsers and players.
    """
    file_path = VIDEOS_DIR / f"{video_id}.mp4"
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found."
        )

    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")

    if not range_header:
        def iterfile_full():
            with open(file_path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    yield chunk

        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": "video/mp4",
        }
        return StreamingResponse(iterfile_full(), headers=headers, media_type="video/mp4")

    # Parse Range: bytes=start-end
    range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
    if not range_match:
        raise HTTPException(status_code=416, detail="Invalid Range header")

    start = int(range_match.group(1))
    end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
    end = min(end, file_size - 1)
    content_length = (end - start) + 1

    def iterfile_range():
        with open(file_path, "rb") as f:
            f.seek(start)
            bytes_left = content_length
            while bytes_left > 0:
                chunk_size = min(1024 * 1024, bytes_left)
                data = f.read(chunk_size)
                if not data:
                    break
                bytes_left -= len(data)
                yield data

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(content_length),
        "Content-Type": "video/mp4",
    }
    return StreamingResponse(iterfile_range(), status_code=206, headers=headers, media_type="video/mp4")


@app.get("/thumbnail/{video_id}")
def get_thumbnail(video_id: str, t: float = 0.0):
    """
    Extract ONE sharp frame at timestamp t using FFmpeg (-ss before -i, -frames:v 1, quality 2),
    keeping the original aspect ratio with NO cropping, and return it as JPEG.
    """
    video_path = VIDEOS_DIR / f"{video_id}.mp4"
    if not video_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found."
        )

    t_clean = max(0.0, round(float(t), 2))
    thumb_path = THUMBNAILS_DIR / f"{video_id}_thumb_{t_clean:.2f}.jpg"

    if not thumb_path.exists():
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(t_clean),
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            str(thumb_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0 or not thumb_path.exists():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to extract thumbnail frame from video."
            )

    return FileResponse(
        thumb_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"}
    )


@app.get("/transcribe-status/{video_id}", response_model=TranscribeStatusResponse)
def get_transcribe_status(video_id: str):
    """Return transcription progress percentage (0-100)."""
    transcript_file = VIDEOS_DIR / f"{video_id}.transcript.json"
    if transcript_file.exists():
        return {"progress": 100}
    
    progress = transcribe_progress.get(video_id, 0)
    return {"progress": progress}


@app.post("/transcribe", response_model=TranscribeResponse)
def transcribe_video(payload: TranscribeRequest):
    """
    Transcribe speech to word-level timestamps using faster-whisper (small, CPU, int8).
    Saves and caches transcript in storage/videos/<video_id>.transcript.json.
    """
    t0 = time.time()
    video_id = payload.video_id
    video_path = VIDEOS_DIR / f"{video_id}.mp4"
    transcript_path = VIDEOS_DIR / f"{video_id}.transcript.json"
    wav_path = VIDEOS_DIR / f"{video_id}.temp.wav"

    if not video_path.exists():
        log_test_step("transcribe", time.time() - t0, None, "error", f"Video {video_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found. Please upload or import a video first."
        )

    # 1. Reuse existing transcript if available
    if transcript_path.exists():
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                transcribe_progress[video_id] = 100
                v_size = video_path.stat().st_size if video_path.exists() else None
                log_test_step("transcribe", time.time() - t0, v_size, "ok", f"Reused cached transcript ({len(cached_data.get('words', []))} words)")
                return cached_data
        except Exception:
            pass

    # 2. Extract 16kHz mono WAV audio if not pre-extracted during import
    t_audio = time.time()
    transcribe_progress[video_id] = 10
    if not wav_path.exists():
        extract_audio_wav(video_path, wav_path)
    audio_time = time.time() - t_audio
    total_duration = get_video_duration(video_path)

    try:
        t_transcribe = time.time()
        transcribe_progress[video_id] = 20
        model = get_whisper_model()

        segments, info = model.transcribe(
            str(wav_path),
            word_timestamps=True,
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        words_list: List[Dict[str, Any]] = []

        for segment in segments:
            if segment.words:
                for w in segment.words:
                    word_clean = w.word.strip()
                    if word_clean:
                        words_list.append({
                            "word": word_clean,
                            "start": round(float(w.start), 2),
                            "end": round(float(w.end), 2)
                        })
            elif segment.text.strip():
                words_list.append({
                    "word": segment.text.strip(),
                    "start": round(float(segment.start), 2),
                    "end": round(float(segment.end), 2)
                })

            if total_duration > 0:
                current_pct = int(20 + (segment.end / total_duration) * 75)
                transcribe_progress[video_id] = min(95, max(20, current_pct))

        transcribe_time = time.time() - t_transcribe
        response_data = {"words": words_list}

        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(response_data, f, indent=2, ensure_ascii=False)

        transcribe_progress[video_id] = 100
        v_size = video_path.stat().st_size if video_path.exists() else None
        elapsed = time.time() - t0
        details = (
            f"{len(words_list)} words ({total_duration:.1f}s, {WHISPER_MODEL_NAME}) | "
            f"audio_extraction: {audio_time:.2f}s, transcription: {transcribe_time:.2f}s"
        )
        log_test_step("transcribe", elapsed, v_size, "ok", details)
        return response_data

    except Exception as e:
        transcribe_progress[video_id] = 0
        log_test_step("transcribe", time.time() - t0, None, "error", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {str(e)}"
        )
    finally:
        if wav_path.exists():
            try:
                wav_path.unlink()
            except Exception:
                pass


@app.post("/highlights", response_model=HighlightsResponse)
def find_highlights(payload: HighlightsRequest):
    """
    Use Gemini to analyze transcript and extract 5-10 high-retention short clips.
    Fast & predictable execution:
    1. Hard 60s timeout per attempt with disabled automatic SDK retries.
    2. Retry up to 3 times on primary model with delays (3s, 8s, 15s), then fallback models once each.
    3. Lowest thinking setting (thinking_budget=0) for rapid JSON generation.
    4. Cleaned model names.
    5. Cache per (video_id, prompt, min_sec, max_sec) in storage/cache/.
    6. Test report details record successful model and total attempts.
    """
    t0 = time.time()
    print(f"[POST /highlights Request] video_id='{payload.video_id}', prompt='{payload.prompt}', min_sec={payload.min_sec}, max_sec={payload.max_sec}")
    if not GEMINI_API_KEY or GEMINI_API_KEY in ("YOUR_GEMINI_API_KEY_HERE", "MY_GEMINI_API_KEY"):
        log_test_step("highlights", time.time() - t0, None, "error", "GEMINI_API_KEY not configured")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gemini API key is not configured. Please add GEMINI_API_KEY in your .env file."
        )

    # 1. Check disk cache per (video_id, prompt, min_sec, max_sec)
    cache_file = get_highlights_cache_file(payload.video_id, payload.prompt, payload.min_sec, payload.max_sec)
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                raw_clips = cached_data.get("clips", [])
                cached_model = cached_data.get("model", "cached")
                cached_attempts = cached_data.get("attempts", 0)
                if raw_clips:
                    clips_objs = [Clip(**c) for c in raw_clips]
                    elapsed = time.time() - t0
                    c_size = cache_file.stat().st_size
                    log_test_step(
                        "highlights",
                        elapsed,
                        c_size,
                        "ok",
                        f"{len(clips_objs)} clips extracted (cached, model: {cached_model}, attempts: {cached_attempts})"
                    )
                    print(f"[POST /highlights Cache Hit] Returned {len(clips_objs)} clips from cache in {elapsed:.3f}s")
                    return {"clips": clips_objs}
        except Exception as ce:
            print(f"[POST /highlights Cache Read Warning]: {ce}")

    video_path = VIDEOS_DIR / f"{payload.video_id}.mp4"
    transcript_path = VIDEOS_DIR / f"{payload.video_id}.transcript.json"

    if not video_path.exists():
        log_test_step("highlights", time.time() - t0, None, "error", f"Video {payload.video_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found. Please upload or import a video first."
        )

    # Read transcript words
    words: List[Dict[str, Any]] = []
    if transcript_path.exists():
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                words = data.get("words", [])
        except Exception:
            pass

    if not words:
        log_test_step("highlights", time.time() - t0, None, "error", "No transcript words found")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No transcript available. Please run /transcribe first."
        )

    total_duration = get_video_duration(video_path)

    # Group words into timestamped sentences
    transcript_text = group_words_into_lines(words)

    # Read system prompt
    prompt_file = PROMPTS_DIR / "highlights.txt"
    if prompt_file.exists():
        system_instruction = prompt_file.read_text(encoding="utf-8")
    else:
        system_instruction = (
            "You are an expert short-form video editor. Find 5-10 engaging clips "
            f"between {payload.min_sec}s and {payload.max_sec}s with strong 3-second hooks."
        )

    # Format min/max seconds into prompt template if present
    system_instruction = system_instruction.replace("{min_sec}", str(payload.min_sec))
    system_instruction = system_instruction.replace("{max_sec}", str(payload.max_sec))

    user_instructions = [
        f"Video Total Length: {total_duration:.1f} seconds.",
        f"Clip duration constraint: strictly between {payload.min_sec} and {payload.max_sec} seconds.",
        "CRITICAL TITLE REQUIREMENT: Every clip title MUST be uniquely crafted from the specific spoken dialogue and substantive topic of that clip's own transcript text (under 50 chars). Do NOT use generic titles like 'Clip 1' or 'Highlight'. Every single clip must have a completely distinct title reflecting what is specifically spoken.",
    ]
    if payload.prompt and payload.prompt.strip():
        user_instructions.append(
            f"IMPORTANT TOPIC FILTER: The user specifically requested clips about: '{payload.prompt.strip()}'. "
            "ONLY return moments that directly relate to this topic."
        )
    user_instructions.append("\nFULL TIMESTAMPED TRANSCRIPT:")
    user_instructions.append(transcript_text)
    user_prompt_content = "\n".join(user_instructions)

    # Clean model names
    primary_model = clean_model_name(GEMINI_MODEL) or "gemini-2.5-flash"
    fallback_models: List[str] = []
    for m in GEMINI_FALLBACK_MODELS_RAW.split(","):
        c_name = clean_model_name(m)
        if c_name and c_name != primary_model and c_name not in fallback_models:
            fallback_models.append(c_name)

    # Helper function for single Gemini attempt with 60s hard timeout and budget=0
    def single_gemini_attempt(model_name: str) -> GeminiClipsOutput:
        http_opts = get_gemini_http_options(timeout_ms=60000)
        client = genai.Client(api_key=GEMINI_API_KEY, http_options=http_opts) if http_opts else genai.Client(api_key=GEMINI_API_KEY)

        thinking_cfg = None
        if hasattr(types, "ThinkingConfig"):
            try:
                thinking_cfg = types.ThinkingConfig(thinking_budget=0)
            except Exception:
                pass

        config_kwargs = {
            "system_instruction": system_instruction,
            "response_mime_type": "application/json",
            "response_schema": GeminiClipsOutput,
            "temperature": 0.3,
        }
        if thinking_cfg is not None:
            config_kwargs["thinking_config"] = thinking_cfg

        config = types.GenerateContentConfig(**config_kwargs)

        def _execute():
            return client.models.generate_content(
                model=model_name,
                contents=user_prompt_content,
                config=config,
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            fut = executor.submit(_execute)
            response = fut.result(timeout=60.0)

        if not response or not response.text:
            raise ValueError("Gemini returned an empty response.")

        cleaned_text = response.text.strip()
        if cleaned_text.startswith("```"):
            cleaned_text = re.sub(r"^```(?:json)?\n", "", cleaned_text)
            cleaned_text = re.sub(r"\n```$", "", cleaned_text).strip()

        data = json.loads(cleaned_text)
        return GeminiClipsOutput(**data)

    parsed_output: Optional[GeminiClipsOutput] = None
    successful_model: str = primary_model
    total_attempts: int = 0

    # 1. Retry up to 3 times on primary model with delays (3s, 8s, 15s)
    retry_delays = [3, 8, 15]
    for idx in range(3):
        total_attempts += 1
        try:
            print(f"[POST /highlights] Attempt {total_attempts} on primary model '{primary_model}'...")
            parsed_output = single_gemini_attempt(primary_model)
            if parsed_output and parsed_output.clips:
                successful_model = primary_model
                break
        except Exception as e:
            print(f"[POST /highlights] Attempt {total_attempts} on primary model '{primary_model}' failed: {e}")
            if idx < 2:
                delay = retry_delays[idx]
                print(f"[POST /highlights] Waiting {delay}s before retry...")
                time.sleep(delay)

    # 2. If primary model failed 3 times, try each fallback model once
    if not parsed_output or not parsed_output.clips:
        for fb_model in fallback_models:
            total_attempts += 1
            try:
                print(f"[POST /highlights] Attempt {total_attempts} on fallback model '{fb_model}'...")
                parsed_output = single_gemini_attempt(fb_model)
                if parsed_output and parsed_output.clips:
                    successful_model = fb_model
                    break
            except Exception as e:
                print(f"[POST /highlights] Fallback model '{fb_model}' failed: {e}")

    if not parsed_output or not parsed_output.clips:
        elapsed = time.time() - t0
        log_test_step(
            "highlights",
            elapsed,
            None,
            "error",
            f"All {total_attempts} attempts failed across primary ({primary_model}) and fallbacks ({','.join(fallback_models)})"
        )
        print(f"[POST /highlights Error] All {total_attempts} attempts failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI is busy right now. Please try again in a minute."
        )

    # Snap to word boundaries, clamp durations, and calculate weighted score
    validated_clips: List[Clip] = []
    for idx, c in enumerate(parsed_output.clips):
        snapped_start = snap_to_word_boundary(c.start, words, is_start=True)
        snapped_end = snap_to_word_boundary(c.end, words, is_start=False)

        # Ensure inside video bounds
        snapped_start = max(0.0, min(snapped_start, max(0.0, total_duration - payload.min_sec)))
        snapped_end = min(total_duration, max(snapped_start + payload.min_sec, snapped_end))

        dur = snapped_end - snapped_start
        if dur > payload.max_sec:
            snapped_end = snap_to_word_boundary(snapped_start + payload.max_sec, words, is_start=False)

        if snapped_start >= snapped_end:
            continue

        hook = max(0, min(100, int(c.scores.hook)))
        pacing = max(0, min(100, int(c.scores.pacing)))
        trend = max(0, min(100, int(c.scores.trend)))
        # Total = 50% hook + 30% pacing + 20% trend
        total = round(hook * 0.5 + pacing * 0.3 + trend * 0.2)

        validated_clips.append(
            Clip(
                id=f"clip-{len(validated_clips) + 1}",
                start=round(snapped_start, 2),
                end=round(snapped_end, 2),
                title=c.title.strip(),
                reason=c.reason.strip(),
                scores=ClipScores(hook=hook, pacing=pacing, trend=trend, total=total),
            )
        )

    # Apply loudness & speech tempo excitement bonus (up to +10 pts)
    try:
        loudness_levels = compute_loudness_per_second(video_path)
        validated_clips = apply_audio_excitement_bonus(validated_clips, loudness_levels, words)
    except Exception:
        pass

    # Sort clips by total score descending
    validated_clips.sort(key=lambda c: c.scores.total, reverse=True)

    # Cache result to disk
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "clips": [c.dict() for c in validated_clips],
                "model": successful_model,
                "attempts": total_attempts,
            }, f, indent=2)
    except Exception as ce:
        print(f"[POST /highlights Cache Save Warning]: {ce}")

    t_size = transcript_path.stat().st_size if transcript_path.exists() else None
    elapsed = time.time() - t0
    log_test_step(
        "highlights",
        elapsed,
        t_size,
        "ok",
        f"{len(validated_clips)} clips extracted (model: {successful_model}, attempts: {total_attempts})"
    )
    print(f"[POST /highlights Response 200] Success: returned {len(validated_clips)} clips using model '{successful_model}' after {total_attempts} attempts ({elapsed:.2f}s)")

    return {"clips": validated_clips}


@app.post("/export", response_model=ExportResponse)
def export_clip(payload: ExportRequest):
    """
    Full short-form clip export pipeline:
    1. Silence & filler word removal with sync preservation.
    2. Smart Reframe (active speaker face tracking & layout switching) or center crop.
    3. Pexels portrait B-roll overlay with crossfade.
    4. Royalty-free background music (-22 dB with ducking) and SFX overlay (-12 dB).
    5. Animated word-level ASS captions (bold_pop, karaoke, clean).
    """
    t0 = time.time()
    video_path = VIDEOS_DIR / f"{payload.video_id}.mp4"
    if not video_path.exists():
        log_test_step("export", time.time() - t0, None, "error", f"Video {payload.video_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source video not found. Please upload or import a video first."
        )

    format_slug = payload.format.replace(":", "_")
    output_filename = f"{payload.video_id}_{payload.clip.id}_{format_slug}.mp4"
    output_path = EXPORTS_DIR / output_filename

    # Options flags
    remove_silence = bool(payload.options.get("remove_silence", False))
    remove_fillers = bool(payload.options.get("remove_fillers", False))
    add_music = bool(payload.options.get("music", False))
    add_sfx = bool(payload.options.get("sfx", False))
    add_broll = bool(payload.options.get("broll", False))
    smart_reframe = bool(payload.options.get("smart_reframe", True))
    caption_opt = payload.options.get("captions")

    # Load transcript words
    words: List[Dict[str, Any]] = []
    transcript_path = VIDEOS_DIR / f"{payload.video_id}.transcript.json"
    if transcript_path.exists():
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                t_data = json.load(f)
                words = t_data.get("words", [])
        except Exception:
            pass

    transcript_text = " ".join(str(w.get("word", "")) for w in words if w.get("end", 0) > payload.clip.start and w.get("start", 0) < payload.clip.end)

    temp_files: List[Path] = []
    credits_list: List[str] = []

    cut_time = 0.0
    reframe_time = 0.0
    broll_time = 0.0
    sfx_music_time = 0.0
    captions_time = 0.0
    enc_args_20 = get_encoder_args(crf=20)

    try:
        # Step 1: Cut clip first (-ss before -i, -t duration) with -preset veryfast
        t_cut = time.time()
        current_video = EXPORTS_DIR / f"step1_{output_filename}"
        temp_files.append(current_video)

        if (remove_silence or remove_fillers) and words:
            keep_segs, adjusted_words = plan_cuts_and_keep_segments(
                words=words,
                clip_start=payload.clip.start,
                clip_end=payload.clip.end,
                remove_silence=remove_silence,
                remove_fillers=remove_fillers,
            )
            current_duration = execute_trim_and_concat(video_path, current_video, payload.clip.start, keep_segs)
            active_words = adjusted_words
        else:
            orig_duration = max(0.5, payload.clip.end - payload.clip.start)
            trim_cmd = [
                "ffmpeg", "-y",
                "-ss", f"{payload.clip.start:.2f}",
                "-t", f"{orig_duration:.2f}",
                "-i", str(video_path),
                *enc_args_20,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                str(current_video)
            ]
            subprocess.run(trim_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            current_duration = orig_duration

            # Shift words relative to 0.0 for captions
            active_words = []
            for w in words:
                ws, we = float(w.get("start", 0)), float(w.get("end", 0))
                if we > payload.clip.start and ws < payload.clip.end:
                    active_words.append({
                        "word": str(w.get("word", "")),
                        "start": max(0.0, ws - payload.clip.start),
                        "end": min(current_duration, we - payload.clip.start),
                    })
        cut_time = time.time() - t_cut

        # Step 2: Framing (Smart Reframe for 9:16 or Center Crop)
        t_reframe = time.time()
        framed_video = EXPORTS_DIR / f"step2_{output_filename}"
        temp_files.append(framed_video)
        reframe_ok = False

        if smart_reframe and payload.format == "9:16":
            try:
                voice_intervals = detect_voice_activity_ffmpeg(current_video, 0.0, current_duration)
                samples, orig_dims = sample_clip_faces(current_video, 0.0, current_duration, sample_fps=3.0)
                crop_path, scenes = compute_smart_reframe_path(samples, orig_dims, voice_intervals, zoom_factor=1.15)
                render_smart_reframe_video(current_video, framed_video, 0.0, current_duration, crop_path, scenes)
                reframe_ok = True
            except Exception as e:
                print(f"[Smart Reframe Error, fallback to center crop]: {e}")
                reframe_ok = False

        if not reframe_ok:
            # Fallback center crop
            center_crop_cmd = build_export_ffmpeg_command(
                input_video=current_video,
                output_video=framed_video,
                start_sec=0.0,
                end_sec=current_duration,
                format_type=payload.format,
            )
            subprocess.run(center_crop_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        current_video = framed_video
        reframe_time = time.time() - t_reframe

        # Step 3: B-Roll video overlay via Pexels API
        t_broll = time.time()
        if add_broll and transcript_text:
            try:
                broll_cues = pick_broll_cues_gemini(transcript_text, current_duration)
                if broll_cues:
                    broll_video = EXPORTS_DIR / f"step3_{output_filename}"
                    temp_files.append(broll_video)
                    broll_ok, b_credits = overlay_broll_clips(current_video, broll_video, broll_cues, format_type=payload.format)
                    if broll_ok:
                        current_video = broll_video
                        credits_list.extend(b_credits)
            except Exception as e:
                print(f"[B-Roll Warning]: {e}")
        broll_time = time.time() - t_broll

        # Step 4: SFX & Music
        t_sfx = time.time()
        if add_sfx and transcript_text:
            try:
                sfx_moments = detect_sfx_moments_gemini(transcript_text, current_duration)
                if sfx_moments:
                    sfx_video = EXPORTS_DIR / f"step4_sfx_{output_filename}"
                    temp_files.append(sfx_video)
                    if apply_sound_effects(current_video, sfx_video, sfx_moments):
                        current_video = sfx_video
            except Exception as e:
                print(f"[SFX Warning]: {e}")

        if add_music:
            try:
                music_video = EXPORTS_DIR / f"step4_music_{output_filename}"
                temp_files.append(music_video)
                if apply_background_music(current_video, music_video, current_duration):
                    current_video = music_video
            except Exception as e:
                print(f"[Music Warning]: {e}")
        sfx_music_time = time.time() - t_sfx

        # Step 5: Burn animated ASS captions if requested
        t_cap = time.time()
        if caption_opt and caption_opt not in (False, "none", "null") and active_words:
            style_key = caption_opt if isinstance(caption_opt, str) and caption_opt in CAPTION_STYLES else "bold_pop"
            ass_path = EXPORTS_DIR / f"{payload.video_id}_{payload.clip.id}_{style_key}.ass"
            temp_files.append(ass_path)

            res_x, res_y = (1080, 1920) if payload.format == "9:16" else ((1080, 1080) if payload.format == "1:1" else (1440, 1080))
            has_subs = generate_ass_subtitles(
                all_words=active_words,
                clip_start=0.0,
                clip_end=current_duration,
                style_name=style_key,
                output_ass_path=ass_path,
                res_x=res_x,
                res_y=res_y,
            )

            if has_subs and ass_path.exists():
                escaped_ass = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")
                fonts_dir = Path("./fonts").resolve()
                escaped_fonts = str(fonts_dir).replace("\\", "/").replace(":", "\\:")
                vf_arg = f"ass='{escaped_ass}':fontsdir='{escaped_fonts}'" if fonts_dir.exists() else f"ass='{escaped_ass}'"

                burn_cmd = [
                    "ffmpeg", "-y",
                    "-i", str(current_video),
                    "-vf", vf_arg,
                    *enc_args_20,
                    "-c:a", "copy",
                    "-movflags", "+faststart",
                    str(output_path),
                ]
                subprocess.run(burn_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            else:
                if output_path.exists():
                    output_path.unlink()
                current_video.rename(output_path)
        else:
            if output_path.exists():
                output_path.unlink()
            current_video.rename(output_path)
        captions_time = time.time() - t_cap

    except Exception as e:
        elapsed = time.time() - t0
        log_test_step("export", elapsed, None, "error", str(e))
        raise
    finally:
        # Clean up temporary stage files
        for tmp in temp_files:
            if tmp.exists() and tmp != output_path:
                try:
                    tmp.unlink()
                except Exception:
                    pass

    out_size = output_path.stat().st_size if output_path.exists() else None
    elapsed = time.time() - t0
    details = (
        f"Clip: {payload.clip.id}, Format: {payload.format}, Duration: {current_duration:.1f}s | "
        f"cut: {cut_time:.2f}s, reframe: {reframe_time:.2f}s, broll: {broll_time:.2f}s, "
        f"sfx_music: {sfx_music_time:.2f}s, captions: {captions_time:.2f}s"
    )
    log_test_step("export", elapsed, out_size, "ok", details)

    return {
        "file_url": f"/exports/{output_filename}",
        "duration": round(current_duration, 2),
        "credits": credits_list if credits_list else None,
    }


@app.get("/exports/{filename}")
def download_export(filename: str):
    """Serve or download an exported clip from storage/exports."""
    safe_name = Path(filename).name
    file_path = EXPORTS_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exported video file not found."
        )
    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=safe_name,
    )


@app.post("/metadata", response_model=MetadataResponse)
def generate_metadata(payload: MetadataRequest):
    """
    Generate 3 curiosity-driven titles (<= 60 chars), a 2-line description with CTA
    (plus 'Full video: <source_url>' backlink if provided), and 5 relevant hashtags (including #Shorts).
    """
    # Load transcript snippet for the clip
    transcript_words = []
    transcript_path = VIDEOS_DIR / f"{payload.video_id}.transcript.json"
    if transcript_path.exists():
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                t_data = json.load(f)
                words = t_data.get("words", [])
                for w in words:
                    if float(w.get("end", 0)) > payload.clip.start and float(w.get("start", 0)) < payload.clip.end:
                        transcript_words.append(str(w.get("word", "")))
        except Exception:
            pass

    transcript_text = " ".join(transcript_words) if transcript_words else payload.clip.title

    # Load system prompt
    prompt_file = PROMPTS_DIR / "metadata.txt"
    if prompt_file.exists():
        with open(prompt_file, "r", encoding="utf-8") as f:
            base_prompt = f.read()
    else:
        base_prompt = (
            "You are an expert viral content creator. Given this clip transcript, generate metadata.\n"
            "Rules:\n"
            "1. 'titles': exactly 3 curiosity-driven honest titles, max 60 chars each.\n"
            "2. 'description': 2 short lines + 1 call to action.\n"
            "3. 'hashtags': exactly 5 relevant hashtags including #Shorts.\n"
            "Output JSON with keys: 'titles', 'description', 'hashtags'."
        )

    if not GEMINI_API_KEY or GEMINI_API_KEY in ("YOUR_GEMINI_API_KEY_HERE", "MY_GEMINI_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GEMINI_API_KEY is not set. Please set GEMINI_API_KEY in your .env file."
        )

    try:
        http_opts = get_gemini_http_options(timeout_ms=30000)
        client = genai.Client(api_key=GEMINI_API_KEY, http_options=http_opts) if http_opts else genai.Client(api_key=GEMINI_API_KEY)
        full_prompt = (
            f"{base_prompt}\n\n"
            f"Clip Title: {payload.clip.title}\n"
            f"Clip Reason: {payload.clip.reason}\n"
            f"Transcript snippet:\n{transcript_text[:1200]}\n"
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        data = json.loads(response.text.strip())
        if not isinstance(data, dict):
            raise ValueError("Invalid metadata format from Gemini.")

        raw_titles = data.get("titles", [])
        if not isinstance(raw_titles, list) or len(raw_titles) < 3:
            raise ValueError("Gemini did not return 3 titles.")
        titles = [str(t).strip()[:60] for t in raw_titles[:3]]

        raw_desc = data.get("description", "")
        if not raw_desc or not isinstance(raw_desc, str):
            raise ValueError("Gemini did not return a description.")
        description = raw_desc.strip()

        raw_tags = data.get("hashtags", [])
        if not isinstance(raw_tags, list) or len(raw_tags) == 0:
            raise ValueError("Gemini did not return hashtags.")
        tags = [t if t.startswith("#") else f"#{t}" for t in raw_tags]
        if "#Shorts" not in tags and "#shorts" not in tags:
            tags.insert(0, "#Shorts")
        hashtags = tags[:5]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate metadata with Gemini: {str(e)}"
        )

    # Append backlink to original video if source_url exists
    if payload.source_url and payload.source_url.strip():
        description = f"{description.rstrip()}\nFull video: {payload.source_url.strip()}"

    return {
        "titles": titles,
        "description": description,
        "hashtags": hashtags,
    }


@app.post("/thumbnails", response_model=ThumbnailsResponse)
def generate_thumbnails(payload: ThumbnailsRequest):
    """
    Sample 1 frame every 0.5s, score by sharpness, face detection, and brightness.
    Pick top 3 diverse frames, generate punchy 2-4 word overlay hooks via Gemini,
    render 1080x1920 tall thumbnails with Pillow (huge bold text, black outline, away from face).
    """
    video_path = VIDEOS_DIR / f"{payload.video_id}.mp4"
    if not video_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source video not found. Please upload or import a video first."
        )

    # 1. Sample and score frames
    scored_frames = sample_and_score_frames(
        video_path=video_path,
        start_sec=payload.clip.start,
        end_sec=payload.clip.end,
        sample_interval=0.5
    )

    # 2. Pick top 3 diverse frames
    chosen_frames = pick_top_diverse_frames(scored_frames, count=3)

    # Fallback if too few samples were returned
    if len(chosen_frames) < 3:
        cap = cv2.VideoCapture(str(video_path))
        if cap.isOpened():
            mid = (payload.clip.start + payload.clip.end) / 2.0
            fallback_times = [payload.clip.start + 0.5, mid, max(payload.clip.start + 1.0, payload.clip.end - 0.5)]
            for t in fallback_times:
                if len(chosen_frames) >= 3:
                    break
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                ret, frame = cap.read()
                if ret:
                    chosen_frames.append({
                        "time": t,
                        "score": 100.0,
                        "frame": frame,
                        "has_face": True,
                        "face_y_ratio": 0.4,
                    })
            cap.release()

    if not chosen_frames:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to capture frames for thumbnail generation."
        )

    # 3. Generate punchy 2-4 word text hooks via Gemini
    transcript_words = []
    transcript_path = VIDEOS_DIR / f"{payload.video_id}.transcript.json"
    if transcript_path.exists():
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                t_data = json.load(f)
                for w in t_data.get("words", []):
                    if float(w.get("end", 0)) > payload.clip.start and float(w.get("start", 0)) < payload.clip.end:
                        transcript_words.append(str(w.get("word", "")))
        except Exception:
            pass

    transcript_snippet = " ".join(transcript_words) if transcript_words else payload.clip.title
    text_hooks = generate_punchy_text_hooks_gemini(payload.clip.title, transcript_snippet)

    # 4. Render 3 thumbnails using Pillow
    image_urls = []
    for idx, frame_info in enumerate(chosen_frames[:3]):
        hook_text = text_hooks[idx] if idx < len(text_hooks) else "MUST WATCH"
        thumb_filename = f"thumb_{payload.video_id}_{payload.clip.id}_{idx+1}.jpg"
        thumb_path = THUMBNAILS_DIR / thumb_filename

        render_thumbnail(
            frame_bgr=frame_info["frame"],
            text_hook=hook_text,
            face_y_ratio=frame_info.get("face_y_ratio", 0.45),
            output_path=thumb_path,
            target_w=1080,
            target_h=1920
        )
        image_urls.append(f"/thumbnails/{thumb_filename}")

    return {"images": image_urls}


@app.get("/thumbnails/{filename}")
def serve_thumbnail(filename: str):
    """Serve generated thumbnail JPEG from storage/thumbnails."""
    safe_name = Path(filename).name
    file_path = THUMBNAILS_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail image not found."
        )
    return FileResponse(
        path=file_path,
        media_type="image/jpeg",
        filename=safe_name,
    )


# ==========================================
# Diagnostics Endpoint
# ==========================================

@app.get("/diagnostics")
def get_diagnostics():
    """
    Returns system diagnostics:
    - FFmpeg found and version
    - FFprobe found and version
    - yt-dlp version
    - GEMINI_API_KEY set (boolean true/false only, never the key)
    - Free disk space
    - Whisper model name
    """
    # 1. FFmpeg detection & version
    ffmpeg_found = False
    ffmpeg_version = None
    try:
        res = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        if res.returncode == 0:
            ffmpeg_found = True
            lines = res.stdout.splitlines()
            ffmpeg_version = lines[0].strip() if lines else "Installed"
    except Exception:
        pass

    # 2. FFprobe detection & version
    ffprobe_found = False
    ffprobe_version = None
    try:
        res = subprocess.run(
            ["ffprobe", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        if res.returncode == 0:
            ffprobe_found = True
            lines = res.stdout.splitlines()
            ffprobe_version = lines[0].strip() if lines else "Installed"
    except Exception:
        pass

    # 3. yt-dlp version
    yt_dlp_version = None
    try:
        import yt_dlp
        yt_dlp_version = getattr(yt_dlp.version, "__version__", None)
    except Exception:
        pass
    if not yt_dlp_version:
        try:
            res = subprocess.run(
                ["yt-dlp", "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            if res.returncode == 0:
                yt_dlp_version = res.stdout.strip()
        except Exception:
            pass

    # 4. GEMINI_API_KEY set (true/false only, NEVER the key)
    gemini_key_set = bool(
        GEMINI_API_KEY and
        GEMINI_API_KEY.strip() and
        GEMINI_API_KEY not in ("YOUR_GEMINI_API_KEY_HERE", "MY_GEMINI_API_KEY")
    )

    # 5. Free disk space
    free_disk_space: Dict[str, Any] = {}
    try:
        target_dir = STORAGE_DIR if STORAGE_DIR.exists() else Path.cwd()
        usage = shutil.disk_usage(str(target_dir.resolve()))
        free_gb = round(usage.free / (1024 ** 3), 2)
        total_gb = round(usage.total / (1024 ** 3), 2)
        free_disk_space = {
            "free_bytes": usage.free,
            "free_gb": free_gb,
            "total_gb": total_gb,
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "display": f"{free_gb} GB free of {total_gb} GB",
        }
    except Exception as e:
        free_disk_space = {"error": str(e)}

    return {
        "ffmpeg": {
            "found": ffmpeg_found,
            "version": ffmpeg_version,
        },
        "ffprobe": {
            "found": ffprobe_found,
            "version": ffprobe_version,
        },
        "yt_dlp": {
            "found": bool(yt_dlp_version),
            "version": yt_dlp_version or "not found",
        },
        "gemini_api_key_set": gemini_key_set,
        "gemini_model": GEMINI_MODEL,
        "gemini_startup_status": _GEMINI_STARTUP_STATUS,
        "video_encoder": detect_best_video_encoder(),
        "free_disk_space": free_disk_space,
        "whisper_model": WHISPER_MODEL_NAME,
    }


# ==========================================
# Test Report Endpoint
# ==========================================

@app.get("/test-report")
def get_test_report():
    """
    Returns the last 20 logged test entries from storage/test_log.json.
    Logged steps: import-file, import-url, transcribe, highlights, export.
    """
    if not TEST_LOG_PATH.exists():
        return {"entries": []}
    try:
        with open(TEST_LOG_PATH, "r", encoding="utf-8") as f:
            entries = json.load(f)
            if not isinstance(entries, list):
                return {"entries": []}
            # Return last 20, newest first
            return {"entries": list(reversed(entries[-20:]))}
    except Exception as e:
        return {"entries": [], "error": str(e)}


# ==========================================
# Serve Front-End (dist) at "/"
# ==========================================

# Mount dist/assets if built
if (DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="dist_assets")


@app.get("/{full_path:path}")
async def serve_spa_frontend(full_path: str):
    """
    Serve the built frontend from dist/ at "/" so everything runs on http://localhost:8000.
    Falls back to dist/index.html for client-side SPA routing.
    """
    if full_path:
        static_candidate = DIST_DIR / full_path
        if static_candidate.is_file() and static_candidate.exists():
            return FileResponse(static_candidate)

    index_file = DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    return {
        "status": "ready",
        "message": "ClipSnap FastAPI backend running. Run 'npm run build' to build and serve the frontend at '/'."
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    app_target = "main:app" if Path("main.py").exists() else "backend.main:app"
    print(f"🚀 ClipSnap Server starting on http://localhost:{port}")
    uvicorn.run(app_target, host="0.0.0.0", port=port, reload=True)
