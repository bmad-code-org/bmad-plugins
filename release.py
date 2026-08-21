#!/usr/bin/env python3
"""Rebuild the Codex plugins from the skills source repo.

Clones the source repo's default branch, reads every skill's
module-manifest.toml, requires all skills to agree on one version, then
rewrites each plugin's skills tree and stamps that version into its
.codex-plugin/plugin.json. Routing: a skill's `module` key names the
plugin directory it ships in. Review and commit the result with git.

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
PLUGINS = ("bmm", "tools")  # module key in module-manifest.toml -> plugins/<name>
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
    for key in ("module", "version"):
        if key not in manifest:
            fail(f"{manifest_path}: missing `{key}`")
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
    if not skill_dirs:
        (skills_dest / ".gitkeep").touch()

    manifest = json.loads(manifest_path.read_text())
    manifest["version"] = version
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"plugins/{name}: {len(skill_dirs)} skills, version {version}")


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


if __name__ == "__main__":
    main()
