"""ReviewPlatformClient protocol — the abstraction for GitHub/GitLab/etc."""

from __future__ import annotations

from typing import Protocol


class ReviewPlatformClient(Protocol):  # pragma: no cover
    """Interface for posting review comments on a hosted git platform.

    Implement this protocol to add support for GitLab, Azure DevOps, etc.
    The first (and currently only) implementation is
    :class:`~mkdocs_to_confluence.sync.github.GitHubReviewClient`.
    """

    def create_review_branch(self, base_branch: str, branch_name: str) -> None:
        """Create *branch_name* from the HEAD of *base_branch*."""
        ...

    def create_pull_request(
        self,
        branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> tuple[int, str]:
        """Open a pull request and return ``(pr_number, pr_node_id)``.

        *pr_node_id* is the platform-specific global ID used for GraphQL
        mutations (GitHub: ``PR_kwDO...``).
        """
        ...

    def post_review_comment(
        self,
        pr_node_id: str,
        path: str,
        body: str,
        line: int | None,
    ) -> None:
        """Post a review thread on the PR.

        *path* is the file path relative to the repository root.
        *line* is the 1-based line number; pass ``None`` for a file-level comment.
        """
        ...

    def get_pr_merge_info(self, pr_number: int) -> tuple[bool, str | None]:
        """Return ``(merged, merge_commit_sha)``."""
        ...
