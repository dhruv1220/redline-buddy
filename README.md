# redline-buddy

**Local-first contract red-flag checker.** Paste in a vendor MSA, get a plain-language risk memo — with zero data leaving your machine.

Existing contract AI tools send your documents to someone else's LLM. redline-buddy is the opposite: deterministic, auditable YAML playbooks, pure-Python heuristics, no API keys, no network calls. What you lose in nuance you gain in privacy and predictability — and every finding links back to the exact rule that fired.

> **Not legal advice.** Heuristic checks, not a lawyer's judgment. Treat the memo as a draft for attorney review.

## Quickstart

```bash
pip install -e .
redline review examples/sample-msa.md
# no --playbook? redline auto-detects the best bundled playbook (clear winner
# only — ambiguous docs fall back to saas-vendor and say so on stderr)
# or with your own playbook:
redline review contract.pdf --playbook saas-vendor
# see the playbook ranking without reviewing:
redline suggest contract.pdf
# list all bundled playbooks:
redline playbooks
# batch review: point at a directory of contracts, get a summary table + per-file memos
# (omit --playbook and each file is auto-detected independently)
redline review ./contracts/
redline review ./contracts/ --playbook lease-tenant
# machine-readable output for CI gates:
redline review contract.pdf --format json | jq '.finding_count'
# fail CI when a high-or-worse finding appears:
redline review contract.pdf --fail-on high || echo "contract gate failed"
# fail CI when the risk grade drops below B:
redline review contract.pdf --fail-below B || echo "risk gate failed"
# minimal local web UI (paste text, pick a playbook, get the memo):
redline serve
# the web UI now shows playbook descriptions in the picker, one-click
# "Copy fallback" buttons per finding, severity filters on memos, and a
# "Download Word redline" link after every review
# validate a playbook you wrote, optionally against a sample contract:
redline validate my-playbook.yaml --sample examples/sample-msa.md
# redline diff view: their language vs. your fallback, per finding:
redline review contract.pdf --format diff
# compare two negotiation rounds — what changed, what risk changed:
redline compare round1.pdf round2.pdf --playbook saas-vendor
# fail CI when the new draft introduces new high-or-worse red flags:
redline compare round1.pdf round2.pdf --fail-on-gain high
# Word redline with tracked changes — a counter-draft you can send back:
redline review contract.pdf --format docx   # writes contract.redline.docx
```

## Comparing negotiation rounds

Contracts move in rounds: the other side sends "draft v2" and you need to know
what they quietly edited. `redline compare` diffs the two drafts at the
paragraph level and re-runs the playbook on both, reporting:

- **🚨 New red flags** — findings present in the new draft but not the old one
  (with the offending language, why it matters, and quotable fallback text),
