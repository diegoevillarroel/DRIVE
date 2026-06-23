#!/usr/bin/env python3
"""
DRIVE — AI SSD Guardian
Main entry point. Starts the Flask web server.
Usage:
    python drive.py [--port 8765] [--host 127.0.0.1] [--no-browser]
"""
from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
import threading
import time
from pathlib import Path

# Ensure project root is on path
_file = Path(__file__).resolve()
sys.path.insert(0, str(_file.parent))

from app import create_app
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("drive")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="DRIVE",
        description="DRIVE — AI SSD Guardian. Protect your SSD from AI agent wear.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Open http://localhost:8765 in your browser after starting.",
    )
    parser.add_argument(
        "--port", type=int, default=8765,
        help="Port to listen on (default: 8765)"
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open browser automatically"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Flask debug mode"
    )
    parser.add_argument(
        "--data-dir",
        type=str, default=None,
        help="Custom data directory for DRIVE state"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Initialize configuration
    config = Config(data_dir=args.data_dir)

    # Create Flask app
    app = create_app(config)

    # ─── Banner ──────────────────────────────────────────────────────
    banner = """
  ========================================
  ::  D R I V E  ::  A I   S S D   G U A R D I A N
  ========================================

  Server:  http://{host}:{port}
  Data:    {data}
"""
    try:
        print(banner.format(host=args.host, port=args.port, data=config.data_dir))
    except UnicodeEncodeError:
        print(banner.encode("ascii", "replace").decode().format(host=args.host, port=args.port, data=config.data_dir))

    if config.smartmontools_path:
        print(f"  smartctl: {config.smartmontools_path}")
    else:
        print("  smartctl: not found (install smartmontools for full SSD health)")

    print()

    # Open browser
    if not args.no_browser:
        def open_browser():
            time.sleep(1.2)
            try:
                webbrowser.open(f"http://localhost:{args.port}")
            except Exception:
                pass
        threading.Thread(target=open_browser, daemon=True).start()

    # Run server
    try:
        app.run(
            host=args.host,
            port=args.port,
            debug=args.debug,
            threaded=True,
            use_reloader=False,
        )
    except KeyboardInterrupt:
        log.info("Shutting down...")
        print("\n  DRIVE stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()