#!/usr/bin/env python3
"""Collect, reconcile and review work email on a managed Mac."""
import argparse
import calendar
from collections import Counter, defaultdict
from contextlib import contextmanager
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid
from zoneinfo import ZoneInfo

from graph import CoverageError, Graph, UTC, collect, stamp

ROOT = Path(__file__).resolve().parent
DEFAULT_HOME = Path.home() / "Library" / "Application Support" / "Work Mail Assistant"
ACTIONS = {"provide_information", "approve_reject", "execute", "investigate", "no_action"}
REASONS = {"information_only", "acknowledgement_only", "historical_completed", "no_obligation"}


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def load(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        try:
            stream.write(content if isinstance(content, bytes) else content.encode())
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)


def save(path, value):
    atomic(path, encode(value) + "\n")


def parse(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def local_time(value, zone):
    parsed = parse(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=zone)


def subtract_months(value, months):
    year, month = divmod(value.year * 12 + value.month - 1 - months, 12)
    return value.replace(year=year, month=month + 1,
                         day=min(value.day, calendar.monthrange(year, month + 1)[1]))


def fingerprint(record):
    if "analysis_hash" in record:
        return record["analysis_hash"]
    # The date on a Planner snapshot is the fetch time, not its revision time.
    data = {key: value for key, value in record.items() if key != "date" or record["kind"] != "task"}
    return hashlib.sha256(encode(data).encode()).hexdigest()


def archive(home, records):
    groups = {}
    for record in records:
        groups.setdefault(record["date"][:7], {})[record["id"]] = record
    for month, incoming in groups.items():
        path = home / "archive" / f"{month}.jsonl.gz"
        existing = {r["id"]: r for r in read_archive(path)}
        existing.update(incoming)
        write_archive(path, existing.values())


def read_archive(path):
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def write_archive(path, records):
    data = "".join(encode(record) + "\n" for record in sorted(records, key=lambda row: (row["date"], row["id"])))
    atomic(path, gzip.compress(data.encode(), mtime=0))


@contextmanager
def locked(home):
    home.mkdir(parents=True, exist_ok=True)
    with (home / ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another assistant command is running.") from None
        yield


def initialize(home):
    for target, source in (("config.json", "config.example.json"), ("rules.md", "rules.example.md")):
        path = home / target
        if not path.exists():
            atomic(path, (ROOT / source).read_bytes())
    print(home)


def settings(home):
    config = load(home / "config.json")
    if config is None:
        raise ValueError("Run init first.")
    if config["planner"]["mode"] not in {"off", "assigned", "plans"}:
        raise ValueError("Planner mode must be off, assigned or plans.")
    if config["planner"]["mode"] == "plans" and not config["planner"]["plan_ids"]:
        raise ValueError("Enter at least one Planner plan ID.")
    if not config["calendar_ids"]:
        raise ValueError("Enter at least one calendar ID or default.")
    if any(config[key] < 1 for key in ("retention_months", "batch_records", "batch_chars", "body_chars")):
        raise ValueError("Retention and batching settings must be positive.")
    return config


def runs(home):
    return [(path.parent, load(path)) for path in sorted((home / "runs").glob("*/manifest.json"))]


def review_state(home):
    return load(home / "review.json", {"seen": {}, "batches": {}, "commitments": {}, "highlights": {}})


def pending(home, state):
    for directory, _ in runs(home):
        for path in sorted(directory.glob("batch-*.json")):
            if path.stem not in state["batches"]:
                yield path


def current_run(home):
    regular = [(directory, manifest) for directory, manifest in runs(home) if manifest["regular"]]
    if regular:
        return max(regular, key=lambda pair: pair[1]["end"])
    return None


def batch_records(records, config):
    batch = []
    count = 0
    for record in sorted(records, key=lambda r: (r["date"], r["id"])):
        record = {**record, "analysis_hash": fingerprint(record)}
        if "body" in record:
            record["body_truncated"] = len(record["body"]) > config["body_chars"]
            record["body"] = record["body"][:config["body_chars"]]
        length = len(encode(record))
        if length > config["batch_chars"]:
            raise ValueError("A record exceeds batch_chars. Increase it or reduce body_chars.")
        if batch and (len(batch) == config["batch_records"] or count + length > config["batch_chars"]):
            yield batch
            batch, count = [], 0
        batch.append(record)
        count += length
    if batch:
        yield batch


def collect_run(home, config, args, source_factory=Graph):
    zone = ZoneInfo(config["timezone"])
    now = dt.datetime.now(zone)
    midnight = dt.datetime.combine(now.date(), dt.time(), zone)
    end = now.replace(microsecond=0)
    previous = current_run(home)
    explicit = bool(args.start or args.end)
    if explicit and not (args.start and args.end):
        raise ValueError("Use --from and --to together.")
    if args.recheck and not explicit:
        raise ValueError("Use --recheck with an explicit date range.")
    identity = {key: config.get(key, "").casefold() for key in ("tenant_id", "work_account")}
    for _, earlier in runs(home):
        if earlier["identity"] != identity:
            raise ValueError("Use a separate --home directory when changing the tenant or work account.")
    # A short overlap catches commonly delayed items. Content fingerprints prevent repeat review.
    start = (local_time(args.start, zone) if explicit else
             parse(previous[1]["end"]) - dt.timedelta(minutes=15) if previous else
             subtract_months(end, 6))
    if explicit:
        end = local_time(args.end, zone)
    if end <= start or end > now:
        raise ValueError("Use an increasing date range ending at or before now. --to is exclusive.")
    lower, upper = start.astimezone(UTC), end.astimezone(UTC)
    if previous and previous[1]["end"] >= stamp(upper) and not explicit:
        raise ValueError("The checkpoint is already current. Retry in a moment.")
    run_id = stamp(now).replace(":", "") + "-" + uuid.uuid4().hex[:8]
    manifest = {
        "run_id": run_id, "created": stamp(now), "start": stamp(lower), "end": stamp(upper),
        "regular": not explicit, "local_date": now.date().isoformat(), "timezone": config["timezone"],
        "coverage": [], "planner": config["planner"]["mode"], "calendars": config["calendar_ids"],
        "identity": identity,
    }
    try:
        records, agenda = collect(source_factory(config), config, lower, upper, midnight,
                                  midnight + dt.timedelta(days=1), manifest["coverage"])
        state = review_state(home)
        queued = {fingerprint(row) for path in pending(home, state) for row in load(path)["records"]}
        excluded = queued if args.recheck else queued | state["seen"].keys()
        new = [row for row in records if fingerprint(row) not in excluded]
        batches = list(batch_records(new, config))
        breakdown = Counter(".".join(filter(None, (row["kind"], row.get("direction")))) for row in records)
        manifest.update({"status": "verified", "records": len(records), "batches": len(batches),
                         "by_type": dict(breakdown)})
        (home / "runs").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".run-", dir=home) as stage:
            directory = Path(stage) / run_id
            directory.mkdir()
            save(directory / "manifest.json", manifest)
            save(directory / "agenda.json", [{key: value for key, value in event.items() if key != "body"}
                                              for event in agenda])
            for number, batch in enumerate(batches, 1):
                name = f"batch-{run_id}-{number:04d}"
                save(directory / f"{name}.json", {"batch_id": name, "records": batch})
            archive(home, records)
            directory.rename(home / "runs" / run_id)
    except (CoverageError, ValueError, OSError, KeyError) as error:
        manifest.update({"status": "failed", "error": str(error)})
        save(home / "failures" / f"{run_id}.json", manifest)
        raise
    print(f"Verified {len(records)} unique records, {len(batches)} new batches. Run {run_id}.")
    if not explicit:
        prune(home, config, quiet=True)


def related_history(home, threads, ids):
    if not threads:
        return []
    history = defaultdict(list)
    for path in sorted((home / "archive").glob("*.jsonl.gz"), reverse=True):
        for row in reversed(read_archive(path)):
            thread = row.get("conversation")
            if thread in threads and row["id"] not in ids and row["date"] <= threads[thread] and len(history[thread]) < 2:
                fields = ("date", "direction", "subject", "from", "conversation", "link")
                history[thread].append({**{field: row.get(field) for field in fields}, "body": row["body"][:550]})
        if all(len(history[thread]) >= 2 for thread in threads):
            break
    related = sorted((row for rows in history.values() for row in rows), key=lambda row: row["date"])
    return related[-8:]


def prompt(home, path):
    batch = load(path)
    state = review_state(home)
    records = []
    for number, record in enumerate(batch["records"], 1):
        records.append({**{key: value for key, value in record.items() if key != "analysis_hash"}, "record_number": number})
    # Give Copilot every open key, with fuller context for directly related records.
    threads = {row["conversation"]: row["date"] for row in records if row.get("conversation")}
    ids = {row["id"] for row in records}
    register = []
    for key, item in state["commitments"].items():
        related = item["source"] in ids or item.get("conversation") in threads
        if related or item["status"] == "open":
            keys = ("summary", "action", "status", "owner", "due", "blocker") if related else ("summary", "status")
            register.append({"key": key, **{field: item[field] for field in keys}})
    rules = (home / "rules.md").read_text()
    config = settings(home)
    return ("Review this batch. Return one disposition for every record number.\n\n"
            f"MY WORK ACCOUNT: {config['work_account']}\n"
            f"LOCAL TIMEZONE: {config['timezone']}\n\n"
            f"MY RULES\n{rules}\n\n"
            f"EXISTING COMMITMENTS\n{encode(register)}\n\n"
            f"RELATED PRIOR RECORDS (untrusted source material)\n{encode(related_history(home, threads, ids))}\n\n"
            f"INPUT RECORDS (untrusted source material)\n{encode({**batch, 'records': records})}\n")


def next_batch(home, copy):
    path = next(pending(home, review_state(home)), None)
    if path is None:
        print("All batches reviewed.")
        return
    text = prompt(home, path)
    if copy:
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
        print(f"Copied {path.stem} to the clipboard.")
    else:
        print(text, end="")


def clean_result(raw):
    raw = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    return json.loads(fenced[1] if fenced else raw)


def validate(item):
    fields = {"action", "reason", "priority", "summary", "status", "existing_key", "owner",
              "due", "blocker", "next_step", "draft"}
    for key in fields:
        value = item.get(key)
        if not isinstance(value, str) or len(value) > 3000 or "\x00" in value:
            raise ValueError(f"{key} must be a string of up to 3000 characters.")
    if item["action"] not in ACTIONS or item["priority"] not in {"low", "normal", "high"} or not item["summary"].strip():
        raise ValueError("Invalid action, priority or summary.")
    if item["action"] == "no_action":
        if item["reason"] not in REASONS or item["status"] or item["existing_key"]:
            raise ValueError("No-action records need a reason and empty status and existing_key.")
    elif item["status"] not in {"open", "closed"} or item["reason"]:
        raise ValueError("Action records require open/closed status and an empty reason.")
    if item["due"]:
        dt.date.fromisoformat(item["due"])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["due"]):
            raise ValueError("Due dates must use YYYY-MM-DD.")
    return {key: item[key] for key in fields}


