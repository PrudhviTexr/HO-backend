"""
Server entry point for uvicorn
Imports the FastAPI app from app.main
"""
from app.main import app

__all__ = ['app']
