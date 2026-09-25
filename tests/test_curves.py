from rates_analytics.curves import (
    InterpolationMethod,
    bootstrap_curve,
    demo_curve_quotes,
    projection_vs_discount_report,
)


def test_bootstrap_reprices_helpers() -> None:
    discount, _projection = demo_curve_quotes()
    result = bootstrap_curve(discount, InterpolationMethod.LINEAR_ZERO)
    assert result.max_abs_error < 1e-3


def test_dual_curve_basis_is_nonzero() -> None:
    discount, projection = demo_curve_quotes()
    discount_curve = bootstrap_curve(discount, InterpolationMethod.LOG_DISCOUNT).curve
    projection_curve = bootstrap_curve(projection, InterpolationMethod.LOG_DISCOUNT).curve
    report = projection_vs_discount_report(discount_curve, projection_curve)
    assert report["pv_basis"] != 0.0
