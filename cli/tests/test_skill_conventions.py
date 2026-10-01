"""Conventions for the six v2 skills (KTD2, KTD12).

Each v2 SKILL.md must:
- be 8 KB or less,
- have a one-sentence frontmatter `description`,
- reference nothing outside its own skill directory,
- contain no v1 stage codes (S0-S20, M2 and the like),
- open with a CLI preflight: the first `##` section is titled "Preflight" and
  checks `solstice --version`, giving the `uv tool install` command.

The v1 skill directories are exempt until U14 removes them. The checker is
proven against synthetic skills in a temp dir, so it bites before any v2
skill exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
V2_SKILLS = ("factory", "find", "qualify", "build", "launch", "review")
MAX_BYTES = 8 * 1024

_STAGE_CODE = re.compile(r"\b(?:S(?:[0-9]|1[0-9]|20)|M[0-9])\b")
_LINK = re.compile(r"\]\(([^)\s]+)\)")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def check_skill(skill_dir: Path) -> list[str]:
    problems: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill_dir.name}: SKILL.md missing"]
    raw = skill_md.read_bytes()
    if len(raw) > MAX_BYTES:
        problems.append(f"SKILL.md is {len(raw)} bytes (max {MAX_BYTES})")
    text = raw.decode("utf-8")

    m = _FRONTMATTER.match(text)
    meta = (yaml.safe_load(m.group(1)) or {}) if m else {}
    desc = str(meta.get("description") or "").strip()
    if not desc:
        problems.append("frontmatter description missing")
    elif len(re.split(r"(?<=[.!?])\s+", desc)) > 1:
        problems.append("description is more than one sentence")
    body = text[m.end():] if m else text

    root = skill_dir.resolve()
    for md in sorted(skill_dir.rglob("*.md")):
        content = md.read_text()
        rel = md.relative_to(skill_dir)
        if "../" in content or "..\\" in content:
            problems.append(f"{rel}: references a path outside the skill directory")
        for target in _LINK.findall(content):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            dest = (md.parent / target.split("#")[0]).resolve()
            if target.startswith(("/", "~")) or not dest.is_relative_to(root) or not dest.exists():
                problems.append(f"{rel}: link {target!r} does not resolve inside the skill")
        codes = sorted(set(_STAGE_CODE.findall(content)))
        if codes:
            problems.append(f"{rel}: stage codes {codes}")

    sections = re.split(r"(?m)^## ", body)
    first = sections[1] if len(sections) > 1 else ""
    if not (first.lower().startswith("preflight") and "solstice --version" in first
            and "uv tool install" in first):
        problems.append("first section is not a CLI preflight "
                        "(## Preflight with `solstice --version` and `uv tool install`)")
    return problems


# --- synthetic fixtures ---------------------------------------------------

PREFLIGHT = (
    "## Preflight\n\n"
    "Run `solstice --version`. If it is missing or differs from the plugin version, stop and "
    "tell the user to run `uv tool install` with the plugin's release tag.\n\n"
)


def _skill(tmp_path: Path, *, desc="Find measured demand for an example niche.", body=None,
           refs: dict[str, str] | None = None) -> Path:
    d = tmp_path / "example-skill"
    d.mkdir()
    body = PREFLIGHT + "## Steps\n\nRead [the lens](references/lens.md).\n" if body is None else body
    (d / "SKILL.md").write_text(f"---\nname: example-skill\ndescription: {desc}\n---\n\n{body}")
    (d / "references").mkdir()
    (d / "references" / "lens.md").write_text("Synthetic lens.\n")
    for rel, content in (refs or {}).items():
        (d / rel).write_text(content)
    return d


def test_good_fixture_passes(tmp_path):
    assert check_skill(_skill(tmp_path)) == []


def test_oversized_skill_fails(tmp_path):
    body = PREFLIGHT + "## Steps\n\n" + ("Synthetic filler line.\n" * 400)
    assert any("bytes" in p for p in check_skill(_skill(tmp_path, body=body)))


def test_multi_sentence_description_fails(tmp_path):
    d = _skill(tmp_path, desc="Find demand. Then score it.")
    assert any("one sentence" in p for p in check_skill(d))


@pytest.mark.parametrize("body_extra", [
    "See [shared](../other-skill/SKILL.md).\n",
    "See [abs](/etc/example.md).\n",
    "Load `../../templates/example.md` first.\n",
    "See [missing](references/nope.md).\n",
])
def test_reference_outside_skill_fails(tmp_path, body_extra):
    d = _skill(tmp_path, body=PREFLIGHT + "## Steps\n\n" + body_extra)
    assert any("outside" in p or "resolve" in p for p in check_skill(d))


@pytest.mark.parametrize("code", ["S4", "M2", "S11", "S20"])
def test_stage_code_fails(tmp_path, code):
    d = _skill(tmp_path, body=PREFLIGHT + f"## Steps\n\nThis is the {code} step.\n")
    assert any("stage codes" in p for p in check_skill(d))


def test_stage_code_in_reference_fails(tmp_path):
    d = _skill(tmp_path, refs={"references/old.md": "Carried over from S6.\n"})
    assert any("stage codes" in p for p in check_skill(d))


def test_missing_preflight_fails(tmp_path):
    d = _skill(tmp_path, body="## Steps\n\nJust do it.\n")
    assert any("preflight" in p.lower() for p in check_skill(d))


def test_preflight_not_first_fails(tmp_path):
    d = _skill(tmp_path, body="## Steps\n\nGo.\n\n" + PREFLIGHT)
    assert any("preflight" in p.lower() for p in check_skill(d))


# --- the real repo --------------------------------------------------------

_present = [s for s in V2_SKILLS if (REPO_ROOT / "skills" / s).is_dir()]


@pytest.mark.parametrize("name", _present or [pytest.param(None, marks=pytest.mark.skip(
    reason="no v2 skill directories yet (U5+)"))])
def test_v2_skill_follows_conventions(name):
    assert check_skill(REPO_ROOT / "skills" / name) == []
