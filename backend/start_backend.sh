#!/bin/bash
cd "$(dirname "$0")"
echo "[$(date)] Starting backend..." > /tmp/backend.log
./venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info >> /tmp/backend.log 2>&1
echo "[$(date)] Backend exited with code $?" >> /tmp/backend.log
