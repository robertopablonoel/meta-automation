#!/usr/bin/env python3
"""Consolidate pipeline output JSONs into a single unified file.

Thin wrapper around pipeline.run.run_consolidate() for standalone use.

Usage:
    python scripts/consolidate_output.py
"""
import sys
from pathlib import Path

# Add repo root to path so we can import the pipeline package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.run import run_consolidate

if __name__ == "__main__":
    run_consolidate()
