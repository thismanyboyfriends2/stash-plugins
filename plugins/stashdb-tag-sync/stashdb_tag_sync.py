#!/usr/bin/env python3
"""Stash plugin wrapper for StashDB Tag Synchroniser.

This wrapper adds the src directory to Python path and invokes the plugin entry point.
Stash executes this file as specified in plugin.yml.
"""
import sys
import json
from pathlib import Path
import os

try:
    # Diagnostic: Log startup environment
    startup_info = {
        "level": "debug",
        "message": f"Plugin wrapper starting - CWD: {os.getcwd()}, Python: {sys.executable}, Args: {sys.argv}"
    }
    print(json.dumps(startup_info), flush=True)

    # Add src directory to path so we can import plugin modules
    plugin_dir = Path(__file__).parent
    src_dir = plugin_dir / 'src'

    if src_dir.exists():
        sys.path.insert(0, str(src_dir))
    else:
        raise FileNotFoundError(f"src directory not found at {src_dir}")

    # Diagnostic: Log stdin availability
    stdin_info = {
        "level": "debug",
        "message": f"stdin isatty: {sys.stdin.isatty()}, stdin readable: {not sys.stdin.isatty()}"
    }
    print(json.dumps(stdin_info), flush=True)

    # Import and run the plugin
    from stashdbTagSync import main

    if __name__ == '__main__':
        main()

except Exception as e:
    import traceback
    tb = traceback.format_exc()
    error_msg = json.dumps({"level": "error", "message": f"Plugin wrapper error: {str(e)}\n{tb}"})
    print(error_msg, flush=True)
    sys.exit(1)
