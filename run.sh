#!/usr/bin/env bash
set -euo pipefail

# Simple dev runner for the Flask app.
# Usage:
#   ./run.sh

export FLASK_ENV=development
python app.py


