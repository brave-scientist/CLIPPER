#!/usr/bin/env python3
"""
ClipSnap Single-Server Runner for Local Laptop (Windows / Mac / Linux).
Starts the unified FastAPI server on 0.0.0.0:8000 serving:
1. All API routes (/import-file, /import-url, /video, /transcribe, /highlights, /export, /diagnostics, etc.)
2. The compiled React frontend (dist/) directly at "/"
"""

import os
import sys
import socket
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT_DIR / "dist"
SRC_DIR = ROOT_DIR / "src"

def get_local_ip() -> str:
    """Find the local LAN / Wi-Fi IP address of this computer."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # Connect to public DNS IP; doesn't send packets, just asks OS for routing interface IP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def is_build_outdated() -> bool:
    """Check if dist is missing or if source files are newer than dist/index.html."""
    index_file = DIST_DIR / "index.html"
    if not index_file.exists():
        return True

    dist_mtime = index_file.stat().st_mtime

    # Check key config files
    for check_file in [ROOT_DIR / "index.html", ROOT_DIR / "package.json", ROOT_DIR / "vite.config.ts"]:
        if check_file.exists() and check_file.stat().st_mtime > dist_mtime:
            return True

    # Check all files in src/
    if SRC_DIR.exists():
        for p in SRC_DIR.rglob("*"):
            if p.is_file() and p.stat().st_mtime > dist_mtime:
                return True

    return False

def ensure_frontend_built():
    """Ensure frontend is compiled to dist/. If missing or source changed, compile with npm run build."""
    if is_build_outdated():
        print("📦 Frontend build is missing or source changed. Running 'npm run build'...")
        try:
            node_modules = ROOT_DIR / "node_modules"
            if not node_modules.exists():
                print("📦 Installing npm packages (npm install)...")
                subprocess.run(["npm", "install"], cwd=str(ROOT_DIR), check=True)

            subprocess.run(["npm", "run", "build"], cwd=str(ROOT_DIR), check=True)
            print("✅ Frontend build completed successfully.")
        except Exception as e:
            print(f"⚠️ Note: Could not auto-build frontend ({e}).")
            print("   Please run: npm install && npm run build")

def main():
    # Load .env
    from dotenv import load_dotenv
    if (ROOT_DIR / ".env").exists():
        load_dotenv(ROOT_DIR / ".env")
    elif (ROOT_DIR / "backend" / ".env").exists():
        load_dotenv(ROOT_DIR / "backend" / ".env")

    ensure_frontend_built()

    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0"
    local_ip = get_local_ip()

    print("\n" + "=" * 76)
    print("🎬  ClipSnap - Personal AI Shorts Generator")
    print("=" * 76)
    print(f"Open http://localhost:{port} on this computer, or http://{local_ip}:{port} on my phone (same Wi-Fi)")
    print("=" * 76 + "\n")

    try:
        import uvicorn
        uvicorn.run("backend.main:app", host=host, port=port, reload=True)
    except ImportError:
        print("❌ uvicorn is not installed in your Python environment.")
        print("   Please install requirements by running:")
        print("   pip install -r backend/requirements.txt")
        sys.exit(1)

if __name__ == "__main__":
    main()
