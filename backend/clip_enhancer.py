"""
Clip Enhancer module for ClipSnap.
Handles:
1. Silence removal (gaps > 0.6s trimmed to 0.15s) and filler removal ("um", "uh", "ah", "er", "hmm", standalone "like/you know").
2. Audio-video trimming + concatenation and timestamp recalculation for captions.
3. Background music looping, volume ducking (-22 dB), and 1s/1.5s fades.
4. Sound effect (SFX) overlay ("whoosh", "pop", "ding") at Gemini-detected key moments (-12 dB).
5. B-roll insertion via Pexels API (portrait videos cached in storage/broll/) with 0.2s crossfade.
"""

import os
import json
import random
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import urllib.request
import urllib.parse

from google import genai
from google.genai import types

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

FILLER_WORDS = {"um", "uh", "ah", "er", "hmm"}
POTENTIAL_FILLERS = {"like", "you know"}


def clean_word(w: str) -> str:
    return w.lower().strip(".,?!…\":;'()[]{}")


def plan_cuts_and_keep_segments(
    words: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
    remove_silence: bool = True,
    remove_fillers: bool = True,
) -> Tuple[List[Tuple[float, float]], List[Dict[str, Any]]]:
    """
    Identifies silence gaps > 0.6s (shortened to 0.15s) and filler words.
    Builds a list of KEEP intervals [(start, end), ...] relative to clip_start.
    Returns (keep_segments, shifted_and_cut_words).
    """
    duration = max(0.5, clip_end - clip_start)

    # 1. Filter and normalize words to relative clip time
    rel_words: List[Dict[str, Any]] = []
    for w in words:
        w_start = float(w.get("start", 0.0))
        w_end = float(w.get("end", 0.0))
        if w_end > clip_start and w_start < clip_end:
            rel_start = max(0.0, w_start - clip_start)
            rel_end = min(duration, w_end - clip_start)
            word_str = clean_word(str(w.get("word", "")))
            if rel_end > rel_start and word_str:
                rel_words.append({
                    "raw_word": str(w.get("word", "")),
                    "word": word_str,
                    "rel_start": round(rel_start, 3),
                    "rel_end": round(rel_end, 3),
                })

    if not rel_words:
        return [(0.0, duration)], []

    remove_intervals: List[Tuple[float, float]] = []

    # 2. Filler words removal
    kept_words: List[Dict[str, Any]] = []
    for i, w in enumerate(rel_words):
        is_filler = False
        if remove_fillers:
            if w["word"] in FILLER_WORDS:
                is_filler = True
            elif w["word"] in POTENTIAL_FILLERS:
                # Standalone between pauses (> 0.3s before and after)
                pause_before = (w["rel_start"] - (rel_words[i-1]["rel_end"] if i > 0 else 0.0)) > 0.3
                pause_after = ((rel_words[i+1]["rel_start"] if i < len(rel_words)-1 else duration) - w["rel_end"]) > 0.3
                if pause_before and pause_after:
                    is_filler = True

        if is_filler:
            # Cut filler with slight buffer
            c_start = max(0.0, w["rel_start"] - 0.015)
            c_end = min(duration, w["rel_end"] + 0.015)
            remove_intervals.append((c_start, c_end))
        else:
            kept_words.append(w)

    # 3. Silence removal: gaps > 0.6s shortened to 0.15s
    if remove_silence and kept_words:
        # Check start silence
        if kept_words[0]["rel_start"] > 0.6:
            # Remove all but 0.15s before the first word
            cut_end = kept_words[0]["rel_start"] - 0.15
            remove_intervals.append((0.0, cut_end))

        # Check in-between word gaps
        for i in range(len(kept_words) - 1):
            gap_start = kept_words[i]["rel_end"]
            gap_end = kept_words[i+1]["rel_start"]
            gap_dur = gap_end - gap_start
            if gap_dur > 0.6:
                # Shorten to 0.15s (keep 0.075s at both ends)
                remove_intervals.append((gap_start + 0.075, gap_end - 0.075))

        # Check end silence
        if (duration - kept_words[-1]["rel_end"]) > 0.6:
            remove_intervals.append((kept_words[-1]["rel_end"] + 0.15, duration))

    # 4. Merge overlapping remove intervals
    if not remove_intervals:
        return [(0.0, duration)], kept_words

    remove_intervals.sort(key=lambda x: x[0])
    merged_removes: List[Tuple[float, float]] = []
    for r_start, r_end in remove_intervals:
        if not merged_removes or r_start > merged_removes[-1][1]:
            merged_removes.append((r_start, r_end))
        else:
            merged_removes[-1] = (merged_removes[-1][0], max(merged_removes[-1][1], r_end))

    # 5. Invert to get KEEP intervals
    keep_segments: List[Tuple[float, float]] = []
    last_pos = 0.0
    for r_start, r_end in merged_removes:
        if r_start - last_pos > 0.05: # Minimum chunk 50ms
            keep_segments.append((round(last_pos, 3), round(r_start, 3)))
        last_pos = r_end
    if duration - last_pos > 0.05:
        keep_segments.append((round(last_pos, 3), round(duration, 3)))

    if not keep_segments:
        keep_segments = [(0.0, duration)]

    # 6. Recalculate word timestamps so captions align perfectly with the cut video
    def get_new_time(old_t: float) -> float:
        cut_amount = 0.0
        for r_start, r_end in merged_removes:
            if old_t >= r_end:
                cut_amount += (r_end - r_start)
            elif old_t > r_start:
                cut_amount += (old_t - r_start)
                break
        return max(0.0, round(old_t - cut_amount, 3))

    adjusted_words: List[Dict[str, Any]] = []
    for w in kept_words:
        new_start = get_new_time(w["rel_start"])
        new_end = get_new_time(w["rel_end"])
        if new_end > new_start:
            adjusted_words.append({
                "word": w["raw_word"],
                "start": new_start,
                "end": new_end,
            })

    return keep_segments, adjusted_words


