"""
Render deployment entry point
Runs the FastAPI app with uvicorn for production deployment
"""
import os
import uvicorn
from app.main import app

if __name__ == "__main__":
    # Get port from environment variable (Render sets this)
    port = int(os.environ.get("PORT", 8000))
    
    # Run the FastAPI app with uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
