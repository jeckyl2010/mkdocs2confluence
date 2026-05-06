"""GitHub implementation of ReviewPlatformClient.

Uses the GitHub REST API (branch/PR creation) and GraphQL API
(addPullRequestReviewThread) so that review comments can be anchored to
specific lines even on files that are unchanged in the PR diff.
"""

from __future__ import annotations

import httpx


class GitHubReviewClient:
    """Posts Confluence comments as GitHub pull request review threads.

    Implements :class:`~mkdocs_to_confluence.sync.platform.ReviewPlatformClient`.
    """

    _API = "https://api.github.com"
    _GRAPHQL = "https://api.github.com/graphql"

    def __init__(self, repo: str, token: str) -> None:
        self._repo = repo  # "owner/repo"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def create_review_branch(self, base_branch: str, branch_name: str) -> None:
        """Create *branch_name* from the current HEAD of *base_branch*."""
        with httpx.Client(headers=self._headers, timeout=30) as http:
            resp = http.get(f"{self._API}/repos/{self._repo}/git/ref/heads/{base_branch}")
            _raise(resp, f"get ref heads/{base_branch}")
            base_sha = resp.json()["object"]["sha"]

            resp = http.post(
                f"{self._API}/repos/{self._repo}/git/refs",
                json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
            )
            _raise(resp, f"create branch {branch_name!r}")

    def create_pull_request(
        self,
        branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> tuple[int, str]:
        """Create a PR and return ``(pr_number, pr_node_id)``."""
        with httpx.Client(headers=self._headers, timeout=30) as http:
            resp = http.post(
                f"{self._API}/repos/{self._repo}/pulls",
                json={"title": title, "body": body, "head": branch, "base": base_branch},
            )
            _raise(resp, "create pull request")
            data = resp.json()
            return int(data["number"]), str(data["node_id"])

    def post_review_comment(
        self,
        pr_node_id: str,
        path: str,
        body: str,
        line: int | None,
    ) -> None:
        """Post a review thread via GitHub GraphQL.

        Uses ``addPullRequestReviewThread`` with ``subjectType: LINE`` for
        line-anchored comments, or ``subjectType: FILE`` for file-level
        (footer/fallback) comments.  Both work on unchanged files.
        """
        if line is not None:
            mutation = _THREAD_LINE_MUTATION
            variables: dict[str, object] = {
                "pullRequestId": pr_node_id,
                "body": body,
                "path": path,
                "line": line,
            }
        else:
            mutation = _THREAD_FILE_MUTATION
            variables = {
                "pullRequestId": pr_node_id,
                "body": body,
                "path": path,
            }

        with httpx.Client(
            headers={**self._headers, "Accept": "application/json"}, timeout=30
        ) as http:
            resp = http.post(self._GRAPHQL, json={"query": mutation, "variables": variables})
            _raise(resp, "addPullRequestReviewThread")
            data = resp.json()
            if "errors" in data:
                raise RuntimeError(f"GitHub GraphQL errors: {data['errors']}")

    def get_pr_merge_info(self, pr_number: int) -> tuple[bool, str | None]:
        """Return ``(merged, merge_commit_sha)``."""
        with httpx.Client(headers=self._headers, timeout=30) as http:
            resp = http.get(f"{self._API}/repos/{self._repo}/pulls/{pr_number}")
            _raise(resp, f"get PR #{pr_number}")
            data = resp.json()
            merged = bool(data.get("merged_at"))
            commit_sha = data.get("merge_commit_sha") if merged else None
            return merged, commit_sha


# ── Helpers ───────────────────────────────────────────────────────────────────


def _raise(resp: httpx.Response, context: str) -> None:
    if resp.is_error:
        raise RuntimeError(f"GitHub {context}: HTTP {resp.status_code} — {resp.text[:300]}")


_THREAD_LINE_MUTATION = """
mutation AddReviewThread($pullRequestId: ID!, $body: String!, $path: String!, $line: Int!) {
  addPullRequestReviewThread(input: {
    pullRequestId: $pullRequestId
    body: $body
    path: $path
    line: $line
    side: RIGHT
    subjectType: LINE
  }) {
    thread { id }
  }
}
"""

_THREAD_FILE_MUTATION = """
mutation AddReviewThread($pullRequestId: ID!, $body: String!, $path: String!) {
  addPullRequestReviewThread(input: {
    pullRequestId: $pullRequestId
    body: $body
    path: $path
    subjectType: FILE
  }) {
    thread { id }
  }
}
"""
