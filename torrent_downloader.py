#!/usr/bin/env python3
"""
Complete Torrent Downloader for GitHub Codespaces
Optimized for workspace environment
"""

import os
import sys
import time
import base64
import subprocess
import threading
import queue
import shutil
import requests
import json
import socket
import re
from typing import List, Optional, Dict, Any

class CodespaceTorrentDownloader:
    def __init__(self):
        # Codespaces-specific paths
        self.WORKSPACE_DIR = "/workspace"
        self.DOWNLOAD_DIR = "/workspace/downloads"
        self.TORRENT_DIR = "/workspace/torrents"
        self.OUTPUT_DIR = "/workspace/completed"
        
        # aria2 RPC configuration
        self.ARIA2_PORT = 6800
        self.aria2_url = f"http://localhost:{self.ARIA2_PORT}/jsonrpc"
        self.aria2_proc = None
        
        # Threading
        self.print_lock = threading.Lock()
        self.task_queue = queue.Queue()
        
        self.setup_environment()

    def setup_environment(self):
        """Setup directories and check environment"""
        print("🚀 Setting up GitHub Codespaces environment...")
        
        # Create directories
        for directory in [self.DOWNLOAD_DIR, self.TORRENT_DIR, self.OUTPUT_DIR]:
            os.makedirs(directory, exist_ok=True)
            print(f"✅ Created: {directory}")
        
        # Check available tools
        self.check_dependencies()
        
        print(f"📁 Workspace: {self.WORKSPACE_DIR}")
        print(f"💾 Download dir: {self.DOWNLOAD_DIR}")
        print(f"📊 Output dir: {self.OUTPUT_DIR}")

    def check_dependencies(self):
        """Check and install dependencies"""
        print("🔍 Checking dependencies...")
        
        tools = ["aria2c", "ffmpeg", "curl"]
        for tool in tools:
            try:
                subprocess.run([tool, "--version"], capture_output=True, check=True)
                print(f"  ✅ {tool}")
            except:
                print(f"  ❌ {tool} not available")

    def get_optimized_trackers(self) -> List[str]:
        """Get trackers that work in cloud environments"""
        return [
            # Most reliable for cloud VPS
            "udp://tracker.opentrackr.org:1337",
            "udp://open.stealth.si:80", 
            "udp://tracker.torrent.eu.org:451",
            "https://tracker.foreverpirates.co:443/announce",
            "http://tracker.openbittorrent.com:80/announce",
            # WebSocket trackers (often work better)
            "wss://tracker.btorrent.xyz",
            "wss://tracker.openwebtorrent.com",
        ]

    def start_aria2_rpc(self):
        """Start aria2 RPC server optimized for Codespaces"""
        print("🔄 Starting aria2 RPC server...")
        
        # Kill any existing processes
        subprocess.run(["pkill", "-f", "aria2c"], capture_output=True)
        time.sleep(2)
        
        cmd = [
            "aria2c",
            "--enable-rpc",
            f"--rpc-listen-port={self.ARIA2_PORT}",
            "--rpc-listen-all=true",  # Important for Codespaces
            "--rpc-allow-origin-all=true",
            "--dir", self.DOWNLOAD_DIR,
            "--continue=true",
            "--max-concurrent-downloads=3",
            "--max-connection-per-server=16",
            "--split=16",
            "--min-split-size=1M",
            "--seed-ratio=0.0",
            "--max-upload-limit=1K",
            "--bt-tracker-connect-timeout=10",
            "--bt-tracker-timeout=10",
            "--follow-torrent=mem",
            "--bt-save-metadata=true",
            "--enable-dht=true",
            "--enable-peer-exchange=true",
            "--dht-entry-point=dht.libtorrent.org:25401",
            "--quiet"  # Less verbose in Codespaces
        ]
        
        try:
            self.aria2_proc = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for RPC to be ready
            for i in range(30):
                try:
                    response = requests.post(
                        self.aria2_url,
                        json={"jsonrpc": "2.0", "method": "aria2.getVersion", "id": "test"},
                        timeout=2
                    )
                    if response.status_code == 200:
                        print("✅ aria2 RPC server ready!")
                        return True
                except:
                    time.sleep(1)
            
            print("❌ aria2 RPC failed to start")
            return False
            
        except Exception as e:
            print(f"❌ Failed to start aria2: {e}")
            return False

    def aria2_call(self, method: str, params: List = None, retries: int = 3) -> Optional[Dict]:
        """Make RPC call with retries"""
        if params is None:
            params = []
            
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": "codespace",
            "params": params
        }
        
        for attempt in range(retries):
            try:
                response = requests.post(self.aria2_url, json=payload, timeout=15)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                if attempt == retries - 1:
                    print(f"❌ RPC call failed: {e}")
                    return None
                time.sleep(1)
        
        return None

    def add_magnet_link(self, magnet_uri: str) -> Optional[str]:
        """Add magnet link to download"""
        trackers = self.get_optimized_trackers()
        
        options = {
            "dir": self.DOWNLOAD_DIR,
            "bt-tracker": ",".join(trackers),
            "bt-tracker-connect-timeout": 10,
            "bt-tracker-timeout": 10,
            "max-upload-limit": "1K",
            "seed-ratio": 0.0,
            "follow-torrent": "mem",
            "enable-dht": True,
            "enable-peer-exchange": True
        }
        
        try:
            result = self.aria2_call("aria2.addUri", [[magnet_uri], options])
            return result.get("result") if result else None
        except Exception as e:
            print(f"❌ Failed to add magnet: {e}")
            return None

    def add_torrent_file(self, torrent_path: str, selected_files: List[int] = None) -> Optional[str]:
        """Add torrent file with optional file selection"""
        try:
            with open(torrent_path, "rb") as f:
                torrent_data = base64.b64encode(f.read()).decode()
            
            options = {
                "dir": self.DOWNLOAD_DIR,
                "pause": "true" if selected_files else "false"
            }
            
            result = self.aria2_call("aria2.addTorrent", [torrent_data, [], options])
            gid = result.get("result") if result else None
            
            if gid and selected_files:
                self.apply_file_selection(gid, selected_files)
                
            return gid
            
        except Exception as e:
            print(f"❌ Failed to add torrent: {e}")
            return None

    def apply_file_selection(self, gid: str, selected_files: List[int]):
        """Apply file selection to torrent"""
        print("📁 Applying file selection...")
        
        # Wait for metadata
        files = self.get_torrent_files(gid)
        if not files:
            print("⚠️ Could not get file list, downloading all")
            self.aria2_call("aria2.unpause", [gid])
            return
        
        # Select files
        for i in range(len(files)):
            select = (i in selected_files)
            self.aria2_call("aria2.selectFile", [gid, i, select])
        
        print(f"✅ Selected {len(selected_files)} files")
        self.aria2_call("aria2.unpause", [gid])

    def get_torrent_files(self, gid: str, timeout: int = 15) -> List[Dict]:
        """Get torrent file list"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            result = self.aria2_call("aria2.tellStatus", [gid, ["files"]])
            if result and "result" in result:
                files = result["result"].get("files", [])
                if files:
                    return files
            time.sleep(1)
        return []

    def monitor_download(self, gid: str, name: str, timeout: int = 600) -> List[str]:
        """Monitor download progress"""
        print(f"⏳ Monitoring: {name}")
        
        start_time = time.time()
        last_update = start_time
        
        while time.time() - start_time < timeout:
            result = self.aria2_call("aria2.tellStatus", [
                gid, ["status", "completedLength", "totalLength", "downloadSpeed", "files"]
            ])
            
            if not result or "result" not in result:
                time.sleep(2)
                continue
                
            status = result["result"]
            state = status.get("status", "")
            completed = int(status.get("completedLength", 0))
            total = int(status.get("totalLength", 0))
            speed = int(status.get("downloadSpeed", 0))
            
            # Progress updates every 5 seconds
            if time.time() - last_update >= 5 and total > 0:
                percent = (completed / total * 100) if total > 0 else 0
                eta = (total - completed) // max(speed, 1) if speed > 0 else 0
                print(f"\r📥 {name[:40]:40s} {percent:5.1f}% | {self.human_bytes(speed)}/s | ETA: {eta}s", end="")
                last_update = time.time()
            
            # Check completion
            if state == "complete":
                files = status.get("files", [])
                downloaded = []
                for f in files:
                    path = f.get("path")
                    if path and os.path.exists(path):
                        downloaded.append(path)
                print(f"\n✅ Download completed: {name}")
                return downloaded
            
            # Check errors
            if state in ("error", "removed"):
                print(f"\n❌ Download failed: {name}")
                return []
            
            time.sleep(2)
        
        print(f"\n⏰ Timeout: {name}")
        return []

    def extract_subtitles(self, video_path: str) -> List[str]:
        """Extract French subtitles"""
        if not os.path.exists(video_path):
            return []
            
        print(f"🎬 Extracting subtitles: {os.path.basename(video_path)}")
        
        extracted = []
        base_name = os.path.splitext(video_path)[0]
        languages = ["fre", "fra", "fr", "french"]
        
        for lang in languages:
            output_file = f"{base_name}.{lang}.srt"
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-map", f"0:s:m:language:{lang}",
                output_file
            ]
            
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=30, text=True)
                if result.returncode == 0 and os.path.exists(output_file) and os.path.getsize(output_file) > 100:
                    extracted.append(output_file)
                    print(f"  ✅ Extracted {lang} subtitles")
                    break
            except:
                continue
        
        # Fallback: any subtitle
        if not extracted:
            output_file = f"{base_name}.srt"
            cmd = ["ffmpeg", "-y", "-i", video_path, "-map", "0:s:0", output_file]
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=30, text=True)
                if result.returncode == 0 and os.path.exists(output_file):
                    extracted.append(output_file)
                    print("  ℹ️ Extracted first available subtitle")
            except:
                print("  ⚠️ No subtitles found")
        
        return extracted

    def human_bytes(self, size: int) -> str:
        """Convert bytes to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f}{unit}"
            size /= 1024.0
        return f"{size:.2f}TB"

    def process_downloaded_files(self, files: List[str], name: str):
        """Process downloaded files"""
        print(f"🔄 Processing {len(files)} files for {name}")
        
        for file_path in files:
            if not os.path.exists(file_path):
                continue
                
            file_size = os.path.getsize(file_path)
            print(f"📦 Processing: {os.path.basename(file_path)} ({self.human_bytes(file_size)})")
            
            # Extract subtitles for video files
            if file_path.lower().endswith(('.mkv', '.mp4', '.avi', '.mov')):
                subtitles = self.extract_subtitles(file_path)
                # Move subtitles to output
                for sub in subtitles:
                    if os.path.exists(sub):
                        shutil.move(sub, self.OUTPUT_DIR)
            
            # Move main file to output
            shutil.move(file_path, self.OUTPUT_DIR)
            
        print(f"✅ Completed processing: {name}")

    def download_item(self, item: str, selected_files: List[int] = None) -> bool:
        """Download a single item"""
        name = os.path.basename(item) if os.path.isfile(item) else item
        if len(name) > 50:
            name = name[:50]
        
        print(f"\n🎯 Starting download: {name}")
        
        try:
            if os.path.isfile(item) and item.lower().endswith('.torrent'):
                gid = self.add_torrent_file(item, selected_files)
            elif item.startswith('magnet:'):
                gid = self.add_magnet_link(item)
            else:
                print(f"❌ Unsupported item: {item}")
                return False
            
            if not gid:
                return False
                
            downloaded_files = self.monitor_download(gid, name, 600)  # 10 minute timeout
            if downloaded_files:
                self.process_downloaded_files(downloaded_files, name)
                return True
            else:
                return False
                
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False

    def get_torrent_selection(self, torrent_path: str) -> List[int]:
        """Interactive file selection for torrents"""
        try:
            gid = self.add_torrent_file(torrent_path, [])
            if not gid:
                return []
                
            files = self.get_torrent_files(gid)
            if not files:
                return []
            
            print(f"\n📁 Files in torrent:")
            for i, file_info in enumerate(files):
                size = int(file_info.get("length", 0))
                path = file_info.get("path", f"file_{i}")
                print(f"[{i}] {path} ({self.human_bytes(size)})")
            
            selection = input("\nEnter file numbers (comma-separated) or 'all': ").strip()
            
            if selection.lower() == 'all':
                selected = list(range(len(files)))
            else:
                try:
                    selected = [int(x.strip()) for x in selection.split(",")]
                except:
                    print("⚠️ Invalid selection, downloading all")
                    selected = list(range(len(files)))
            
            # Remove the temporary torrent
            self.aria2_call("aria2.remove", [gid])
            return selected
            
        except Exception as e:
            print(f"⚠️ Selection error: {e}")
            return []

    def upload_torrent_file(self):
        """Upload torrent file in Codespaces"""
        print("\n📤 Upload torrent file:")
        print("1. Drag and drop .torrent file into the file explorer")
        print("2. It will appear in the workspace directory")
        print("3. Enter the filename when prompted")
        
        filename = input("Enter torrent filename: ").strip()
        if not filename:
            return None
            
        torrent_path = os.path.join(self.WORKSPACE_DIR, filename)
        if os.path.exists(torrent_path):
            return torrent_path
        else:
            print(f"❌ File not found: {filename}")
            return None

    def main(self):
        """Main application"""
        print("=" * 60)
        print("🚀 GitHub Codespaces Torrent Downloader")
        print("=" * 60)
        
        # Start aria2
        if not self.start_aria2_rpc():
            print("❌ Cannot continue without aria2")
            return
        
        while True:
            print("\n📥 Options:")
            print("1. Enter magnet link")
            print("2. Upload torrent file") 
            print("3. List downloaded files")
            print("4. Exit")
            
            choice = input("\nSelect option (1-4): ").strip()
            
            if choice == "1":
                magnet = input("Enter magnet link: ").strip()
                if magnet:
                    self.download_item(magnet)
                    
            elif choice == "2":
                torrent_path = self.upload_torrent_file()
                if torrent_path:
                    selected = self.get_torrent_selection(torrent_path)
                    self.download_item(torrent_path, selected)
                    
            elif choice == "3":
                self.list_downloaded_files()
                
            elif choice == "4":
                break
                
            else:
                print("❌ Invalid choice")
        
        self.cleanup()

    def list_downloaded_files(self):
        """List downloaded files"""
        print(f"\n📂 Downloaded files in {self.OUTPUT_DIR}:")
        try:
            files = os.listdir(self.OUTPUT_DIR)
            if files:
                for file in sorted(files):
                    path = os.path.join(self.OUTPUT_DIR, file)
                    size = os.path.getsize(path)
                    print(f"  📄 {file} ({self.human_bytes(size)})")
            else:
                print("  No files downloaded yet")
        except Exception as e:
            print(f"  Error listing files: {e}")

    def cleanup(self):
        """Cleanup resources"""
        print("\n🧹 Cleaning up...")
        if self.aria2_proc:
            self.aria2_proc.terminate()
        subprocess.run(["pkill", "-f", "aria2c"], capture_output=True)
        print("✅ Cleanup complete")

if __name__ == "__main__":
    downloader = CodespaceTorrentDownloader()
    downloader.main()
