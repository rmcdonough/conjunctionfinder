"""Shared fixtures.

Every test that needs a chart uses explicit lat/lon so the suite is offline by
default — the only test that touches the network is explicitly marked
``network`` and skipped unless ``RUN_NETWORK_TESTS=1``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Allow `pytest` from inside backend/ without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.natal import compute_natal_chart  # noqa: E402
from app.schemas import BirthInfo  # noqa: E402

# Toronto, 15 March 1971, 04:30 local (EST). Used across the suite.
TORONTO_LAT = 43.6532
TORONTO_LON = -79.3832


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_NETWORK_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_NETWORK_TESTS=1 to run network tests")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def birth_info() -> BirthInfo:
    return BirthInfo(
        birth_date="1971-03-15",
        birth_time="04:30",
        latitude=TORONTO_LAT,
        longitude=TORONTO_LON,
        birth_place="Toronto, Canada",
        name="Test Subject",
    )


@pytest.fixture(scope="session")
def chart(birth_info: BirthInfo):
    return compute_natal_chart(birth_info)
