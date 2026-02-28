# Instagram/TikTok/YouTube Reposter - Windows Setup
# Run in PowerShell: irm https://raw.githubusercontent.com/JulCCrum/instagram-tiktok-and-youtube-reposter/main/setup_windows.ps1 | iex

$ErrorActionPreference = "Stop"

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  Instagram/TikTok/YouTube Reposter Setup" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# --- Check Python ---
Write-Host "[1/6] Checking Python..." -ForegroundColor Yellow

$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 9) {
                $python = $cmd
                Write-Host "  Found: $ver"
                break
            }
        }
    } catch {}
}

if (-not $python) {
    Write-Host "  Python 3.9+ not found." -ForegroundColor Red
    Write-Host "  Installing via winget..." -ForegroundColor Yellow
    try {
        winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
        $python = "python"
        Write-Host "  Python installed. You may need to restart PowerShell." -ForegroundColor Green
    } catch {
        Write-Host "  ERROR: Could not install Python automatically." -ForegroundColor Red
        Write-Host "  Please install Python 3.9+ from https://www.python.org/downloads/" -ForegroundColor Red
        Write-Host "  IMPORTANT: Check 'Add Python to PATH' during installation!" -ForegroundColor Red
        exit 1
    }
}

# --- Check ffmpeg ---
Write-Host ""
Write-Host "[2/6] Checking ffmpeg..." -ForegroundColor Yellow

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "  ffmpeg not found. Installing via winget..." -ForegroundColor Yellow
    try {
        winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
        Write-Host "  ffmpeg installed." -ForegroundColor Green
    } catch {
        Write-Host "  Could not auto-install ffmpeg." -ForegroundColor Red
        Write-Host "  Download from https://ffmpeg.org/download.html and add to PATH" -ForegroundColor Red
    }
} else {
    Write-Host "  ffmpeg found."
}

# --- Check yt-dlp ---
Write-Host ""
Write-Host "[3/6] Checking yt-dlp..." -ForegroundColor Yellow

if (-not (Get-Command yt-dlp -ErrorAction SilentlyContinue)) {
    Write-Host "  yt-dlp not found. Installing via winget..." -ForegroundColor Yellow
    try {
        winget install yt-dlp.yt-dlp --accept-package-agreements --accept-source-agreements
        Write-Host "  yt-dlp installed." -ForegroundColor Green
    } catch {
        Write-Host "  Could not auto-install yt-dlp. Will install via pip later." -ForegroundColor Yellow
    }
} else {
    Write-Host "  yt-dlp found."
}

# --- Clone repo ---
Write-Host ""
Write-Host "[4/6] Setting up project..." -ForegroundColor Yellow

$installDir = "$HOME\instagram-tiktok-reposter"

if (Test-Path "$installDir\.git") {
    Write-Host "  Project exists at $installDir, pulling latest..."
    Push-Location $installDir
    git pull --ff-only 2>$null
    Pop-Location
} else {
    Write-Host "  Cloning to $installDir..."
    git clone https://github.com/JulCCrum/instagram-tiktok-and-youtube-reposter.git $installDir
}

Push-Location $installDir

# --- Create venv ---
Write-Host ""
Write-Host "[5/6] Setting up Python environment..." -ForegroundColor Yellow

if (-not (Test-Path "venv")) {
    & $python -m venv venv
}

# Activate venv
& .\venv\Scripts\Activate.ps1

# Install deps
pip install --upgrade pip -q
pip install -r requirements.txt -q

# yt-dlp via pip as fallback
if (-not (Get-Command yt-dlp -ErrorAction SilentlyContinue)) {
    pip install yt-dlp -q
}

# Install Playwright browsers
Write-Host ""
Write-Host "[6/6] Installing browser automation..." -ForegroundColor Yellow
python -m playwright install chromium
python -m playwright install firefox

# --- Run configure ---
Write-Host ""
Write-Host "Starting configuration wizard..." -ForegroundColor Green
Write-Host ""
python configure.py

Pop-Location

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Quick reference:" -ForegroundColor Cyan
Write-Host "  cd $installDir"
Write-Host "  .\venv\Scripts\Activate.ps1"
Write-Host "  python main.py test       # Verify setup"
Write-Host "  python main.py init       # Login to platforms (first time)"
Write-Host "  python main.py download   # Download your Instagram reels"
Write-Host "  python main.py run        # Download + upload one post"
Write-Host "  python main.py status     # Check progress"
Write-Host ""
Write-Host "NOTE: On Windows, cron is not available." -ForegroundColor Yellow
Write-Host "Use Task Scheduler for automation instead:" -ForegroundColor Yellow
Write-Host "  1. Open Task Scheduler (search in Start Menu)" -ForegroundColor Yellow
Write-Host "  2. Create Basic Task -> set trigger to repeat every 3 hours" -ForegroundColor Yellow
Write-Host "  3. Action: Start a program" -ForegroundColor Yellow
Write-Host "     Program: $installDir\venv\Scripts\python.exe" -ForegroundColor Yellow
Write-Host "     Arguments: main.py run" -ForegroundColor Yellow
Write-Host "     Start in: $installDir" -ForegroundColor Yellow
Write-Host ""