- **✅ Resolved** — findings the new draft fixed (their concessions),
- **🔁 Reworded but still flagged** — a rule still fires, but on rewritten
  language (they redrafted the clause; it's still risky),
- **📝 Text changes** — every paragraph added, removed, or reworded, as
  `+`/`-` diff hunks.

Use `--format json` for machine-readable output and `--fail-on-gain high`
as a CI gate: fail the pipeline when a new round introduces new red flags at
or above a severity. Add `--format html` for a shareable comparison page
you can send to your attorney, or `--format docx` for a Word redline of the
new draft — gained and reworded flags as tracked changes, concessions won,
and paragraph-level text changes, ready to send back as your counter to
their round. Try it on the bundled example:

```bash
redline compare examples/compare-round1.md examples/compare-round2.md
```

## How it works

1. A **playbook** (`src/redline/playbooks/saas-vendor.yaml`) declares rules: severity, plain-language explanation, and checks (`requires_any`, `forbids_any`, `forbids_unless`, `max_value`).
2. The **review engine** runs every rule against the contract text and collects findings with excerpts.
3. Findings render five ways: a **markdown memo** (default), **JSON** (`--format json`) for CI gates, a **redline diff** (`--format diff`) — each finding as a unified-diff hunk with the flagged contract language as `-` lines and quotable fallback clause language as `+` lines, ready to paste into your counter-draft — a **Word redline** (`--format docx`), the full contract as a `.docx` with each finding's flagged language struck through and the fallback inserted as real tracked changes (open Review → All Markup to accept/reject each edit, then send it back), or a **self-contained HTML memo** (`--format html`), a single file with inline CSS (no JS, no network) you can email to your attorney or save as a PDF from the browser.

Every rule carries a `fallback:` field: concrete, quotable clause language — not just advice — so the diff view gives you something you can actually propose back.

### Optional LLM second reader

The deterministic engine is the default: offline, no API keys, nothing leaves
your machine. Regex rules can still miss paraphrased clauses or get fooled by
negations, so `review` accepts an opt-in second pass:

```bash
pip install "redline-buddy[llm]"   # adds litellm (optional dependency)
export OPENAI_API_KEY=...          # or ANTHROPIC_API_KEY, etc. — your key, your provider

redline review contract.md --playbook saas-vendor --second-reader gpt-4o-mini
```

The model re-reads the contract against the same playbook. Rule hits it
independently flags are marked **✓ confirmed by second reader**; genuinely new
observations are appended as **🤖 second-reader observations** (anything
referencing an unknown rule, lacking a verbatim quote, or carrying a bogus
severity is dropped — a hallucinating model must not invent findings).

⚠️ `--second-reader` sends your contract text to the model provider. Redact
or skip it for documents you can't share. Single-file review only; batch mode
ignores the flag with a warning. Output is still a first-pass draft for human
attorney review — never legal advice.

## Risk score

Every memo opens with a headline: **Risk score: 63/100 · Grade C** — a
deterministic 0–100 score (critical findings cost 30 points, high 15,
medium 7, low 3) mapped to ToS;DR-style letter grades (A ≥ 90, B ≥ 75,
C ≥ 60, D ≥ 40, else F). It also appears in JSON output (`risk_score`,
`risk_grade`), in the batch summary table, in the web UI banner, and —
most usefully — in `redline compare`, which reports the risk delta between
negotiation rounds (`Risk: C (63) → B (78) — improved`).

## Playbooks

| Playbook | Reviews from | Checks |
|---|---|---|
| `saas-vendor` | customer side | liability cap, mutual indemnification, auto-renewal, termination for convenience, confidentiality, notice period, AI training on customer data, data return/deletion on exit, uptime SLA/service credits, unilateral terms changes |
| `saas-provider` | provider side | liability cap, customer termination for convenience, uncapped SLA credits, customer IP ownership claims, late-payment remedy, price uplift rights, overbroad indemnity, customer audit rights |
| `nda-recipient` | recipient side | hidden non-compete, survival > 5 years, missing standard exclusions, injunctive relief, return-or-destroy |
| `contractor` | hiring-company side | IP assignment, hidden non-compete, payment terms, termination at will, confidentiality, expense pre-approval |
| `dpa` | customer / controller side | subprocessor objection, return-or-delete, breach-notification timeline, security measures, audit rights, cross-border transfers |
| `offer-letter` | candidate side | equity terms, non-compete, severance, stated base salary, arbitration, at-will |
| `client-sow` | freelancer / agency side | change-order process, payment terms, late-payment remedy, kill fee, liability cap, non-compete |
| `consulting-msa` | client (hiring-company) side | work-product IP assignment, background-IP carve-out, liability cap, mutual indemnity, termination for convenience, rate-increase cap, warranty, acceptance, auto-renewal, transition assistance |
| `lease-tenant` | tenant side | deposit cap, rent-escalation cap, repair obligations, early termination, personal guarantee, entry notice, subletting, attorneys' fees, auto-renewal, utilities, wear and tear |
| `consulting-vendor` | vendor (consultant/agency) side | IP assignment scope, liability cap, mutual indemnity, payment terms, late-payment remedy, kill fee, non-compete, one-sided non-solicitation, change-order process, client cooperation, insurance terms |
| `loan-borrower` | borrower side | confession of judgment, prepayment penalty / yield maintenance, variable-rate cap, personal guarantee, blanket lien, default cure period, vague late fee, arbitration, lender assignment, rate disclosure, governing law |
| `commercial-landlord` | landlord side | CAM cap / exclusions, base year, audit right, personal / good-guy guarantee, holdover premium, assignment consent, exclusivity, casualty termination, relocation limits, environmental indemnity, ADA allocation, subrogation waiver |
| `commercial-tenant` | tenant side | personal guarantee, uncapped CAM pass-throughs, landlord relocation / redevelopment termination, assignment consent standard, renewal option, competitor exclusivity, structural repair burden, excessive security deposit |
| `employment-agreement` | employee side | post-employment non-compete, invention-assignment scope (§2870 carve-out), non-solicitation, perpetual confidentiality, mandatory arbitration, severance, signing-bonus clawback, equity acceleration, garden leave, moonlighting ban, termination notice period, prior-inventions exhibit |
| `employment-employer` | employer side | missing invention assignment, missing confidentiality, missing at-will statement, included non-compete, overtime waiver, severance without release, missing arbitration, missing non-solicitation |
| `nda-discloser` | discloser side | marked-only definition, residual-knowledge carve-out, license grant, unbounded affiliate sharing, return-or-destroy, one-year survival, injunctive relief, defined purpose, fixed term, compelled-disclosure notice, no-obligation clause |
| `advisor-agreement` | advisor side | vesting schedule, stated compensation, background-IP carve-out, termination right, non-compete, confidentiality, expense reimbursement, term length |
| `franchise-agreement` | franchisee side | exclusive territory, unilateral fee increases, personal guarantee, post-term non-compete, sole-supplier pricing, transfer fee, unilateral manual amendments, renewal right |
| `software-license` | licensee side | vendor audit rights, retroactive true-up fees, source-code escrow, transfer restriction without M&A carve-out, unilateral discontinuation, seat minimums, mandatory support fees, refund of prepaid fees |
| `software-licensor` | licensor side | liability cap, warranty disclaimer, unrestricted sublicensing, licensee-owned improvements, overbroad IP indemnity, license-compliance verification, termination for breach, export-control compliance |
| `distribution-agreement` | distributor side | post-term non-compete, inventory buyback on termination, unilateral wholesale price increases, termination without cause, MAP pricing, goodwill compensation, prepayment terms, marketing/co-op support |
| `tos-user` | user side | mandatory arbitration, class-action waiver, unilateral term changes, account termination at will, sale of personal data, data-deletion right, perpetual content license, easy cancellation |
| `privacy-policy` | user side | admitted data sale, data-deletion right, retention limits, breach notification, biometric collection, marketing sharing, opt-out of sale/sharing, policy-change notice |
| `severance-agreement` | employee side | general release of claims, 21-day consideration period, mutual non-disparagement, paid cooperation, non-compete in severance, no-rehire clause, COBRA coverage, tax treatment |
| `equipment-lease` | lessee side | hell-or-high-water payment clause, evergreen auto-renewal, no early-termination right, no purchase option, as-is disclaimer, lessee insurance burden, assignment restriction, excessive late fees |
| `real-estate-purchase` | buyer side | non-refundable earnest money, no inspection contingency, no financing contingency, as-is sale, seller specific performance, buyer pays all closing costs, uncapped HOA assessments, no closing deadline |
| `partnership-agreement` | partner side | no deadlock resolution, no buyout mechanism, no vesting schedule, unlimited capital calls, overbroad post-exit non-compete, no IP contribution terms, no mandatory tax distributions, fiduciary duty waiver |
| `ip-assignment` | assignor side | no prior-inventions exhibit, unrelated future IP capture, post-employment trailer, moral-rights waiver, no stated consideration, no license-back, blanket disclosure duty, no open-source carve-out |
| `website-development` | client side | no IP ownership of deliverables, no source-code delivery, no acceptance testing, no warranty/bug-fix period, uncapped change fees, site-hostage takedown right, no third-party license terms, no launch deadline |
| `settlement-agreement` | claimant / individual side | broad release incl. unknown claims (§1542 waiver), no firm payment deadline, dismissal required before payment, one-sided non-disparagement, one-sided confidentiality, no tax allocation, no late-payment remedy, no enforcement fee-shifting |
| `data-license-agreement` | licensee side | no data-accuracy warranty, no refresh obligation, termination kill-switch on derived data/models, unilateral use-restriction changes, licensor reselling derived insights, broad usage audits, no feed uptime SLA, uncapped overage fees |
| `software-escrow` | beneficiary / licensee side | narrow release conditions, no deposit verification, no update deposits, beneficiary pays all fees, no build instructions, vendor can stall release with objections, no post-release support, escrow-agent liability capped at fees |
| `event-venue` | organizer side | narrow force majeure, F&B minimum with no attrition, front-loaded cancellation fees, exclusive in-house vendors, uncapped damage liability, venue can move/bump your date, no setup/teardown time included, restrictive noise curfew |
| `dpa-processor` | processor / vendor side | uncapped liability for data incidents, unlimited audits at your expense, impossible deletion timeline, full flow-down sub-processor liability, breach-notice window under 48 hours, unilateral scope expansion, unlimited DSR handling at your cost, suspension on mere allegation |
| `homeowners-insurance` | policyholder side | anti-concurrent causation exclusion, dwelling settled at actual cash value, percentage windstorm/hurricane deductible, mold/fungi sublimit, sewer/drain backup exclusion, low ALE cap, insurer's right to repair with own contractors, no ordinance-or-law coverage |
| `reseller-agreement` | reseller side | vendor termination for convenience on short notice, exclusivity/non-compete lock-in, no price protection, quotas without marketing support, no deal-registration protection, reseller indemnifying vendor's IP, unilateral program changes, no transition assistance |
| `term-sheet` | founder side | discount with no valuation cap, full-ratchet anti-dilution, participating preferred, MFN without carveouts, super pro-rata, investor veto over operating decisions, founder vesting with no acceleration, exclusivity > 30 days |
| `convertible-note` | founder side | cash repayment at maturity, change-of-control payout multiple, shadow-series liquidation preference, compounding interest, no pro-rata rights for noteholders, discount+cap with no "greater of" language, qualified-financing threshold too high, noteholder consent veto over operations |
| `construction-contract` | homeowner side | large upfront deposit, final payment before inspection, no written change orders, no start/completion dates, no lien-waiver protection, vague scope, binding arbitration, assignment/subcontracting without consent, no workmanship warranty, no three-day cancellation right, uncapped time-and-materials pricing, owner made responsible for permits |
| `term-sheet-investor` | investor side | no pro-rata rights, no information rights, no founder vesting, no liquidation preference, no protective provisions, no anti-dilution, no drag-along, no board seat or observer rights |

Write your own playbook in YAML — see `src/redline/playbooks/saas-vendor.yaml` for the schema, or scaffold one:

```bash
redline new-playbook equipment-lease --description "Lessee-side review of equipment leases."
```

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
