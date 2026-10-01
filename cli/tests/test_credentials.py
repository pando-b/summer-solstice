"""One credentials helper reads keys, from the process environment only
(KTD17, R26). Every key value here is synthetic and assembled at runtime."""

import re
from pathlib import Path

import pytest
import yaml

from solstice import credentials
from solstice.adapters import REGISTRY
from solstice.init import template_dir

PKG = Path(credentials.__file__).resolve().parent

# Modules that touch the process environment for something other than keys,
# and why. A new module reading the environment fails this test until it is
# listed here, so key reads cannot slip in beside credentials.py.
ENV_READERS = {
    "credentials.py": "the only key reader (KTD17)",
    "workspace.py": "SOLSTICE_WORKSPACE and a scrubbed git environment",
    "init.py": "a scrubbed git environment",
    "leakscan.py": "a scrubbed git environment",
    "doctor.py": "the Probes snapshot and a scrubbed git environment; key presence goes "
                 "through credentials.missing",
    "approvals.py": "the Deps default env, read only for the SOLSTICE_SCHEDULED_RUN marker "
                    "(not a key)",
}
_ENV_ACCESS = re.compile(r"\bos\.environ\b|\bgetenv\b|\benviron\[|\benviron\.get\b")


def _fake(name: str) -> str:
    return "fake" + "-" + name.lower().replace("_", "-") + "-" + "0123456789abcdef"


def test_load_reads_only_the_given_environment():
    env = {"EXAMPLE_KEY": _fake("EXAMPLE_KEY")}
    assert credentials.load(["EXAMPLE_KEY"], env=env) == env


def test_missing_key_raises_naming_it_and_never_defaults():
    with pytest.raises(credentials.MissingKey) as exc:
        credentials.load(["EXAMPLE_KEY", "OTHER_KEY"], env={"EXAMPLE_KEY": _fake("x")})
    assert exc.value.names == ["OTHER_KEY"]
    assert str(exc.value) == "missing key OTHER_KEY"


def test_blank_value_counts_as_missing():
    assert credentials.missing(["EXAMPLE_KEY"], env={"EXAMPLE_KEY": "  "}) == ["EXAMPLE_KEY"]


def test_redact_replaces_loaded_values_and_url_secret_params():
    value = _fake("REDACT_ME")
    credentials.load(["REDACT_ME"], env={"REDACT_ME": value})
    text = (f"request failed for key {value} at "
            f"https://api.example.com/v1?query=x&token=abc123def456&api_key=zzz999&key=k1")
    out = credentials.redact(text)
    assert value not in out
    assert "abc123def456" not in out and "zzz999" not in out and "key=k1" not in out
    assert "query=x" in out and "[redacted]" in out


def test_no_module_other_than_credentials_reads_keys_from_the_environment():
    offenders = []
    for path in sorted(PKG.rglob("*.py")):
        rel = path.relative_to(PKG).as_posix()
        if rel in ENV_READERS:
            continue
        if _ENV_ACCESS.search(path.read_text()):
            offenders.append(rel)
    assert offenders == [], f"only credentials.py may read keys from the environment: {offenders}"


def test_adapters_and_demand_never_touch_the_environment():
    paths = [PKG / "demand.py", *sorted((PKG / "adapters").glob("*.py"))]
    for path in paths:
        assert not _ENV_ACCESS.search(path.read_text()), path.name


def test_doctor_checks_key_presence_through_credentials():
    src = (PKG / "doctor.py").read_text()
    assert "credentials.missing(" in src
    for adapter in REGISTRY.values():
        for key in adapter.keys:
            assert key not in src, f"doctor names {key}; key names belong to the manifest"


def test_secrets_manifest_lists_every_adapter_key_and_no_values():
    manifest = yaml.safe_load((template_dir() / "secrets-manifest.yaml").read_text())
    listed = {s["key"] for s in manifest["secrets"]}
    for adapter in REGISTRY.values():
        assert set(adapter.keys) <= listed, adapter.name
    assert "SCRAPECREATORS_API_KEY" in listed
    assert "APIFY_TOKEN" not in listed
    for s in manifest["secrets"]:
        assert set(s) == {"key", "adapter", "name", "used_for"}
    text = (template_dir() / "secrets-manifest.yaml").read_text().lower()
    assert "infisical" not in text