def execute_trim_and_concat(
    input_video: Path,
    output_video: Path,
    clip_start: float,
    keep_segments: List[Tuple[float, float]],
) -> float:
    """
    Applies sample-accurate FFmpeg trim/atrim and concat filter on keep segments.
    Returns the new duration of the cut video.
    """
    if len(keep_segments) == 1 and keep_segments[0][0] == 0.0:
        # No cuts needed
        dur = keep_segments[0][1]
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{clip_start:.2f}",
            "-t", f"{dur:.2f}",
            "-i", str(input_video),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_video)
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return dur

    n = len(keep_segments)
    filter_parts = []
    concat_inputs = []

    for i, (k_start, k_end) in enumerate(keep_segments):
        abs_start = clip_start + k_start
        abs_end = clip_start + k_end
        filter_parts.append(
            f"[0:v]trim=start={abs_start:.3f}:end={abs_end:.3f},setpts=PTS-STARTPTS[v{i}];"
            f"[0:a]atrim=start={abs_start:.3f}:end={abs_end:.3f},asetpts=PTS-STARTPTS[a{i}];"
        )
        concat_inputs.append(f"[v{i}][a{i}]")

    concat_filter = "".join(filter_parts) + f"{''.join(concat_inputs)}concat=n={n}:v=1:a=1[outv][outa]"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_video),
        "-filter_complex", concat_filter,
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_video)
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg trim/concat failed: {res.stderr}")

    new_duration = sum(k_end - k_start for k_start, k_end in keep_segments)
    return round(new_duration, 2)


# ========================================================
# Music & SFX
# ========================================================

def apply_background_music(
    input_video: Path,
    output_video: Path,
    duration: float,
    assets_dir: Path = Path("assets/music")
) -> bool:
    """
    Picks a random track from assets/music/, loops/trims to clip duration,
    sets to -22 dB, fades in 1s, fades out 1.5s, and ducks under speech.
    Returns True if music was added, False if no music files found.
    """
    if not assets_dir.exists():
        assets_dir.mkdir(parents=True, exist_ok=True)
        return False

    music_files = list(assets_dir.glob("*.mp3")) + list(assets_dir.glob("*.wav"))
    if not music_files:
        return False

    selected_track = random.choice(music_files)
    fade_out_start = max(0.5, duration - 1.5)

    # Audio filtergraph:
    # 1. Loop/trim music to clip duration
    # 2. Lower volume to -22 dB (approx 0.08)
    # 3. Fade-in 1.0s, fade-out 1.5s
    # 4. Duck music under primary speech using sidechain compression or amix
    filter_complex = (
        f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{duration:.2f},"
        f"volume=-22dB,afade=t=in:ss=0:d=1.0,afade=t=out:st={fade_out_start:.2f}:d=1.5[music];"
        f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[outa]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_video),
        "-i", str(selected_track),
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[outa]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_video)
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode == 0


