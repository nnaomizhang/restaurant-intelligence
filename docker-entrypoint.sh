#!/bin/bash
set -e

echo "🍽️  Restaurant Intelligence Platform starting..."

# Wait for PostgreSQL
until python -c "
from sqlalchemy import create_engine, text
import os
engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    conn.execute(text('SELECT 1'))
print('PostgreSQL ready')
" 2>/dev/null; do
    echo "⏳ Waiting for PostgreSQL..."
    sleep 3
done

# Wait for MongoDB
until python -c "
from pymongo import MongoClient
import os
client = MongoClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=2000)
client.server_info()
print('MongoDB ready')
" 2>/dev/null; do
    echo "⏳ Waiting for MongoDB..."
    sleep 3
done

# Check if data needs loading
python -c "
from sqlalchemy import create_engine, text
import os
engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    try:
        count = conn.execute(text('SELECT COUNT(*) FROM restaurants')).scalar()
        if count < 100:
            exit(1)
        print(f'Data already loaded: {count} restaurants')
        exit(0)
    except:
        exit(1)
" && echo "✅ Data already loaded" || {
    echo "📦 Loading data into databases..."
    python -m processing.postgres_loader
    python -m processing.mongo_loader
    python -m collectors.tfl_enricher
    python -m processing.hours_analyser
    python -m processing.geo_analyser
    echo "✅ Data loaded"
}

# Start the application
exec "$@"