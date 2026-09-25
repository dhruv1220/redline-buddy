# redline-buddy

**Local-first contract red-flag checker.** Paste in a vendor MSA, get a plain-language risk memo — with zero data leaving your machine.

Existing contract AI tools send your documents to someone else's LLM. redline-buddy is the opposite: deterministic, auditable YAML playbooks, pure-Python heuristics, no API keys, no network calls. What you lose in nuance you gain in privacy and predictability — and every finding links back to the exact rule that fired.

> **Not legal advice.** Heuristic checks, not a lawyer's judgment. Treat the memo as a draft for attorney review.

## Quickstart

```bash
pip install -e .
redline review examples/sample-msa.md
# or with your own playbook:
redline review contract.pdf --playbook saas-vendor
# batch review: point at a directory of contracts, get a summary table + per-file memos
redline review ./contracts/ --playbook lease-tenant
# machine-readable output for CI gates:
redline review contract.pdf --format json | jq '.finding_count'
# fail CI when a high-or-worse finding appears:
redline review contract.pdf --fail-on high || echo "contract gate failed"
# minimal local web UI (paste text, pick a playbook, get the memo):
redline serve
# the web UI now shows playbook descriptions in the picker, one-click
# "Copy fallback" buttons per finding, and severity filters on memos
# validate a playbook you wrote, optionally against a sample contract:
redline validate my-playbook.yaml --sample examples/sample-msa.md
# redline diff view: their language vs. your fallback, per finding:
redline review contract.pdf --format diff
```

## How it works

1. A **playbook** (`src/redline/playbooks/saas-vendor.yaml`) declares rules: severity, plain-language explanation, and checks (`requires_any`, `forbids_any`, `forbids_unless`, `max_value`).
2. The **review engine** runs every rule against the contract text and collects findings with excerpts.
3. Findings render three ways: a **markdown memo** (default), **JSON** (`--format json`) for CI gates, or a **redline diff** (`--format diff`) — each finding as a unified-diff hunk with the flagged contract language as `-` lines and quotable fallback clause language as `+` lines, ready to paste into your counter-draft.

Every rule carries a `fallback:` field: concrete, quotable clause language — not just advice — so the diff view gives you something you can actually propose back.

## Playbooks

| Playbook | Reviews from | Checks |
|---|---|---|
| `saas-vendor` | customer side | liability cap, mutual indemnification, auto-renewal, termination for convenience, confidentiality, notice period |
| `nda-recipient` | recipient side | hidden non-compete, survival > 5 years, missing standard exclusions, injunctive relief, return-or-destroy |
| `contractor` | hiring-company side | IP assignment, hidden non-compete, payment terms, termination at will, confidentiality, expense pre-approval |
| `dpa` | customer / controller side | subprocessor objection, return-or-delete, breach-notification timeline, security measures, audit rights, cross-border transfers |
| `offer-letter` | candidate side | equity terms, non-compete, severance, stated base salary, arbitration, at-will |
| `client-sow` | freelancer / agency side | change-order process, payment terms, late-payment remedy, kill fee, liability cap, non-compete |
| `consulting-msa` | client (hiring-company) side | work-product IP assignment, background-IP carve-out, liability cap, mutual indemnity, termination for convenience, rate-increase cap, warranty, acceptance, auto-renewal, transition assistance |
| `lease-tenant` | tenant side | deposit cap, rent-escalation cap, repair obligations, early termination, personal guarantee, entry notice, subletting, attorneys' fees, auto-renewal, utilities, wear and tear |
| `consulting-vendor` | vendor (consultant/agency) side | IP assignment scope, liability cap, mutual indemnity, payment terms, late-payment remedy, kill fee, non-compete, one-sided non-solicitation, change-order process, client cooperation, insurance terms |
| `loan-borrower` | borrower side | confession of judgment, prepayment penalty / yield maintenance, variable-rate cap, personal guarantee, blanket lien, default cure period, vague late fee, arbitration, lender assignment, rate disclosure, governing law |

Write your own playbook in YAML — see `src/redline/playbooks/saas-vendor.yaml` for the schema.

## Input formats

Markdown, plain text, `.docx` (Word), and **PDF** files are accepted — all text is extracted locally with no network calls.

Scanned/image-only PDFs are rejected with a clear error instead of silently reviewing nothing. Pass `--ocr` to run those pages through Tesseract OCR instead — it needs the `tesseract` and `pdftoppm` system binaries (e.g. `apt install tesseract-ocr poppler-utils`), still fully local, no extra Python packages. If a readable PDF contains pages with no extractable text, the memo notes which pages were skipped.

## Development

```bash
pip install -e ".[dev]" 2>/dev/null || pip install -e .
python -m pytest
```

## License

MIT — see [LICENSE](LICENSE).
