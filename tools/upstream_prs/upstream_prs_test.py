from datetime import date, datetime, timedelta, timezone
import unittest

import upstream_prs as up


def _pr(
    number=100,
    title="fix something",
    created_at="2026-11-18T16:00:00Z",
    is_draft=False,
    mergeable="MERGEABLE",
    commits=None,
    contexts=None,
    reviews=None,
    comments=None,
    threads=None,
    requested_reviewers=None,
):
    if commits is None:
        commits = [("2026-11-18T16:00:00Z", "fix something")]
    commit_nodes = []
    for idx, (dt, headline) in enumerate(commits):
        rollup = None
        if idx == len(commits) - 1 and contexts is not None:
            rollup = {"contexts": {"nodes": contexts}}
        commit_nodes.append(
            {
                "commit": {
                    "committedDate": dt,
                    "messageHeadline": headline,
                    "statusCheckRollup": rollup,
                }
            }
        )
    req_nodes = [
        {"requestedReviewer": {"login": login}} for login in (requested_reviewers or [])
    ]
    return {
        "number": number,
        "title": title,
        "url": f"https://example.invalid/pull/{number}",
        "isDraft": is_draft,
        "createdAt": created_at,
        "mergeable": mergeable,
        "reviewRequests": {"nodes": req_nodes},
        "commits": {"nodes": commit_nodes},
        "reviews": {"nodes": reviews or []},
        "comments": {"nodes": comments or []},
        "reviewThreads": {"nodes": threads or []},
    }


class TestCheckFiltering(unittest.TestCase):

    def test_pr_head_error_excludes_pr_as_author_move(self):
        pr = _pr(
            contexts=[
                {
                    "__typename": "StatusContext",
                    "context": "CI-Public/pr-head",
                    "state": "ERROR",
                },
                {
                    "__typename": "StatusContext",
                    "context": "CI-Public/pr-merge",
                    "state": "SUCCESS",
                },
            ]
        )
        self.assertIsNone(up.waiting_since_for_pr(pr, "alice"))

    def test_pr_merge_error_with_pr_head_green_stays_reviewer_move(self):
        pr = _pr(
            contexts=[
                {
                    "__typename": "StatusContext",
                    "context": "CI-Public/pr-head",
                    "state": "SUCCESS",
                },
                {
                    "__typename": "StatusContext",
                    "context": "CI-Public/pr-merge",
                    "state": "ERROR",
                },
                {
                    "__typename": "CheckRun",
                    "name": "Clang-Tidy-Bazel",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                },
            ]
        )
        self.assertEqual(
            up.waiting_since_for_pr(pr, "alice"),
            up.parse_iso("2026-11-18T16:00:00Z"),
        )

    def test_pending_pr_head_is_not_treated_as_failure(self):
        pr = _pr(
            contexts=[
                {
                    "__typename": "StatusContext",
                    "context": "CI-Public/pr-head",
                    "state": "PENDING",
                },
                {
                    "__typename": "CheckRun",
                    "name": "Mac-Build",
                    "status": "IN_PROGRESS",
                    "conclusion": None,
                },
            ]
        )
        self.assertIsNotNone(up.waiting_since_for_pr(pr, "alice"))

    def test_draft_and_conflicting_are_excluded(self):
        self.assertIsNone(up.waiting_since_for_pr(_pr(is_draft=True), "alice"))
        self.assertIsNone(
            up.waiting_since_for_pr(_pr(mergeable="CONFLICTING"), "alice")
        )

    def test_unresolved_review_thread_not_answered_by_author_excludes(self):
        unresolved = [
            {
                "isResolved": False,
                "comments": {
                    "nodes": [
                        {
                            "author": {"login": "gemini-code-assist[bot]"},
                            "createdAt": "2026-11-19T08:00:00Z",
                            "body": "nit",
                        }
                    ]
                },
            }
        ]
        self.assertIsNone(up.waiting_since_for_pr(_pr(threads=unresolved), "alice"))


