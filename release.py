#!/usr/bin/env python3
"""Rebuild the plugins from the skills source repos.

Clones every source repo's default branch, reads each skill's
module-manifest.toml, then rewrites each plugin's skills tree (pointing each
copied manifest's update_source at the plugin, e.g. plugin:bmad-method) and
stamps that module's version into its .codex-plugin/plugin.json and into its
entry in the Claude marketplace (.claude-plugin/marketplace.json -- both
ecosystems share the same skills trees).

Routing: SOURCES maps each source repo to the modules it ships, and a skill's
`module` key names the plugin directory it ships in, so a module comes
entirely from the one source that declares it. Each manifest must carry
exactly the keys module, version, update_source, and knowledge --
update_source naming its own source repo, and version and knowledge each
identical across every skill in its module, whatever they say.

A version belongs to a module, not to a release of this repo: what a plugin
ships as is its own module's version, and two modules need not agree, whether
or not they share a source repo. Nothing here models dependencies between
modules -- no plugin ecosystem declares them, so a skill referencing another
module's skill is left to resolve at runtime.

Review and commit the result with git.

Stdlib only. Usage: python3 release.py [--source SLUG=URL ...]
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
# Source repo -> the modules it ships. A module name is both the plugin
# directory (plugins/<module>) and the plugin itself (bmad-<module>).
SOURCES = {
    "bmad-code-org/BMAD-METHOD": ("method", "toolbox"),
}
PLUGINS = tuple(module for modules in SOURCES.values() for module in modules)
MANIFEST_KEYS = frozenset({"module", "version", "update_source", "knowledge"})
CLAUDE_MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")


def fail(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def clone_url(slug):
    return f"https://github.com/{slug}"


def update_source(slug):
    return f"github:{slug}/skills"


def read_manifest(skill_dir, slug):
    manifest_path = skill_dir / "module-manifest.toml"
    if not manifest_path.is_file():
        fail(f"{slug}/{skill_dir.name}: missing module-manifest.toml")
    with open(manifest_path, "rb") as f:
        try:
            manifest = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            fail(f"{slug}/{skill_dir.name}: {e}")
    if set(manifest) != MANIFEST_KEYS:
        fail(
            f"{slug}/{skill_dir.name}: keys must be exactly {', '.join(sorted(MANIFEST_KEYS))}; "
            f"found {', '.join(sorted(manifest)) or 'none'}"
        )
    if manifest["update_source"] != update_source(slug):
        fail(f"{slug}/{skill_dir.name}: update_source must be exactly {update_source(slug)!r}")
    if not isinstance(manifest["knowledge"], str) or not manifest["knowledge"].strip():
        fail(f"{slug}/{skill_dir.name}: knowledge must be a non-empty string")
    return manifest


def collect_skills(skills_root, slug, modules):
    """Return {module: (skill dirs, version)} for one source, after validating it."""
    if not skills_root.is_dir():
        fail(f"{slug} has no skills/ directory")
    found = {module: [] for module in modules}
    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        manifest = read_manifest(skill_dir, slug)
        module = manifest["module"]
        if module not in found:
            fail(
                f"{slug}/{skill_dir.name}: unknown module `{module}` "
                f"({slug} ships {', '.join(modules)})"
            )
        found[module].append((skill_dir, manifest))

    collected = {}
    for module, entries in found.items():
        if not entries:
            fail(f"{slug} ships no skills for module `{module}`")
        # A module speaks for itself, so these values are whatever it says --
        # but every skill in one module must say the same thing. Modules need
        # not agree with each other, even within one source repo.
        for key in ("version", "knowledge"):
            values = {skill_dir.name: manifest[key] for skill_dir, manifest in entries}
            if len(set(values.values())) > 1:
                detail = ", ".join(f"{name}={value!r}" for name, value in sorted(values.items()))
                fail(f"module `{module}` skills disagree on {key}: {detail}")
        collected[module] = ([skill_dir for skill_dir, _ in entries], entries[0][1]["version"])
    return collected


def rebuild_plugin(module, skill_dirs, version, slug):
    plugin_root = REPO_ROOT / "plugins" / module
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
        old = f'update_source = "{update_source(slug)}"'
        if text.count(old) != 1:
            fail(f"{copied}: expected exactly one update_source line")
        copied.write_text(text.replace(old, f'update_source = "plugin:bmad-{module}"'))

    manifest = json.loads(manifest_path.read_text())
    manifest["version"] = version
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"plugins/{module}: {len(skill_dirs)} skills from {slug}, version {version}")


def stamp_claude_marketplace(versions):
    if not CLAUDE_MARKETPLACE.is_file():
        fail(f"missing {CLAUDE_MARKETPLACE}")
    data = json.loads(CLAUDE_MARKETPLACE.read_text())
    entries = {
        entry.get("name"): entry
        for entry in data.get("plugins", [])
        if isinstance(entry, dict)
    }
    expected = [f"bmad-{module}" for module in PLUGINS]
    if sorted(entries) != sorted(expected):
        fail(
            f"{CLAUDE_MARKETPLACE}: plugin entries must be exactly "
            f"{', '.join(expected)}; found {', '.join(sorted(entries))}"
        )
    for module in PLUGINS:
        entry = entries[f"bmad-{module}"]
        if entry.get("source") != f"./plugins/{module}":
            fail(
                f"{CLAUDE_MARKETPLACE}: bmad-{module} source must be ./plugins/{module} "
                "so Claude Code serves the same skills tree as Codex"
            )
        entry["version"] = versions[module]
    CLAUDE_MARKETPLACE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    stamped = ", ".join(f"bmad-{module} {versions[module]}" for module in PLUGINS)
    print(f".claude-plugin/marketplace.json: {stamped}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="SLUG=URL",
        help="clone SLUG from URL instead of GitHub (repeatable); manifests are still "
        "validated against SLUG, so this rehearses a release without weakening any check",
    )
    args = parser.parse_args()

    overrides = {}
    for item in args.source:
        slug, sep, url = item.partition("=")
        if not sep or slug not in SOURCES:
            fail(f"--source wants SLUG=URL with SLUG one of {', '.join(SOURCES)}; got {item!r}")
        overrides[slug] = url

    modules = {}
    with tempfile.TemporaryDirectory() as tmp:
        for slug, names in SOURCES.items():
            url = overrides.get(slug, clone_url(slug))
            dest = Path(tmp) / slug.replace("/", "_")
            clone = subprocess.run(
                ["git", "clone", "--quiet", "--depth", "1", url, str(dest)],
                capture_output=True,
                text=True,
            )
            if clone.returncode != 0:
                fail(f"git clone {url} failed: {clone.stderr.strip()}")
            for module, (skill_dirs, version) in collect_skills(dest / "skills", slug, names).items():
                modules[module] = (skill_dirs, version, slug)
        for module in PLUGINS:
            skill_dirs, version, slug = modules[module]
            rebuild_plugin(module, skill_dirs, version, slug)
        stamp_claude_marketplace({module: modules[module][1] for module in PLUGINS})


if __name__ == "__main__":
    main()
