#!/usr/bin/env python3
import sys

"""Test script to isolate import issues."""

print("Testing imports step by step...")

try:
    print("1. Testing basic imports...")

    print("   ✓ Basic imports OK")
except Exception as e:
    print(f"   ✗ Basic imports failed: {e}")
    sys.exit(1)

try:
    print("2. Testing mangum import...")

    print("   ✓ Mangum import OK")
except Exception as e:
    print(f"   ✗ Mangum import failed: {e}")
    sys.exit(1)

try:
    print("3. Testing core.logging import...")

    print("   ✓ Core logging import OK")
except Exception as e:
    print(f"   ✗ Core logging import failed: {e}")
    sys.exit(1)

try:
    print("4. Testing lambda_handler create_handler function...")
    from app.lambda_handler import create_handler

    print("   ✓ create_handler import OK")
except Exception as e:
    print(f"   ✗ create_handler import failed: {e}")
    sys.exit(1)

try:
    print("5. Testing main app import...")

    print("   ✓ Main app import OK")
except Exception as e:
    print(f"   ✗ Main app import failed: {e}")
    sys.exit(1)

try:
    print("6. Testing handler creation...")
    handler = create_handler()
    print("   ✓ Handler creation OK")
except Exception as e:
    print(f"   ✗ Handler creation failed: {e}")
    sys.exit(1)

print("All imports successful!")
