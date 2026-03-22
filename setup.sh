#!/usr/bin/env bash
# setup.sh — run this once to get everything working locally
set -e

echo ""
echo "╔══════════════════════════════════════╗"
echo "║       Job Alert — Local Setup        ║"
echo "╚══════════════════════════════════════╝"
echo ""

# 1. Python check
if ! command -v python3 &>/dev/null; then
  echo "❌  Python 3 not found. Install from https://python.org"
  exit 1
fi

PYTHON=$(command -v python3)
echo "✓ Python: $($PYTHON --version)"

# 2. Create virtualenv
if [ ! -d "venv" ]; then
  echo "→ Creating virtual environment..."
  $PYTHON -m venv venv
  echo "✓ venv created"
else
  echo "✓ venv already exists"
fi

# 3. Activate + install deps
echo "→ Installing dependencies..."
source venv/bin/activate
pip install -q -r requirements.txt
echo "✓ Python packages installed"

# 4. Playwright
echo "→ Installing Playwright browser (chromium)..."
playwright install chromium --with-deps 2>&1 | tail -3
echo "✓ Playwright ready"

# 5. Check config
if grep -q "your_gmail" config.yaml; then
  echo ""
  echo "⚠️  You need to edit config.yaml with your email credentials."
  echo "   Open config.yaml and fill in:"
  echo "     email.sender   → your Gmail address"
  echo "     email.password → Gmail App Password"
  echo "     email.recipient → where to receive alerts"
  echo ""
  echo "   To get an App Password:"
  echo "   Google Account → Security → 2-Step Verification → App Passwords"
fi

echo ""
echo "╔══════════════════════════════════════╗"
echo "║           Setup Complete! 🎉         ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo ""
echo "  1. Edit config.yaml with your email + companies"
echo ""
echo "  2. Test scraper (no email sent):"
echo "     source venv/bin/activate"
echo "     python main.py --dry-run"
echo ""
echo "  3. Start the API + open dashboard:"
echo "     python api.py            ← terminal 1"
echo "     open dashboard/index.html ← in your browser"
echo ""
echo "  4. Run on schedule (every 4h):"
echo "     python main.py"
echo ""
