#!/bin/bash
# Verify front-end formatting without modifying files.
# Exits non-zero if any file is not formatted — suitable for CI / pre-commit.
# Run from the repo root (Git Bash on Windows).
set -e

echo "Checking front-end formatting with Prettier..."
npm run format:check
echo "All front-end files are properly formatted."
