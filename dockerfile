FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite (if used)
RUN mkdir -p /app/data

# Set environment variables
ENV PORT=10000
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/app/data

# Expose port
EXPOSE 10000

# Initialize database on startup (if needed)
# The app will auto-create tables, but we can also run setup explicitly
# RUN python setup_database.py || true

# Use socketio_asgi for WebSocket support
# The app automatically wraps with Socket.IO if available
# Note: socketio_asgi is exported from src.api.main module
CMD ["python", "-m", "uvicorn", "src.api.main:socketio_asgi", "--host", "0.0.0.0", "--port", "10000"]
