#!/bin/bash
# Starts everything fresh and runs the live demo.
set -e
cd "$(dirname "$0")"

echo "Cleaning up any previous run..."
docker compose down --remove-orphans >/dev/null 2>&1 || true

echo "Starting Bob, Alice and Bob's Tractus-X Digital Twin Registry..."
docker compose up -d

echo "Waiting for everything to be ready (can take 1-2 minutes)..."
.venv/bin/python demo.py

echo
echo "Demo finished. Everything is still running."
echo "To stop it:        docker compose down"
echo "To run it again:   bash run-demo.sh"
