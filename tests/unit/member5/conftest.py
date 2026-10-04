import pytest

from m5_env import Env, T0  # noqa: F401


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path / "nexa.db")
