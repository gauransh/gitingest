#!/bin/sh
exec python -m uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-9900}