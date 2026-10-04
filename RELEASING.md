# Releasing redline-buddy to PyPI

The package is publish-ready: `python -m build` produces an sdist + wheel and
`twine check` passes. Bundled playbooks ship inside the wheel via
`importlib.resources` (`redline.playbook.bundled_playbook_path`), so
`redline review contract.md --playbook consulting-msa` works after a plain
`pip install redline-buddy` — verified from both the wheel and the sdist in
clean virtualenvs.

## One-time setup (needs Dhruv)

1. Create an account at https://pypi.org and enable 2FA.
2. Generate an API token (Account settings → API tokens). For the very first
   upload the project won't appear in the scope dropdown (it doesn't exist yet),
   so scope the first token to "Entire account"; once the first release is live,
   mint project-scoped tokens for `redline-buddy` and retire the broad one.
3. The token is supplied transiently at release time (pasted in chat) and used
   once via `TWINE_USERNAME=__token__` / `TWINE_PASSWORD` env vars. It is never
   written to `~/.pypirc`, files, or memory — do not persist it anywhere.

## Cutting a release

```bash
cd ~/workspace/projects/redline-buddy
# 1. Bump the version in pyproject.toml and add a CHANGELOG entry under a
#    dated heading (Keep a Changelog format, matching existing entries).
# 2. Full check:
python -m pytest -q && python -m build && python -m twine check dist/*
# 3. Upload:
python -m twine upload dist/*
# 4. Tag and push the release commit:
#    (via the gh.py API flow used for this repo, or git)
```

## Pre-publish sanity checklist

- `python -m pytest -q` — all green.
- `pip install dist/redline_buddy-<ver>-py3-none-any.whl` in a fresh venv,
  then `redline review examples/sample-msa.md --playbook saas-vendor`
  resolves the bundled playbook (no repo checkout on `sys.path`).
- `twine check dist/*` passes (long description renders on PyPI).
- CHANGELOG has a dated entry; README quickstart matches the CLI.
