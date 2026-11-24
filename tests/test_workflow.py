import argparse
from contextlib import redirect_stdout
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest

import assistant
from graph import CoverageError, GRAPH, UTC, reconcile, stamp


def party(email):
    return {"emailAddress": {"address": email}}


class FakeGraph:
    fail = False
    account = "owner@example.invalid"

    def __init__(self, config):
        now = dt.datetime.now(UTC)
        timestamp = stamp(now - dt.timedelta(hours=1))
        self.messages = [
            {"id": "request", "subject": "Synthetic reconciliation request", "from": party("vendor@example.invalid"),
             "toRecipients": [party(self.account)], "receivedDateTime": timestamp, "sentDateTime": timestamp,
             "bodyPreview": "Please confirm the figures.", "conversationId": "thread-a",
             "webLink": "https://outlook.office.com/mail/id/request"},
            {"id": "outgoing", "subject": "Synthetic invite", "from": party(self.account),
             "toRecipients": [party("vendor@example.invalid")], "receivedDateTime": timestamp, "sentDateTime": timestamp,
             "parentFolderId": "sent", "@odata.type": "#microsoft.graph.eventMessageRequest"},
        ]

    def get(self, url):
        if url.startswith(GRAPH + "/me/mailFolders"):
            return {"id": "sent"}
        return {"id": "account", "mail": self.account, "userPrincipalName": self.account}

    def pages(self, path, params):
        if path == "/me/messages":
            _, _, start, _, _, _, end = params["$filter"].split()
            rows = [row for row in self.messages if start <= row["sentDateTime"] < end]
            if params["$select"] == "id":
                rows = [{"id": row["id"]} for row in rows]
                if self.fail and rows:
                    rows.append({"id": "uncollected"})
            yield rows[:1]
            yield rows[1:]
        elif path == "/me/calendarView":
            yield []
        else:
            raise AssertionError(path)


def result(number, **overrides):
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
        self.config["work_account"] = FakeGraph.account
        assistant.save(self.home / "config.json", self.config)

    def fetch(self, **kwargs):
        with redirect_stdout(self.output):
            assistant.collect_run(self.home, self.config,
                                  argparse.Namespace(start=None, end=None, recheck=False), **kwargs)

    def test_backfill_review_brief_and_duplicate_recheck(self):
        self.fetch(source_factory=FakeGraph)
        directory, manifest = assistant.current_run(self.home)
        self.assertEqual(manifest["by_type"], {"mail.received": 1, "invite.sent": 1})
        self.assertEqual(len(list((self.home / "archive").glob("*.jsonl.gz"))), 1)
        path = next(assistant.pending(self.home, assistant.review_state(self.home)))
        batch = assistant.load(path)
        prompt = assistant.prompt(self.home, path)
        self.assertIn("MY RULES", prompt)
        self.assertIn("source material", prompt)
        first_record = next(i for i, row in enumerate(batch["records"], 1) if row["kind"] == "mail")
        action = result(first_record, action="provide_information", reason="", priority="high",
                        summary="Confirm the figures", status="open", next_step="Check with Finance")
        invalid = {"batch_id": path.stem, "dispositions": [action, action]}
        with self.assertRaisesRegex(ValueError, "exactly once"):
            assistant.import_result(self.home, json.dumps(invalid))
        self.assertTrue(path.exists())
        valid = {**invalid, "dispositions": [action, result(3 - first_record)]}
        with redirect_stdout(self.output):
            assistant.import_result(self.home, json.dumps(valid))
            assistant.brief(self.home, self.config)
        self.assertIn("Confirm the figures", self.output.getvalue())
        self.assertIn("[Source]", self.output.getvalue())
        self.assertFalse(list(assistant.pending(self.home, assistant.review_state(self.home))))
        with self.assertRaisesRegex(ValueError, "already imported"):
            assistant.import_result(self.home, json.dumps(valid))

        args = argparse.Namespace(start=manifest["start"], end=manifest["end"], recheck=False)
        with redirect_stdout(self.output):
            assistant.collect_run(self.home, self.config, args, source_factory=FakeGraph)
        self.assertEqual(assistant.current_run(self.home)[0], directory)
        self.assertFalse(list(assistant.pending(self.home, assistant.review_state(self.home))))
        args.recheck = True
        with redirect_stdout(self.output):
            assistant.collect_run(self.home, self.config, args, source_factory=FakeGraph)
        self.assertTrue(list(assistant.pending(self.home, assistant.review_state(self.home))))

    def test_mismatched_id_prevents_checkpoint(self):
        class BrokenGraph(FakeGraph):
            fail = True

        with self.assertRaisesRegex(CoverageError, "missing"):
            self.fetch(source_factory=BrokenGraph)
        self.assertIsNone(assistant.current_run(self.home))
        failure = assistant.load(next((self.home / "failures").glob("*.json")))
        self.assertEqual(failure["status"], "failed")
        self.assertEqual(failure["coverage"][-1]["missing"], 1)

    def test_verification_checks_ids_even_when_counts_match(self):
        class DivergingGraph:
            def pages(self, path, options):
                yield [{"id": "a" if options["$select"] == "id" else "b"}]

        notes = []
        with self.assertRaises(CoverageError):
            reconcile(DivergingGraph(), "mail", "/me/messages", {}, "id,subject", notes)
        self.assertEqual((notes[0]["missing"], notes[0]["extra"]), (1, 1))
