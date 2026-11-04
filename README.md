# ClipSnap 🎬

**Turn long videos into viral YouTube Shorts, TikToks, and Instagram Reels with AI.**  
ClipSnap runs as **ONE app on ONE server** locally on your laptop (Windows or Mac), serving both the AI video processing engine and the web interface at **`http://localhost:8000`**.

---

## 📋 What to Install (Prerequisites)

Before running ClipSnap for the first time, install these four tools on your computer:

### 1. Git
- **Windows**: Download from [git-scm.com](https://git-scm.com) or run in PowerShell:
  ```powershell
  winget install Git.Git
  ```
- **macOS**: Open Terminal and run:
  ```bash
  brew install git
  ```
  *(Or install Xcode Command Line Tools: `xcode-select --install`)*

### 2. Node.js (LTS 20 or newer)
- **Windows**: Download the LTS installer from [nodejs.org](https://nodejs.org) or run:
  ```powershell
  winget install OpenJS.NodeJS.LTS
  ```
- **macOS**: Run in Terminal:
  ```bash
  brew install node
  ```

### 3. Python (3.11 or newer)
- **Windows**: Download from [python.org](https://python.org).  
  ⚠️ **CRITICAL:** Check the box that says **"Add Python to PATH"** at the bottom of the installer window before clicking Install.  
  *(Or via Winget: `winget install Python.Python.3.11`)*
- **macOS**: Run in Terminal:
  ```bash
  brew install python@3.11
  ```

### 4. FFmpeg (Required for audio/video trimming and captions)
- **Windows**: Open PowerShell and run:
  ```powershell
  winget install Gyan.FFmpeg
  ```
  *(Close and reopen your terminal after installation so your computer recognizes `ffmpeg`)*
- **macOS**: Open Terminal and run:
  ```bash
  brew install ffmpeg
  ```
- **Linux (Ubuntu/Debian)**:
  ```bash
  sudo apt update && sudo apt install -y ffmpeg
  ```

*To verify FFmpeg is working, run:*
```bash
ffmpeg -version
```

---

## 🚀 How to Clone & Run

### Step 1: Clone the repository
Open your Terminal (macOS) or Command Prompt / PowerShell (Windows):
```bash
git clone https://github.com/brave-scientist/CLIPPER.git
cd CLIPPER
```

---

### Step 2: Add your free Gemini API Key
1. Create your `.env` configuration file from the template:
   - **Windows**:
     ```cmd
     copy .env.example .env
     ```
   - **macOS / Linux**:
     ```bash
     cp .env.example .env
     ```
2. Get a free API key from [Google AI Studio](https://aistudio.google.com/app/apikey).
3. Open `.env` in Notepad or VS Code and paste your key:
   ```ini
   GEMINI_API_KEY="AIzaSyYourActualKeyHere..."
   GEMINI_MODEL="gemini-2.5-flash"
   WHISPER_MODEL=base
   PORT=8000
   ```

---

### Step 3: Run the Application

#### On Windows (Effortless 1-Click)
Double-click **`start.bat`** in the project folder (or run in Command Prompt):
```cmd
start.bat
```

#### On macOS / Linux
Open Terminal and run:
```bash
./start.sh
```

**That's it!** The startup script automatically:
1. Creates the Python virtual environment (`venv`) if missing.
2. Installs or updates dependencies from `backend/requirements.txt`.
3. Runs `npm install` and compiles the frontend (`npm run build`) if needed.
4. Starts FastAPI on `0.0.0.0:8000`.
5. Prints your computer and phone URLs.

Open your browser to: **[http://localhost:8000](http://localhost:8000)**

---

## 📱 How to Open on Your Phone (Same Wi-Fi)

You can preview and export video clips straight from your iPhone or Android phone!

1. Make sure your phone and laptop are connected to the **same Wi-Fi network**.
2. Look at the terminal output when ClipSnap starts:
   ```text
   ====================================================================
   Open http://localhost:8000 on this computer, or http://192.168.1.150:8000 on my phone (same Wi-Fi)
   ====================================================================
   ```
3. Open Safari, Chrome, or any browser on your phone and go to that address (e.g. `http://192.168.1.150:8000`).

---

## 🔄 Update yt-dlp

YouTube updates its video player code frequently. If a YouTube link fails to download, update yt-dlp to the latest release with:

```bash
pip install -U yt-dlp
```

---

## 🛠 Fixing the 5 Most Common Problems

### 1. `FFmpeg not found` or `ffprobe is not installed`
- **Why**: FFmpeg is not installed or not in your system's `PATH`.
- **Fix (Windows)**: Run `winget install Gyan.FFmpeg`. Then close and restart your terminal or reboot your computer so the PATH updates.
- **Fix (Mac)**: Run `brew install ffmpeg`. Verify with `ffmpeg -version`.
- **Diagnostics check**: Visit [http://localhost:8000/diagnostics](http://localhost:8000/diagnostics) in your browser to verify FFmpeg detection.

### 2. `Port 8000 already in use` (`WinError 10048` or `Address already in use`)
- **Why**: Another program or a previous instance of ClipSnap is still running on port 8000.
- **Fix A (Easiest)**: Open `.env` and change `PORT=8000` to `PORT=8080`.
- **Fix B (Free port 8000)**:
  - **Windows**: Open Command Prompt as Administrator and run:
    ```cmd
    netstat -ano | findstr :8000
    taskkill /PID <PID_NUMBER> /F
    ```
  - **Mac/Linux**: Run in Terminal:
    ```bash
    lsof -i :8000
    kill -9 <PID>
    ```

### 3. `yt-dlp outdated` / YouTube download error (403 Forbidden or Sign-in required)
- **Why**: YouTube changes video streaming signatures on a regular basis.
- **Fix**: Update yt-dlp to the latest version:
  ```bash
  pip install -U yt-dlp
  ```

### 4. `Whisper is slow` (Audio transcription takes several minutes)
- **Why**: Larger models (`small`, `medium`, `large-v3`) require substantial processing power on laptop CPUs.
- **Fix**: Open `.env` and switch to a lighter model:
  ```ini
  WHISPER_MODEL=base
  ```
  *(Or `WHISPER_MODEL=tiny` for maximum speed on older laptops. `base` transcribes most 5-minute videos in under 30 seconds).*

### 5. `Gemini rate limit` (HTTP 429 Too Many Requests / Resource Exhausted)
- **Why**: Free-tier Gemini API keys have a rate limit of requests per minute (RPM).
- **Fix**: Wait 60 seconds and click **"Find the best parts"** again. Also ensure `.env` is set to:
  ```ini
  GEMINI_MODEL="gemini-2.5-flash"
  ```
  `gemini-2.5-flash` provides the highest throughput and speed with generous free quotas.

---

## 🔍 Diagnostics

ClipSnap includes a built-in health check and diagnostic tool.  
Open **[http://localhost:8000/diagnostics](http://localhost:8000/diagnostics)** to inspect:
- FFmpeg & ffprobe version
- yt-dlp version
- Whether your `GEMINI_API_KEY` is loaded (safe boolean check, never exposes your secret key)
- Active Gemini model & Whisper model
- Available free disk storage for video processing
