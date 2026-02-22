#!/usr/bin/env bash
# SageMaker passes "serve" as the command argument.
# Accept it (or no args) and start the uvicorn server.
exec uvicorn app.server:app --host 0.0.0.0 --port 8080 --workers 1
