# BMAD Method — Plugins

Plugin distribution for the [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD),
covering every agent platform except Vercel/skills.sh, which installs
straight from [bmad-skills](https://github.com/bmad-code-org/bmad-skills).

This repository exists only for distribution. Development, issues, and pull
requests happen in
[bmad-code-org/BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD).

## The plugins

- **bmad-method** — the BMAD Method core: agents and workflows for product analysis, planning, architecture, and implementation.
- **bmad-toolbox** — generally useful standalone skills.

Both ecosystems below serve the same two skills trees
(`plugins/method/skills/`, `plugins/toolbox/skills/`) with their own metadata.

## Claude Code

This repository is a Claude Code plugin marketplace:

```
/plugin marketplace add bmad-code-org/bmad-plugins
```

Then install `bmad-method` and/or `bmad-toolbox` from it.

## OpenAI Codex

This repository is also a [Codex plugin marketplace](https://developers.openai.com/codex/plugins/build):

```
codex plugin marketplace add bmad-code-org/bmad-plugins
```

Then install the plugins you want.

## Release

`python3 release.py` rebuilds both plugins from the skills source repo
([bmad-code-org/bmad-skills](https://github.com/bmad-code-org/bmad-skills)):
it routes each skill by the `module` key in its `module-manifest.toml` and
stamps the (single, uniform) skill version into each plugin's Codex manifest
and its Claude marketplace entry. Review and commit the result.
