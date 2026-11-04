# ClipSnap - Unified App & FastAPI Backend

A complete, self-contained personal AI YouTube video clipper app.
Runs as **ONE application with ONE server** on `http://localhost:8000`, serving both the FastAPI backend and the compiled React frontend.

---

## 🚀 Quick Setup (Laptop: Windows or Mac)

### 1. Prerequisites: Install FFmpeg

- **macOS** (using Homebrew):
  ```bash
  brew install ffmpeg
  ```
- **Windows** (using Winget or Chocolatey):
  ```powershell
  winget install Gyan.FFmpeg
  ```
- **Linux (Ubuntu / Debian)**:
  ```bash
  sudo apt update && sudo apt install -y ffmpeg
  ```

---

### 2. Install Python Dependencies

From the project root:
```bash
pip install -r backend/requirements.txt
```

---

### 3. Configure `.env`

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Set your free Gemini API key:
```ini
GEMINI_API_KEY="your_actual_gemini_api_key_here"
GEMINI_MODEL="gemini-2.5-flash"
PORT=8000
```

---

### 4. Run the Unified App (One Command)

- **On Mac / Linux**:
  ```bash
  python3 run.py
  # Or: ./start.sh
  ```
- **On Windows**:
  ```powershell
  python run.py
  # Or double-click: start.bat
  ```

Open your browser at **[http://localhost:8000](http://localhost:8000)**!

---

## 📡 Endpoints

- `GET /` ➔ Serves built React frontend (`dist/index.html`)
- `GET /diagnostics` ➔ Returns FFmpeg, ffprobe, yt-dlp, Gemini API key status, free disk space, Whisper model
- `GET /health` ➔ Quick health check
- `POST /import-file` (multipart upload) ➔ `{ "video_id": string, "duration": number, "title": string }`
- `POST /import-url` `{ "url": string }` ➔ `{ "video_id": string, "duration": number, "title": string }`
- `GET /video/{video_id}` ➔ HTTP range stream of video
- `GET /thumbnail/{video_id}?t={seconds}` ➔ Frame thumbnail
- `POST /transcribe` `{ "video_id": string }` ➔ Word-level timestamps
- `GET /transcribe-status/{video_id}` ➔ Progress percentage (0-100)
- `POST /highlights` `{ "video_id": string, "prompt"?: string, "min_sec": 15, "max_sec": 60 }` ➔ High-retention clips extracted with Gemini
- `POST /export` `{ "video_id": string, "clip": Clip, "format": "9:16"|"1:1"|"4:3", "options": {} }` ➔ Re-encoded clip URL
- `GET /exports/{filename}` ➔ Download exported clip
- `POST /metadata` `{ "video_id": string, "clip": Clip, "source_url"?: string }` ➔ Viral titles, description & hashtags
- `POST /thumbnails` `{ "video_id": string, "clip": Clip }` ➔ 3 face-scored covers with text hooks
- `GET /docs` ➔ Interactive Swagger UI documentation

