#!/usr/bin/env python3
"""Stash plugin wrapper for StashDB Tag Synchroniser.

This wrapper adds the src directory to Python path and invokes the plugin entry point.
Stash executes this file as specified in plugin.yml.
"""
import sys
from pathlib import Path

# Add src directory to path so we can import plugin modules
src_dir = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_dir))

from stashdbTagSync import main

if __name__ == '__main__':
    main()
