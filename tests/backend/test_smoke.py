
"""Basic smoke tests."""
import pytest


def test_import_backend():
    from backend.app import main
    assert main.app is not None


def test_import_adapters():
    from backend.app.adapters import HailuoAdapter, SeedanceAdapter, LLMAdapter, TTSAdapter
    assert HailuoAdapter.name == "hailuo"
    assert SeedanceAdapter.name == "seedance"


def test_schemas():
    from backend.app.schemas import ProjectCreate, Manga2AnimeRequest
    p = ProjectCreate(name="test")
    assert p.name == "test"
    r = Manga2AnimeRequest(project_id="p", upload_id="u")
    assert r.video_backend == "hailuo"


def test_workflow_loader():
    from backend.app.comfy_client import list_workflows
    wfs = list_workflows()
    assert any("text2image.json" in w for w in wfs)


def test_pipeline_import():
    from backend.app.pipelines import Manga2AnimePipeline, render_episode
    assert Manga2AnimePipeline is not None
    assert render_episode is not None


def test_provider_schema():
    from backend.app.services import config_service
    assert "hailuo" in config_service.list_providers()
    assert "seedance" in config_service.list_providers()
    assert config_service.PROVIDER_SCHEMA["hailuo"]["api_key"]["secret"] is True


def test_crypto_roundtrip():
    from backend.app.utils.crypto import encrypt, decrypt, mask
    plain = "sk-abcdef1234567890"
    enc = encrypt(plain)
    assert enc != plain and enc != ""
    assert decrypt(enc) == plain
    assert mask(plain) == "*" * (len(plain) - 4) + "7890"


def test_adapter_requires_config(monkeypatch, tmp_path):
    """Hailuo adapter must refuse to construct without a configured api_key."""
    import os
    # Use isolated DB file so previous state does not interfere
    db_file = tmp_path / "t.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    # Clear cached settings so DATABASE_URL takes effect
    from backend.app.core import config as cfg_mod
    cfg_mod.get_settings.cache_clear()

    from backend.app.db import init_db
    init_db()

    from backend.app.adapters import HailuoAdapter
    from backend.app.core.exceptions import AdapterError
    with pytest.raises(AdapterError):
        HailuoAdapter()
