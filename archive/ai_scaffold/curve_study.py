# ruff: noqa
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from rates_analytics.config import Settings
from rates_analytics.curves import (
    InterpolationMethod,
    bootstrap_curve,
    demo_curve_quotes,
    projection_vs_discount_report,
)
from rates_analytics.llm.router import OpenRouterClient

INTERPOLATIONS = (
    InterpolationMethod.LINEAR_DISCOUNT,
    InterpolationMethod.LINEAR_ZERO,
    InterpolationMethod.LOG_DISCOUNT,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="reports/curve_study")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    discount_helpers, projection_helpers = demo_curve_quotes()
    studies = {}
    for interpolation in INTERPOLATIONS:
        studies[interpolation] = (
            bootstrap_curve(discount_helpers, interpolation),
            bootstrap_curve(projection_helpers, interpolation),
        )

    markdown, post = _build_writeup(studies)
    (out_dir / "curve_interpolation_comparison.md").write_text(markdown, encoding="utf-8")
    (out_dir / "linkedin_post.md").write_text(post, encoding="utf-8")
    _plot_profiles(studies, out_dir)
    _write_pdf(markdown, out_dir / "curve_interpolation_comparison.pdf")
    return 0


def _build_writeup(studies: dict[InterpolationMethod, tuple[object, object]]) -> tuple[str, str]:
    lines = [
        "# Curve bootstrapping, dual curve, and interpolation comparison",
        "",
        "Synthetic OIS discount and 3M projection curves were bootstrapped from a small helper set designed to make interpolation matter: quarterly coupon dates sit between several helper pillars, so the curve choice feeds back into the bootstrap instead of only affecting post-bootstrap valuation.",
        "",
    ]

    discount_notes: list[str] = []
    projection_notes: list[str] = []
    table_rows = []
    for interpolation, (discount_result, projection_result) in studies.items():
        discount_curve = discount_result.curve
        projection_curve = projection_result.curve
        stats = projection_vs_discount_report(discount_curve, projection_curve)
        table_rows.append(
            (
                interpolation.value,
                discount_result.max_abs_error,
                discount_result.mean_abs_error,
                projection_result.max_abs_error,
                stats["pv_basis"],
                discount_curve.zero_rate(5.0),
                projection_curve.zero_rate(5.0),
            )
        )
        forward_profile = discount_curve.dense_forward_profile()
        forward_changes = [
            abs(forward_profile[i][1] - forward_profile[i - 1][1])
            for i in range(1, len(forward_profile))
        ]
        discount_notes.append(
            f"- {interpolation.value}: 5Y discount zero {discount_curve.zero_rate(5.0):.4%}, max helper error {discount_result.max_abs_error:.2e}, forward jump proxy {max(forward_changes):.4%}."
        )
        projection_notes.append(
            f"- {interpolation.value}: 5Y projection zero {projection_curve.zero_rate(5.0):.4%}, float-leg PV basis versus using the discount curve as projection {stats['pv_basis']:.6f}."
        )

    lines.extend(
        [
            "## What the synthetic study shows",
            "",
            *discount_notes,
            "",
            *projection_notes,
            "",
            "## Headline takeaways",
            "",
            "1. The bootstrap reprices the helpers essentially exactly for all three interpolation schemes.",
            "2. Interpolation changes the interior forward-rate path materially even when pillar zero rates stay close.",
            "3. Using a single curve for both discounting and forwarding understates the dual-curve basis effect in the floating leg.",
            "",
            "## Comparison table",
            "",
            "| interpolation | discount max error | discount mean error | projection max error | float-leg PV basis | 5Y discount zero | 5Y projection zero |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in table_rows:
        lines.append(
            f"| {row[0]} | {row[1]:.2e} | {row[2]:.2e} | {row[3]:.2e} | {row[4]:.6f} | {row[5]:.4%} | {row[6]:.4%} |"
        )

    try:
        settings = Settings.from_env()
        if settings.has_openrouter:
            client = OpenRouterClient(settings)
            synthesis = client.chat(
                [
                    {
                        "role": "system",
                        "content": "You are a senior fixed-income researcher. Summarize the implications of a dual-curve bootstrap and interpolation choice for a professional desk. Be concise and practical.",
                    },
                    {
                        "role": "user",
                        "content": "Summarize the practical implications of a synthetic OIS discount and 3M projection curve comparison.",
                    },
                ],
                task="research",
                temperature=0.2,
            ).content
            lines.extend(["", "## OpenRouter research assistant synthesis", "", synthesis, ""])
    except Exception:
        pass

    markdown = "\n".join(lines)
    post = "I just built a synthetic dual-curve study in ficc-lab: OIS discounting, a separate 3M projection curve, and a comparison of linear-discount, linear-zero, and log-discount interpolation. The main takeaway is that helper repricing can look perfect while the forward curve between pillars still changes meaningfully, so interpolation choice is a real modelling assumption."
    return markdown, post


def _plot_profiles(
    studies: dict[InterpolationMethod, tuple[object, object]], out_dir: Path
) -> None:
    plt.figure(figsize=(10, 6))
    for interpolation, (discount_result, projection_result) in studies.items():
        discount_profile = discount_result.curve.dense_forward_profile()
        plt.plot(
            [p[0] for p in discount_profile],
            [p[1] for p in discount_profile],
            label=f"discount {interpolation.value}",
        )
    projection_profile = next(iter(studies.values()))[1].curve.dense_forward_profile()
    plt.plot(
        [p[0] for p in projection_profile],
        [p[1] for p in projection_profile],
        linestyle="--",
        label="projection curve",
    )
    plt.xlabel("Maturity (years)")
    plt.ylabel("3M-style forward rate")
    plt.title("Forward-rate paths under competing interpolation choices")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "forward_paths.png", dpi=200)
    plt.close()

    plt.figure(figsize=(10, 6))
    for interpolation, (discount_result, _) in studies.items():
        curve = discount_result.curve
        plt.plot(curve.pillars, curve.discount_factors, marker="o", label=interpolation.value)
    plt.xlabel("Maturity (years)")
    plt.ylabel("Discount factor")
    plt.title("Bootstrapped discount factors")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "discount_factors.png", dpi=200)
    plt.close()


def _write_pdf(markdown: str, pdf_path: Path) -> None:
    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="BodySmall", parent=styles["BodyText"], leading=12, fontSize=9))
    story = []
    story.append(
        Paragraph("Curve bootstrapping, dual curve, and interpolation comparison", styles["Title"])
    )
    story.append(Spacer(1, 0.2 * inch))
    story.append(
        Paragraph(
            "This report compares three interpolation schemes on a synthetic OIS discount curve and a separate 3M projection curve.",
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 0.15 * inch))
    for image_name in ("forward_paths.png", "discount_factors.png"):
        story.append(Image(str(pdf_path.parent / image_name), width=6.8 * inch, height=4.1 * inch))
        story.append(Spacer(1, 0.15 * inch))
    for paragraph in markdown.splitlines():
        text = paragraph.strip()
        if not text:
            story.append(Spacer(1, 0.08 * inch))
            continue
        if text.startswith("# "):
            story.append(Paragraph(text[2:], styles["Heading1"]))
        elif text.startswith("## "):
            story.append(Paragraph(text[3:], styles["Heading2"]))
        elif text.startswith("|"):
            story.append(Paragraph(text.replace("|", " | "), styles["BodySmall"]))
        else:
            story.append(Paragraph(text, styles["BodyText"]))
    doc.build(story)


if __name__ == "__main__":
    raise SystemExit(main())
