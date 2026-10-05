# Releasing redline-buddy to PyPI

Releases publish from GitHub Actions via PyPI Trusted Publishing (OIDC) — no
API tokens, no pasting tokens in chat. Pushing a `v*` tag runs
`.github/workflows/pypi-publish.yml`, which tests, builds, checks the
distributions with `twine check`, and publishes to PyPI.

The package is publish-ready: `python -m build` produces an sdist + wheel and
`twine check` passes. Bundled playbooks ship inside the wheel via
`importlib.resources` (`redline.playbook.bundled_playbook_path`), so
`redline review contract.md --playbook consulting-msa` works after a plain
`pip install redline-buddy` — verified from both the wheel and the sdist in
clean virtualenvs.

## One-time setup (needs Dhruv, ~4 minutes)

1. Add the release workflow: in the GitHub web UI, go to redline-buddy →
   Add file → Create new file, set the path to
   `.github/workflows/pypi-publish.yml`, and paste in the contents of
   `docs/pypi-publish.yml` (kept in sync with the workflow). The filename must
   match exactly — PyPI's trusted-publisher config references it.
2. Register the trusted publisher on PyPI: go to
   https://pypi.org/manage/project/redline-buddy/settings/publishing/ →
   "Add a new trusted publisher" with Owner `dhruv1220`, Repository
   `redline-buddy`, Workflow name `pypi-publish.yml`, and an empty
   Environment name.
3. Once the first OIDC publish succeeds, retire any PyPI API tokens for the
   project (Account settings → API tokens) — they are redundant.

Note: the workflow fails with an OIDC error until step 2 is done — expected,
not a bug.

## Cutting a release

```bash
# 1. Bump the version in pyproject.toml and add a CHANGELOG entry under a
#    dated heading (Keep a Changelog format, matching existing entries).
# 2. Commit, tag, and push — the workflow does the rest:
git tag v0.2.0 && git push origin v0.2.0
# 3. Watch the "Publish to PyPI" workflow run on the tag; no token needed.
```

## Pre-publish sanity checklist

- `python -m pytest -q` — all green.
- `pip install dist/redline_buddy-<ver>-py3-none-any.whl` in a fresh venv,
  then `redline review examples/sample-msa.md --playbook saas-vendor`
  resolves the bundled playbook (no repo checkout on `sys.path`).
- `twine check dist/*` passes (long description renders on PyPI).
- CHANGELOG has a dated entry; README quickstart matches the CLI.
