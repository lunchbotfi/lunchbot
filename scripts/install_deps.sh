#!/usr/bin/env bash
# install_deps.sh — install Python dependencies for LunchBot
set -e
pip install --quiet requests beautifulsoup4 lxml
echo "✅ LunchBot dependencies installed."
