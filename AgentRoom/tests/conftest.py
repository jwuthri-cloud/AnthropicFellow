"""Shared pytest setup."""

import pytest
import structlog


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Undo any structlog configuration a test made, so loggers never outlive its stderr."""
    yield
    structlog.reset_defaults()
