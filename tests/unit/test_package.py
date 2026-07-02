"""Unit tests for package metadata exposure."""

import ai_data_harness


def test_package_exposes_version() -> None:
    """Verify package exposes version."""
    assert isinstance(ai_data_harness.__version__, str)
    assert ai_data_harness.__version__
