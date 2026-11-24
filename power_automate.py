"""Build Power Automate collection requests and validate exported response pages."""
from collections import defaultdict
import datetime as dt
import json
import re
from urllib.parse import urlencode, urlsplit

from graph import CoverageError, GRAPH, UTC, collect, stamp


class Export:
    def __init__(self, config, request_id, observed):
        self.config = config
        self.request_id = request_id
        self.observed = observed
        self.feeds = []

    def feed(self, path, params=None):
        key = f"feed-{len(self.feeds) + 1:04d}"
        feed = {"key": key, "kind": "outlook", "url": GRAPH + path}
        if params:
            # Keep date-time and options encoded as a query string for the Outlook action.
            feed["url"] += "?" + urlencode(params)
        if path == "/me/planner/tasks":
            feed.update(kind="assigned", url="")
        elif path.startswith("/planner/plans/"):
            plan_id = path.split("/")[3]
            feed.update(kind="plan", url="", plan_id=plan_id,
                        group_id=self.config["planner"]["group_ids"][plan_id])
        self.feeds.append(feed)
        return feed


class Plan(Export):
    def get(self, path):
        self.feed(path)
        return {"id": "planning", "owner": {"address": self.config["work_account"]}}

    def pages(self, path, params):
        self.feed(path, params)
        yield []


class Replay(Export):
    def __init__(self, config, request, directory):
        request_id = request["request_id"]
        super().__init__(config, request_id, request["created"])
        if not directory.is_dir():
            raise CoverageError("Export directory does not exist.")
        self.expected = request["feeds"]
        self.files = defaultdict(dict)
        prefix = request_id + "--"
        for path in directory.glob(prefix + "*.json"):
            match = re.fullmatch(r"(feed-\d{4,})--([1-9]\d*)\.json", path.name[len(prefix):])
            if not match:
                raise CoverageError(f"Unexpected export filename: {path.name}.")
            key, number = match.groups()
            self.files[key][int(number)] = path
        self.check_file_inventory()
        times = [dt.datetime.fromtimestamp(path.stat().st_mtime, UTC)
                 for pages in self.files.values() for path in pages.values()]
        self.observed = stamp(max(times))

    def check_file_inventory(self):
        keys = {feed["key"] for feed in self.expected}
        actual = set(self.files)
        missing = sorted(keys - actual)
        if missing:
            raise CoverageError(f"Missing {len(missing)} export feeds, starting with {missing[0]}. Wait for sync or rerun the flow.")
        if actual - keys:
            raise CoverageError("Unexpected export feeds for this request.")

    def read(self, path, params=None):
        feed = self.feed(path, params)
        index = len(self.feeds) - 1
        if index >= len(self.expected) or feed != self.expected[index]:
            raise CoverageError("The export request does not match the current collection configuration.")
        url = feed["url"]
        seen = set()
        pages = self.files[feed["key"]]
        for number, file in sorted(pages.items()):
            if number != len(seen) + 1 or url in seen or (number > 1 and not url):
                raise CoverageError(f"Broken pagination chain in {feed['key']}, page {number}.")
            envelope = json.loads(file.read_text(encoding="utf-8-sig"))
            if (not isinstance(envelope, dict) or envelope.get("url") != url
                    or not isinstance(envelope.get("body"), dict) or "error" in envelope["body"]):
                raise CoverageError(f"Invalid response in {feed['key']}, page {number}.")
            seen.add(url)
            body = envelope["body"]
            url = body.get("@odata.nextLink") or ""
            if url:
                destination = urlsplit(url)
                if destination.scheme != "https" or destination.netloc != "graph.microsoft.com":
                    raise CoverageError(f"Unexpected pagination address in {feed['key']}.")
            yield body
        if url:
            raise CoverageError(f"The export ended before all pages were captured in {feed['key']}.")

    def get(self, path):
        pages = list(self.read(path))
        if len(pages) != 1:
            raise CoverageError("An Outlook metadata request returned more than one response.")
        return pages[0]

    def pages(self, path, params):
        for page in self.read(path, params):
            rows = page.get("value")
            if (not isinstance(rows, list)
                    or any(not isinstance(row, dict) or not isinstance(row.get("id"), str)
                           or not row["id"] for row in rows)):
                raise CoverageError("A connector response contains invalid or missing record IDs.")
            yield rows


def build_request(config, manifest, window):
    planner = Plan(config, manifest["run_id"], manifest["created"])
    collect(planner, config, *window, [])
    return {"request_id": planner.request_id, "created": planner.observed, "feeds": planner.feeds}
