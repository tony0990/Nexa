import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "unit", "member5"))
from m5_env import Env  # noqa: E402


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path / "nexa.db")
