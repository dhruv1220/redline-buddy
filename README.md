# redline-buddy

**Local-first contract red-flag checker.** Paste in a vendor MSA, get a plain-language risk memo — with zero data leaving your machine.

Existing contract AI tools send your documents to someone else's LLM. redline-buddy is the opposite: deterministic, auditable YAML playbooks, pure-Python heuristics, no API keys, no network calls. What you lose in nuance you gain in privacy and predictability — and every finding links back to the exact rule that fired.

> **Not legal advice.** Heuristic checks, not a lawyer's judgment. Treat the memo as a draft for attorney review.

## Quickstart

```bash
pip install -e .
redline review examples/sample-msa.md
# or with your own playbook:
redline review contract.md --playbook playbooks/saas-vendor.yaml
```

## How it works

1. A **playbook** (`playbooks/saas-vendor.yaml`) declares rules: severity, plain-language explanation, and checks (`requires_any`, `forbids_any`, `forbids_unless`, `max_value`).
2. The **review engine** runs every rule against the contract text and collects findings with excerpts.
3. Findings render as a **markdown memo**: severity-ranked, each with why-it-matters and suggested fallback language.

## Playbooks

| Playbook | Reviews from | Checks |
|---|---|---|
| `saas-vendor` | customer side | liability cap, mutual indemnification, auto-renewal, termination for convenience, confidentiality, notice period |
| `nda-recipient` | recipient side | hidden non-compete, survival > 5 years, missing standard exclusions, injunctive relief, return-or-destroy |

Write your own playbook in YAML — see `playbooks/saas-vendor.yaml` for the schema.

## Input formats

Markdown, plain text, and `.docx` (Word) files are accepted — `.docx` text is extracted locally with no network calls.

## Development

```bash
pip install -e ".[dev]" 2>/dev/null || pip install -e .
python -m pytest
```

## License

MIT — see [LICENSE](LICENSE).
