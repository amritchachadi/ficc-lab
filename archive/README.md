# archive/ai_scaffold

Early AI-assisted scaffolding of a curve bootstrapper (`curves/`), its tests,
and a study script. It is kept as a reference implementation only, and is
excluded from lint, type-checking and CI.

The maintained, hand-derived implementation lives in
`src/rates_analytics/curves2/`. It is built independently and tested against
hand-computed values; this archive exists to cross-check it.

Known gaps in the archived code: float-year maturities with no day-count
integration, and no handling of negative rates.
