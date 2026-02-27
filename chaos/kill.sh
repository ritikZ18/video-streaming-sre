#!/usr/bin/env sh
set -eu

echo "Simulating origin failure..."
docker compose stop origin
sleep 30
echo "Restarting origin..."
docker compose start origin

echo "Origin kill scenario complete."