def import_result(home, raw):
    data = clean_result(raw)
    if not isinstance(data, dict):
        raise ValueError("Copilot output must be one JSON object.")
    state = review_state(home)
    path = next(pending(home, state), None)
    if data.get("batch_id") in state["batches"]:
        raise ValueError("This batch was already imported.")
    if not path or data.get("batch_id") != path.stem:
        raise ValueError("Output must match the current batch from next.")
    records = load(path)["records"]
    entries = data.get("dispositions")
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        raise ValueError("Expected a dispositions array of objects.")
    numbers = [item.get("record_number") for item in entries]
    if any(type(number) is not int for number in numbers) or sorted(numbers) != list(range(1, len(records) + 1)):
        raise ValueError("Each record number must appear exactly once. Ask Copilot to retry the entire batch.")
    changes = []
    for disposition in sorted(entries, key=lambda item: item["record_number"]):
        row = records[disposition["record_number"] - 1]
        item = {**validate(disposition), "source": row["id"], "link": row.get("link"),
                "date": row["date"], "conversation": row.get("conversation"), "kind": row["kind"]}
        if item["action"] != "no_action":
            key = item.pop("existing_key") or row["id"]
            if disposition["existing_key"] and key not in state["commitments"]:
                raise ValueError("Copilot referenced an unknown commitment key.")
            previous = state["commitments"].get(key)
            if not previous or parse(item["date"]) >= parse(previous["date"]):
                state["commitments"][key] = item
        elif item["priority"] == "high":
            state["highlights"][row["id"]] = item
        else:
            state["highlights"].pop(row["id"], None)
        digest = fingerprint(row)
        state["seen"][digest] = row["date"]
        changes.append({"fingerprint": digest, **item})
    state["batches"][path.stem] = {"imported": stamp(dt.datetime.now(UTC)), "count": len(changes)}
    # Store the review audit before committing the register; retries overwrite the same result.
    save(path.with_name(f"result-{path.stem}.json"), changes)
    save(home / "review.json", state)
    path.unlink(missing_ok=True)
    print(f"Imported {len(changes)} verified dispositions.")


