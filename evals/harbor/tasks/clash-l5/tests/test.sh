#!/bin/bash
# Scores the shared checkout with the same checker used by the local harness.
mkdir -p /logs/verifier
python3 -B /tests/score.py L5
