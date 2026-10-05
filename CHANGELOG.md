# Changelog

All notable changes to redline-buddy. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- `saas-provider` playbook: provider-side review of SaaS / subscription
  agreements — the mirror of `saas-vendor` for founders selling software,
  not just buying it. 8 rules (no liability cap [high], customer
  termination for convenience [high], uncapped SLA credits [high],
  customer claims on provider IP [high], no late-payment remedy [medium],
  no price-uplift right [medium], overbroad provider indemnity [medium],
  customer audit rights over provider books [low]), each with quotable
  fallback language; sample fixture fires 8/8, clean fixture fires 0.
- `redline serve` now offers a "Download Word redline" link after every
  review: `GET /download.docx` serves the last review as a tracked-changes
  `.docx` (same renderer as `--format docx`), as a file download. 5 new
  tests; full suite 391 passed, 1 skipped.
- `redline compare --format docx`: Word redline of a negotiation round.
  Writes `<old>-vs-<new>.redline.docx` with the new draft's gained and
  reworded flags as tracked changes (their round-2 language struck,
  fallback inserted), a "Concessions won" table for resolved flags, the
  paragraph-level text changes as tracked changes, and the new draft's
  findings summary. 7 new tests; full suite 386 passed, 1 skipped.
- `redline review --format docx`: Word redline export with real tracked
  changes. The full contract is written to `<contract>.redline.docx` with
  each finding's flagged language struck through (`w:del`) and the
  playbook's quotable fallback language inserted after it (`w:ins`), so the
  file opens in Word ready for Review → All Markup accept/reject — a
  counter-draft you can send back, not just a memo. Missing-clause findings
  (no excerpt) become tracked insertions under a "Proposed additions"
  section; every finding is also listed in a summary table with severity,
  rationale, and proposed language. Works for single files and batch
  directories (one `.redline.docx` per contract); `--fail-on` /
  `--fail-below` still apply. 10 new tests; full suite 379 passed, 1 skipped.
- Optional LLM second reader: `redline review --second-reader <model>`
  (e.g. `gpt-4o-mini`) re-reads the contract against the same playbook after
  the deterministic engine. Rule hits the model independently flags are
  marked "✓ confirmed by second reader"; genuinely new observations are
  appended as "🤖 second-reader observations". Model output is validated
  hard: unknown rule ids, missing verbatim quotes, and invalid severities
  are dropped, and an empty/garbled response is an error, not a silent pass.
  Strictly opt-in via the `llm` extra (`pip install "redline-buddy[llm]"`,
  BYO provider API key) — the default path stays offline and keyless, and
  the flag sends contract text to the provider, so it warns accordingly.
  Single-file review only. 16 new tests; full suite 369 passed, 1 skipped.

## [0.1.0] - 2026-10-03

First PyPI release.

### Added
- `term-sheet-investor` playbook: investor-side review of startup financing
  term sheets (angels / small funds reviewing founder-drafted SAFE,
  convertible-note, or priced-seed terms) — 8 rules (no pro-rata rights
  [high], no information rights [high], no founder vesting [high], no
  liquidation preference [high], no protective provisions [medium], no
  anti-dilution [medium], no drag-along [medium], no board seat or observer
  rights [low]), each with quotable fallback language; sample fixture fires
  8/8, clean fixture fires 0
- `construction-contract` playbook: homeowner-side review of home-improvement
  and construction contracts (kitchen/bath remodels, additions, GC agreements)
  — 12 rules (large upfront deposit over 33% [high], final payment before
  final inspection [high], no written change-order requirement [high], no
  start/completion dates [high], no lien-waiver protection [high], uncapped
  time-and-materials pricing [high], vague scope [medium], binding arbitration
  [medium], no workmanship warranty [medium], no three-day cancellation right
  [medium], owner made responsible for permits [medium], contractor may
  assign/subcontract without consent [low]), each with quotable fallback
  language; sample fixture fires 12/12, clean fixture fires 0
- `redline review --format html`: self-contained HTML memo export for a
  single review or a whole directory (batch summary table plus per-file
  memos), and `redline compare --format html`: shareable comparison page
  with gained/resolved/reworded findings and text-change hunks. One file
  each, inline CSS, zero JavaScript, zero network — built to be emailed
  to a human attorney or saved as PDF from the browser, with a print
  stylesheet and grade-colored risk banners. All contract-derived text
  is HTML-escaped at render time.
- `convertible-note` playbook: founder-side review of SAFE and
  convertible-note instruments — 8 rules (cash repayment at maturity
  [high], change-of-control payout multiple [high], shadow-series
  liquidation preference [high], compounding interest, no pro-rata
  rights for noteholders, discount+cap with no "greater of" language,
  qualified-financing threshold set too high, noteholder consent veto
  over operations [low]), each with quotable fallback language; sample
  fixture fires 8/8, clean fixture fires 0
