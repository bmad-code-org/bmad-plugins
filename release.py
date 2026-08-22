#!/usr/bin/env python3
"""Rebuild the plugins from the skills source repo.

Clones the source repo's default branch, reads every skill's
module-manifest.toml, requires all skills to agree on one version, then
rewrites each plugin's skills tree (pointing each copied manifest's
update_source at the plugin, e.g. plugin:bmad-method) and stamps that
version into its
.codex-plugin/plugin.json and into its entry in the Claude marketplace
(.claude-plugin/marketplace.json — both ecosystems share the same skills
trees). Routing: a skill's `module` key names the plugin directory it
ships in, and each manifest must carry exactly the keys module, version,
update_source, and knowledge, the latter two with their one known value.
Review and commit the result with git.

Stdlib only. Usage: python3 release.py [--source URL]
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

DEFAULT_SOURCE = "https://github.com/bmad-code-org/bmad-skills"
REPO_ROOT = Path(__file__).resolve().parent
PLUGINS = ("method", "toolbox")  # module key in module-manifest.toml -> plugins/<name>, plugin bmad-<name>
UPDATE_SOURCE = "github:bmad-code-org/bmad-skills/skills"
KNOWLEDGE = "`references/help.md` in the `bmad` skill"
MANIFEST_KEYS = frozenset({"module", "version", "update_source", "knowledge"})
CLAUDE_MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")


def fail(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def read_manifest(skill_dir):
    manifest_path = skill_dir / "module-manifest.toml"
    if not manifest_path.is_file():
        fail(f"{skill_dir.name}: missing module-manifest.toml")
    with open(manifest_path, "rb") as f:
        try:
            manifest = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            fail(f"{manifest_path}: {e}")
    if set(manifest) != MANIFEST_KEYS:
        fail(
            f"{manifest_path}: keys must be exactly {', '.join(sorted(MANIFEST_KEYS))}; "
            f"found {', '.join(sorted(manifest)) or 'none'}"
        )
    if manifest["update_source"] != UPDATE_SOURCE:
        fail(f"{manifest_path}: update_source must be exactly {UPDATE_SOURCE!r}")
    if manifest["knowledge"] != KNOWLEDGE:
        fail(f"{manifest_path}: knowledge must be exactly {KNOWLEDGE!r}")
    return manifest


def collect_skills(skills_root):
    """Return ({module: [skill dirs]}, version) after validating the tree."""
    if not skills_root.is_dir():
        fail(f"source repo has no skills/ directory at {skills_root}")
    by_module = {name: [] for name in PLUGINS}
    versions = {}
    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        manifest = read_manifest(skill_dir)
        module = manifest["module"]
        if module not in by_module:
            fail(f"{skill_dir.name}: unknown module `{module}` (expected one of {', '.join(PLUGINS)})")
        by_module[module].append(skill_dir)
        versions[skill_dir.name] = manifest["version"]
    if not versions:
        fail("no skills found in source repo")
    if len(set(versions.values())) != 1:
        detail = ", ".join(f"{name}={v}" for name, v in sorted(versions.items()))
        fail(f"skills disagree on version: {detail}")
    return by_module, next(iter(versions.values()))


def rebuild_plugin(name, skill_dirs, version):
    plugin_root = REPO_ROOT / "plugins" / name
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    if not manifest_path.is_file():
        fail(f"missing plugin manifest {manifest_path}")

    skills_dest = plugin_root / "skills"
    if skills_dest.exists():
        shutil.rmtree(skills_dest)
    skills_dest.mkdir()
    for skill_dir in skill_dirs:
        shutil.copytree(skill_dir, skills_dest / skill_dir.name, ignore=COPY_IGNORE)
        # Shipped copies are updated by updating the plugin, not the files;
        # setup.py reads this and points users at their plugin marketplace.
        copied = skills_dest / skill_dir.name / "module-manifest.toml"
        text = copied.read_text()
        old = f'update_source = "{UPDATE_SOURCE}"'
        if text.count(old) != 1:
            fail(f"{copied}: expected exactly one update_source line")
        copied.write_text(text.replace(old, f'update_source = "plugin:bmad-{name}"'))
    if not skill_dirs:
        (skills_dest / ".gitkeep").touch()

    manifest = json.loads(manifest_path.read_text())
    manifest["version"] = version
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"plugins/{name}: {len(skill_dirs)} skills, version {version}")


def stamp_claude_marketplace(version):
    if not CLAUDE_MARKETPLACE.is_file():
        fail(f"missing {CLAUDE_MARKETPLACE}")
    data = json.loads(CLAUDE_MARKETPLACE.read_text())
    entries = {
        entry.get("name"): entry
        for entry in data.get("plugins", [])
        if isinstance(entry, dict)
    }
    expected = [f"bmad-{name}" for name in PLUGINS]
    if sorted(entries) != sorted(expected):
        fail(
            f"{CLAUDE_MARKETPLACE}: plugin entries must be exactly "
            f"{', '.join(expected)}; found {', '.join(sorted(entries))}"
        )
    for name in PLUGINS:
        entry = entries[f"bmad-{name}"]
        if entry.get("source") != f"./plugins/{name}":
            fail(
                f"{CLAUDE_MARKETPLACE}: bmad-{name} source must be ./plugins/{name} "
                "so Claude Code serves the same skills tree as Codex"
            )
        entry["version"] = version
    CLAUDE_MARKETPLACE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f".claude-plugin/marketplace.json: {len(expected)} entries, version {version}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="skills source repo URL (default: %(default)s)")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        clone = subprocess.run(
            ["git", "clone", "--quiet", "--depth", "1", args.source, tmp],
            capture_output=True,
            text=True,
        )
        if clone.returncode != 0:
            fail(f"git clone failed: {clone.stderr.strip()}")
        by_module, version = collect_skills(Path(tmp) / "skills")
        for name in PLUGINS:
            rebuild_plugin(name, by_module[name], version)
        stamp_claude_marketplace(version)


if __name__ == "__main__":
    main()
