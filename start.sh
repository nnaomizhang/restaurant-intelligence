#!/bin/bash
# Restaurant Intelligence Platform — Full System Startup
# Usage: ./start.sh

echo "🍽️  Starting Restaurant Intelligence Platform..."

# Start all containers
docker-compose up -d

echo "⏳ Waiting for databases to be ready..."
sleep 10

# Load data into Docker PostgreSQL and MongoDB
echo "📦 Loading data..."
export DATABASE_URL="postgresql://user:password@postgres:5432/restaurants"
export MONGO_URL="mongodb://mongodb:27017"

docker-compose exec api python -m processing.postgres_loader
docker-compose exec api python -m processing.mongo_loader
docker-compose exec api python -m collectors.tfl_enricher
docker-compose exec api python -m processing.hours_analyser
docker-compose exec api python -m processing.geo_analyser

echo "✅ System ready!"
echo "   Frontend: http://localhost:8501"
echo "   API docs: http://localhost:8000/docs"
echo "   API health: http://localhost:8000/api/health"
