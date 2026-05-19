# cdv1 character in lens-solver

Why this exists: lens-solver fits TranslationFields for three cdv1-foundational
substrates (glass, quantum, brain). Their character is doing load-bearing work
in cdv1 itself — the framework's theorems composed across them. Decisions about
score-function depth, observable conventions, and per-substrate behavior all
need to be made against that character, not in spite of it.

This document is the frame those decisions get made against. It is not a
specification — [`cdv1_compressed.md`](../../mpa-atlas/framework/cdv1_compressed.md)
is. It is the reading-order primer that keeps lens-solver coherent with cdv1.

## How character flows through lens today

The mechanism is in three layers, all already in code:

- **Priors** (`_PRIOR_DISPATCH` in `mpa_lens_solver/priors.py`) are each
  substrate's leading-order universality form:
  - Glass: `chit = Tc − T` — Landau distance from criticality.
  - QEC: `chit = ln(p_threshold / p_base)` — laser-analogue ln(G_0/L) that
    cdv1 §Bridge-to-v9 fixes.
  - Brain: scenario table — regime-by-regime hand-fit.

  Each prior is the substrate at universality-class resolution. The
  per-substrate dispatch in code IS cdv1's substrate-conditional reading
  rules made operational.

- **Regime-band guard** is cdv1's `{c, s, r}` three-regime ontology in code:
  refinement candidates that cross the seed's regime are rejected.

- **Adaptive predictor bracket** is substrate-class character speaking back
  through the apparatus: QEC trajectories migrate fast in chit (the log-form
  prior expands per order-of-magnitude `p_base`); glass moves slow (linear in
  T). The bracket adapts because the substrate's character varies.

## Refinement reads character

When `max_passes > 0`, refinement against real (C, χ) data measures the
**substrate-thermodynamic deviation** from the leading-order prior. cdv1's
[`Open Items`](../../mpa-atlas/framework/cdv1_compressed.md) section is
explicit: substrate-thermodynamic derivation of the exact functional form of
each leading-order posit is the *canonical extension mode of the framework's
API*. Universality fixes the exponent; substrates fix the amplitude.

Concrete:

- Glass refinement against CK-aging data measures `α_s` — the CK
  aging-diagonal slope, which is the deviation from linear `chit = Tc − T`
  near criticality.
- QEC refinement measures how surface-code character departs from
  pure-laser analogue at regime boundaries (where the discrete syndrome
  dynamics don't match the continuous laser kernel).
- Brain refinement measures context-modulated departures from the scenario
  table.

The deviation is **not error against ground truth**. It is the
substrate-thermodynamic content cdv1 catalogs as "predictions awaiting
empirical contact." A refinement pass that "beats the prior" is the
framework's API earning weight, not the score function fighting the
substrate.

**Trigger for score-function depth (BLOCK_IN item 1):** when we want a
specific cdv1 posit's deviation measured on a specific substrate. Not
generic depth. The framing of any future score-depth work must name
the posit and the substrate.

## Observable conventions belong in TranslationField

The TranslationField today carries `(operating_point → chit, γ_AB, k_frust)`.
It does **not** carry observable conventions. This is a gap.

Concrete case: QEC's empirical chi sits on a different scale than glass's
because QEC's susceptibility-via-stabilizer-perturbation has a deep-r
asymptote set by code distance + stabilizer structure. That asymptote is
substrate-class character, not arbitrary scale. Per the [CLAUDE.md](../CLAUDE.md)
preprocessing rule, the TranslationField IS the normalization; observable
conventions are part of the normalization the substrate declares.

Status today:

- The mismatch is absorbed downstream by mpa-conform's per-substrate
  baselines ([`SYSTEM_OVERVIEW.md`](../../mpa-central/SYSTEM_OVERVIEW.md) §5).
  Production works; the auditor sees substrate-relative percentiles, not
  raw scale.
- Reintroducing a normalizer as preprocessing in
  `iterate.py::empirical_rows_from_cell` would duplicate the correction and
  violate the CLAUDE.md preprocessing rule. Do not do that.
- The right long-term home is a TranslationField shape extension that
  declares observable conventions per substrate
  (`TranslationRule.canonical.extras` or a sibling field). This is **not**
  present work — it is the frame that closes BLOCK_IN item 2.

**Trigger for the TranslationField extension:** a fourth substrate with
strange chi scaling that downstream baselines can't cleanly absorb; or
auditor cross-substrate disagreement that points back to scale; or a Banach
comparison that wants normalization explicit per substrate.

## Cross-substrate transfer is the framework's load-bearing empirical claim

cdv1's empirical content rests on universality-class transfer across
substrates. Three substrates instanced means three independent tests. Each
per-substrate TranslationField IS that claim made operational for that
substrate.

This is why the bootstrap rollout (BLOCK_IN item 3, landed 2026-05-18)
matters more than its code-change size suggests: a fourth substrate now
instances the same claim with zero lens-solver code change. The substrate's
character flows through `_resolve_bootstrap` + `_resolve_bootstrap_seed_range`
fallbacks; its deviation from leading-order becomes measurable via the same
refinement path the named substrates use. The dispatch's auto-bootstrap-on-
unknown is cross-substrate-transfer made operational.

## Banach as limit form (deferred)

The three cdv1 substrates could in principle be replaced by a dimensionless
Banach substrate as the canonical reference frame; per-substrate
TranslationFields would factor through Banach.

This direction is **deferred**. The three substrates carry load Banach has
not earned (see program memory: `project_banach_substrate_cdv1_promotion`).
Do not re-engage the promotion question. Do hold the limit-form frame as
orientation for why lens-solver's per-substrate dispatch is the present
multiplicity, not a permanent shape.

## When this frame applies

Read this document before any decision involving:

- Changes to the score function
  ([`mpa_scale_solver.gfdr_model.locus_residual`](../../mpa-scale-solver/python/mpa_scale_solver/gfdr_model.py)
  or its consumers in `iterate.py`).
- Changes to the TranslationField shape — anything that would touch
  observable conventions, normalization, or per-substrate metadata.
- Adding a new substrate to `_PRIOR_DISPATCH` — the prior's form is a
  declaration about the substrate's character at universality-class
  resolution, not a convenience for the dispatch table.
- Reasoning about why refinement does or does not "beat" the prior — the
  deviation is character, not error.

This frame does **not** apply to: pipeline glue, IO, test mechanics,
build/packaging. Those are normal engineering and do not need the cdv1
discipline overhead.

## Pointers

- cdv1 source of truth: [`H:/mpa-atlas/framework/cdv1_compressed.md`](../../mpa-atlas/framework/cdv1_compressed.md)
- cdv1 receipts (line-keyed justifications): [`H:/mpa-atlas/framework/cdv1_receipts.md`](../../mpa-atlas/framework/cdv1_receipts.md)
- RFC-S Scale Management (driver-profile vocabulary): [`H:/mpa-atlas/rfcs/MPA-RFC-S_Scale-Management.md`](../../mpa-atlas/rfcs/MPA-RFC-S_Scale-Management.md)
- Suite-wide framing: [`H:/mpa-central/SYSTEM_OVERVIEW.md`](../../mpa-central/SYSTEM_OVERVIEW.md)
- Lens-solver session discipline: [`CLAUDE.md`](../CLAUDE.md)
- Open items: [`BLOCK_IN.md`](BLOCK_IN.md)
