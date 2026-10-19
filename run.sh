#!/bin/bash
# Start the IPL Auction Arena server
cd "$(dirname "$0")"
exec ./venv/bin/python app.py
