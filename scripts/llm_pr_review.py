"""AI code reviewer for pull requests, routed through OpenRouter.

Runs in GitHub Actions on every PR: fetches the diff via the GitHub REST
API, has the code model review it, and posts the review as a PR comment.
The review prompt encodes this repo's failure modes: convention errors,
look-ahead bias in backtests, and silent dependency on QuantLib.

Required environment::

    OPENROUTER_API_KEY  OpenRouter key (GitHub secret)
    GITHUB_TOKEN        Actions-provided token (pull-requests: write)
    GITHUB_REPOSITORY   e.g. "amritchachadi/ficc-lab"
    PR_NUMBER           Pull request number

Wired up in .github/workflows/llm-review.yml.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from rates_analytics.config import Settings  # noqa: E402
from rates_analytics.llm.router import OpenRouterClient  # noqa: E402

GITHUB_API = "https://api.github.com"

#: Cap on diff size sent to the model, keeping well inside context limits.
MAX_DIFF_CHARS = 200_000

SYSTEM_REVIEW = (
    "You are reviewing a Python fixed-income analytics repo. Check for: "
    "day-count and schedule convention errors, look-ahead bias or off-by-one "
    "in backtest weight/return alignment, transaction costs being ignored, "
    "numerically unstable code, test coverage gaps, and general Python "
    "quality. Be concise: bullet list of concrete findings with file/line "
    "references, then a one-line verdict (LGTM or CHANGES REQUESTED)."
)


def github_request(path: str, accept: str) -> requests.Response:
    """Return an authenticated GitHub API response for ``path``."""
    return requests.get(
        f"{GITHUB_API}{path}",
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=60,
    )


def post_comment(repo: str, pr_number: int, body: str) -> None:
    """Post ``body`` as an issue comment on the pull request."""
    requests.post(
        f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments",
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
        },
        data=json.dumps({"body": body}),
        timeout=60,
    ).raise_for_status()


def main() -> int:
    """Entry point; returns a process exit code."""
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = int(os.environ["PR_NUMBER"])

    diff_response = github_request(
        f"/repos/{repo}/pulls/{pr_number}", accept="application/vnd.github.diff"
    )
    diff_response.raise_for_status()
    diff = diff_response.text[:MAX_DIFF_CHARS]

    client = OpenRouterClient(Settings.from_env())
    review = client.chat(
        [
            {"role": "system", "content": SYSTEM_REVIEW},
            {"role": "user", "content": f"Review this PR diff:\n\n```diff\n{diff}\n```"},
        ],
        task="code",
        temperature=0.0,
    )
    post_comment(
        repo, pr_number, f"## OpenRouter code review (`{review.model}`)\n\n{review.content}"
    )
    print("Review posted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
