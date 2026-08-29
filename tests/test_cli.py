"""The `python -m boddos` entrypoint's first-run behavior: a genuinely fresh
checkout has no config/boddos.yaml (it's gitignored), and the CLI should
bootstrap one from the example rather than hard-failing."""
from pathlib import Path

from boddos.__main__ import _bootstrap_config


def test_bootstrap_creates_config_from_example(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    example = config_dir / "boddos.example.yaml"
    example.write_text("node:\n  id: test\n")
    target = config_dir / "boddos.yaml"

    assert not target.exists()
    ok = _bootstrap_config(str(target))
    assert ok is True
    assert target.exists()
    assert target.read_text() == example.read_text()


def test_bootstrap_leaves_existing_config_untouched(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "boddos.example.yaml").write_text("node:\n  id: example\n")
    target = config_dir / "boddos.yaml"
    target.write_text("node:\n  id: my-real-config\n")

    ok = _bootstrap_config(str(target))
    assert ok is True
    assert target.read_text() == "node:\n  id: my-real-config\n"


def test_bootstrap_fails_cleanly_with_no_example(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    target = config_dir / "boddos.yaml"

    ok = _bootstrap_config(str(target))
    assert ok is False
    assert not target.exists()


def test_bootstrap_creates_parent_directories(tmp_path):
    # boddos.example.yaml sitting next to a --config path whose parent
    # directory doesn't exist yet (e.g. a custom --config path).
    config_dir = tmp_path / "nested" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "boddos.example.yaml").write_text("node:\n  id: x\n")
    target = tmp_path / "nested" / "config" / "boddos.yaml"

    ok = _bootstrap_config(str(target))
    assert ok is True
    assert target.exists()