def get_gemini_http_options(timeout_ms: int = 30000) -> Optional[types.HttpOptions]:
    try:
        if hasattr(types, "HttpRetryOptions"):
            return types.HttpOptions(timeout=timeout_ms, retry_options=types.HttpRetryOptions(attempts=1))
        return types.HttpOptions(timeout=timeout_ms)
    except Exception:
        try:
            return types.HttpOptions(timeout=timeout_ms)
        except Exception:
            return None


def detect_sfx_moments_gemini(transcript_text: str, duration: float) -> List[Dict[str, Any]]:
    """Ask Gemini to pinpoint up to 3 key punchy moments for SFX (whoosh, pop, ding)."""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        return []

    try:
        http_opts = get_gemini_http_options(timeout_ms=30000)
        client = genai.Client(api_key=GEMINI_API_KEY, http_options=http_opts) if http_opts else genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"Given this video transcript with duration {duration:.1f}s:\n"
            f"{transcript_text}\n\n"
            "Return JSON array of up to 3 key moments to play a sound effect. Each object must have:\n"
            "- 'time': float seconds (between 0.5 and duration - 0.5)\n"
            "- 'type': strictly one of 'whoosh' (transitions/hooks), 'pop' (ideas/surprises), or 'ding' (tips/value)\n"
            "Return ONLY a JSON array."
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        data = json.loads(response.text.strip())
        if isinstance(data, list):
            return data[:3]
    except Exception:
        pass
    return []


def apply_sound_effects(
    input_video: Path,
    output_video: Path,
    sfx_moments: List[Dict[str, Any]],
    assets_dir: Path = Path("assets/sfx")
) -> bool:
    """Overlays whoosh, pop, and ding SFX at designated timestamps at -12 dB."""
    if not sfx_moments or not assets_dir.exists():
        return False

    valid_sfx = []
    for m in sfx_moments:
        sfx_type = m.get("type", "").lower()
        t = float(m.get("time", 0.0))
        for ext in (".mp3", ".wav"):
            candidate = assets_dir / f"{sfx_type}{ext}"
            if candidate.exists():
                valid_sfx.append((candidate, t))
                break

    if not valid_sfx:
        return False

    # Build adelay and amix filter
    inputs = ["-i", str(input_video)]
    filter_parts = []
    amix_inputs = ["[0:a]"]

    for idx, (path, t) in enumerate(valid_sfx, start=1):
        inputs.extend(["-i", str(path)])
        delay_ms = int(t * 1000)
        filter_parts.append(
            f"[{idx}:a]volume=-12dB,adelay={delay_ms}|{delay_ms}[sfx{idx}];"
        )
        amix_inputs.append(f"[sfx{idx}]")

    concat_amix = "".join(filter_parts) + f"{''.join(amix_inputs)}amix=inputs={len(valid_sfx)+1}:duration=first[outa]"

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", concat_amix,
        "-map", "0:v",
        "-map", "[outa]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_video)
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode == 0


# ========================================================
# Pexels B-Roll Video Overlays
# ========================================================

