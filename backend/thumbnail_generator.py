"""
Thumbnail Generator module for ClipSnap.
- Samples frames every 0.5s inside a clip.
- Evaluates sharpness (Laplacian variance), face presence, and brightness.
- Drops dark (< 35 mean) and blurry (< 60 variance) frames.
- Selects top 3 distinct frames separated in time.
- Uses Gemini to generate 2-4 word punchy text hooks.
- Renders 1080x1920 tall thumbnails with Pillow (huge bold text, black outline, placed away from faces).
"""

import os
import json
import math
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from google import genai
from google.genai import types

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Load FaceTracker if available
try:
    from reframe import FaceTracker
except ImportError:
    FaceTracker = None


def find_system_bold_font(font_size: int = 90) -> ImageFont.ImageFont:
    """Finds a bold truetype font or falls back gracefully to default."""
    candidates = [
        "fonts/Montserrat-ExtraBold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "Arial Bold.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, font_size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=font_size)
    except Exception:
        return ImageFont.load_default()


def generate_punchy_text_hooks_gemini(clip_title: str, transcript_snippet: str) -> List[str]:
    """Ask Gemini for 3 distinct 2-4 word punchy overlay text hooks."""
    fallback_hooks = ["WAIT FOR IT", "DON'T MISS THIS", "THE SECRET"]
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        return fallback_hooks

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"Clip title: {clip_title}\n"
            f"Transcript snippet: {transcript_snippet[:400]}\n\n"
            "Generate exactly 3 punchy, curiosity-inducing short text overlays for video thumbnail covers.\n"
            "Rules:\n"
            "- Exactly 2 to 4 words each.\n"
            "- ALL UPPERCASE.\n"
            "- High curiosity and emotion (e.g. 'NEVER DO THIS', 'THE REAL REASON', 'SECRET EXPOSED', 'WATCH TILL END').\n"
            "Return JSON array of 3 strings: [\"TEXT 1\", \"TEXT 2\", \"TEXT 3\"]."
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        data = json.loads(response.text.strip())
        if isinstance(data, list) and len(data) >= 3:
            return [str(s).upper().strip() for s in data[:3]]
    except Exception:
        pass
    return fallback_hooks


def sample_and_score_frames(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    sample_interval: float = 0.5
) -> List[Dict[str, Any]]:
    """
    Samples frames every 0.5s.
    Scores by sharpness, brightness, and face presence.
    Drops dark and blurry frames.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    duration = max(0.5, end_sec - start_sec)
    tracker = FaceTracker() if FaceTracker else None

    scored_frames: List[Dict[str, Any]] = []
    num_samples = int(duration / sample_interval)

    for i in range(num_samples):
        t_sec = start_sec + (i * sample_interval)
        cap.set(cv2.CAP_PROP_POS_MSEC, t_sec * 1000.0)
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(np.mean(gray))
        # Drop dark frames
        if brightness < 35.0:
            continue

        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        # Drop blurry frames
        if laplacian_var < 60.0:
            continue

        faces = tracker.detect_faces(frame) if tracker else []
        has_face = len(faces) > 0
        face_y_ratio = (faces[0]["y"] / frame.shape[0]) if has_face else 0.5

        # Score formula: sharpness + face bonus + brightness stability
        score = laplacian_var * 0.5 + (150.0 if has_face else 0.0)
        if has_face and 0.02 < faces[0].get("mouth", 0) < 0.25:
            score += 50.0 # Good open natural expression

        scored_frames.append({
            "time": t_sec,
            "score": score,
            "frame": frame,
            "has_face": has_face,
            "face_y_ratio": face_y_ratio,
        })

    cap.release()
    return scored_frames


def pick_top_diverse_frames(scored_frames: List[Dict[str, Any]], count: int = 3) -> List[Dict[str, Any]]:
    """Picks top-scoring frames while ensuring they are spaced at least 1.5s apart."""
    if len(scored_frames) <= count:
        return scored_frames

    # Sort by score descending
    sorted_by_score = sorted(scored_frames, key=lambda f: f["score"], reverse=True)
    selected: List[Dict[str, Any]] = []

    for candidate in sorted_by_score:
        # Check time distance from already selected
        too_close = any(abs(candidate["time"] - s["time"]) < 1.5 for s in selected)
        if not too_close:
            selected.append(candidate)
            if len(selected) == count:
                break

    # If not enough separated frames, fill with highest remaining
    if len(selected) < count:
        for candidate in sorted_by_score:
            if candidate not in selected:
                selected.append(candidate)
                if len(selected) == count:
                    break

    return selected


def render_thumbnail(
    frame_bgr: np.ndarray,
    text_hook: str,
    face_y_ratio: float,
    output_path: Path,
    target_w: int = 1080,
    target_h: int = 1920
) -> Path:
    """
    Crops frame to 9:16 portrait, resizes to 1080x1920, and draws huge bold text with outline
    placed away from the detected face.
    """
    h_orig, w_orig = frame_bgr.shape[:2]
    target_aspect = target_w / target_h

    # Center-crop to 9:16
    crop_h = min(float(h_orig), float(w_orig) / target_aspect)
    crop_w = crop_h * target_aspect
    x_start = int((w_orig - crop_w) / 2)
    y_start = int((h_orig - crop_h) / 2)

    cropped = frame_bgr[y_start:y_start + int(crop_h), x_start:x_start + int(crop_w)]
    resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

    # Convert to PIL Image
    img_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(pil_img)

    font = find_system_bold_font(font_size=88)

    # Determine vertical position away from face
    # If face is in top half (face_y_ratio < 0.5), place text in lower-third
    # If face is in bottom half or center, place text in top-third
    if face_y_ratio < 0.45:
        text_y = int(target_h * 0.72)
    else:
        text_y = int(target_h * 0.18)

    # Split text into 1 or 2 lines if needed
    words = text_hook.split()
    if len(words) >= 3:
        mid = len(words) // 2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
    else:
        lines = [text_hook]

    # Calculate line positions and draw with thick black outline
    outline_width = 8
    line_spacing = 20

    # Measure total height
    line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_heights = [b[3] - b[1] for b in line_bboxes]
    line_widths = [b[2] - b[0] for b in line_bboxes]

    current_y = text_y
    for i, line in enumerate(lines):
        lw = line_widths[i]
        text_x = int((target_w - lw) / 2)

        # Draw thick black outline
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx * dx + dy * dy <= outline_width * outline_width:
                    draw.text((text_x + dx, current_y + dy), line, font=font, fill=(0, 0, 0))

        # Draw pure white text fill
        draw.text((text_x, current_y), line, font=font, fill=(255, 255, 255))
        current_y += line_heights[i] + line_spacing

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pil_img.save(str(output_path), "JPEG", quality=92)
    return output_path
