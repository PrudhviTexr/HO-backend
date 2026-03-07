"""
Run the API on your own server (e.g. after uploading via WinSCP).
Usage: python run_server.py
Uses PORT from environment, default 8000.
"""
import os
import uvicorn
from app.main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