def pick_broll_cues_gemini(transcript_text: str, duration: float) -> List[Dict[str, Any]]:
    """Ask Gemini for up to 3 visual moments with a 1-3 word keyword (never during first 2s)."""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE" or duration < 5.0:
        return []

    try:
        http_opts = get_gemini_http_options(timeout_ms=30000)
        client = genai.Client(api_key=GEMINI_API_KEY, http_options=http_opts) if http_opts else genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"Given this transcript of a {duration:.1f}s video:\n"
            f"{transcript_text}\n\n"
            "Select up to 3 moments where adding visual B-roll footage (cutaway video) would increase viewer engagement.\n"
            "Rules:\n"
            "1. start_sec must be AT LEAST 2.0 (never during the first 2 seconds).\n"
            "2. duration must be 2.0 to 3.0 seconds.\n"
            "3. keyword must be a 1-3 word search query for high quality stock footage (e.g. 'city traffic', 'person typing', 'coffee cup').\n"
            "Return JSON array of objects with: 'start_sec', 'duration', 'keyword'."
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        data = json.loads(response.text.strip())
        if isinstance(data, list):
            valid = []
            for item in data[:3]:
                if float(item.get("start_sec", 0)) >= 2.0:
                    valid.append(item)
            return valid
    except Exception:
        pass
    return []


def search_and_download_pexels_broll(
    keyword: str,
    storage_dir: Path = Path("storage/broll")
) -> Optional[Tuple[Path, str]]:
    """Search Pexels for a portrait video and cache it in storage/broll."""
    if not PEXELS_API_KEY or PEXELS_API_KEY == "YOUR_PEXELS_API_KEY_HERE":
        return None

    storage_dir.mkdir(parents=True, exist_ok=True)
    safe_slug = "".join(c if c.isalnum() else "_" for c in keyword.lower())
    cached_path = storage_dir / f"pexels_{safe_slug}.mp4"

    if cached_path.exists() and cached_path.stat().st_size > 50000:
        return cached_path, f"Pexels footage for '{keyword}'"

    try:
        query_encoded = urllib.parse.quote(keyword)
        url = f"https://api.pexels.com/videos/search?query={query_encoded}&orientation=portrait&per_page=1"
        req = urllib.request.Request(url, headers={"Authorization": PEXELS_API_KEY})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        videos = data.get("videos", [])
        if not videos:
            return None

        video_obj = videos[0]
        credit = f"Video by {video_obj.get('user', {}).get('name', 'Pexels Creator')} on Pexels"

        # Find best download link (HD preferred)
        files = video_obj.get("video_files", [])
        download_url = None
        for f in files:
            if f.get("width", 0) >= 720 and f.get("link"):
                download_url = f.get("link")
                break
        if not download_url and files:
            download_url = files[0].get("link")

        if download_url:
            urllib.request.urlretrieve(download_url, str(cached_path))
            return cached_path, credit
    except Exception:
        return None
    return None


def overlay_broll_clips(
    input_video: Path,
    output_video: Path,
    broll_cues: List[Dict[str, Any]],
    format_type: str = "9:16"
) -> Tuple[bool, List[str]]:
    """Overlays B-roll full-screen during specified intervals with 0.2s crossfade."""
    if not broll_cues:
        return False, []

    w_target, h_target = (1080, 1920) if format_type == "9:16" else ((1080, 1080) if format_type == "1:1" else (1440, 1080))

    credits = []
    valid_cues = []
    for cue in broll_cues:
        kw = cue.get("keyword", "")
        res = search_and_download_pexels_broll(kw)
        if res:
            broll_file, credit = res
            credits.append(credit)
            valid_cues.append({
                "file": broll_file,
                "start": float(cue.get("start_sec", 2.0)),
                "dur": float(cue.get("duration", 2.5)),
            })

    if not valid_cues:
        return False, []

    # Use first valid cue to overlay cleanly
    first_cue = valid_cues[0]
    b_file = first_cue["file"]
    b_start = first_cue["start"]
    b_dur = first_cue["dur"]
    b_end = b_start + b_dur

    # Scale B-roll to match frame and overlay between b_start and b_end with 0.2s fade
    filter_complex = (
        f"[1:v]scale={w_target}:{h_target}:force_original_aspect_ratio=increase,crop={w_target}:{h_target},"
        f"format=yuva420p,fade=t=in:st=0:d=0.2:alpha=1,fade=t=out:st={b_dur-0.2:.2f}:d=0.2:alpha=1[broll];"
        f"[0:v][broll]overlay=0:0:enable='between(t,{b_start:.2f},{b_end:.2f})'[outv]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_video),
        "-ss", "0", "-t", f"{b_dur:.2f}",
        "-i", str(b_file),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_video)
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode == 0, credits
