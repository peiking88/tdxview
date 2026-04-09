"""
Shared pytest fixtures for tdxview test suite.
"""

import sys
import os
import tempfile
from pathlib import Path

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that is cleaned up after each test."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def project_root():
    """Return the project root path."""
    return PROJECT_ROOT
