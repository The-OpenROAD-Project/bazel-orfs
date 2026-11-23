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
        self.assertIsNone(up.waiting_since_for_pr(pr, "oharboe"))

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
            up.waiting_since_for_pr(pr, "oharboe"),
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
        self.assertIsNotNone(up.waiting_since_for_pr(pr, "oharboe"))

    def test_draft_and_conflicting_are_excluded(self):
        self.assertIsNone(up.waiting_since_for_pr(_pr(is_draft=True), "oharboe"))
        self.assertIsNone(
            up.waiting_since_for_pr(_pr(mergeable="CONFLICTING"), "oharboe")
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
        self.assertIsNone(up.waiting_since_for_pr(_pr(threads=unresolved), "oharboe"))


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
                    "author": {"login": "oharboe"},
                    "createdAt": "2026-11-21T10:36:00Z",
                    "body": "@reviewer Thoughts?",
                },
                {
                    "author": {"login": "oharboe"},
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
            up.waiting_since_for_pr(pr, "oharboe"),
            up.parse_iso("2026-11-19T07:42:00Z"),
        )

    def test_unanswered_human_changes_requested_excludes_pr(self):
        pr = _pr(
            commits=[("2026-11-18T16:00:00Z", "initial")],
            reviews=[
                {
                    "author": {"login": "vvbandeira"},
                    "state": "CHANGES_REQUESTED",
                    "submittedAt": "2026-11-19T13:49:00Z",
                    "body": "Please fix LEF handling.",
                }
            ],
        )
        self.assertIsNone(up.waiting_since_for_pr(pr, "oharboe"))

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
                    "author": {"login": "maliberty"},
                    "createdAt": "2026-11-21T22:31:00Z",
                    "body": "Why keep helper.sh?",
                },
                {
                    "author": {"login": "oharboe"},
                    "createdAt": "2026-11-21T22:43:00Z",
                    "body": "Deleted in 8a147b4.",
                },
                {
                    "author": {"login": "oharboe"},
                    "createdAt": "2026-11-23T06:03:00Z",
                    "body": "@maliberty Fixed.",
                },
            ],
        )
        self.assertEqual(
            up.waiting_since_for_pr(pr, "oharboe"),
            up.parse_iso("2026-11-21T22:42:00Z"),
        )

    def test_prose_reply_without_commit_hands_ball_back_once(self):
        pr = _pr(
            commits=[("2026-11-18T10:00:00Z", "initial")],
            comments=[
                {
                    "author": {"login": "reviewer1"},
                    "createdAt": "2026-11-19T09:00:00Z",
                    "body": "Does this affect flat mode?",
                },
                {
                    "author": {"login": "oharboe"},
                    "createdAt": "2026-11-19T10:15:00Z",
                    "body": "No, only hierarchical mode reaches this branch.",
                },
                {
                    "author": {"login": "oharboe"},
                    "createdAt": "2026-11-21T08:00:00Z",
                    "body": "@reviewer1 gentle ping",
                },
            ],
        )
        self.assertEqual(
            up.waiting_since_for_pr(pr, "oharboe"),
            up.parse_iso("2026-11-19T10:15:00Z"),
        )


class TestEmpiricalReviewerActivity(unittest.TestCase):

    def test_egypt_sun_thu_vs_sat_sun_and_part_time_profiles(self):
        # End on Monday 2026-11-23; 4-week window has 4 of each weekday.
        end = date(2026, 11, 23)
        start_window = end - timedelta(days=27)

        # Reviewer A (Egypt): active every Sun..Thu (100%), never Fri/Sat (0%).
        egypt_dates = set()
        # Reviewer B (Part-time): active only on 2 of the 4 Tuesdays (50% Tue).
        part_time_dates = set()
        tuesdays = []

        cur = start_window
        while cur <= end:
            if cur.weekday() not in (4, 5):  # not Fri, Sat
                egypt_dates.add(cur)
            if cur.weekday() == 1:
                tuesdays.append(cur)
            cur += timedelta(days=1)
        part_time_dates.update(tuesdays[:2])

        egypt_prof = up.build_reviewer_profile(
            "egypt_rev", egypt_dates, end_date=end, weeks=4
        )
        pt_prof = up.build_reviewer_profile(
            "part_time_rev", part_time_dates, end_date=end, weeks=4
        )

        self.assertAlmostEqual(egypt_prof.weekday_weights[4], 0.0)  # Fri
        self.assertAlmostEqual(egypt_prof.weekday_weights[5], 0.0)  # Sat
        self.assertAlmostEqual(egypt_prof.weekday_weights[6], 1.0)  # Sun
        self.assertAlmostEqual(egypt_prof.days_per_week, 5.0)

        self.assertAlmostEqual(pt_prof.weekday_weights[1], 0.5)  # Tue
        self.assertAlmostEqual(pt_prof.days_per_week, 0.5)

        # Wait interval: Thu 2026-11-19 12:00Z -> Mon 2026-11-23 12:00Z
        # Spans 0.5 Thu + 1.0 Fri + 1.0 Sat + 1.0 Sun + 0.5 Mon.
        wait_start = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
        now = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)

        # Egypt: 0.5(Thu) + 0(Fri) + 0(Sat) + 1.0(Sun) + 0.5(Mon) = 2.0d
        self.assertAlmostEqual(
            up.integrate_active_days(wait_start, now, egypt_prof.weekday_weights),
            2.0,
        )
        # Standard Mon-Fri: 0.5(Thu) + 1.0(Fri) + 0 + 0 + 0.5(Mon) = 2.0d
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
            number=4771,
            commits=[("2026-11-01T09:00:00Z", "feat c")],
            requested_reviewers=["fast_rev"],
        )

        ranked = up.evaluate_waiting_prs(
            prs_by_repo=[
                (
                    "ORFS",
                    "The-OpenROAD-Project/OpenROAD-flow-scripts",
                    "maliberty",
                    [pr_fast, pr_rare, pr_excluded],
                )
            ],
            author="oharboe",
            profiles=profiles,
            now=now,
            excluded={"orfs#4771"},
        )
        # pr_fast waited 2d * 1.0 = 2.0 active days; pr_rare waited <0.5 active days.
        self.assertEqual([r.number for r in ranked], [10, 11])


if __name__ == "__main__":
    unittest.main()