class TestInactivityClockStart(unittest.TestCase):

    def test_master_merge_commit_and_ping_do_not_reset_clock(self):
        pr = _pr(
            created_at="2026-11-19T07:30:00Z",
            commits=[
                ("2026-11-19T07:42:00Z", "sdc: hash -to objects"),
                (
                    "2026-11-22T09:34:00Z",
                    "Merge remote-tracking branch 'origin/master' into feat",
                ),
            ],
            comments=[
                {
                    "author": {"login": "alice"},
                    "createdAt": "2026-11-21T10:36:00Z",
                    "body": "@bob Thoughts?",
                },
                {
                    "author": {"login": "alice"},
                    "createdAt": "2026-11-22T09:35:00Z",
                    "body": "/gemini review",
                },
                {
                    "author": {"login": "openroad-ci"},
                    "createdAt": "2026-11-22T10:00:00Z",
                    "body": "QoR check",
                },
            ],
        )
        self.assertEqual(
            up.waiting_since_for_pr(pr, "alice"),
            up.parse_iso("2026-11-19T07:42:00Z"),
        )

    def test_unanswered_human_changes_requested_excludes_pr(self):
        pr = _pr(
            commits=[("2026-11-18T16:00:00Z", "initial")],
            reviews=[
                {
                    "author": {"login": "bob"},
                    "state": "CHANGES_REQUESTED",
                    "submittedAt": "2026-11-19T13:49:00Z",
                    "body": "Please fix LEF handling.",
                }
            ],
        )
        self.assertIsNone(up.waiting_since_for_pr(pr, "alice"))

    def test_substantive_fix_after_human_review_starts_clock_and_ignores_later_ping(
        self,
    ):
        pr = _pr(
            commits=[
                ("2026-11-20T13:25:00Z", "make: delete target"),
                ("2026-11-21T22:42:00Z", "flow: delete helper script"),
            ],
            comments=[
                {
                    "author": {"login": "carol"},
                    "createdAt": "2026-11-21T22:31:00Z",
                    "body": "Why keep helper.sh?",
                },
                {
                    "author": {"login": "alice"},
                    "createdAt": "2026-11-21T22:43:00Z",
                    "body": "Deleted in 8a147b4.",
                },
                {
                    "author": {"login": "alice"},
                    "createdAt": "2026-11-23T06:03:00Z",
                    "body": "@carol Fixed.",
                },
            ],
        )
        self.assertEqual(
            up.waiting_since_for_pr(pr, "alice"),
            up.parse_iso("2026-11-21T22:42:00Z"),
        )

    def test_prose_reply_without_commit_hands_ball_back_once(self):
        pr = _pr(
            commits=[("2026-11-18T10:00:00Z", "initial")],
            comments=[
                {
                    "author": {"login": "bob"},
                    "createdAt": "2026-11-19T09:00:00Z",
                    "body": "Does this affect flat mode?",
                },
                {
                    "author": {"login": "alice"},
                    "createdAt": "2026-11-19T10:15:00Z",
                    "body": "No, only hierarchical mode reaches this branch.",
                },
                {
                    "author": {"login": "alice"},
                    "createdAt": "2026-11-21T08:00:00Z",
                    "body": "@bob gentle ping",
                },
            ],
        )
        self.assertEqual(
            up.waiting_since_for_pr(pr, "alice"),
            up.parse_iso("2026-11-19T10:15:00Z"),
        )


class TestReviewerDiscovery(unittest.TestCase):

    def test_top_reviewer_from_merged_prs_ignores_author_and_bots(self):
        merged = [
            {
                "mergedBy": {"login": "alice"},
                "reviews": {"nodes": [{"author": {"login": "gemini-code-assist"}}]},
            },
            {
                "mergedBy": {"login": "bob"},
                "reviews": {"nodes": [{"author": {"login": "carol"}}]},
            },
            {
                "mergedBy": {"login": "carol"},
                "reviews": {"nodes": []},
            },
        ]
        self.assertEqual(up.top_reviewer_from_merged_prs(merged, "alice"), "carol")

    def test_fetch_reviewer_profiles_unpacks_repos(self):
        def fake_gh(_args):
            return {
                "data": {
                    "u": {
                        "contributionsCollection": {
                            "pullRequestReviewContributions": {
                                "pageInfo": {"hasNextPage": False},
                                "nodes": [
                                    {
                                        "occurredAt": "2026-11-20T12:00:00Z",
                                        "repository": {
                                            "nameWithOwner": "The-OpenROAD-Project/OpenROAD"
                                        },
                                    }
                                ],
                            }
                        },
                        "issueComments": {
                            "pageInfo": {"hasPreviousPage": False},
                            "nodes": [],
                        },
                    },
                    "m": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                }
            }

        now = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)
        profs = up.fetch_reviewer_profiles(["bob"], now=now, weeks=4, gh_runner=fake_gh)
        self.assertEqual(profs["bob"].active_days_observed, 1)


