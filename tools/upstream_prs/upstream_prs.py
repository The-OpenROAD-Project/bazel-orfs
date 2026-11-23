#!/usr/bin/env python3
"""Triage and rank open upstream PRs across OpenROAD, ORFS and OpenSTA.

Queries The-OpenROAD-Project/{OpenROAD, OpenROAD-flow-scripts, OpenSTA} for
open non-draft pull requests authored by ``--author`` (default ``@me``).

Modes:
  * Default: list PRs where the next move is the reviewer's, ranked descending
    by expected reviewer-active days elapsed, flagging rows at or above
    ``--ping-days`` (default 4.0) with ``[PING]``.
  * ``--actionable``: exclude PRs where we are merely waiting on the reviewer
    below ``--ping-days``, and show only (1) PRs needing author action and
    (2) reviewer-waiting PRs at or above ``--ping-days`` where a ping may be
    considered.

CI policy:
  * ``CI-Public/pr-head`` red (or any other completed failing check besides
    ``CI-Public/pr-merge``) requires author action (e.g. a merge commit so
    reviewers do not skip a red ``pr-head``).
  * ``CI-Public/pr-merge`` red while ``pr-head`` is green/pending is left
    alone: pushing a merge commit risks turning a green ``pr-head`` red, so
    waiting for a ``pr-merge`` rerun is preferred.

Reviewer activity model:
  Each reviewer's empirical weekday reaction rate ``p[weekday]`` in ``[0, 1]``
  is measured from the dates they reviewed, commented on, or merged PRs across
  the three repositories over the preceding ``--weeks`` weeks (default 12 = 84
  days), capturing regional weekends, weekend-active maintainers, and part-time
  reviewers without hardcoded schedules.
"""

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import subprocess
import sys
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

OWNER = "The-OpenROAD-Project"

REPOS: Tuple[Tuple[str, str], ...] = (
    ("OpenROAD", f"{OWNER}/OpenROAD"),
    ("ORFS", f"{OWNER}/OpenROAD-flow-scripts"),
    ("OpenSTA", f"{OWNER}/OpenSTA"),
)

IGNORED_FAILING_CHECKS = frozenset({"CI-Public/pr-merge"})

BOT_LOGINS = frozenset(
    {
        "claassistant",
        "codecov",
        "copilot",
        "dependabot",
        "gemini-code-assist",
        "github-actions",
        "openroad-ci",
        "readthedocs",
    }
)

DEFAULT_MON_FRI_WEIGHTS: Tuple[float, ...] = (
    1.0,
    1.0,
    1.0,
    1.0,
    1.0,
    0.0,
    0.0,
)

WEEKDAY_NAMES: Tuple[str, ...] = (
    "Mon",
    "Tue",
    "Wed",
    "Thu",
    "Fri",
    "Sat",
    "Sun",
)

DEFAULT_PING_DAYS = 4.0


@dataclass(frozen=True)
class ReviewerProfile:
    login: str
    weekday_weights: Tuple[float, ...]  # Mon=0 .. Sun=6, each in [0, 1]
    active_days_observed: int
    weeks_observed: float
    is_fallback: bool = False

    @property
    def days_per_week(self) -> float:
        return sum(self.weekday_weights)


@dataclass(frozen=True)
class WaitingPR:
    repo_short: str
    repo_full: str
    number: int
    title: str
    url: str
    reviewers: Tuple[str, ...]
    waiting_since: datetime
    active_days: float
    calendar_days: float
    days_per_week: float
    used_fallback_schedule: bool


@dataclass(frozen=True)
class AuthorActionPR:
    repo_short: str
    repo_full: str
    number: int
    title: str
    url: str
    reasons: Tuple[str, ...]


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def is_bot(login: Optional[str]) -> bool:
    if not login:
        return True
    low = login.lower()
    if low.endswith("[bot]") or low.endswith("-bot"):
        return True
    return low in BOT_LOGINS


def is_merge_commit(headline: str) -> bool:
    return headline.lstrip().startswith("Merge ")


def is_command_comment(body: str) -> bool:
    stripped = body.strip()
    return not stripped or stripped.startswith("/")


def failing_checks(contexts: Sequence[dict]) -> List[str]:
    """Return failing check names, ignoring ``CI-Public/pr-merge``."""
    failed: List[str] = []
    for ctx in contexts:
        typename = ctx.get("__typename")
        if typename == "CheckRun":
            name = ctx.get("name") or "check"
            if name in IGNORED_FAILING_CHECKS:
                continue
            if ctx.get("status") != "COMPLETED":
                continue
            if ctx.get("conclusion") not in ("SUCCESS", "NEUTRAL", "SKIPPED"):
                failed.append(name)
        elif typename == "StatusContext":
            name = ctx.get("context") or "status"
            if name in IGNORED_FAILING_CHECKS:
                continue
            state = ctx.get("state")
            if state in ("PENDING", "EXPECTED", None):
                continue
            if state != "SUCCESS":
                failed.append(name)
    return failed


