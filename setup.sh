#!/bin/bash
# One-time setup: pull Ollama model after containers start
set -e

echo "[1] Starting all services..."
docker compose up -d

echo "[2] Waiting for Ollama to be ready..."
until curl -s http://localhost:11435/api/tags > /dev/null 2>&1; do
  echo "  waiting for Ollama..."
  sleep 5
done

echo "[3] Pulling mistral model (this takes ~5 min, ~4GB download)..."
docker compose exec ollama ollama pull mistral

echo ""
echo "Setup complete!"
echo "  API:      http://localhost:8002"
echo "  API docs: http://localhost:8002/docs"
echo "  Qdrant:   http://localhost:6333/dashboard"
echo ""
echo "Run tests: chmod +x test_pipeline.sh && ./test_pipeline.sh"