- `term-sheet` playbook: founder-side review of startup financing term
  sheets (SAFE, convertible note, priced seed) — 8 rules (discount with
  no valuation cap [high], full-ratchet anti-dilution [high],
  participating preferred [high], MFN without carveouts, super pro-rata,
  investor veto over operating decisions, founder vesting with no
  acceleration, exclusivity over 30 days [low]), each with quotable
  fallback language; sample fixture fires 8/8, clean fixture fires 0
- `homeowners-insurance` playbook: policyholder-side review of HO-3 style
  homeowners policies — 8 rules (anti-concurrent causation exclusion
  [high], dwelling settled at actual cash value instead of replacement
  cost [high], percentage-based windstorm/hurricane deductible [high],
  mold/fungi sublimit, sewer/drain water-backup exclusion, low
  additional-living-expense cap, insurer's right to repair with its own
  contractors, no ordinance-or-law coverage [low]), each with quotable
  fallback language; sample fixture fires 8/8, clean fixture fires 0
- `reseller-agreement` playbook: reseller/channel-partner-side review of
  vendor reseller agreements — 8 rules (vendor termination for
  convenience on 30 days [high], exclusivity/non-compete lock-in [high],
  no price protection, quotas without marketing support, no
  deal-registration protection, reseller indemnifying vendor's IP, unilateral
  program changes, no transition assistance [low]), each with quotable
  fallback language; sample fixture fires 8/8, clean fixture fires 0
