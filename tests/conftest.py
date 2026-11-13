import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Point every ingest module at an empty scratch data dir."""
    import ingest.common as common
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    return tmp_path