class TestEmpiricalReviewerActivity(unittest.TestCase):

    def test_sun_thu_vs_mon_fri_and_part_time_profiles(self):
        # End on Monday 2026-11-23; 4-week window has 4 of each weekday.
        end = date(2026, 11, 23)
        start_window = end - timedelta(days=27)

        # Reviewer A: active every Sun..Thu (100%), never Fri/Sat (0%).
        sun_thu_dates = set()
        # Reviewer B: active only on 2 of the 4 Tuesdays (50% Tue).
        part_time_dates = set()
        tuesdays = []

        cur = start_window
        while cur <= end:
            if cur.weekday() not in (4, 5):  # not Fri, Sat
                sun_thu_dates.add(cur)
            if cur.weekday() == 1:
                tuesdays.append(cur)
            cur += timedelta(days=1)
        part_time_dates.update(tuesdays[:2])

        sun_thu_prof = up.build_reviewer_profile(
            "rev_a", sun_thu_dates, end_date=end, weeks=4
        )
        pt_prof = up.build_reviewer_profile(
            "rev_b", part_time_dates, end_date=end, weeks=4
        )

        self.assertAlmostEqual(sun_thu_prof.weekday_weights[4], 0.0)  # Fri
        self.assertAlmostEqual(sun_thu_prof.weekday_weights[5], 0.0)  # Sat
        self.assertAlmostEqual(sun_thu_prof.weekday_weights[6], 1.0)  # Sun
        self.assertAlmostEqual(sun_thu_prof.days_per_week, 5.0)

        self.assertAlmostEqual(pt_prof.weekday_weights[1], 0.5)  # Tue
        self.assertAlmostEqual(pt_prof.days_per_week, 0.5)

        # Wait interval: Thu 2026-11-19 12:00Z -> Mon 2026-11-23 12:00Z
        # Spans 0.5 Thu + 1.0 Fri + 1.0 Sat + 1.0 Sun + 0.5 Mon.
        wait_start = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
        now = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)

        # Sun..Thu: 0.5(Thu) + 0(Fri) + 0(Sat) + 1.0(Sun) + 0.5(Mon) = 2.0d
        self.assertAlmostEqual(
            up.integrate_active_days(wait_start, now, sun_thu_prof.weekday_weights),
            2.0,
        )
        # Standard Mon..Fri: 0.5(Thu) + 1.0(Fri) + 0 + 0 + 0.5(Mon) = 2.0d
        self.assertAlmostEqual(
            up.integrate_active_days(wait_start, now, up.DEFAULT_MON_FRI_WEIGHTS),
            2.0,
        )
        # Part-time Tuesday-only reviewer: 0 active days elapsed Thu->Mon!
        self.assertAlmostEqual(
            up.integrate_active_days(wait_start, now, pt_prof.weekday_weights),
            0.0,
        )

    def test_zero_history_uses_mon_fri_fallback(self):
        prof = up.build_reviewer_profile(
            "new_person", set(), end_date=date(2026, 11, 23), weeks=12
        )
        self.assertTrue(prof.is_fallback)
        self.assertEqual(prof.weekday_weights, up.DEFAULT_MON_FRI_WEIGHTS)

    def test_ranking_and_exclude_flag(self):
        now = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)
        profiles = {
            "fast_rev": up.ReviewerProfile("fast_rev", (1, 1, 1, 1, 1, 1, 1), 84, 12.0),
            "rare_rev": up.ReviewerProfile(
                "rare_rev", (0.1, 0.1, 0.1, 0.1, 0.1, 0, 0), 6, 12.0
            ),
        }
        pr_fast = _pr(
            number=10,
            commits=[("2026-11-21T09:00:00Z", "feat a")],
            requested_reviewers=["fast_rev"],
        )
        pr_rare = _pr(
            number=11,
            commits=[("2026-11-18T09:00:00Z", "feat b")],
            requested_reviewers=["rare_rev"],
        )
        pr_excluded = _pr(
            number=99,
            commits=[("2026-11-01T09:00:00Z", "feat c")],
            requested_reviewers=["fast_rev"],
        )

        ranked = up.evaluate_waiting_prs(
            prs_by_repo=[
                (
                    "ORFS",
                    "The-OpenROAD-Project/OpenROAD-flow-scripts",
                    "fast_rev",
                    [pr_fast, pr_rare, pr_excluded],
                )
            ],
            author="alice",
            profiles=profiles,
            now=now,
            excluded={"orfs#99"},
        )
        # pr_fast waited 2d * 1.0 = 2.0 active days; pr_rare waited <0.5 active days.
        self.assertEqual([r.number for r in ranked], [10, 11])

    def test_actionable_excludes_quiet_waiting_and_flags_ping_at_four_days(self):
        now = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)
        profiles = {
            "rev": up.ReviewerProfile("rev", (1, 1, 1, 1, 1, 1, 1), 84, 12.0),
        }
        pr_head_red = _pr(
            number=1,
            title="broken head",
            contexts=[
                {
                    "__typename": "StatusContext",
                    "context": "CI-Public/pr-head",
                    "state": "ERROR",
                }
            ],
            requested_reviewers=["rev"],
        )
        pr_quiet_wait = _pr(
            number=2,
            title="waiting two days",
            commits=[("2026-11-21T09:00:00Z", "feat two")],
            requested_reviewers=["rev"],
        )
        pr_stale_wait = _pr(
            number=3,
            title="waiting five days",
            commits=[("2026-11-18T09:00:00Z", "feat three")],
            requested_reviewers=["rev"],
        )
        repos_data = [
            (
                "OpenROAD",
                "The-OpenROAD-Project/OpenROAD",
                "rev",
                [pr_head_red, pr_quiet_wait, pr_stale_wait],
            )
        ]

        actions = up.evaluate_author_action_prs(repos_data, "alice", set())
        self.assertEqual([a.number for a in actions], [1])
        self.assertIn("CI-Public/pr-head red", actions[0].reasons[0])

        waiting = up.evaluate_waiting_prs(repos_data, "alice", profiles, now, set())
        self.assertEqual([w.number for w in waiting], [3, 2])

        report = up.format_actionable(
            actions, waiting, profiles, ping_days=4.0, markdown=False
        )
        self.assertIn("OpenROAD #1", report)
        self.assertIn("OpenROAD #3", report)
        self.assertIn("[PING]", report)
        self.assertNotIn("OpenROAD #2", report)
        self.assertIn("Excluded 1 PR(s)", report)


if __name__ == "__main__":
    unittest.main()