- `redline suggest` ranks per file for directories: `suggest <dir>` now
  shows an independent playbook ranking per contract (consistent with
  batch review's per-file auto-detection) instead of one ranking for the
  concatenated blob
- `event-venue` playbook: organizer-side review of venue rental agreements
  — 8 rules (narrow force majeure [high], F&B minimum with no attrition
  [high], front-loaded cancellation fees, exclusive in-house vendors,
  uncapped damage liability, venue can move/bump your date, no
  setup/teardown time included [low], restrictive noise curfew [low]),
  each with quotable fallback language; sample fixture fires 8/8, clean
  fixture fires 0
- `redline playbooks` command: lists all bundled playbooks with rule
  counts and descriptions (text or `--format json`) for discoverability
- `data-license-agreement` playbook: licensee-side review of commercial
  data licenses — 8 rules (no data-accuracy warranty [high], no refresh
  obligation [high], termination kill-switch on derived data/models
  [high], unilateral use-restriction changes, licensor reselling derived
  insights, broad usage audits, no feed uptime SLA, uncapped overage fees
  [low]), each with quotable fallback language; sample fixture fires 8/8,
  clean fixture fires 0
- `software-escrow` playbook: beneficiary/licensee-side review of software
  escrow agreements — 8 rules (narrow release conditions [high], no
  deposit verification [high], no update deposits, beneficiary pays all
  fees, no build instructions, vendor can stall release with objections,
  no post-release support [low], escrow-agent liability capped at fees
  [low]), each with quotable fallback language; sample fixture fires
  8/8, clean fixture fires 0
- Batch review auto-detects per file: `redline review <directory>` without
  `--playbook` now selects the best playbook for each contract
  independently (a mixed folder of MSA + DPA + HO-3 gets the right
  playbook per file instead of one playbook for the concatenated blob);
  the summary table gains a Playbook column and each file's pick is
  noted on stderr. Explicit `--playbook` keeps the old single-playbook
  report unchanged
- `dpa-processor` playbook: processor/vendor-side review of DPAs — 8 rules
  (uncapped breach liability [high], unlimited audit rights at your
  expense, impossible deletion timeline, full flow-down sub-processor
  liability, sub-48-hour breach notification, unilateral instruction
  rights, unlimited free DSAR handling [low], suspension on mere
  allegation), each with quotable fallback language; sample fixture
  fires 8/8, clean fixture fires 0
- Auto playbook suggestion: `redline review` and `redline compare` now
  auto-detect the best bundled playbook when `--playbook` is omitted —
  deterministic local TF-IDF keyword scoring plus a capped bonus for
  rules that actually fire (which detects document perspective: mirror
  playbooks like `dpa` vs `dpa-processor` share vocabulary, but only the
  right side's rules fire). No LLM or network calls. A clear winner is
  used directly; ambiguous or low-confidence documents keep the historic
  `saas-vendor` default with an explanatory stderr note, so no document
  ever gets a silently wrong playbook. Calibrated on all 28 sample
  fixtures: 24/28 top-1 correct, the other 4 fall back honestly
- `redline suggest <contract>`: rank bundled playbooks against a contract
  without reviewing it — prints scores, matched terms, and the
  `redline review --playbook <name>` command to run
- Risk score + letter grade on every review: deterministic 0–100 score
  (critical −30, high −15, medium −7, low −3, floored at 0) with
  ToS;DR-style grades (A ≥ 90, B ≥ 75, C ≥ 60, D ≥ 40, else F) —
  shown as a headline in memo/diff output, as `risk_score`/`risk_grade`
  in JSON (plus per-severity `by_severity`), as a Risk column in batch
  summaries, as a grade-colored banner in `redline serve`, and as a
  risk delta (`Risk: C (63) → B (78) — improved`) in `redline compare`
  memo and JSON
- `redline review --fail-below <grade>`: CI gate on the headline score —
  exit 1 when the review's letter grade is worse than the given grade
  (e.g. `--fail-below B` fails on C, D, F)
- `settlement-agreement` playbook: claimant/individual-side review of
  settlement agreements — 8 rules (broad release incl. unknown claims /
  §1542 waiver [high], no firm payment deadline [high], dismissal with
  prejudice required before payment [high], one-sided non-disparagement,
  one-sided confidentiality, no tax allocation/reporting, no late-payment
  remedy, no enforcement fee-shifting [low]), each with quotable fallback
  language; sample (8/8 fire) + clean (0 fire) fixtures
- `real-estate-purchase` playbook: buyer-side review of purchase
  agreements — 8 rules (non-refundable earnest money, no inspection
  contingency, no financing contingency, as-is sale, seller specific
  performance, buyer pays all closing costs, uncapped HOA assessments,
  no closing deadline), each with quotable fallback language; sample
  fixture fires 8/8, clean fixture fires 0.
- `equipment-lease` playbook: lessee-side review of equipment leases —
  8 rules (hell-or-high-water payment clause, evergreen auto-renewal,
  no early-termination right, no purchase option, as-is disclaimer,
  lessee insurance burden, assignment restriction, excessive late fees),
  each with quotable fallback language; sample fixture fires 8/8, clean
  fixture fires 0.
- `severance-agreement` playbook: employee-side review of severance
  agreements — 8 rules (broad general release, 21-day consideration
  period, one-sided non-disparagement, unpaid cooperation clause,
  non-compete in severance, no-rehire clause, COBRA unaddressed, tax
  treatment unaddressed), each with quotable fallback language; sample
  (8/8 fire) + clean (0 fire) fixtures
- `privacy-policy` playbook: user-side review of privacy policies — 8
  rules (admitted data sale, no data-deletion right, no retention limit, no
  breach-notification commitment, biometric collection, marketing sharing,
  no opt-out of sale/sharing, silent policy changes), each with quotable
  fallback language; sample (8/8 fire) + clean (0 fire) fixtures
- `tos-user` playbook: user-side review of website/app Terms of Service —
  8 rules (mandatory arbitration, class-action waiver, unilateral term
  changes, account termination at will, sale of personal data, no
  data-deletion right, perpetual content license, no easy cancellation),
  each with quotable fallback language; sample (8/8 fire) + clean (0 fire)
  fixtures
- `distribution-agreement` playbook: distributor-side review of product
  distribution agreements — 8 rules (post-term non-compete, no inventory
  buyback, unilateral wholesale price increases, termination without cause,
  MAP pricing, no goodwill compensation, prepayment terms, no marketing
  support), each with quotable fallback language; sample (8/8 fire) + clean
  (0 fire) fixtures
- `software-license` playbook: licensee-side review of perpetual software
  license agreements — 8 rules (vendor audit rights, retroactive true-up
  fees, no source-code escrow, transfer restriction without M&A carve-out,
  unilateral discontinuation, seat minimums, mandatory support fees, no
  refund), each with quotable fallback language; sample (8/8 fire) + clean
  (0 fire) fixtures
- `saas-vendor` playbook: 4 new rules for the flagship SaaS-buyer playbook —
  vendor AI-training on customer data [high], no data return/deletion on
  exit [high], no uptime SLA or service credits, unilateral terms changes
  by website posting — each with quotable fallback language (10 rules total)
- `franchise-agreement` playbook: franchisee-side review of franchise
  agreements — 8 rules (no exclusive territory, unilateral fee increases,
  personal guarantee, post-term non-compete, sole-supplier pricing,
  transfer fee, unilateral manual amendments, no renewal right), each with
  quotable fallback language; built end-to-end with the new `new-playbook`
  scaffolder as a dogfood test; sample (8/8 fire) + clean (0 fire) fixtures
- `redline new-playbook <name>`: scaffolds a new playbook — YAML with
  commented schema and example rules for every check kind, sample/clean
  fixture stubs, and a test skeleton — plus printed next steps; refuses to
  overwrite and validates the slug
- `advisor-agreement` playbook: advisor-side review of startup advisor
  agreements — 8 rules (no vesting schedule [high], vague compensation
  [high], IP assignment without background-IP carve-out, no termination
  right, non-compete, no confidentiality, unaddressed expenses, term over
  two years), each with quotable fallback language; sample (8/8 fire) +
  clean (0 fire) fixtures

### Fixed
- Engine now collapses all whitespace runs to single spaces before running
  rules (`review_contract`). PDF/DOCX extraction wraps phrases mid-line
  ("signing\nbonus"), which silently defeated literal-space patterns — e.g.
  `moonlighting-ban` missed on a line-wrapped contract (11/12 fired) and
  now fires (12/12). Applies uniformly to CLI, web UI, batch, compare, and
  `validate --sample`; excerpts were already single-line so output shape is
  unchanged, and no clean fixture gains a false positive.

### Added
- `nda-discloser` playbook: discloser-side review of NDAs (mirror of
  `nda-recipient`) — 11 rules (marked-only definition excluding oral/visual
  disclosures [high], residual-knowledge / unaided-memory carve-out [high],
  license grant to recipient, unbounded affiliate sharing, no
  return-or-destroy, one-year survival, no injunctive-relief
  acknowledgment, undefined purpose, no fixed term, no compelled-disclosure
  notice, no no-obligation clause), each with quotable fallback language;
  sample (11/11 fire) + clean (0 fire) fixtures
- `employment-agreement` playbook: employee-side review of employment
  agreements — 12 rules (post-employment non-compete [critical],
  overbroad invention assignment without a §2870 / own-time carve-out,
  non-solicitation, perpetual confidentiality without exclusions,
  mandatory binding arbitration with jury/class waivers, no severance on
  without-cause termination, signing-bonus clawback, no equity
  acceleration on termination or acquisition, garden leave, blanket
  moonlighting ban, without-cause notice longer than 30 days, missing
  prior-inventions exhibit), each with quotable fallback language;
  sample (12/12 fire) + clean (0 fire) fixtures
- `commercial-landlord` playbook: landlord-side review of commercial leases —
  12 rules (uncapped CAM / operating-expense pass-throughs, missing base year,
  no audit right, no personal / good-guy guarantee, holdover without premium,
  assignment without consent, exclusivity grant, no casualty termination
  right, unlimited relocation, no environmental indemnity, unallocated ADA
  duty, no subrogation waiver), each with quotable fallback language;
  sample + clean fixtures
- `redline compare OLD NEW` — negotiation-round diffing: paragraph-level text
  changes (added/removed/reworded) plus risk deltas between drafts — new red
  flags introduced, findings resolved, and clauses reworded but still flagged;
  memo and JSON output, `--fail-on-gain` CI gating, and bundled
  `examples/compare-round1.md` / `compare-round2.md` demo pair

### Changed
- Bundled playbooks moved into the installed package (`src/redline/playbooks/`)
  and resolved via `importlib.resources`, so `redline review --playbook <name>`
  works after a plain `pip install redline-buddy` — previously they only
  resolved from a source checkout, which would have broken the PyPI install
  (PR #19)

### Added
- `loan-borrower` playbook: borrower-side review of business term loans —
  11 rules (confession of judgment [critical], prepayment penalty / yield
  maintenance, uncapped variable rate, personal guarantee, blanket lien,
  default cure period, vague late fee, arbitration, lender assignment),
  each with quotable fallback language; sample + clean fixtures (PR #24)
- `consulting-vendor` playbook: vendor (consultant/agency) side MSA review —
  12 rules (IP assignment scope, liability cap, mutual indemnity, payment
  terms, late-payment remedy, kill fee, non-compete, one-sided
  non-solicitation, change-order process, client cooperation, insurance
  terms), each with quotable fallback language; sample + clean fixtures
  (PR #23)
- Batch review: `redline review <directory>` reviews every supported contract
  file recursively — summary table (per-file counts by severity) plus per-file
  memos, batch JSON with totals, concatenated diffs; `--fail-on` applies
  across all files (PR #22)
- `lease-tenant` playbook: tenant-side review of residential leases — 11 rules
  (deposit cap via max_value, rent-escalation cap, repair obligations, early
  termination, personal guarantee, entry notice, subletting, attorneys' fees,
  auto-renewal, utilities, wear and tear), each with quotable fallback
  language; sample + clean fixtures (PR #21)
- `redline serve` upgrades: playbook descriptions in the picker, one-click
  "Copy fallback" buttons on memo findings (clipboard via hidden textarea —
  XSS-safe), and severity filter toggles on the memo view (PR #20)
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