def has_blocking_check_failure(contexts: Sequence[dict]) -> bool:
    """Return True if any check failed, ignoring ``CI-Public/pr-merge``."""
    return bool(failing_checks(contexts))


def unanswered_review_thread_count(threads: Sequence[dict], author: str) -> int:
    author_low = author.lower()
    count = 0
    for thread in threads:
        if thread.get("isResolved"):
            continue
        comments = thread.get("comments", {}).get("nodes") or []
        if not comments:
            continue
        last_author = (comments[-1].get("author") or {}).get("login") or ""
        if last_author.lower() != author_low:
            count += 1
    return count


def has_unanswered_review_thread(threads: Sequence[dict], author: str) -> bool:
    return unanswered_review_thread_count(threads, author) > 0


def author_action_reasons(pr: dict, author: str) -> Tuple[str, ...]:
    """Return reasons the next move on ``pr`` belongs to ``author``.

    Returns an empty tuple for drafts (not ready for review) and for PRs where
    the next move is the reviewer's.
    """
    if pr.get("isDraft"):
        return ()

    reasons: List[str] = []
    if pr.get("mergeable") == "CONFLICTING":
        reasons.append("merge conflict")

    commit_nodes = pr.get("commits", {}).get("nodes") or []
    if commit_nodes:
        last_commit = commit_nodes[-1].get("commit") or {}
        rollup = last_commit.get("statusCheckRollup") or {}
        contexts = rollup.get("contexts", {}).get("nodes") or []
        for check_name in failing_checks(contexts):
            if check_name == "CI-Public/pr-head":
                reasons.append("CI-Public/pr-head red (needs merge commit)")
            else:
                reasons.append(f"check failed: {check_name}")

    threads = pr.get("reviewThreads", {}).get("nodes") or []
    unresolved_cnt = unanswered_review_thread_count(threads, author)
    if unresolved_cnt:
        reasons.append(f"unresolved review thread ({unresolved_cnt})")

    # Check for unanswered human review/comment.
    _, unanswered_by = _timeline_waiting_state(pr, author)
    if unanswered_by is not None:
        reasons.append(f"unanswered feedback from {unanswered_by}")

    return tuple(reasons)


def _timeline_waiting_state(
    pr: dict, author: str
) -> Tuple[Optional[datetime], Optional[str]]:
    """Return ``(waiting_since, unanswered_human_login)`` from PR events."""
    author_low = author.lower()
    created_at = parse_iso(pr["createdAt"])
    commit_nodes = pr.get("commits", {}).get("nodes") or []
    threads = pr.get("reviewThreads", {}).get("nodes") or []

    substantive_commits: List[datetime] = []
    for node in commit_nodes:
        commit = node.get("commit") or {}
        headline = commit.get("messageHeadline") or ""
        committed = commit.get("committedDate")
        if committed and not is_merge_commit(headline):
            substantive_commits.append(parse_iso(committed))
    last_substantive_commit = (
        max(substantive_commits) if substantive_commits else created_at
    )

    human_events: List[Tuple[datetime, str]] = []
    author_replies: List[datetime] = []

    for rev in pr.get("reviews", {}).get("nodes") or []:
        rev_author = (rev.get("author") or {}).get("login")
        submitted = rev.get("submittedAt")
        state = rev.get("state") or ""
        body = (rev.get("body") or "").strip()
        if not submitted or state == "PENDING":
            continue
        ts = parse_iso(submitted)
        if rev_author and rev_author.lower() == author_low:
            if body and not is_command_comment(body):
                author_replies.append(ts)
        elif rev_author and not is_bot(rev_author):
            if state != "COMMENTED" or body:
                human_events.append((ts, rev_author))

    for comment in pr.get("comments", {}).get("nodes") or []:
        c_author = (comment.get("author") or {}).get("login")
        created = comment.get("createdAt")
        body = comment.get("body") or ""
        if not created:
            continue
        ts = parse_iso(created)
        if c_author and c_author.lower() == author_low:
            if not is_command_comment(body):
                author_replies.append(ts)
        elif c_author and not is_bot(c_author):
            human_events.append((ts, c_author))

    for thread in threads:
        for comment in thread.get("comments", {}).get("nodes") or []:
            c_author = (comment.get("author") or {}).get("login")
            created = comment.get("createdAt")
            body = comment.get("body") or ""
            if not created:
                continue
            ts = parse_iso(created)
            if c_author and c_author.lower() == author_low:
                if not is_command_comment(body):
                    author_replies.append(ts)
            elif c_author and not is_bot(c_author):
                human_events.append((ts, c_author))

    if not human_events:
        return max(created_at, last_substantive_commit), None

    last_human_ts, last_human_login = max(human_events, key=lambda item: item[0])
    if last_substantive_commit > last_human_ts:
        return last_substantive_commit, None

    later_replies = sorted(ts for ts in author_replies if ts > last_human_ts)
    if later_replies:
        return later_replies[0], None

    return None, last_human_login


