#!/usr/bin/env python3
"""List open upstream PRs waiting on a reviewer, sorted by reviewer inactivity.

Queries The-OpenROAD-Project/{OpenROAD, OpenROAD-flow-scripts, OpenSTA} for
open non-draft pull requests authored by ``--author`` (default ``@me``), keeps
those where the next move is the reviewer's, and ranks them descending by
expected reviewer-active days elapsed since the ball moved to the reviewer.

CI policy:
  * ``CI-Public/pr-head`` red (or any other completed failing check besides
    ``CI-Public/pr-merge``) means the PR needs action from the author (e.g. a
    merge commit so reviewers do not skip a red ``pr-head``) and is excluded.
  * ``CI-Public/pr-merge`` red while ``pr-head`` is green/pending is kept:
    pushing a merge commit risks turning a green ``pr-head`` red, so waiting
    for a ``pr-merge`` rerun is preferred.

Reviewer activity model:
  Rather than hardcoding country weekends or full-time schedules, each
  reviewer's empirical weekday reaction rate ``p[weekday]`` in ``[0, 1]`` is
  measured from the dates they reviewed, commented on, or merged PRs across the
  three repositories over the preceding ``--weeks`` weeks (default 12 = 84
  days). Expected active days elapsed integrates ``p[weekday]`` over the UTC
  interval ``[waiting_since, now]``.
"""

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import subprocess
import sys
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

OWNER = "The-OpenROAD-Project"

