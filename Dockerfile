FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    postgresql-client \
    wget \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.ai/install.sh | sh

# Install Node.js for frontend build
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs

# Set working directory
WORKDIR /app

# Copy backend requirements
COPY backend/requirements-prod.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements-prod.txt

# Copy source code
COPY backend /app/backend
COPY src /app/src
COPY frontend /app/frontend
COPY package.json vite.config.js index.html /app/

# Build frontend
WORKDIR /app
RUN npm install --production && npm run build

# Expose ports
EXPOSE 8000 3000 11434

# Environment
ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=postgresql://propscore:propscore@db:5432/propscore
ENV OLLAMA_BASE_URL=http://localhost:11434

# Startup script
RUN cat > /app/start.sh << 'EOF'
#!/bin/bash
set -e

echo "Starting PropScore..."

# Start Ollama in background
echo "[1/3] Starting Ollama (LLM server)..."
ollama serve > /tmp/ollama.log 2>&1 &
sleep 5

# Wait for Ollama to be ready
echo "[2/3] Waiting for Ollama..."
while ! curl -s http://localhost:11434/api/tags > /dev/null; do
  sleep 1
done

# Initialize database
echo "[3/3] Initializing database..."
python3 -c "
from backend.database import Base, get_db_engine
engine = get_db_engine('$DATABASE_URL')
Base.metadata.create_all(bind=engine)
print('Database ready!')
"

# Start backend
echo "Starting PropScore Backend on port 8000..."
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend
echo "Starting Frontend on port 3000..."
cd /app && npx serve -s dist -l 3000 &
FRONTEND_PID=$!

echo ""
echo "================================"
echo "PropScore is running!"
echo "================================"
echo "Frontend:  http://localhost:3000"
echo "API:       http://localhost:8000"
echo "API Docs:  http://localhost:8000/docs"
echo "Ollama:    http://localhost:11434"
echo ""

# Keep container running
wait $BACKEND_PID $FRONTEND_PID
EOF

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
