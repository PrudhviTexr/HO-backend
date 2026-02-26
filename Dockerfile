# Pin Python 3.11 to avoid supabase-auth Pydantic errors on Python 3.14
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Render sets PORT at runtime
EXPOSE 8000
CMD ["python", "run_render.py"]
