"""Batch test runner for TradingAgents backend.

Discovers and runs all test modules in the tests/ directory using pytest.
Usage: python test.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest


def run_all_tests():
    """Discover and run all tests in the tests/ directory."""
    test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")
    args = [
        test_dir,
        "-v",
        "--tb=short",
        "--color=yes",
    ]
    return pytest.main(args)


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
