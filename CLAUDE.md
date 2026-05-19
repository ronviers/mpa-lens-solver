# mpa-lens-solver — session discipline

Read this before touching anything in this repo.

## Program-level discipline

This repo is **framework runtime** per [`H:/mpa-central/METHODOLOGY.md`](../mpa-central/METHODOLOGY.md) Cut 4 — fits per-substrate `TranslationField` instances (the substrate's "ICC profile"). Fits feed Cut 2 clause (b) (calibration records) at the curator step.

**Three-solver split** (canonical at
[`H:/mpa-conform/docs/SOLVERS_BLOCK_IN.md`](../mpa-conform/docs/SOLVERS_BLOCK_IN.md)):

| Solver | Repo | Job |
|---|---|---|
| mpa-solver | `H:/mpa-solver` | Substrate physics → observations |
| mpa-scale-solver | `H:/mpa-scale-solver` | Canonical-space runtime (consumes TranslationFields) |
| **mpa-lens-solver** | **`H:/mpa-lens-solver`** | **Produces TranslationFields from observations + cdv1 priors** |

## What lives here

- `mpa_lens_solver/priors.py` — per-substrate-class cdv1 prior application
  (glass: `chit = Tc − T`; QEC: `chit = ln(p_threshold/p_base)`; brain:
  scenario table) + dispatch + `fit_translation_field` (the public surface)
  + natural-trajectory-order sort per substrate
- `mpa_lens_solver/iterate.py` — `empirical_rows_from_cell` + `predict_next_chit`
  (line extension from prior history) + `refine_chit` (hill-climb under
  regime-band guard and predictor-corrector bracket, both default-on)
- `mpa_lens_solver/__init__.py` — public surface re-exports + `__version__`
- `tests/` — pure unit tests on priors + iterator + guards (53 tests)

## What does NOT live here

| Concern | Belongs to |
|---|---|
| Substrate physics / observation extraction | mpa-solver |
| Canonical-space operations (`apply_translation`, `regime_at`, etc.) | mpa-scale-solver |
| Library cell production | mpa-central (the substrate grinders) |
| Bundle orchestration, curator + researcher path | mpa-conform |
| EXR rendering, particle systems, DJV | mpa-conform |
| RFC text, schemas, framework prose | mpa-atlas |

The line you will most want to cross and must not: *"I'll just normalize the
substrate observation here before fitting."* No. The TranslationField IS the
normalization, returned as data. The caller (mpa-conform) applies it via
mpa-scale-solver's `apply_translation` at the right point in the pipeline.

## Thin discipline borrowings (program-wide)

- **Document size by function**, not percentage cuts. This file is short
  because the load-bearing distinctions fit short.
- **No declared virtues in user-facing copy** (memory): scrub
  "honest/transparent/sincere/ethical" from CLI strings, READMEs, and
  field metadata. Show behavior; don't announce it.
- **Single-move design**: ship one move, hand it to
  `library_sequence_shot.py`, render, look at the PNGs together, plan
  the next move from observation. Resist multi-step plans.
- **Self-evolving block-in** ([`docs/BLOCK_IN.md`](docs/BLOCK_IN.md)):
  the v0→v0.3+ ladder collapsed at v1.0. BLOCK_IN is now a thin
  next-session handoff listing open items, not a multi-version trajectory.

## cdv1 character framing

The substrates lens-solver handles (glass, quantum, brain) are
cdv1-foundational — their theorems composed across them and they carry
framework load. Decisions about the score function, TranslationField
shape, or new-substrate onboarding must be grounded in cdv1 character,
not made on engineering reflex (the "thin where standards bodies are
thick" discipline does NOT apply where the framework's testable content
lives — only to scaffolding and protocol prose).

Read [`docs/CHARACTER_FRAMING.md`](docs/CHARACTER_FRAMING.md) before any
change that touches: the score function (`locus_residual` or its
consumers), the TranslationField shape (observable conventions,
normalization, per-substrate metadata), the `_PRIOR_DISPATCH` registry
(a prior is a declaration about substrate character), or any reasoning
about why refinement does or does not "beat" the prior (the deviation
is character, not error).

The frame does not apply to pipeline glue, IO, test mechanics, or
build/packaging — those are normal engineering.

## Sibling-repo relationships

| Repo | We read | We write |
|---|---|---|
| mpa-scale-solver | `TranslationField`, `TranslationRule`, `OperatingPoint`, `CanonicalPoint` (output types) | — |
| mpa-central/library | library cells (json under `data/{brain,glass,quantum}/`) | — |
| mpa-atlas | RFC-S §4 (driver-profile vocabulary); cdv1 (chit conventions per substrate; resolved Q-glass-chit-sign) | — |
| mpa-conform | — | — (mpa-conform imports us; we do not import mpa-conform) |

Pure read-only consumer of mpa-scale-solver's types + mpa-central's data +
mpa-atlas's spec. Output is consumed by mpa-conform.

## Reproducibility

Pure functions on plain frozen dataclasses (no mutable state, no globals).
Same inputs → byte-identical output. Following mpa-scale-solver's
stateless commitment.

## Session handoff

[`docs/BLOCK_IN.md`](docs/BLOCK_IN.md) is the thin open-items list the
next session reads cold. README's Session Log is the historical residue.
The v1.0 architecture is documented in the README; new sessions pivot
from the open items, not from a version ladder.
