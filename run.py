#!/usr/bin/env python3
"""
Uvicorn runner script for Fraud Detection API

This script starts the FastAPI application using uvicorn.

Usage:
    python run.py
    python run.py --host 0.0.0.0 --port 8002 --reload
"""

import sys
import os
from pathlib import Path

# Add the project root to the path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from apppp.core.config import Settings
from apppp.main import app


def main():
    """Start the uvicorn server."""
    settings = Settings()
    
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.api_log_level,
        workers=1,
    )


if __name__ == "__main__":
    main()