# BMAD Method — Codex Plugins

This repository is the [OpenAI Codex](https://developers.openai.com/codex/plugins/build) plugin marketplace for the [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD).

It exists only for distribution. Development, issues, and pull requests happen in
[bmad-code-org/BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD).

## Install

```
codex plugin marketplace add bmad-code-org/codex-plugins
```

Then install the plugins you want:

- **bmad-bmm** — the BMAD Method core: agents and workflows for product analysis, planning, architecture, and implementation.
- **bmad-tools** — generally useful standalone skills.

## Release

`python3 release.py` rebuilds both plugins from the skills source repo
([bmad-code-org/bmad-skills](https://github.com/bmad-code-org/bmad-skills)):
it routes each skill by the `module` key in its `module-manifest.toml` and
stamps the (single, uniform) skill version into each plugin manifest.
Review and commit the result.
