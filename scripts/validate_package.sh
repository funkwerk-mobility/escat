#!/bin/bash
set -e

echo "Building distribution packages..."
python -m build

echo "Checking wheel contents..."
check-wheel-contents dist/*.whl

echo "Running twine check..."
twine check dist/*

echo "All validation checks passed!"
