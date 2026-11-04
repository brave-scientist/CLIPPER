#!/usr/bin/env bash
# ClipSnap Startup Script for Mac & Linux
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "===================================================================="
echo "🎬 Starting ClipSnap on Mac / Linux..."
echo "===================================================================="

# 1. Create Python venv if missing
if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
    echo "⚙️  [1/4] Creating Python virtual environment (venv)..."
    python3 -m venv venv
    VENV_JUST_CREATED=1
fi

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 2. Install Python requirements if needed
if [ "$VENV_JUST_CREATED" = "1" ] || [ ! -f "venv/.installed" ] || [ "backend/requirements.txt" -nt "venv/.installed" ]; then
    echo "📦 [2/4] Installing / updating Python requirements..."
    pip install -r backend/requirements.txt
    touch venv/.installed
fi

# 3. Build frontend if dist is missing or source changed
NEED_BUILD=0
if [ ! -f "dist/index.html" ]; then
    NEED_BUILD=1
else
    # Check if any source file or config is newer than dist/index.html
    if [ $(find src index.html package.json vite.config.ts -newer dist/index.html 2>/dev/null | head -n 1) ]; then
        NEED_BUILD=1
    fi
fi

if [ "$NEED_BUILD" = "1" ]; then
    echo "🔨 [3/4] Building frontend (npm install & npm run build)..."
    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules" ]; then
        npm install
    fi
    npm run build
fi

# 4. Detect local Wi-Fi / LAN IP address
LOCAL_IP=$(python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")

echo ""
echo "===================================================================="
echo "Open http://localhost:8000 on this computer, or http://$LOCAL_IP:8000 on my phone (same Wi-Fi)"
echo "===================================================================="
echo ""

# 5. Start uvicorn on 0.0.0.0:8000
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
