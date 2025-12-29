# Gunicorn configuration for Render deployment
bind = "0.0.0.0:8000"
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
timeout = 120
keepalive = 2
max_requests = 1000
max_requests_jitter = 100
preload_app = True
log_level = "info"
accesslog = "-"
errorlog = "-"
