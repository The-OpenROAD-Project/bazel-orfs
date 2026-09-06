"""Measure who reviews OpenROAD pull requests, and what becomes of them.

Reads the GitHub API through `gh` and writes data.json. No arguments, no
credentials of its own: it borrows whatever `gh auth` already has.

The question is not "how many pull requests are abandoned" -- that number
is easy and uninteresting. It is which kind of attention a pull request
gets before it dies: machine review, human review, or none.

Definitions, stated here because every number below depends on them:

  * A REVIEW THREAD is one inline conversation on a diff line, attributed
    to whoever opened it. Threads, not comments, so a long back-and-forth
    counts once.
  * HUMAN ENGAGEMENT is any review, review thread or issue comment from a
    human who is not the pull request's own author. A pull request with
    zero human engagement is one no person said anything about.
  * A BOT is matched by login substring (see BOTS). This under-counts if a
    new bot appears and over-counts nothing, since the names are distinct.
  * COMMITS AFTER BOT, BEFORE HUMAN counts commits whose committedDate
    falls after the first bot thread and before any human engagement. It
    uses committedDate, which can precede the push, so it UNDER-counts.

Sampling: the N most recently updated pull requests in each state. That is
recency-weighted on purpose -- the question is about how the project works
now -- and it is not a random sample of the year, which is why no
significance test is reported and none should be inferred.
"""

import datetime
import json
import subprocess
import statistics
import sys

OWNER = "The-OpenROAD-Project"
NAME = "OpenROAD"
SAMPLE = 120

BOTS = (
    "gemini-code-assist",
    "github-actions",
    "clang-tidy",
    "openroad-ci",
    "codex",
    "chatgpt-codex-connector",
    "copilot",
    "dependabot",
    "coderabbitai",
)

QUERY = """
query($cursor:String, $states:[PullRequestState!], $owner:String!, $name:String!) {
 repository(owner:$owner, name:$name) {
  pullRequests(states:$states, first:25,
               orderBy:{field:UPDATED_AT, direction:DESC}, after:$cursor) {
   pageInfo { hasNextPage endCursor }
   nodes {
    number createdAt mergedAt closedAt merged
    author { login }
    commits(first:100) { totalCount nodes { commit { committedDate } } }
    reviews(first:60) { nodes { author { login } state submittedAt } }
    comments(first:60) { nodes { author { login } createdAt } }
    reviewThreads(first:60) {
      nodes { comments(first:1) { nodes { author { login } createdAt } } } }
   }
  }
 }
}
"""


def is_bot(login):
    login = (login or "").lower().replace("[bot]", "")
    return any(bot in login for bot in BOTS)


def when(stamp):
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def fetch(states, want):
    nodes, cursor = [], None
    while len(nodes) < want:
        args = [
            "gh",
            "api",
            "graphql",
            "-f",
            "query=" + QUERY,
            "-F",
            "states=" + states,
            "-F",
            "owner=" + OWNER,
            "-F",
            "name=" + NAME,
        ]
        if cursor:
            args += ["-F", "cursor=" + cursor]
        done = subprocess.run(args, capture_output=True, text=True)
        if done.returncode != 0:
            sys.exit("gh api failed: " + done.stderr.strip())
        page = json.loads(done.stdout)["data"]["repository"]["pullRequests"]
        nodes += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return nodes[:want]


def rows_for(nodes):
    rows = []
    for node in nodes:
        author = (node["author"] or {}).get("login", "")
        # Bot-authored pull requests (dependabot, the CI mirror) are a
        # different population and would swamp the human one.
        if is_bot(author):
            continue

        threads = [
            thread["comments"]["nodes"][0]
            for thread in node["reviewThreads"]["nodes"]
            if thread["comments"]["nodes"]
        ]
        bot_threads = [
            t for t in threads if is_bot((t["author"] or {}).get("login", ""))
        ]
        human_threads = [t for t in threads if t not in bot_threads]

        human_reviews = [
            r
            for r in node["reviews"]["nodes"]
            if r["author"] and not is_bot(r["author"]["login"]) and r["submittedAt"]
        ]
        human_comments = [
            c
            for c in node["comments"]["nodes"]
            if c["author"]
            and not is_bot(c["author"]["login"])
            and c["author"]["login"] != author
        ]

        human_events = (
            [when(t["createdAt"]) for t in human_threads]
            + [when(r["submittedAt"]) for r in human_reviews]
            + [when(c["createdAt"]) for c in human_comments]
        )
        bot_events = [when(t["createdAt"]) for t in bot_threads]
        first_human = min(human_events) if human_events else None
        first_bot = min(bot_events) if bot_events else None

        commits = [when(c["commit"]["committedDate"]) for c in node["commits"]["nodes"]]
        after_bot_only = sum(
            1
            for c in commits
            if first_bot and c > first_bot and (not first_human or c < first_human)
        )

        closed = node["mergedAt"] or node["closedAt"]
        rows.append(
            {
                "number": node["number"],
                "merged": node["merged"],
                "bot_threads": len(bot_threads),
                "human_threads": len(human_threads),
                "human_engagement": len(human_events),
                "commits": node["commits"]["totalCount"],
                "commits_after_bot_before_human": after_bot_only,
                "days_open": (
                    ((when(closed) - when(node["createdAt"])).total_seconds() / 86400)
                    if closed
                    else None
                ),
            }
        )
    return rows


def summarise(rows, label):
    total = len(rows)
    bot = sum(r["bot_threads"] for r in rows)
    human = sum(r["human_threads"] for r in rows)
    silent = sum(1 for r in rows if r["human_engagement"] == 0)
    churn = sum(1 for r in rows if r["commits_after_bot_before_human"] > 0)
    days = [r["days_open"] for r in rows if r["days_open"] is not None]
    return {
        "label": label,
        "pull_requests": total,
        "bot_threads": bot,
        "human_threads": human,
        "bot_thread_share": round(bot / max(1, bot + human), 3),
        "zero_human_engagement": silent,
        "zero_human_engagement_share": round(silent / max(1, total), 3),
        "commits_after_bot_before_human": churn,
        "commits_after_bot_before_human_share": round(churn / max(1, total), 3),
        "median_days_open": round(statistics.median(days), 2) if days else None,
    }


def main():
    merged = rows_for(fetch("MERGED", SAMPLE))
    abandoned = rows_for([n for n in fetch("CLOSED", SAMPLE) if not n["merged"]])
    out = {
        "collected": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
        "repository": f"{OWNER}/{NAME}",
        "sample_per_state": SAMPLE,
        "summary": [summarise(merged, "merged"), summarise(abandoned, "abandoned")],
        "rows": {"merged": merged, "abandoned": abandoned},
    }
    with open("data.json", "w") as handle:
        json.dump(out, handle, indent=2)
    for block in out["summary"]:
        print(json.dumps(block, indent=2))


if __name__ == "__main__":
    main()
