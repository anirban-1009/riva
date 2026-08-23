#!/bin/bash

# run_daily.sh - Daily automation for Job Hunt Mindmapper
# This script performs the standard daily workflow:
# 1. Scrape new job postings
# 2. Score jobs against the resume
# 3. Analyze skills gaps
# 4. Generate email digest

set -e # Exit on error

# Ensure we are in the project root
cd "$(dirname "$0")/.."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

echo "--- [$(date)] Starting Daily Job Hunt Update ---"

# 1. Scrape new jobs (headless mode)
# Adjust keywords in config.yaml for variety
echo "[1/4] Scraping LinkedIn for new jobs..."
uv run mindmap scrape --headless --limit 50

# 2. Score new jobs
echo "[2/4] Scoring jobs against resume..."
uv run mindmap score --all

# 3. Analyze gaps
echo "[3/4] Running gap analysis..."
uv run mindmap analyze-gaps

# 4. Send notifications
echo "[4/4] Sending notifications..."
uv run mindmap notify --min-score 70

echo "--- Daily Update Complete ---"
