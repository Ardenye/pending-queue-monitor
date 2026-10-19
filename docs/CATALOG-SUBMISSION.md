# Catalog submission checklist

Target: add `plugin-catalog/pending-queue-monitor.yaml` to
[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent).
Rules: `website/docs/developer-guide/plugins/catalog-submission.md` and
`plugin-catalog/README.md` (entry schema).

## 1. Local readiness

- [x] `plugin.yaml` manifest (`name`, `version`, `description`, `author`, `license`,
      `requires_hermes`, `tags`, `provides_tools`, `provides_hooks`)
- [x] Entrypoints present: `__init__.py`, `desktop/plugin.js`, `dashboard/manifest.json`
- [x] `README.md` documents data scope, privacy boundary, supported platforms
- [x] `LICENSE` (MIT, matches `plugin.yaml`)
- [x] `.gitignore` excludes `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, venvs, `.env*`,
      `.DS_Store`
- [x] Tests: `python -m pytest -p no:cacheprovider -q tests` → 8 passed
- [x] `hermes plugins validate .` → Validation passed
- [x] `docs/screenshots/pending-monitor.png` rendered from sample data (no real profile
      names or counts)

## 2. Public repository

```bash
cd ~/.hermes/plugins/pending-queue-monitor
git init -b main
git add -A
git status --porcelain          # confirm no caches, no .env, no secrets
git commit -m "pending-queue-monitor 0.1.0: read-only pending approval monitor"
gh repo create Ardenye/pending-queue-monitor --public --source=. --remote=origin --push
```

Pre-flight before `git add`:

- [ ] no `__pycache__/`, `.pytest_cache/`, `*.pyc` staged
- [ ] no credential values anywhere (`grep -rIiE 'api[_-]?key|token|secret|password'` reviewed)
- [ ] `docs/screenshots/` contains only the sample-data render

## 3. Pin the commit

```bash
git rev-parse HEAD          # 40 lowercase hex — quote it in YAML
```

- [ ] replace both zero-sha placeholders in `docs/plugin-catalog-entry.yaml`
      (`sha:` and the `screenshots:` raw URL)
- [ ] re-run the validator, expect `OK: 1 file(s) valid`
- [ ] CI equivalence: `hermes plugins validate . --install-deps`

## 4. Open the PR

- [ ] fork `NousResearch/hermes-agent`
- [ ] add exactly one file: `plugin-catalog/pending-queue-monitor.yaml`
- [ ] PR description: what the plugin does, which Hermes surfaces it uses (Desktop plugin
      SDK pane + command-palette command), and the full disclosure required by rule 13 —
      reads `pending/memory/*.json` and `pending/skills/*.json` under `HERMES_HOME` and
      immediate named profile dirs; metadata only; no approve/reject/delete; no network I/O;
      no credentials; macOS verified, Linux unverified, Windows unsupported
- [ ] attach the panel screenshot to the PR
- [ ] wait for catalog CI to clone the pinned commit and pass

## Notes

- `tier: community` — this is a personal plugin, not a Nous-official one.
- `platforms: [macos]` is deliberate: the symlink/hardlink hardening depends on
  `O_NOFOLLOW`, absent on Windows, and Linux is untested.
- The entry's `sha` must point at the *published* commit, not a local working tree.