REPOS: Tuple[Tuple[str, str, str], ...] = (
    ("OpenROAD", f"{OWNER}/OpenROAD", "maliberty"),
    ("ORFS", f"{OWNER}/OpenROAD-flow-scripts", "maliberty"),
    ("OpenSTA", f"{OWNER}/OpenSTA", "dsengupta0628"),
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


def has_blocking_check_failure(contexts: Sequence[dict]) -> bool:
    """Return True if any check failed, ignoring ``CI-Public/pr-merge``."""
    for ctx in contexts:
        typename = ctx.get("__typename")
        if typename == "CheckRun":
            name = ctx.get("name") or ""
            if name in IGNORED_FAILING_CHECKS:
                continue
            if ctx.get("status") != "COMPLETED":
                continue
            if ctx.get("conclusion") not in ("SUCCESS", "NEUTRAL", "SKIPPED"):
                return True
        elif typename == "StatusContext":
            name = ctx.get("context") or ""
            if name in IGNORED_FAILING_CHECKS:
                continue
            state = ctx.get("state")
            if state in ("PENDING", "EXPECTED", None):
                continue
            if state != "SUCCESS":
                return True
    return False


def has_unanswered_review_thread(threads: Sequence[dict], author: str) -> bool:
    author_low = author.lower()
    for thread in threads:
        if thread.get("isResolved"):
            continue
        comments = thread.get("comments", {}).get("nodes") or []
        if not comments:
            continue
        last_author = (comments[-1].get("author") or {}).get("login") or ""
        if last_author.lower() != author_low:
            return True
    return False


def waiting_since_for_pr(pr: dict, author: str) -> Optional[datetime]:
    """Return UTC timestamp when the ball moved to the reviewer, or None.

    Returns ``None`` when the PR requires author action (draft, merge conflict,
    red ``pr-head`` / lint check, unresolved review thread, or unanswered human
    review/comment).
    """
    if pr.get("isDraft"):
        return None
    if pr.get("mergeable") == "CONFLICTING":
        return None

    commit_nodes = pr.get("commits", {}).get("nodes") or []
    if commit_nodes:
        last_commit = commit_nodes[-1].get("commit") or {}
        rollup = last_commit.get("statusCheckRollup") or {}
        contexts = rollup.get("contexts", {}).get("nodes") or []
        if has_blocking_check_failure(contexts):
            return None

    threads = pr.get("reviewThreads", {}).get("nodes") or []
    if has_unanswered_review_thread(threads, author):
        return None

    author_low = author.lower()
    created_at = parse_iso(pr["createdAt"])

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

    human_events: List[datetime] = []
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
        elif not is_bot(rev_author):
            if state != "COMMENTED" or body:
                human_events.append(ts)

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
        elif not is_bot(c_author):
            human_events.append(ts)

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
            elif not is_bot(c_author):
                human_events.append(ts)

    if not human_events:
        return max(created_at, last_substantive_commit)

    last_human = max(human_events)
    if last_substantive_commit > last_human:
        return last_substantive_commit

    later_replies = sorted(ts for ts in author_replies if ts > last_human)
    if later_replies:
        return later_replies[0]

    # Human reviewer left feedback/changes-requested with no commit or reply
    # from the author since.
    return None


def resolve_reviewers(pr: dict, author: str, fallback_reviewer: str) -> Tuple[str, ...]:
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

    # 4. Repository default maintainer.
    return (fallback_reviewer,)


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

    # 1. Reviews (within [since_iso, now_iso]) + issue comments + merges,
    #    paginating any stream that hits 100 items before reaching cutoff_date.
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
    target_repos = {repo_full for _, repo_full, _ in REPOS}
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


def evaluate_waiting_prs(
    prs_by_repo: Sequence[Tuple[str, str, str, Sequence[dict]]],
    author: str,
    profiles: Dict[str, ReviewerProfile],
    now: datetime,
    excluded: Set[str],
) -> List[WaitingPR]:
    results: List[WaitingPR] = []
    for repo_short, repo_full, fallback_rev, prs in prs_by_repo:
        repo_name = repo_full.split("/", 1)[1]
        for pr in prs:
            num = int(pr["number"])
            keys = {
                f"{repo_short}#{num}".lower(),
                f"{repo_name}#{num}".lower(),
                f"{repo_full}#{num}".lower(),
            }
            if keys & excluded:
                continue
            wait_since = waiting_since_for_pr(pr, author)
            if wait_since is None:
                continue
            revs = resolve_reviewers(pr, author, fallback_rev)
            rev_profiles = [profiles[r] for r in revs if r in profiles]
            weights = combined_weights(rev_profiles)
            active_d = integrate_active_days(wait_since, now, weights)
            cal_d = max(0.0, (now - wait_since).total_seconds() / 86400.0)
            results.append(
                WaitingPR(
                    repo_short=repo_short,
                    repo_full=repo_full,
                    number=num,
                    title=str(pr["title"]),
                    url=str(pr["url"]),
                    reviewers=revs,
                    waiting_since=wait_since,
                    active_days=active_d,
                    calendar_days=cal_d,
                    days_per_week=sum(weights),
                    used_fallback_schedule=any(p.is_fallback for p in rev_profiles),
                )
            )
    results.sort(key=lambda item: (item.active_days, item.calendar_days), reverse=True)
    return results


def format_plain_table(
    items: Sequence[WaitingPR], profiles: Dict[str, ReviewerProfile]
) -> str:
    lines: List[str] = []
    header = (
        f"{'Active':>7}  {'Cal':>5}  {'PR':<16}  "
        f"{'Reviewer (d/wk)':<28}  {'Since (UTC)':<16}  Title"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for item in items:
        pr_ref = f"{item.repo_short} #{item.number}"
        fb = "*" if item.used_fallback_schedule else ""
        rev_label = f"{','.join(item.reviewers)} ({item.days_per_week:.1f}/wk{fb})"
        since_str = item.waiting_since.strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"{item.active_days:6.2f}d  {item.calendar_days:4.1f}d  "
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


def format_markdown_table(items: Sequence[WaitingPR]) -> str:
    lines = [
        "| Active days | Calendar | PR | Reviewer (obs d/wk) | Waiting since (UTC) | Title |",
        "|---:|---:|---|---|---|---|",
    ]
    for item in items:
        fb = "*" if item.used_fallback_schedule else ""
        pr_cell = f"[{item.repo_short} #{item.number}]({item.url})"
        rev_cell = f"`{'`, `'.join(item.reviewers)}` ({item.days_per_week:.1f}/wk{fb})"
        since_str = item.waiting_since.strftime("%Y-%m-%d %H:%M")
        title_escaped = item.title.replace("|", "\\|")
        lines.append(
            f"| {item.active_days:.2f} d | {item.calendar_days:.1f} d | "
            f"{pr_cell} | {rev_cell} | {since_str} | {title_escaped} |"
        )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="List open OpenROAD/ORFS/OpenSTA PRs where the next move "
        "is the reviewer's, sorted descending by reviewer-active days elapsed."
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
        "--exclude",
        action="append",
        default=[],
        help="Exclude a PR as <repo>#<number> (e.g. ORFS#4771). Repeatable.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Format output as a GitHub Markdown table.",
    )
    args = parser.parse_args(argv)
    if args.weeks < 1:
        parser.error("--weeks must be >= 1")

    now = datetime.now(timezone.utc)
    author = resolve_author_login(args.author)
    excluded = {spec.strip().lower() for spec in args.exclude if spec.strip()}

    prs_by_repo: List[Tuple[str, str, str, List[dict]]] = []
    needed_reviewers: Set[str] = set()

    for repo_short, repo_full, fallback_rev in REPOS:
        prs = fetch_open_prs(repo_full, args.author)
        prs_by_repo.append((repo_short, repo_full, fallback_rev, prs))
        for pr in prs:
            if waiting_since_for_pr(pr, author) is not None:
                needed_reviewers.update(resolve_reviewers(pr, author, fallback_rev))

    profiles = fetch_reviewer_profiles(needed_reviewers, now=now, weeks=args.weeks)
    waiting = evaluate_waiting_prs(
        prs_by_repo=prs_by_repo,
        author=author,
        profiles=profiles,
        now=now,
        excluded=excluded,
    )

    if args.markdown:
        print(format_markdown_table(waiting))
    else:
        print(format_plain_table(waiting, profiles))
    return 0


if __name__ == "__main__":
    sys.exit(main())
