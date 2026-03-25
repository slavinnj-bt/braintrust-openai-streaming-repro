#!/usr/bin/env bash
set -e

echo "Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "Installing dependencies..."
pip install "openai>=2.0.0" "httpx"
pip install --extra-index-url https://test.pypi.org/simple/ braintrust==0.10.0rc16

echo ""
echo "Setup complete. Activate the environment and set env vars:"
echo "  source .venv/bin/activate"
echo "  export OPENAI_API_KEY=sk-..."
echo "  export BRAINTRUST_API_KEY=..."
echo ""
echo "Then run:"
echo "  python repro_sync.py"
