#!/bin/bash
pip install -r integrations/requirements.txt
cd integrations && uvicorn server:app --host 0.0.0.0 --port 8080
