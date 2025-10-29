#!/usr/bin/env python3
import sys

"""Test script to simulate exact Lambda import."""

print("Testing exact Lambda import path...")

try:
    print("Importing app.lambda_handler.lambda_handler...")
    from app.lambda_handler import lambda_handler

    print("   ✓ lambda_handler import successful")
    print(f"   Handler type: {type(lambda_handler)}")
except Exception as e:
    print(f"   ✗ lambda_handler import failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print("Lambda import test successful!")
