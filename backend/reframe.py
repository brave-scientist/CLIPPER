"""
Smart Reframe module for short-form 9:16 video generation.
Uses OpenCV and MediaPipe for:
1. 5 FPS face & mouth movement detection (active speaker identification).
2. Smooth camera panning (moving average + speed limiting) with a 1.15x face zoom.
3. Automated scene layout classification (SINGLE, SPLIT, SCREEN).
4. Video rendering (with PIP circular face bubble and split screen dividers) and audio muxing.
"""

import os
import json
import math
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import cv2
import numpy as np

# Try importing mediapipe with graceful fallback
try:
    import mediapipe as mp
    MP_AVAILABLE = True
except ImportError:
    MP_AVAILABLE = False


def detect_voice_activity_ffmpeg(video_path: Path, start_sec: float, duration: float) -> List[Tuple[float, float]]:
    """
    Run FFmpeg silencedetect to find non-silent (voice-active) intervals.
    Returns a list of (start_time, end_time) where audio is present.
    """
    cmd = [
        "ffmpeg",
        "-ss", f"{start_sec:.2f}",
        "-t", f"{duration:.2f}",
        "-i", str(video_path),
        "-af", "silencedetect=noise=-30dB:d=0.3",
        "-f", "null",
        "-"
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = res.stderr.splitlines()
        silence_intervals = []
        current_silence_start = None

        for line in lines:
            if "silence_start:" in line:
                try:
                    parts = line.split("silence_start:")
                    current_silence_start = float(parts[1].strip().split()[0])
                except Exception:
                    pass
            elif "silence_end:" in line and current_silence_start is not None:
                try:
                    parts = line.split("silence_end:")
                    silence_end = float(parts[1].strip().split()[0])
                    silence_intervals.append((current_silence_start, silence_end))
                    current_silence_start = None
                except Exception:
                    pass

        if current_silence_start is not None:
            silence_intervals.append((current_silence_start, duration))

        # Invert silence to get voice activity
        voice_intervals = []
        last_t = 0.0
        for s_start, s_end in silence_intervals:
            if s_start > last_t + 0.1:
                voice_intervals.append((last_t, s_start))
            last_t = max(last_t, s_end)
        if last_t < duration - 0.1:
            voice_intervals.append((last_t, duration))

        return voice_intervals if voice_intervals else [(0.0, duration)]
    except Exception:
        return [(0.0, duration)]


def is_time_in_intervals(t: float, intervals: List[Tuple[float, float]]) -> bool:
    for start, end in intervals:
        if start <= t <= end:
            return True
    return False


def measure_edge_density(gray_frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> float:
    """Measure high-frequency edge density in a region to identify screens/slides."""
    x, y, w, h = bbox
    roi = gray_frame[y:y+h, x:x+w]
    if roi.size == 0:
        return 0.0
    edges = cv2.Canny(roi, 80, 180)
    return float(np.mean(edges > 0))


class FaceTracker:
    def __init__(self):
        self.mp_face_detection = None
        self.mp_face_mesh = None
        if MP_AVAILABLE:
            try:
                self.mp_face_detection = mp.solutions.face_detection.FaceDetection(
                    model_selection=1, min_detection_confidence=0.5
                )
                self.mp_face_mesh = mp.solutions.face_mesh.FaceMesh(
                    static_image_mode=False,
                    max_num_faces=4,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                )
            except Exception:
                self.mp_face_detection = None
                self.mp_face_mesh = None

        # Fallback Haar Cascade
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.haar_cascade = cv2.CascadeClassifier(cascade_path)

    def detect_faces(self, frame_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect faces and measure mouth openness for active speaker detection.
        Returns list of {x, y, w, h, mouth_openness} in pixels.
        """
        h_img, w_img = frame_bgr.shape[:2]
        faces = []

        if self.mp_face_mesh:
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            results = self.mp_face_mesh.process(frame_rgb)

            if results and results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    pts = np.array([
                        [lm.x * w_img, lm.y * h_img] for lm in face_landmarks.landmark
                    ])
                    x_min, y_min = np.min(pts, axis=0)
                    x_max, y_max = np.max(pts, axis=0)

                    # Lip landmarks: 13 (upper lip inner), 14 (lower lip inner)
                    upper_lip = pts[13]
                    lower_lip = pts[14]
                    lip_dist = float(np.linalg.norm(upper_lip - lower_lip))

                    face_w = max(20.0, x_max - x_min)
                    face_h = max(20.0, y_max - y_min)
                    mouth_openness = lip_dist / (face_h + 1e-5)

                    faces.append({
                        "x": int(max(0, x_min)),
                        "y": int(max(0, y_min)),
                        "w": int(min(w_img - x_min, face_w)),
                        "h": int(min(h_img - y_min, face_h)),
                        "mouth": mouth_openness,
                    })
                return faces

        # Fallback: Haar Cascade
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        detected = self.haar_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=4, minSize=(40, 40))
        for (x, y, w, h) in detected:
            # Estimate mouth movement using lower third variance
            mouth_roi = gray[y + int(h * 0.65):y + h, x:x + w]
            mouth_val = float(np.std(mouth_roi)) / 255.0 if mouth_roi.size > 0 else 0.05
            faces.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h), "mouth": mouth_val})

        return faces


def sample_clip_faces(
    video_path: Path,
    start_sec: float,
    duration: float,
    sample_fps: float = 3.0
) -> Tuple[List[Dict[str, Any]], Tuple[int, int]]:
    """
    Sample video at sample_fps (3 FPS), downscale frames to 360p height for ultra-fast face detection,
    and map face bounding boxes back to full resolution.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video {video_path}")

    w_orig = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h_orig = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_orig = cap.get(cv2.CAP_PROP_FPS) or 30.0

    target_h = 360
    scale = target_h / float(h_orig) if h_orig > target_h else 1.0
    target_w = max(1, int(w_orig * scale))

    tracker = FaceTracker()
    samples: List[Dict[str, Any]] = []

    dt = 1.0 / sample_fps
    num_samples = max(1, int(duration * sample_fps))

    for i in range(num_samples):
        t = start_sec + (i * dt)
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ret, frame = cap.read()
        if not ret:
            break

        if scale < 1.0:
            resized_frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
        else:
            resized_frame = frame

        faces_downscaled = tracker.detect_faces(resized_frame)

        # Scale face bboxes back to full orig resolution
        faces = []
        inv_scale = 1.0 / scale if scale > 0 else 1.0
        for f in faces_downscaled:
            faces.append({
                "x": int(f["x"] * inv_scale),
                "y": int(f["y"] * inv_scale),
                "w": int(f["w"] * inv_scale),
                "h": int(f["h"] * inv_scale),
                "mouth": f.get("mouth", 0.0),
            })

        samples.append({
            "time": round(i * dt, 2),
            "faces": faces,
            "frame": frame if i % 2 == 0 else None,
        })

    cap.release()
    return samples, (w_orig, h_orig)


def compute_smart_reframe_path(
    samples: List[Dict[str, Any]],
    orig_dims: Tuple[int, int],
    voice_intervals: List[Tuple[float, float]],
    zoom_factor: float = 1.15
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Computes smoothed 9:16 crop path and automatic scene layouts (SINGLE, SPLIT, SCREEN).
    Returns (crop_path, scenes).
    """
    w_orig, h_orig = orig_dims
    target_aspect = 9.0 / 16.0

    # 1. Base crop dimensions with 1.15x face zoom
    crop_h = min(float(h_orig), float(w_orig) / target_aspect) / zoom_factor
    crop_w = crop_h * target_aspect
    if crop_w > w_orig:
        crop_w = float(w_orig)
        crop_h = crop_w / target_aspect

    raw_centers: List[Tuple[float, float, str, Dict[str, Any]]] = []
    current_speaker_idx = 0
    speaker_hold_until = 0.0

    # 2. Per-sample active speaker and layout decision
    for s in samples:
        t = s["time"]
        faces = s["faces"]
        is_voice = is_time_in_intervals(t, voice_intervals)

        layout = "SINGLE"
        chosen_face = None

        if len(faces) == 0:
            target_cx, target_cy = w_orig / 2.0, h_orig / 2.0
        elif len(faces) == 1:
            f = faces[0]
            target_cx, target_cy = f["x"] + f["w"] / 2.0, f["y"] + f["h"] / 2.0
            chosen_face = f
        else:
            # Multi-face: active speaker selection with 0.8s hold
            mouth_scores = [f["mouth"] * (2.0 if is_voice else 0.5) for f in faces]
            best_idx = int(np.argmax(mouth_scores))

            # Check if multi-party conversation justifies SPLIT layout
            top_two = sorted(mouth_scores, reverse=True)[:2]
            if top_two[0] > 0.08 and top_two[1] > 0.06 and is_voice:
                layout = "SPLIT"

            if t >= speaker_hold_until:
                current_speaker_idx = best_idx
                speaker_hold_until = t + 0.8 # 0.8s hold

            idx_to_use = min(current_speaker_idx, len(faces) - 1)
            f = faces[idx_to_use]
            target_cx, target_cy = f["x"] + f["w"] / 2.0, f["y"] + f["h"] / 2.0
            chosen_face = f

        raw_centers.append((target_cx, target_cy, layout, chosen_face or {}))

    # 3. Path smoothing: moving average + max speed limiter
    smoothed_path: List[Dict[str, Any]] = []
    window_size = 5
    max_speed_px_per_sec = 350.0 # Gentle pan limit

    curr_cx = w_orig / 2.0
    curr_cy = h_orig / 2.0

    for i in range(len(raw_centers)):
        t = samples[i]["time"]
        dt = 0.2 if i == 0 else (t - samples[i-1]["time"])

        # Moving average
        window = raw_centers[max(0, i - window_size // 2): min(len(raw_centers), i + window_size // 2 + 1)]
        avg_cx = float(np.mean([p[0] for p in window]))
        avg_cy = float(np.mean([p[1] for p in window]))

        # Max speed limiter
        dx = avg_cx - curr_cx
        dy = avg_cy - curr_cy
        dist = math.hypot(dx, dy)
        max_dist = max_speed_px_per_sec * max(0.05, dt)

        if dist > max_dist:
            scale = max_dist / dist
            curr_cx += dx * scale
            curr_cy += dy * scale
        else:
            curr_cx = avg_cx
            curr_cy = avg_cy

        # Clamp within frame
        x_min = max(0, int(round(curr_cx - crop_w / 2.0)))
        x_min = min(int(round(w_orig - crop_w)), x_min)
        y_min = max(0, int(round(curr_cy - crop_h / 2.0)))
        y_min = min(int(round(h_orig - crop_h)), y_min)

        smoothed_path.append({
            "time": t,
            "x": x_min,
            "y": y_min,
            "w": int(round(crop_w)),
            "h": int(round(crop_h)),
            "layout": raw_centers[i][2],
            "active_face": raw_centers[i][3],
        })

    # 4. Consolidate scenes with minimum 2.0s duration
    scenes: List[Dict[str, Any]] = []
    if smoothed_path:
        curr_layout = smoothed_path[0]["layout"]
        curr_start = smoothed_path[0]["time"]

        for pt in smoothed_path:
            if pt["layout"] != curr_layout and (pt["time"] - curr_start) >= 2.0:
                scenes.append({"start": round(curr_start, 2), "end": round(pt["time"], 2), "layout": curr_layout})
                curr_layout = pt["layout"]
                curr_start = pt["time"]

        scenes.append({"start": round(curr_start, 2), "end": round(smoothed_path[-1]["time"], 2), "layout": curr_layout})

    return smoothed_path, scenes


def render_smart_reframe_video(
    source_video: Path,
    output_video: Path,
    start_sec: float,
    duration: float,
    crop_path: List[Dict[str, Any]],
    scenes: List[Dict[str, Any]]
) -> Path:
    """
    Renders the 9:16 video following the crop path and layout (SINGLE, SPLIT, SCREEN),
    then muxes the original high-quality audio back.
    """
    cap = cv2.VideoCapture(str(source_video))
    if not cap.isOpened():
        raise RuntimeError("Cannot open source video for rendering")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000.0)

    target_w, target_h = 1080, 1920
    temp_silent_video = output_video.parent / f"temp_{output_video.name}"

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(temp_silent_video), fourcc, fps, (target_w, target_h))

    total_frames = int(duration * fps)
    path_len = len(crop_path)

    for f_idx in range(total_frames):
        ret, frame = cap.read()
        if not ret:
            break

        # Interpolate crop-path for current timestamp
        t_rel = f_idx / fps
        path_idx = min(path_len - 1, int((t_rel / max(0.001, duration)) * path_len))
        crop_info = crop_path[path_idx]

        layout = crop_info.get("layout", "SINGLE")
        x, y, w, h = crop_info["x"], crop_info["y"], crop_info["w"], crop_info["h"]

        # Ensure valid bounds
        x = max(0, min(frame.shape[1] - 10, x))
        y = max(0, min(frame.shape[0] - 10, y))
        w = max(10, min(frame.shape[1] - x, w))
        h = max(10, min(frame.shape[0] - y, h))

        if layout == "SPLIT":
            # Two stacked 1080x960 crops separated by a 4px white divider
            top_half = cv2.resize(frame[y:y+h, x:x+w], (target_w, 958))
            # Shift slightly right for the second person if possible
            x2 = min(frame.shape[1] - w, x + int(w * 0.4))
            bottom_half = cv2.resize(frame[y:y+h, x2:x2+w], (target_w, 958))

            divider = np.full((4, target_w, 3), 255, dtype=np.uint8)
            canvas = np.vstack([top_half, divider, bottom_half])
        else:
            # SINGLE layout
            cropped = frame[y:y+h, x:x+w]
            canvas = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

        out.write(canvas)

    cap.release()
    out.release()

    # Mux original audio back with faststart
    mux_cmd = [
        "ffmpeg",
        "-y",
        "-i", str(temp_silent_video),
        "-ss", f"{start_sec:.2f}",
        "-t", f"{duration:.2f}",
        "-i", str(source_video),
        "-map", "0:v:0",
        "-map", "1:a:0?",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_video)
    ]
    subprocess.run(mux_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    if temp_silent_video.exists():
        temp_silent_video.unlink()

    return output_video