def waiting_since_for_pr(pr: dict, author: str) -> Optional[datetime]:
    """Return UTC timestamp when the ball moved to the reviewer, or None."""
    if pr.get("isDraft"):
        return None
    if author_action_reasons(pr, author):
        return None
    waiting_since, _ = _timeline_waiting_state(pr, author)
    return waiting_since


def resolve_reviewers(
    pr: dict, author: str, fallback_reviewer: Optional[str] = None
) -> Tuple[str, ...]:
    """Identify the human reviewer(s) whose move the PR is waiting on."""
    author_low = author.lower()

    # 1. Any reviewer currently holding a CHANGES_REQUESTED review is the
    #    explicit blocker until they re-review.
    latest_state_by_user: Dict[str, str] = {}
    casing: Dict[str, str] = {}
    for rev in pr.get("reviews", {}).get("nodes") or []:
        login = (rev.get("author") or {}).get("login")
        state = rev.get("state") or ""
        if (
            not login
            or is_bot(login)
            or login.lower() == author_low
            or state in ("PENDING", "COMMENTED")
        ):
            continue
        casing[login.lower()] = login
        latest_state_by_user[login.lower()] = state

    blockers = [
        casing[u] for u, st in latest_state_by_user.items() if st == "CHANGES_REQUESTED"
    ]
    if blockers:
        return tuple(blockers)

    # 2. Individual users in reviewRequests (ignoring team slugs).
    requested: List[str] = []
    for node in pr.get("reviewRequests", {}).get("nodes") or []:
        req = node.get("requestedReviewer") or {}
        login = req.get("login")
        if (
            login
            and not is_bot(login)
            and login.lower() != author_low
            and login not in requested
        ):
            requested.append(login)
    if requested:
        return tuple(requested)

    # 3. Most recent human reviewer/commenter on the PR.
    recent_humans: List[Tuple[datetime, str]] = []
    for rev in pr.get("reviews", {}).get("nodes") or []:
        login = (rev.get("author") or {}).get("login")
        ts = rev.get("submittedAt")
        if login and ts and not is_bot(login) and login.lower() != author_low:
            recent_humans.append((parse_iso(ts), login))
    for comment in pr.get("comments", {}).get("nodes") or []:
        login = (comment.get("author") or {}).get("login")
        ts = comment.get("createdAt")
        if login and ts and not is_bot(login) and login.lower() != author_low:
            recent_humans.append((parse_iso(ts), login))
    if recent_humans:
        recent_humans.sort(key=lambda item: item[0], reverse=True)
        return (recent_humans[0][1],)

    # 4. Discovered active maintainer of the repository (if any).
    if fallback_reviewer:
        return (fallback_reviewer,)
    return ()


def build_reviewer_profile(
    login: str,
    active_dates: Set[date],
    end_date: date,
    weeks: int = 12,
    effective_start_date: Optional[date] = None,
) -> ReviewerProfile:
    """Compute empirical weekday weights ``p[0..6]`` over the window."""
    window_start = end_date - timedelta(days=weeks * 7 - 1)
    start = (
        max(window_start, effective_start_date)
        if effective_start_date is not None
        else window_start
    )
    if start > end_date:
        start = end_date

    denom = [0] * 7
    cur = start
    while cur <= end_date:
        denom[cur.weekday()] += 1
        cur += timedelta(days=1)

    in_window = {d for d in active_dates if start <= d <= end_date}
    if not in_window:
        return ReviewerProfile(
            login=login,
            weekday_weights=DEFAULT_MON_FRI_WEIGHTS,
            active_days_observed=0,
            weeks_observed=(end_date - start + timedelta(days=1)).days / 7.0,
            is_fallback=True,
        )

    counts = [0] * 7
    for d in in_window:
        counts[d.weekday()] += 1

    weights = tuple(
        (counts[wd] / denom[wd]) if denom[wd] > 0 else 0.0 for wd in range(7)
    )
    return ReviewerProfile(
        login=login,
        weekday_weights=weights,
        active_days_observed=len(in_window),
        weeks_observed=(end_date - start + timedelta(days=1)).days / 7.0,
        is_fallback=False,
    )