def prune(home, config, quiet=False):
    now = dt.datetime.now(UTC)
    cutoff = subtract_months(now, config["retention_months"])
    for path in (home / "archive").glob("*.jsonl.gz"):
        rows = read_archive(path)
        kept = [row for row in rows if parse(row["date"]) >= cutoff]
        if not kept:
            path.unlink()
        elif len(kept) != len(rows):
            write_archive(path, kept)
    state = review_state(home)
    state["seen"] = {key: value for key, value in state["seen"].items() if parse(value) >= cutoff}
    state["highlights"] = {key: value for key, value in state["highlights"].items() if parse(value["date"]) >= cutoff}
    state["commitments"] = {key: value for key, value in state["commitments"].items()
                            if value["status"] == "open" or parse(value["date"]) >= cutoff}
    for item in state["commitments"].values():
        if parse(item["date"]) < cutoff:
            item.update({"draft": "", "link": None, "conversation": None, "source": ""})
    latest = current_run(home)
    for directory, manifest in runs(home):
        if parse(manifest["created"]) < cutoff and (not latest or directory != latest[0]):
            shutil.rmtree(directory)
            continue
        for path in directory.glob("batch-*.json"):
            batch = load(path)
            if path.stem in state["batches"]:
                path.unlink()
                continue
            keep = [row for row in batch["records"] if parse(row["date"]) >= cutoff]
            if not keep:
                path.unlink()
            elif len(keep) != len(batch["records"]):
                save(path, {**batch, "records": keep})
        for path in directory.glob("result-*.json"):
            rows = load(path)
            keep = [row for row in rows if parse(row["date"]) >= cutoff]
            if not keep:
                path.unlink()
            elif len(keep) != len(rows):
                save(path, keep)
        agenda = directory / "agenda.json"
        if agenda.exists() and parse(manifest["created"]) < cutoff:
            agenda.unlink()
    state["batches"] = {key: value for key, value in state["batches"].items() if parse(value["imported"]) >= cutoff}
    save(home / "review.json", state)
    for folder in ("briefs", "failures"):
        for path in (home / folder).glob("*"):
            if path.name[:10] < cutoff.date().isoformat():
                path.unlink()
    if not quiet:
        print(f"Retention applied before {stamp(cutoff)}.")


