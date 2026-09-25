# Changelog

All notable changes to redline-buddy. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Changed
- Bundled playbooks moved into the installed package (`src/redline/playbooks/`)
  and resolved via `importlib.resources`, so `redline review --playbook <name>`
  works after a plain `pip install redline-buddy` — previously they only
  resolved from a source checkout, which would have broken the PyPI install
  (PR #19)

### Added
- PyPI packaging metadata: classifiers, keywords, author, project URLs
  (PR #19)
- `RELEASING.md`: release checklist + one-time PyPI token setup (PR #19)
- `consulting-msa` playbook: client (hiring-company) side review of consulting
  MSAs — 15 rules (work-product IP assignment, background-IP carve-out,
  liability cap, mutual indemnity, termination for convenience, rate-increase
  cap, warranty, acceptance, auto-renewal, mutual confidentiality, non-compete,
  transition assistance, governing law), each with quotable fallback language;
  sample + clean fixtures (PR #18)
- `redline review --format diff`: redline-style diff view — each finding as a
  unified-diff hunk with flagged contract language as `-` lines and quotable
  fallback clause language as `+` lines (PR #4)
- Optional `fallback:` field per playbook rule: concrete, quotable
  replacement/insertion clause language, distinct from advice-style
  `suggestion:`; quotable fallbacks for all rules in all six playbooks (PR #4)
- `offer-letter` playbook: candidate-side review (equity terms, non-compete,
  severance, base salary, arbitration, at-will) (PR #5)
- `client-sow` playbook: freelancer/agency-side SOW review (change-order
  process, payment terms, late-payment remedy, kill fee, liability cap,
  non-compete) (PR #7)
- `redline review --ocr`: opt-in Tesseract OCR for scanned/image-only PDF
  pages (requires `tesseract` + `pdftoppm` system binaries, no new Python
  dependencies) (PR #6)
- `redline review --fail-on <severity>`: exit 1 when any finding is at or
  above the given severity, for CI gates (PR #8)
- `redline validate <playbook.yaml>`: playbook linter for authors; with
  `--sample` it reports per-rule hit/miss coverage (PR #9, #11)
- `redline serve`: minimal local web UI (stdlib `http.server` only, binds
  127.0.0.1) — paste text, pick a playbook, get the memo or diff as HTML
  (PR #12)
- Clean-document fixtures (`examples/clean-*.md`) proving zero false
  positives on each playbook's intended document type (PR #10)

### Changed
- Finding excerpts snap to sentence boundaries instead of cutting mid-word
  (PR #13)

## 2026-09-23

### Added
- PDF ingestion via pypdf (page-by-page); scanned/image-only PDFs rejected
  with a clear error; blank pages inside readable PDFs flagged in the memo
  (PR #1)
- `contractor` playbook: hiring-company-side review (PR #1)
- `dpa` playbook: controller-side DPA review (PR #2)
- `redline review --format json`: machine-readable findings for CI gates
  (PR #3)
