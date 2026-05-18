"""mpa-lens-solver — substrate-class translation-field characterizer.

The substrate's ICC profile for the MPA suite. Produces per-substrate-class
mpa_scale_solver.TranslationField instances that map raw substrate
observations into canonical (chit, gamma_AB) coordinates the framework
can read.

One process: fit_translation_field stamps the cdv1 prior (or random seed
when bootstrap=True), then refines each cell up to max_passes against
(C, chi) observations. max_passes=0 = pure prior (clear in zero passes).
max_passes>0 = random-perturbation hill climb on chit until residual
<= tolerance.

Every TranslationRule.canonical.extras carries a `fit_diagnostics` dict
emitted by mpa_lens_solver.diagnostics.FitDiagnostics. Same shape across
prior'd and bootstrap modes; downstream readers branch on the `source`
field.
"""

from .diagnostics import (  # noqa: F401
    FitDiagnostics,
    RefineHistory,
    Source,
    build_diagnostics,
)
from .iterate import (  # noqa: F401
    empirical_rows_from_cell,
    predict_next_chit,
    refine_chit,
)
from .priors import (  # noqa: F401
    BRAIN_SCENARIO_CHIT,
    DEFAULT_BOOTSTRAP_SEED_RANGE,
    GLASS_TC,
    QEC_P_THRESHOLD,
    brain_prior,
    cdv1_prior_chit,
    fit_translation_field,
    glass_prior,
    quantum_prior,
)

__version__ = "1.2.0"
