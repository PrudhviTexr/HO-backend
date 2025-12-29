"""
Passenger WSGI entry point for cPanel with enhanced error handling.

Place this file in your cPanel Python App's Application root and set:
  - Application startup file: passenger_wsgi.py
  - Application entry point: application

This wraps the FastAPI ASGI app into a WSGI callable for Passenger/Apache.
"""

import os
import sys
from pathlib import Path
import traceback

def log_error(message):
    """Log error to stderr and potentially to a file"""
    print(f"[WSGI] ERROR: {message}", file=sys.stderr)
    # Also try to write to a log file if possible
    try:
        log_path = Path("/home/uvzzwroing49/logs/passenger_debug.log")
        with open(log_path, 'a') as f:
            f.write(f"{message}\n")
    except:
        pass

try:
    from dotenv import load_dotenv
    log_error("python-dotenv available")
except ImportError:
    log_error("python-dotenv not available - this may cause issues")
    def load_dotenv(_path=None):
        pass

# Ensure the app package is importable
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
    log_error(f"Added {BASE_DIR} to Python path")

# Load environment variables
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)
    log_error(f"Loaded environment from {env_path}")
else:
    log_error(f"Environment file not found at {env_path}")

# Try to import the FastAPI app
try:
    from app.main import app as asgi_app
    log_error("Successfully imported FastAPI app")
    log_error(f"App root_path: {getattr(asgi_app, 'root_path', 'None')}")
except Exception as e:
    log_error(f"Failed to import FastAPI app: {e}")
    log_error(f"Traceback: {traceback.format_exc()}")

    # Create a minimal fallback app
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        asgi_app = FastAPI(title="Home & Own API - Error State")

        @asgi_app.get("/health")
        async def health():
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Application failed to start",
                    "details": str(e),
                    "python_path": sys.path[:3],
                    "working_dir": str(BASE_DIR),
                    "root_path": os.getenv("ROOT_PATH", "Not set")
                }
            )

        @asgi_app.get("/")
        async def root():
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Application failed to start",
                    "message": "Check server logs for details"
                }
            )
    except Exception as fallback_e:
        log_error(f"Fallback app creation failed: {fallback_e}")
        asgi_app = None

# Try to set up ASGI->WSGI bridge with multiple fallbacks
application = None

# Try a2wsgi first (most reliable)
try:
    from a2wsgi import ASGIMiddleware
    application = ASGIMiddleware(asgi_app)
    log_error("Using a2wsgi.ASGIMiddleware for ASGI->WSGI conversion")
except ImportError as e1:
    log_error(f"a2wsgi not available: {e1}")
    
    # Try asgi2wsgi as second option
    try:
        from asgi2wsgi import AsgiToWsgi
        application = AsgiToWsgi(asgi_app)
        log_error("Using asgi2wsgi.AsgiToWsgi for ASGI->WSGI conversion")
    except ImportError as e2:
        log_error(f"asgi2wsgi not available: {e2}")
        
        # Try mangum as third option (for AWS Lambda compatibility)
        try:
            from mangum import Mangum
            application = Mangum(asgi_app, lifespan="off")
            log_error("Using mangum.Mangum for ASGI->WSGI conversion")
        except ImportError as e3:
            log_error(f"mangum not available: {e3}")

            # Final fallback - create a comprehensive error response
            class ErrorApp:
                def __init__(self, error_message):
                    self.error_message = error_message

                def __call__(self, environ, start_response):
                    start_response('500 Internal Server Error', [
                        ('Content-Type', 'text/html; charset=utf-8'),
                        ('Cache-Control', 'no-cache')
                    ])
                    html_response = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Home & Own API - Configuration Error</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
                            .container {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                            .error {{ color: #d32f2f; background: #ffebee; padding: 15px; border-radius: 4px; margin: 20px 0; }}
                            pre {{ background: #f5f5f5; padding: 15px; border-radius: 4px; overflow-x: auto; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>Home & Own API - Configuration Error</h1>
                            <div class="error">
                                <strong>ASGI-to-WSGI Bridge Not Available</strong><br>
                                The required packages for running FastAPI on cPanel are missing.
                            </div>
                            <h3>Required Packages:</h3>
                            <ul>
                                <li><code>a2wsgi>=1.10.0</code> (recommended)</li>
                                <li><code>asgi2wsgi>=0.2.0</code> (alternative)</li>
                                <li><code>mangum>=0.17.0</code> (fallback)</li>
                            </ul>
                            <h3>Installation:</h3>
                            <pre>pip install a2wsgi asgi2wsgi mangum</pre>
                            <h3>Error Details:</h3>
                            <pre>{self.error_message}</pre>
                        </div>
                    </body>
                    </html>
                    """
                    return [html_response.encode('utf-8')]

            error_msg = (
                f"ASGI->WSGI bridge packages not available.\n"
                f"Import errors:\n"
                f"  - a2wsgi: {e1}\n"
                f"  - asgi2wsgi: {e2}\n"
                f"  - mangum: {e3}\n"
                f"Python path: {sys.path[:3]}\n"
                f"Working directory: {os.getcwd()}\n"
                f"Please install: pip install a2wsgi asgi2wsgi mangum"
            )
            application = ErrorApp(error_msg)
            log_error("Created comprehensive fallback error application")

if application:
    log_error("WSGI application successfully created")
else:
    log_error("Failed to create WSGI application")
    class ErrorApp:
        def __init__(self, error_message):
            self.error_message = error_message

        def __call__(self, environ, start_response):
            start_response('500 Internal Server Error', [('Content-Type','text/plain')])
            return [self.error_message.encode('utf-8')]

    application = ErrorApp("Critical error: Could not create WSGI application")
