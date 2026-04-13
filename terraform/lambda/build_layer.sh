#!/bin/bash
# Rebuilds the Lambda layer from layer_requirements.txt
# Run this once before `terraform apply` on any new machine.
# Requires: Python 3.11, pip

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAYER_DIR="$SCRIPT_DIR/layer_src/python"

echo "Installing layer packages into $LAYER_DIR ..."
rm -rf "$LAYER_DIR"
mkdir -p "$LAYER_DIR"

pip install \
  --platform manylinux2014_x86_64 \
  --target "$LAYER_DIR" \
  --implementation cp \
  --python-version 3.11 \
  --only-binary=:all: \
  -r "$SCRIPT_DIR/layer_requirements.txt"

echo "Done. Layer ready at $LAYER_DIR"