def integrate_active_days(
    start: datetime, end: datetime, weekday_weights: Sequence[float]
) -> float:
    """Integrate ``weekday_weights[weekday]`` over UTC ``[start, end]``."""
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    if end_utc <= start_utc:
        return 0.0

    total_days = 0.0
    cur = start_utc
    while cur < end_utc:
        next_midnight = (cur + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        step_end = min(next_midnight, end_utc)
        frac = (step_end - cur).total_seconds() / 86400.0
        total_days += frac * weekday_weights[cur.weekday()]
        cur = step_end
    return total_days


def combined_weights(profiles: Sequence[ReviewerProfile]) -> Tuple[float, ...]:
    """Mean weekday weight across assigned reviewers on a PR."""
    if not profiles:
        return DEFAULT_MON_FRI_WEIGHTS
    n = len(profiles)
    return tuple(sum(p.weekday_weights[wd] for p in profiles) / n for wd in range(7))


# --- GitHub CLI queries -----------------------------------------------------

_PR_FRAGMENT = """
fragment PRFields on PullRequest {
  number
  title
  url
  isDraft
  createdAt
  mergeable
  reviewRequests(first: 15) {
    nodes {
      requestedReviewer {
        ... on User { login }
      }
    }
  }
  commits(last: 25) {
    nodes {
      commit {
        committedDate
        messageHeadline
        statusCheckRollup {
          contexts(first: 100) {
            nodes {
              __typename
              ... on CheckRun {
                name
                status
                conclusion
              }
              ... on StatusContext {
                context
                state
              }
            }
          }
        }
      }
    }
  }
  comments(last: 50) {
    nodes {
      author { login }
      createdAt
      body
    }
  }
  reviews(last: 50) {
    nodes {
      author { login }
      state
      submittedAt
      body
    }
  }
  reviewThreads(first: 100) {
    nodes {
      isResolved
      comments(last: 10) {
        nodes {
          author { login }
          createdAt
          body
        }
      }
    }
  }
}
"""


def run_gh_json(args: Sequence[str]) -> object:
    out = subprocess.check_output(["gh", *args], text=True)
    return json.loads(out)


def resolve_author_login(
    author_arg: str, gh_runner: Callable[[Sequence[str]], object] = run_gh_json
) -> str:
    if author_arg != "@me":
        return author_arg
    user = gh_runner(["api", "user"])
    assert isinstance(user, dict)
    return str(user["login"])


def discover_repo_default_reviewer(
    repo_full: str,
    author: str,
    gh_runner: Callable[[Sequence[str]], object] = run_gh_json,
) -> Optional[str]:
    """Infer a repository's most active recent merger/reviewer dynamically."""
    owner, name = repo_full.split("/", 1)
    query = f"""
    query {{
      repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{
        pullRequests(
          states: MERGED,
          first: 25,
          orderBy: {{field: UPDATED_AT, direction: DESC}}
        ) {{
          nodes {{
            mergedBy {{ login }}
            reviews(last: 10) {{
              nodes {{ author {{ login }} }}
            }}
          }}
        }}
      }}
    }}
    """
    resp = gh_runner(["api", "graphql", "-f", f"query={query}"])
    assert isinstance(resp, dict)
    nodes = resp["data"]["repository"]["pullRequests"]["nodes"] or []
    return top_reviewer_from_merged_prs(nodes, author)


def top_reviewer_from_merged_prs(
    merged_pr_nodes: Sequence[dict], author: str
) -> Optional[str]:
    """Pick the human login with the most recent merge/review actions."""
    author_low = author.lower()
    counts: Counter = Counter()
    casing: Dict[str, str] = {}
    for pr in merged_pr_nodes:
        if not pr:
            continue
        merger = (pr.get("mergedBy") or {}).get("login")
        if merger and not is_bot(merger) and merger.lower() != author_low:
            counts[merger.lower()] += 1
            casing.setdefault(merger.lower(), merger)
        seen_in_pr: Set[str] = set()
        for rev in pr.get("reviews", {}).get("nodes") or []:
            login = (rev.get("author") or {}).get("login")
            if login and not is_bot(login) and login.lower() != author_low:
                seen_in_pr.add(login.lower())
                casing.setdefault(login.lower(), login)
        for low in seen_in_pr:
            counts[low] += 1
    if not counts:
        return None
    best_low = max(counts.items(), key=lambda item: item[1])[0]
    return casing[best_low]


def fetch_open_prs(
    repo_full: str,
    author_arg: str,
    gh_runner: Callable[[Sequence[str]], object] = run_gh_json,
) -> List[dict]:
    """Fetch full PR nodes in small GraphQL batches to avoid 502s."""
    listing = gh_runner(
        [
            "pr",
            "list",
            "-R",
            repo_full,
            "--author",
            author_arg,
            "--state",
            "open",
            "--limit",
            "100",
            "--json",
            "number",
        ]
    )
    assert isinstance(listing, list)
    numbers = sorted(int(item["number"]) for item in listing)
    if not numbers:
        return []

    owner, name = repo_full.split("/", 1)
    prs: List[dict] = []
    for idx in range(0, len(numbers), 5):
        batch = numbers[idx : idx + 5]
        fields = "\n".join(
            f"pr{n}: pullRequest(number: {n}) {{ ...PRFields }}" for n in batch
        )
        query = (
            f"{_PR_FRAGMENT}\n"
            f"query {{ repository(owner: {json.dumps(owner)}, "
            f"name: {json.dumps(name)}) {{\n{fields}\n}} }}"
        )
        resp = gh_runner(["api", "graphql", "-f", f"query={query}"])
        assert isinstance(resp, dict)
        repo_node = resp["data"]["repository"]
        for n in batch:
            if repo_node.get(f"pr{n}"):
                prs.append(repo_node[f"pr{n}"])
    return prs


def _collect_paginated_dates(
    login: str,
    target_repos: Set[str],
    cutoff_date: date,
    now: datetime,
    gh_runner: Callable[[Sequence[str]], object],
    max_pages: int = 4,
) -> Tuple[Set[date], Optional[date]]:
    """Fetch PR reaction dates for ``login`` across ``target_repos``."""
    since_iso = datetime.combine(
        cutoff_date, datetime.min.time(), tzinfo=timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    repo_filter = " ".join(f"repo:{r}" for r in sorted(target_repos))
    merge_query = (
        f"{repo_filter} is:pr merged:>={cutoff_date.isoformat()} " f"merged-by:{login}"
    )

    dates: Set[date] = set()
    truncated_boundaries: List[date] = []

    rev_cursor: Optional[str] = None
    ic_cursor: Optional[str] = None
    m_cursor: Optional[str] = None
    need_rev = True
    need_ic = True
    need_m = True

    for page in range(max_pages):
        if not (need_rev or need_ic or need_m):
            break
        parts: List[str] = []
        user_fields: List[str] = []
        if need_rev:
            after_arg = f", after: {json.dumps(rev_cursor)}" if rev_cursor else ""
            user_fields.append(
                f"contributionsCollection(from: {json.dumps(since_iso)}, "
                f"to: {json.dumps(now_iso)}) {{\n"
                f"  pullRequestReviewContributions(first: 100{after_arg}) {{\n"
                f"    pageInfo {{ hasNextPage endCursor }}\n"
                f"    nodes {{ occurredAt repository {{ nameWithOwner }} }}\n"
                f"  }}\n"
                f"}}"
            )
        if need_ic:
            before_arg = f", before: {json.dumps(ic_cursor)}" if ic_cursor else ""
            user_fields.append(
                f"issueComments(last: 100{before_arg}) {{\n"
                f"  pageInfo {{ hasPreviousPage startCursor }}\n"
                f"  nodes {{ createdAt repository {{ nameWithOwner }} }}\n"
                f"}}"
            )
        if user_fields:
            parts.append(
                f"u: user(login: {json.dumps(login)}) {{\n"
                + "\n".join(user_fields)
                + "\n}"
            )
        if need_m:
            after_m = f", after: {json.dumps(m_cursor)}" if m_cursor else ""
            parts.append(
                f"m: search(type: ISSUE, query: {json.dumps(merge_query)}, "
                f"first: 100{after_m}) {{\n"
                f"  pageInfo {{ hasNextPage endCursor }}\n"
                f"  nodes {{ ... on PullRequest {{ mergedAt }} }}\n"
                f"}}"
            )

        query = "query {\n" + "\n".join(parts) + "\n}"
        resp = gh_runner(["api", "graphql", "-f", f"query={query}"])
        assert isinstance(resp, dict)
        data = resp["data"]
        u_node = data.get("u") or {}

        if need_rev:
            rc = (u_node.get("contributionsCollection") or {}).get(
                "pullRequestReviewContributions"
            ) or {}
            rc_nodes = rc.get("nodes") or []
            oldest_rev: Optional[date] = None
            for item in rc_nodes:
                if not item:
                    continue
                dt = parse_iso(item["occurredAt"]).date()
                oldest_rev = dt if oldest_rev is None else min(oldest_rev, dt)
                if item["repository"]["nameWithOwner"] in target_repos:
                    dates.add(dt)
            pi = rc.get("pageInfo") or {}
            if pi.get("hasNextPage") and oldest_rev and oldest_rev > cutoff_date:
                rev_cursor = pi.get("endCursor")
                if page == max_pages - 1:
                    truncated_boundaries.append(oldest_rev)
            else:
                need_rev = False

        if need_ic:
            ic = u_node.get("issueComments") or {}
            ic_nodes = ic.get("nodes") or []
            oldest_ic: Optional[date] = None
            for item in ic_nodes:
                if not item:
                    continue
                dt = parse_iso(item["createdAt"]).date()
                oldest_ic = dt if oldest_ic is None else min(oldest_ic, dt)
                if item["repository"]["nameWithOwner"] in target_repos:
                    dates.add(dt)
            pi = ic.get("pageInfo") or {}
            if pi.get("hasPreviousPage") and oldest_ic and oldest_ic > cutoff_date:
                ic_cursor = pi.get("startCursor")
                if page == max_pages - 1:
                    truncated_boundaries.append(oldest_ic)
            else:
                need_ic = False

        if need_m:
            mc = data.get("m") or {}
            mc_nodes = mc.get("nodes") or []
            oldest_m: Optional[date] = None
            for item in mc_nodes:
                if not item or not item.get("mergedAt"):
                    continue
                dt = parse_iso(item["mergedAt"]).date()
                oldest_m = dt if oldest_m is None else min(oldest_m, dt)
                dates.add(dt)
            pi = mc.get("pageInfo") or {}
            if pi.get("hasNextPage") and oldest_m and oldest_m > cutoff_date:
                m_cursor = pi.get("endCursor")
                if page == max_pages - 1:
                    truncated_boundaries.append(oldest_m)
            else:
                need_m = False

    effective_start = max(truncated_boundaries) if truncated_boundaries else None
    return dates, effective_start


def fetch_reviewer_profiles(
    reviewers: Iterable[str],
    now: datetime,
    weeks: int = 12,
    gh_runner: Callable[[Sequence[str]], object] = run_gh_json,
) -> Dict[str, ReviewerProfile]:
    target_repos = {repo_full for _, repo_full in REPOS}
    end_date = now.astimezone(timezone.utc).date()
    cutoff_date = end_date - timedelta(days=weeks * 7 - 1)

    profiles: Dict[str, ReviewerProfile] = {}
    for login in sorted(set(reviewers), key=str.lower):
        active_dates, eff_start = _collect_paginated_dates(
            login=login,
            target_repos=target_repos,
            cutoff_date=cutoff_date,
            now=now,
            gh_runner=gh_runner,
        )
        profiles[login] = build_reviewer_profile(
            login=login,
            active_dates=active_dates,
            end_date=end_date,
            weeks=weeks,
            effective_start_date=eff_start,
        )
    return profiles


def _is_excluded(
    repo_short: str, repo_full: str, number: int, excluded: Set[str]
) -> bool:
    repo_name = repo_full.split("/", 1)[1]
    keys = {
        f"{repo_short}#{number}".lower(),
        f"{repo_name}#{number}".lower(),
        f"{repo_full}#{number}".lower(),
    }
    return bool(keys & excluded)


def evaluate_author_action_prs(
    prs_by_repo: Sequence[Tuple[str, str, Optional[str], Sequence[dict]]],
    author: str,
    excluded: Set[str],
) -> List[AuthorActionPR]:
    results: List[AuthorActionPR] = []
    for repo_short, repo_full, _, prs in prs_by_repo:
        for pr in prs:
            num = int(pr["number"])
            if _is_excluded(repo_short, repo_full, num, excluded):
                continue
            reasons = author_action_reasons(pr, author)
            if reasons:
                results.append(
                    AuthorActionPR(
                        repo_short=repo_short,
                        repo_full=repo_full,
                        number=num,
                        title=str(pr["title"]),
                        url=str(pr["url"]),
                        reasons=reasons,
                    )
                )
    return results


def evaluate_waiting_prs(
    prs_by_repo: Sequence[Tuple[str, str, Optional[str], Sequence[dict]]],
    author: str,
    profiles: Dict[str, ReviewerProfile],
    now: datetime,
    excluded: Set[str],
) -> List[WaitingPR]:
    results: List[WaitingPR] = []
    for repo_short, repo_full, fallback_rev, prs in prs_by_repo:
        for pr in prs:
            num = int(pr["number"])
            if _is_excluded(repo_short, repo_full, num, excluded):
                continue
            wait_since = waiting_since_for_pr(pr, author)
            if wait_since is None:
                continue
            revs = resolve_reviewers(pr, author, fallback_rev)
            rev_profiles = [profiles[r] for r in revs if r in profiles]
            weights = combined_weights(rev_profiles)
            active_d = integrate_active_days(wait_since, now, weights)
            cal_d = max(0.0, (now - wait_since).total_seconds() / 86400.0)
            used_fb = (not rev_profiles) or any(p.is_fallback for p in rev_profiles)
            results.append(
                WaitingPR(
                    repo_short=repo_short,
                    repo_full=repo_full,
                    number=num,
                    title=str(pr["title"]),
                    url=str(pr["url"]),
                    reviewers=revs or ("unassigned",),
                    waiting_since=wait_since,
                    active_days=active_d,
                    calendar_days=cal_d,
                    days_per_week=sum(weights),
                    used_fallback_schedule=used_fb,
                )
            )
    results.sort(key=lambda item: (item.active_days, item.calendar_days), reverse=True)
    return results


def format_plain_table(
    items: Sequence[WaitingPR],
    profiles: Dict[str, ReviewerProfile],
    ping_days: float = DEFAULT_PING_DAYS,
) -> str:
    lines: List[str] = []
    header = (
        f"{'Active':>7}  {'Cal':>5}  {'Flag':<6}  {'PR':<16}  "
        f"{'Reviewer (d/wk)':<28}  {'Since (UTC)':<16}  Title"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for item in items:
        pr_ref = f"{item.repo_short} #{item.number}"
        flag = "[PING]" if item.active_days >= ping_days else ""
        fb = "*" if item.used_fallback_schedule else ""
        rev_label = f"{','.join(item.reviewers)} ({item.days_per_week:.1f}/wk{fb})"
        since_str = item.waiting_since.strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"{item.active_days:6.2f}d  {item.calendar_days:4.1f}  {flag:<6}  "
            f"{pr_ref:<16}  {rev_label:<28}  {since_str}  {item.title}"
        )

    seen_revs = sorted(
        {r for item in items for r in item.reviewers if r in profiles},
        key=str.lower,
    )
    if seen_revs:
        lines.append("")
        lines.append("Observed reviewer PR-reaction rates (Mon..Sun):")
        for login in seen_revs:
            prof = profiles[login]
            bars = " ".join(
                f"{WEEKDAY_NAMES[i]}:{prof.weekday_weights[i]:.2f}" for i in range(7)
            )
            fb_note = " [fallback Mon-Fri]" if prof.is_fallback else ""
            lines.append(
                f"  {login:<20} {prof.days_per_week:4.1f}d/wk "
                f"({prof.active_days_observed}d/{prof.weeks_observed:.1f}wk): "
                f"{bars}{fb_note}"
            )
    return "\n".join(lines)


def format_markdown_table(
    items: Sequence[WaitingPR], ping_days: float = DEFAULT_PING_DAYS
) -> str:
    lines = [
        "| Active days | Calendar | Flag | PR | Reviewer (obs d/wk) | Waiting since (UTC) | Title |",
        "|---:|---:|---|---|---|---|---|",
    ]
    for item in items:
        flag = "`PING`" if item.active_days >= ping_days else ""
        fb = "*" if item.used_fallback_schedule else ""
        pr_cell = f"[{item.repo_short} #{item.number}]({item.url})"
        rev_cell = f"`{'`, `'.join(item.reviewers)}` ({item.days_per_week:.1f}/wk{fb})"
        since_str = item.waiting_since.strftime("%Y-%m-%d %H:%M")
        title_escaped = item.title.replace("|", "\\|")
        lines.append(
            f"| {item.active_days:.2f} d | {item.calendar_days:.1f} d | {flag} | "
            f"{pr_cell} | {rev_cell} | {since_str} | {title_escaped} |"
        )
    return "\n".join(lines)


def format_actionable(
    author_actions: Sequence[AuthorActionPR],
    waiting: Sequence[WaitingPR],
    profiles: Dict[str, ReviewerProfile],
    ping_days: float = DEFAULT_PING_DAYS,
    markdown: bool = False,
) -> str:
    pingable = [item for item in waiting if item.active_days >= ping_days]
    quiet_count = len(waiting) - len(pingable)

    if not author_actions and not pingable:
        return (
            f"No actionable PRs ({quiet_count} waiting on reviewers, "
            f"all < {ping_days:.1f} active days)."
        )

    sections: List[str] = []
    if author_actions:
        if markdown:
            rows = [
                "### Author's move",
                "",
                "| PR | Action needed | Title |",
                "|---|---|---|",
            ]
            for a in author_actions:
                pr_cell = f"[{a.repo_short} #{a.number}]({a.url})"
                why = "; ".join(a.reasons).replace("|", "\\|")
                title_esc = a.title.replace("|", "\\|")
                rows.append(f"| {pr_cell} | {why} | {title_esc} |")
            sections.append("\n".join(rows))
        else:
            rows = ["Author's move:"]
            for a in author_actions:
                pr_ref = f"{a.repo_short} #{a.number}"
                rows.append(f"  {pr_ref:<16}  {'; '.join(a.reasons)}  — {a.title}")
            sections.append("\n".join(rows))

    if pingable:
        if markdown:
            sections.append(
                f"### Ping candidates (>= {ping_days:.1f} active days)\n\n"
                + format_markdown_table(pingable, ping_days=ping_days)
            )
        else:
            sections.append(
                f"Ping candidates (>= {ping_days:.1f} active days):\n"
                + format_plain_table(pingable, profiles, ping_days=ping_days)
            )

    if quiet_count:
        sections.append(
            f"(Excluded {quiet_count} PR(s) waiting on reviewers < {ping_days:.1f} active days.)"
        )
    return "\n\n".join(sections)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="List or triage open OpenROAD/ORFS/OpenSTA PRs using "
        "empirical reviewer PR-reaction rates."
    )
    parser.add_argument(
        "--author",
        default="@me",
        help="GitHub login of PR author (default: @me).",
    )
    parser.add_argument(
        "--weeks",
        type=int,
        default=12,
        help="Lookback window in weeks for reviewer PR reaction rates "
        "(default: 12).",
    )
    parser.add_argument(
        "--ping-days",
        type=float,
        default=DEFAULT_PING_DAYS,
        help="Active-days threshold to flag a waiting PR as a ping candidate "
        f"(default: {DEFAULT_PING_DAYS}).",
    )
    parser.add_argument(
        "--actionable",
        action="store_true",
        help="Exclude PRs waiting on reviewers below --ping-days; show only "
        "PRs needing author action and >= --ping-days ping candidates.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Exclude a PR as <repo>#<number> (e.g. ORFS#123). Repeatable.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Format output as GitHub Markdown.",
    )
    args = parser.parse_args(argv)
    if args.weeks < 1:
        parser.error("--weeks must be >= 1")
    if args.ping_days < 0:
        parser.error("--ping-days must be >= 0")

    now = datetime.now(timezone.utc)
    author = resolve_author_login(args.author)
    excluded = {spec.strip().lower() for spec in args.exclude if spec.strip()}

    prs_by_repo: List[Tuple[str, str, Optional[str], List[dict]]] = []
    needed_reviewers: Set[str] = set()

    for repo_short, repo_full in REPOS:
        prs = fetch_open_prs(repo_full, args.author)
        waiting_prs = [pr for pr in prs if waiting_since_for_pr(pr, author) is not None]
        needs_fallback = any(
            not resolve_reviewers(pr, author, None) for pr in waiting_prs
        )
        fallback_rev = (
            discover_repo_default_reviewer(repo_full, author)
            if needs_fallback
            else None
        )
        prs_by_repo.append((repo_short, repo_full, fallback_rev, prs))
        for pr in waiting_prs:
            needed_reviewers.update(resolve_reviewers(pr, author, fallback_rev))

    profiles = fetch_reviewer_profiles(needed_reviewers, now=now, weeks=args.weeks)
    waiting = evaluate_waiting_prs(
        prs_by_repo=prs_by_repo,
        author=author,
        profiles=profiles,
        now=now,
        excluded=excluded,
    )

    if args.actionable:
        author_actions = evaluate_author_action_prs(
            prs_by_repo=prs_by_repo, author=author, excluded=excluded
        )
        print(
            format_actionable(
                author_actions=author_actions,
                waiting=waiting,
                profiles=profiles,
                ping_days=args.ping_days,
                markdown=args.markdown,
            )
        )
    elif args.markdown:
        print(format_markdown_table(waiting, ping_days=args.ping_days))
    else:
        print(format_plain_table(waiting, profiles, ping_days=args.ping_days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
