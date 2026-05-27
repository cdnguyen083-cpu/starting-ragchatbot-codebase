#!/bin/bash
# Auto-format all front-end files (HTML / CSS / JS) with Prettier.
# Run from the repo root (Git Bash on Windows).
set -e

echo "Formatting front-end files with Prettier..."
npm run format
echo "Done. Front-end files reformatted."
