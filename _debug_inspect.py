#!/usr/bin/env python3
"""Inspect ClobClient setup and find deposit-related endpoints."""
import inspect, json, os
from py_clob_client_v2.client import ClobClient
from py_clob_client_v2 import ClobClient as ClobClientDirect

# Look at __init__
try:
    src = inspect.getsource(ClobClient.__init__)
    print(src)
except Exception as e:
    print(f"__init__ source not available: {e}")

# Check all endpoints
print("\n=== POST endpoints ===")
for attr_name in dir(ClobClient):
    attr = getattr(ClobClient, attr_name)
    if callable(attr) and not attr_name.startswith("_"):
        try:
            src = inspect.getsource(attr)
            if "_post(" in src or "POST" in src.upper():
                print(f"{attr_name}")
        except:
            pass
