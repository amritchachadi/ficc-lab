"""Market data loading.

Today this is a deterministic synthetic price generator: backtests and CI
run with no network access and bit-identical data, which makes regressions
interpretable. The synthetic generator can embed persistent cross-sectional
drift dispersion so signal research has something real to find, or produce
pure noise so a strategy's null behaviour can be measured.
"""