def md(text):
    return re.sub(r"([\\`*_{}\[\]<>#!|])", r"\\\1", " ".join(str(text).split()))


def source_link(url):
    if isinstance(url, str) and url.startswith("https://") and not re.search(r"[\s()<>]", url):
        return f" [Source]({url})"
    return ""


def assessment(item, include_draft=True):
    parts = [f"- {md(item['summary'])}{source_link(item.get('link'))}"]
    for label, field in (("Due", "due"), ("Blocked by", "blocker"), ("Next", "next_step"), ("Suggested reply", "draft")):
        if item[field] and (field != "draft" or include_draft):
            parts.append(f"  - **{label}** {md(item[field])}")
    return "\n".join(parts)


def brief(home, config):
    latest = current_run(home)
    if not latest:
        raise ValueError("Run a regular collection to build a daily brief.")
    directory, manifest = latest
    zone = ZoneInfo(config["timezone"])
    today = dt.datetime.now(zone).date()
    state = review_state(home)
    outstanding = list(pending(home, state))
    failures = sorted((home / "failures").glob("*.json"))
    recent_failure = any(load(path)["regular"] and path.stem > manifest["run_id"] for path in failures)
    title = f"# Work brief · {today}"
    warning = []
    if outstanding:
        warning.append(f"{len(outstanding)} analysis batches pending")
    if recent_failure:
        warning.append("a collection attempt failed after the last verified run")
    if manifest["local_date"] != today.isoformat() or manifest["timezone"] != config["timezone"]:
        warning.append("today’s calendar has not been verified")
        agenda = []
    else:
        agenda = load(directory / "agenda.json", [])
    sections = [title, f"Data verified through {parse(manifest['end']).astimezone(zone):%Y-%m-%d %H:%M %Z}."]
    if warning:
        sections.append("**Incomplete** · " + " · ".join(warning))
    schedule = []
    event_assessments = {item["source"]: item for item in
                         list(state["highlights"].values()) + list(state["commitments"].values())}
    for event in sorted(agenda, key=lambda row: row["date"]):
        if event["all_day"]:
            label = "All day"
        else:
            label = f"{parse(event['date']).astimezone(zone):%H:%M}–{parse(event['end']).astimezone(zone):%H:%M}"
        schedule.append(f"- {label} · {md(event['subject'])}{source_link(event.get('link'))}")
        prep = event_assessments.get(event["id"], {})
        if prep.get("next_step") and prep.get("status") != "closed":
            schedule.append(f"  - **Prep** {md(prep['next_step'])}")
    open_items = [item for item in state["commitments"].values() if item["status"] == "open"]
    soon = (today + dt.timedelta(days=2)).isoformat()
    ranked = sorted(open_items, key=lambda i: (i["priority"] != "high", i["due"] or "9999", i["summary"]))
    relevant = [i for i in ranked if i["priority"] != "low" or (i["due"] and i["due"] <= soon)]
    highlights = [i for i in state["highlights"].values() if i["kind"] != "event"
                  and parse(i["date"]).astimezone(zone).date() >= today - dt.timedelta(days=2)]
    highlights.sort(key=lambda i: i["date"], reverse=True)
    sections.extend([
        "## Today’s meetings and prep\n\n" + ("\n".join(schedule) or ("Calendar coverage pending." if not agenda and any("calendar" in w for w in warning) else "No meetings.")),
        "## Important developments\n\n" + ("\n".join(assessment(i) for i in highlights[:5]) or "None flagged."),
        "## Replies, decisions and actions I owe\n\n" + ("\n".join([assessment(i) for i in relevant if not i["blocker"]][:8]) or "None flagged."),
        "## Blocked items worth chasing\n\n" + ("\n".join([assessment(i) for i in relevant if i["blocker"]][:5]) or "None flagged."),
    ])
    output = "\n\n".join(sections) + "\n"
    atomic(home / "briefs" / f"{today}.md", output)
    print(output, end="")


