# GCP Setup Guide

This guide will help you set up the Instagram to TikTok reposter on Google Cloud Platform.

## Step 1: Create a GCP VM

### Option A: Using GCP Console

1. Go to [GCP Console](https://console.cloud.google.com/)
2. Navigate to **Compute Engine** > **VM Instances**
3. Click **Create Instance**
4. Configure:
   - **Name**: `content-system/reposter`
   - **Region**: Choose one close to you
   - **Machine type**: `e2-medium` (2 vCPU, 4 GB RAM) - ~$25/month
     - OR use `e2-micro` for free tier (may be slower)
   - **Boot disk**:
     - Ubuntu 22.04 LTS
     - 20 GB SSD
   - **Firewall**: Allow HTTP/HTTPS (optional, for monitoring)
5. Click **Create**

### Option B: Using gcloud CLI

```bash
gcloud compute instances create content-system/reposter \
    --machine-type=e2-medium \
    --zone=us-central1-a \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=20GB
```

## Step 2: Connect to Your VM

```bash
gcloud compute ssh content-system/reposter --zone=us-central1-a
```

## Step 3: Install Dependencies

Run these commands on your VM:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11+
sudo apt install -y python3.11 python3.11-venv python3-pip

# Install Chrome dependencies
sudo apt install -y wget gnupg2

# Install Chrome
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update
sudo apt install -y google-chrome-stable

# Install additional dependencies for Playwright
sudo apt install -y libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libgbm1 libasound2
```

## Step 4: Set Up the Project

```bash
# Clone/copy the project
cd ~
mkdir -p content-system/reposter
cd content-system/reposter

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install playwright python-dotenv

# Install Playwright browsers
playwright install chromium
playwright install-deps chromium
```

## Step 5: Upload Project Files

From your local machine:

```bash
# Copy files to VM
gcloud compute scp --recurse ~/content-system/reposter/* content-system/reposter:~/content-system/reposter/ --zone=us-central1-a
```

Or create files directly on the VM using nano/vim.

## Step 6: Configure Environment

On the VM:

```bash
cd ~/content-system/reposter
cp .env.example .env
nano .env  # Edit with your credentials
```

Add your credentials:
```
INSTAGRAM_USERNAME=your_username
INSTAGRAM_PASSWORD=your_password
TIKTOK_USERNAME=your_tiktok_username
TIKTOK_PASSWORD=your_tiktok_password
```

## Step 7: Initial Login (Important!)

For the first time, you need to login manually to save your session. This requires a display.

### Option A: Use SSH with X11 Forwarding (Mac/Linux)

```bash
# On your local machine, install XQuartz (Mac) or have X11 (Linux)
gcloud compute ssh content-system/reposter --zone=us-central1-a -- -X

# On VM
cd ~/content-system/reposter
source venv/bin/activate
python main.py init
```

### Option B: Use a Virtual Display (Headless Server)

```bash
# Install virtual display
sudo apt install -y xvfb

# Run with virtual display
cd ~/content-system/reposter
source venv/bin/activate

# Set headless to False in config.py temporarily
# Then run:
xvfb-run -a python main.py init
```

### Option C: Use VNC (Recommended for first-time setup)

```bash
# Install desktop environment and VNC
sudo apt install -y xfce4 xfce4-goodies tigervnc-standalone-server

# Set VNC password
vncpasswd

# Start VNC server
vncserver :1 -geometry 1280x720

# On your local machine, create SSH tunnel
gcloud compute ssh content-system/reposter --zone=us-central1-a -- -L 5901:localhost:5901

# Connect with VNC viewer to localhost:5901
# Then in the VNC session, open terminal and run:
cd ~/content-system/reposter
source venv/bin/activate
python main.py init
```

## Step 8: Test the Script

```bash
cd ~/content-system/reposter
source venv/bin/activate

# Check status
python main.py status

# Download a few posts to test
python main.py download --max 5

# Upload one post
python main.py upload
```

## Step 9: Set Up Cron Job (Every 3 Hours)

```bash
# Open crontab
crontab -e

# Add this line (runs every 3 hours):
0 */3 * * * cd /home/$USER/content-system/reposter && /home/$USER/content-system/reposter/venv/bin/python main.py run >> /home/$USER/content-system/reposter/cron.log 2>&1
```

This will:
- Run every 3 hours (at minute 0)
- Download new posts if needed
- Upload one video to TikTok
- Log output to `cron.log`

## Step 10: Monitor

```bash
# Check cron logs
tail -f ~/content-system/reposter/cron.log

# Check progress
cd ~/content-system/reposter
source venv/bin/activate
python main.py status
```

---

## Troubleshooting

### "Browser not found"
```bash
playwright install chromium
playwright install-deps chromium
```

### "Display not found"
Make sure `HEADLESS = True` in `config.py` for automated runs.

### "Login failed"
Re-run `python main.py init` to refresh your session.

### "CAPTCHA detected"
TikTok may require CAPTCHA. Run with `HEADLESS = False` and solve manually, then your session will be saved.

### Session expired
Sessions may expire after a while. Re-run the init command to refresh them:
```bash
python main.py init
```

---

## Cost Estimate

| Resource | Cost |
|----------|------|
| e2-medium VM (730 hrs) | ~$25/month |
| e2-micro VM (free tier) | $0 |
| Storage (20GB) | ~$1/month |
| **Total** | **$0-26/month** |

---

## Security Notes

1. **Keep your `.env` file secure** - Never commit it to git
2. **Use a dedicated account** - Don't use your main Instagram/TikTok accounts
3. **Monitor for bans** - Check your accounts periodically
4. **Rate limits** - Posting every 3 hours is conservative and safe
