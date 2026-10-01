"""plugin.json, marketplace.json, and the CLI package agree on one version
after PEP 440 normalization (KTD2: `2.0.0-dev` == `2.0.0.dev0`)."""

import json
import tomllib
from pathlib import Path

import solstice
from solstice.doctor import normalize_version

REPO_ROOT = Path(__file__).resolve().parents[2]


def _versions() -> dict[str, str]:
    plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    market = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entry = next(p for p in market["plugins"] if p["name"] == plugin["name"])
    project = tomllib.loads((REPO_ROOT / "cli" / "pyproject.toml").read_text())["project"]
    return {
        "plugin.json": plugin["version"],
        "marketplace.json": entry["version"],
        "cli/pyproject.toml": project["version"],
        "solstice.__version__": solstice.__version__,
    }


def test_versions_agree_after_normalization():
    versions = _versions()
    normalized = {k: normalize_version(v) for k, v in versions.items()}
    assert len(set(normalized.values())) == 1, versions


def test_plugin_and_marketplace_use_the_same_spelling():
    v = _versions()
    assert v["plugin.json"] == v["marketplace.json"]
