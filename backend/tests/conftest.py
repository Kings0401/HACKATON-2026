import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.memory_repo import MemoryRepository  # noqa: E402

ROBOT_KEY = "test-robot-key-0123456789"
ADMIN_TOKEN = "test-admin-token"


@pytest.fixture
def faces(tmp_path):
    """Storage simulado con nombres reales del bucket (espacios y paréntesis)."""
    for persona, names in {
        "VIP001": ["foto1.png", "WhatsApp Image 2026-10-23 at 23.18.33.jpeg"],
        "INV001": ["WhatsApp Image 2026-10-24 at 00.23.06 (1).jpeg"],
    }.items():
        folder = tmp_path / persona
        folder.mkdir()
        for name in names:
            (folder / name).write_bytes(b"\x89PNG fake " + name.encode())
    return tmp_path


@pytest.fixture
def repo(faces):
    return MemoryRepository(faces_dir=faces, admin_token=ADMIN_TOKEN)


@pytest.fixture
def settings():
    s = Settings()
    s.mode = "memory"
    s.robot_api_key = ROBOT_KEY
    s.public_app_url = "http://app.test"
    s.public_api_url = "http://api.test"
    s.store_evidence = False
    return s


@pytest.fixture
def client(settings, repo):
    return TestClient(create_app(settings, repo))


@pytest.fixture
def robot():
    return {"X-Robot-Key": ROBOT_KEY}


@pytest.fixture
def admin():
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}
