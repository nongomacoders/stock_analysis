#!/bin/bash
# Run tests for the gui package
cd "$(dirname "$0")" || exit 1
cd ..
python -m unittest discover gui/test -v
