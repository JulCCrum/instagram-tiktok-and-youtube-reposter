#!/bin/bash
# One-line setup: bash <(curl -sSL https://raw.githubusercontent.com/JulCCrum/instagram-tiktok-and-youtube-reposter/main/setup.sh)
set -e

echo "=============================================="
echo "  Instagram/TikTok/YouTube Reposter Setup"
echo "=============================================="
echo ""

# Detect OS
OS="$(uname -s)"
ARCH="$(uname -m)"

install_mac() {
    # Check for Homebrew
    if ! command -v brew &>/dev/null; then
        echo "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    echo "Installing dependencies via Homebrew..."
    brew install python@3.11 ffmpeg yt-dlp 2>/dev/null || true
}

install_linux() {
    echo "Installing dependencies via apt..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3 python3-venv python3-pip ffmpeg
    # yt-dlp via pip (apt version is often outdated)
    pip3 install --user yt-dlp 2>/dev/null || true
}

# --- Check & install system dependencies ---
echo "[1/6] Checking system dependencies..."

if [[ "$OS" == "Darwin" ]]; then
    install_mac
elif [[ "$OS" == "Linux" ]]; then
    install_linux
else
    echo "Unsupported OS: $OS. Please install Python 3.9+, ffmpeg, and yt-dlp manually."
fi

# Verify essentials
for cmd in python3 ffmpeg yt-dlp; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd is required but not found. Please install it and re-run."
        exit 1
    fi
done

echo "  Python: $(python3 --version)"
echo "  ffmpeg: $(ffmpeg -version 2>&1 | head -1)"
echo "  yt-dlp: $(yt-dlp --version)"
echo ""

# --- Clone or update repo ---
echo "[2/6] Setting up project..."

INSTALL_DIR="${INSTALL_DIR:-$HOME/instagram-tiktok-reposter}"

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "  Project already exists at $INSTALL_DIR, pulling latest..."
    cd "$INSTALL_DIR"
    git pull --ff-only 2>/dev/null || true
else
    echo "  Cloning to $INSTALL_DIR..."
    git clone https://github.com/JulCCrum/instagram-tiktok-and-youtube-reposter.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo ""

# --- Create virtual environment ---
echo "[3/6] Creating Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
echo ""

# --- Install Python dependencies ---
echo "[4/6] Installing Python packages..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo ""

# --- Install Playwright browsers ---
echo "[5/6] Installing browser automation (this may take a minute)..."
python -m playwright install chromium
python -m playwright install firefox
echo ""

# --- Run interactive configuration ---
echo "[6/6] Starting configuration wizard..."
echo ""
python configure.py

echo ""
echo "=============================================="
echo "  Setup complete!"
echo "=============================================="
echo ""
echo "Quick reference:"
echo "  cd $INSTALL_DIR"
echo "  source venv/bin/activate"
echo "  python main.py init       # Login to platforms (first time)"
echo "  python main.py download   # Download your Instagram reels"
echo "  python main.py run        # Download + upload one post"
echo "  python main.py status     # Check progress"
echo "  python schedule_all.py    # Schedule all pending videos"
echo ""
