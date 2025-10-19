#!/bin/bash

echo "🚀 Setting up Torrent Downloader environment..."

# Update package list
sudo apt-get update

# Install essential tools
echo "📦 Installing system packages..."
sudo apt-get install -y \
    aria2 \
    ffmpeg \
    curl \
    wget \
    python3-pip \
    transmission-cli \
    transmission-daemon

# Install Python packages
echo "🐍 Installing Python packages..."
pip3 install requests google-api-python-client google-auth-httplib2 google-auth-oauthlib

# Create necessary directories
mkdir -p /workspace/downloads
mkdir -p /workspace/torrents  
mkdir -p /workspace/completed

echo "✅ Setup complete! All dependencies installed."
echo "📁 Created directories:"
echo "   - /workspace/downloads (active downloads)"
echo "   - /workspace/torrents (torrent files)"
echo "   - /workspace/completed (finished downloads)"
