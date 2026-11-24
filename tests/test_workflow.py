import argparse
from contextlib import redirect_stdout
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

import assistant
from graph import CoverageError, UTC, stamp


ACCOUNT = "owner@example.invalid"


def party(email):
    return {"emailAddress": {"address": email}}


def disposition(number, **overrides):
    item = {"record_number": number, "action": "no_action", "reason": "no_obligation", "priority": "low",
            "summary": "Synthetic item", "status": "", "existing_key": "", "owner": "", "due": "",
            "blocker": "", "next_step": "", "draft": ""}
    return {**item, **overrides}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.output = io.StringIO()
        self.addCleanup(self.output.close)
        with redirect_stdout(self.output):
            assistant.initialize(self.home)
        self.config = assistant.settings(self.home)
        self.config["work_account"] = ACCOUNT
        assistant.save(self.home / "config.json", self.config)
        self.exports = self.home / "export"
        self.exports.mkdir()
        self.timestamp = stamp(dt.datetime.now(UTC) - dt.timedelta(hours=1))

    def prepare(self, start=None, end=None, recheck=False):
        with redirect_stdout(self.output):
            assistant.prepare(self.home, self.config,
                              argparse.Namespace(start=start, end=end, recheck=recheck, replace=False))
        request = assistant.load(self.home / "pending-request.json")["request"]
        self.assertEqual(assistant.load(self.home / "flow-request.json"), request)
        return request

    def synthetic_exports(self, request, *, change_id=False, wrong_owner=False):
        for feed in request["feeds"]:
            url = feed["url"]
            parts = urlsplit(url)
            query = parse_qs(parts.query)
            filename = f"{request['request_id']}--{feed['key']}"
            if feed["kind"] in {"assigned", "plan"}:
                body = {"value": [{"id": "task-1", "planId": "test-plan", "title": "Synthetic task",
                                   "_assignments": [{"userId": "synthetic-person"}]}]}
            elif parts.path.endswith("/calendar"):
                body = {"owner": {"address": "wrong@example.invalid" if wrong_owner else ACCOUNT}}
            elif parts.path.endswith("/sentitems"):
                body = {"id": "sent"}
            elif parts.path.endswith("/calendarView"):
                body = {"value": []}
            else:
                _, _, start, _, _, _, end = query["$filter"][0].split()
                body = {"value": []}
                if start <= self.timestamp < end:
                    messages = [
                        {"id": "request", "subject": "Synthetic reconciliation request",
                         "from": party("vendor@example.invalid"), "toRecipients": [party(ACCOUNT)],
                         "receivedDateTime": self.timestamp, "sentDateTime": self.timestamp,
                         "bodyPreview": "Please confirm the figures.", "conversationId": "thread-a",
                         "webLink": "https://outlook.office.com/mail/id/request"},
                        {"id": "outgoing", "subject": "Synthetic invite", "from": party(ACCOUNT),
                         "toRecipients": [party("vendor@example.invalid")],
                         "receivedDateTime": self.timestamp, "sentDateTime": self.timestamp,
                         "parentFolderId": "sent", "@odata.type": "#microsoft.graph.eventMessageRequest"},
                    ]
                    if query["$select"] == ["id"]:
                        messages = [{"id": row["id"]} for row in messages]
                        if change_id:
                            messages[1]["id"] = "uncollected"
                    next_url = url + "&%24skip=1"
                    body = {"value": messages[:1], "@odata.nextLink": next_url}
                    assistant.save(self.exports / f"{filename}--2.json",
                                   {"url": next_url, "body": {"value": messages[1:]}})
            assistant.save(self.exports / f"{filename}--1.json", {"url": url, "body": body})

    def import_export(self):
        with redirect_stdout(self.output):
            assistant.import_export(self.home, self.config, self.exports)

    def test_backfill_review_brief_and_duplicate_recheck(self):
        request = self.prepare()
        self.synthetic_exports(request)
        self.import_export()
        directory, manifest = assistant.current_run(self.home)
        self.assertEqual(manifest["by_type"], {"mail.received": 1, "invite.sent": 1})
        self.assertEqual(len(list((self.home / "archive").glob("*.jsonl.gz"))), 1)
        path = next(assistant.pending(self.home, assistant.review_state(self.home)))
        batch = assistant.load(path)
        prompt = assistant.prompt(self.home, path)
        self.assertIn("MY RULES", prompt)
        first_record = next(i for i, row in enumerate(batch["records"], 1) if row["kind"] == "mail")
        action = disposition(first_record, action="provide_information", reason="", priority="high",
                             summary="Confirm the figures", status="open", next_step="Check with Finance")
        invalid = {"batch_id": path.stem, "dispositions": [action, action]}
        with self.assertRaisesRegex(ValueError, "exactly once"):
            assistant.import_result(self.home, json.dumps(invalid))
        self.assertTrue(path.exists())
        valid = {**invalid, "dispositions": [action, disposition(3 - first_record)]}
        with redirect_stdout(self.output):
            assistant.import_result(self.home, json.dumps(valid))
            assistant.brief(self.home, self.config)
        self.assertIn("Confirm the figures", self.output.getvalue())
        self.assertIn("[Source]", self.output.getvalue())
        self.assertFalse(list(assistant.pending(self.home, assistant.review_state(self.home))))

        for recheck in (False, True):
            self.synthetic_exports(self.prepare(manifest["start"], manifest["end"], recheck))
            self.import_export()
            self.assertEqual(assistant.current_run(self.home)[0], directory)
            self.assertEqual(bool(list(assistant.pending(self.home, assistant.review_state(self.home)))), recheck)

    def test_mismatched_id_prevents_checkpoint_even_when_counts_match(self):
        self.synthetic_exports(self.prepare(), change_id=True)
        with self.assertRaisesRegex(CoverageError, "1 missing, 1 extra"):
            self.import_export()
        self.assertIsNone(assistant.current_run(self.home))
        self.assertTrue((self.home / "pending-request.json").exists())
        failure = assistant.load(next((self.home / "failures").glob("*.json")))
        self.assertEqual(failure["coverage"][-1]["missing"], 1)

    def test_missing_page_can_be_retried(self):
        request = self.prepare()
        self.synthetic_exports(request)
        page = next(self.exports.glob("*--2.json"))
        page.unlink()
        with self.assertRaisesRegex(CoverageError, "before all pages"):
            self.import_export()
        self.assertIsNone(assistant.current_run(self.home))
        self.assertEqual(self.prepare(), request)
        self.synthetic_exports(request)
        self.import_export()
        self.assertIsNotNone(assistant.current_run(self.home))
        self.assertFalse((self.home / "pending-request.json").exists())
        self.assertFalse(list((self.home / "failures").glob("*.json")))

    def test_missing_feed_and_wrong_outlook_connection_are_rejected(self):
        request = self.prepare()
        with self.assertRaisesRegex(CoverageError, "Missing .* export feeds"):
            self.import_export()
        self.synthetic_exports(request, wrong_owner=True)
        with self.assertRaisesRegex(CoverageError, "connection does not match"):
            self.import_export()
        self.assertIsNone(assistant.current_run(self.home))

    def test_selected_planner_uses_standard_action_and_assignments(self):
        self.config["planner"] = {"mode": "plans", "plan_ids": ["test-plan"],
                                  "group_ids": {"test-plan": "test-group"}, "user_id": "synthetic-person"}
        request = self.prepare()
        plan_feeds = [feed for feed in request["feeds"] if feed["kind"] == "plan"]
        self.assertEqual([feed["group_id"] for feed in plan_feeds], ["test-group", "test-group"])
        self.synthetic_exports(request)
        self.import_export()
        path = next(assistant.pending(self.home, assistant.review_state(self.home)))
        task = next(row for row in assistant.load(path)["records"] if row["kind"] == "task")
        self.assertTrue(task["assigned_to_me"])
        self.assertEqual(task["assignments"], ["synthetic-person"])