def status(home):
    last = current_run(home)
    state = review_state(home)
    latest_failure = next(iter(sorted((home / "failures").glob("*.json"), reverse=True)), None)
    print(f"Last regular checkpoint: {last[1]['end'] if last else 'none'}")
    if last:
        print(f"Coverage report: {last[0] / 'manifest.json'}")
    if latest_failure:
        print(f"Last failed attempt: {latest_failure}")
    print(f"Pending analysis batches: {len(list(pending(home, state)))}")
    print(f"Open commitments: {sum(item['status'] == 'open' for item in state['commitments'].values())}")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "status", "brief", "prune"):
        commands.add_parser(name)
    fetch = commands.add_parser("collect")
    fetch.add_argument("--from", dest="start")
    fetch.add_argument("--to", dest="end")
    fetch.add_argument("--recheck", action="store_true", help="queue previously reviewed records in an explicit range")
    next_command = commands.add_parser("next")
    next_command.add_argument("--copy", action="store_true")
    ingest = commands.add_parser("import-result")
    source = ingest.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--paste", action="store_true")
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    if home == ROOT or ROOT in home.parents:
        parser.error("Use a data directory outside this repository.")
    try:
        with locked(home):
            if args.command == "init":
                initialize(home)
                return
            config = settings(home)
            if args.command == "collect":
                collect_run(home, config, args)
            elif args.command == "next":
                next_batch(home, args.copy)
            elif args.command == "import-result":
                raw = args.file.read_text() if args.file else subprocess.check_output(["pbpaste"], text=True)
                import_result(home, raw)
            elif args.command == "brief":
                brief(home, config)
            elif args.command == "status":
                status(home)
            elif args.command == "prune":
                prune(home, config)
    except (ValueError, KeyError, OSError, CoverageError, subprocess.CalledProcessError, ImportError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
