"""Normalize and reconcile Outlook and Planner records."""
import datetime as dt
from html.parser import HTMLParser
import re
from urllib.parse import quote

GRAPH = "https://graph.microsoft.com/v1.0"
UTC = dt.timezone.utc


class CoverageError(Exception):
    pass


def stamp(value):
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def address(value):
    return (value or {}).get("emailAddress", {}).get("address", "").casefold()


class BodyText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"style", "script"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"style", "script"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def body_text(row):
    body = row.get("uniqueBody") or row.get("body") or {}
    value = body.get("content") or row.get("bodyPreview") or ""
    if body.get("contentType", "").casefold() == "html":
        parser = BodyText()
        parser.feed(value)
        value = " ".join(parser.parts)
    return re.sub(r"\s+", " ", value).strip()


MAIL_FIELDS = (
    "id,subject,from,sender,toRecipients,ccRecipients,bodyPreview,uniqueBody,"
    "receivedDateTime,sentDateTime,isDraft,conversationId,internetMessageId,"
    "parentFolderId,webLink,importance,hasAttachments"
)
EVENT_FIELDS = (
    "id,subject,start,end,isAllDay,isCancelled,responseStatus,organizer,webLink,"
    "location,bodyPreview,body,showAs,iCalUId,isOrganizer"
)


def reconcile(graph, name, path, params, fields, notes):
    """Compare complete ID sets from a content pass and a second read."""
    def scan(select):
        options = {**params, "$select": select} if select else params
        items = {}
        pages = 0
        duplicates = 0
        for page in graph.pages(path, options):
            pages += 1
            for row in page:
                duplicates += row["id"] in items
                items[row["id"]] = row
        return items, pages, duplicates

    rows, pages, duplicates = scan(fields)
    # Planner does not document $select on these endpoints.
    check, check_pages, check_duplicates = scan("id" if fields else None)
    missing = len(check.keys() - rows.keys())
    extra = len(rows.keys() - check.keys())
    notes.append({
        "source": name, "records": len(rows), "verification_records": len(check),
        "pages": pages, "verification_pages": check_pages, "duplicates": duplicates,
        "verification_duplicates": check_duplicates, "missing": missing, "extra": extra,
    })
    if missing or extra:
        raise CoverageError(f"{name} changed between passes ({missing} missing, {extra} extra). Retry collection.")
    return rows.values()


def collect(graph, config, start, end, today_start, today_end, notes):
    identities = {config["work_account"].casefold(), *(x.casefold() for x in config["mail_aliases"])}
    owner = graph.get("/me/calendar?$select=owner")["owner"]["address"].casefold()
    if owner not in identities:
        raise CoverageError("The Outlook connection does not match work_account or mail_aliases.")
    sent_folder = graph.get("/me/mailFolders/sentitems?$select=id")["id"]
    mail = {}
    cursor = start
    while cursor < end:
        until = min(cursor + dt.timedelta(days=14), end)
        for direction, field in (("received", "receivedDateTime"), ("sent", "sentDateTime")):
            source = f"mail.{direction} {stamp(cursor)} to {stamp(until)}"
            params = {"$filter": f"{field} ge {stamp(cursor)} and {field} lt {stamp(until)}", "$top": 75}
            for row in reconcile(graph, source, "/me/messages", params, MAIL_FIELDS, notes):
                if row.get("isDraft"):
                    continue
                own = (row.get("parentFolderId") == sent_folder
                       or bool({address(row.get("from")), address(row.get("sender"))} & identities))
                self_mail = bool({address(person) for person in row.get("toRecipients", []) + row.get("ccRecipients", [])} & identities)
                if direction == "sent" and not own:
                    continue
                if direction == "received" and own and (not self_mail or row.get("parentFolderId") == sent_folder):
                    continue
                date = row[field]
                key = f"mail:{row['id']}"
                subtype = row.get("@odata.type", "").rsplit(".", 1)[-1]
                mail[key] = {
                    "id": key, "kind": "invite" if subtype.startswith("eventMessage") else "mail",
                    "subtype": subtype, "date": date, "direction": direction,
                    "subject": row.get("subject") or "(no subject)", "body": body_text(row),
                    "from": address(row.get("from")),
                    "to": [address(person) for person in row.get("toRecipients", [])],
                    "cc": [address(person) for person in row.get("ccRecipients", [])],
                    "conversation": row.get("conversationId"), "message_id": row.get("internetMessageId"),
                    "link": row.get("webLink"), "has_attachments": row.get("hasAttachments"),
                    "received_at": row.get("receivedDateTime"), "sent_at": row.get("sentDateTime"),
                }
        cursor = until
    events = {}
    agenda = {}
    windows = [(start, end, "history"), (today_start, today_end, "today")]
    for calendar in config["calendar_ids"]:
        path = "/me/calendar/calendarView" if calendar == "default" else f"/me/calendars/{quote(calendar, safe='')}/calendarView"
        for lower, upper, purpose in windows:
            params = {"startDateTime": stamp(lower), "endDateTime": stamp(upper), "$top": 75}
            for row in reconcile(graph, f"calendar.{purpose} {calendar}", path, params, EVENT_FIELDS, notes):
                # Use the calendar ID namespace to keep copies in different calendars distinct.
                key = f"event:{calendar}:{row['id']}"
                event = {
                    "id": key, "kind": "event", "date": row["start"]["dateTime"][:19] + "Z",
                    "end": row["end"]["dateTime"][:19] + "Z", "subject": row.get("subject") or "(no subject)",
                    "all_day": row.get("isAllDay"),
                    "cancelled": row.get("isCancelled"), "response": (row.get("responseStatus") or {}).get("response"),
                    "organizer": address(row.get("organizer")), "is_organizer": row.get("isOrganizer"),
                    "location": (row.get("location") or {}).get("displayName"), "show_as": row.get("showAs"),
                    "ical_uid": row.get("iCalUId"), "link": row.get("webLink"),
                    "body": body_text(row),
                }
                events[key] = event
                if purpose == "today" and not event["cancelled"] and event["response"] != "declined":
                    agenda[key] = event
    tasks = {}
    planner = config["planner"]
    observed = graph.observed
    paths = {
        "off": [],
        "assigned": [("assigned", "/me/planner/tasks")],
        "plans": [(plan, f"/planner/plans/{quote(plan, safe='')}/tasks") for plan in planner["plan_ids"]],
    }[planner["mode"]]
    for label, path in paths:
        for row in reconcile(graph, f"planner.{label}", path, {}, None, notes):
            key = f"task:{row['id']}"
            assignments = sorted(person["userId"] for person in row.get("_assignments", []) or [])
            user_id = planner.get("user_id")
            tasks[key] = {
                "id": key, "kind": "task", "date": observed, "subject": row.get("title") or "(no title)",
                "due": row.get("dueDateTime"), "created": row.get("createdDateTime"),
                "complete": row.get("completedDateTime"), "percent_complete": row.get("percentComplete"),
                "plan": row.get("planId"), "assignments": assignments,
                "assigned_to_me": True if label == "assigned" else user_id in assignments if user_id else None,
                "link": f"https://planner.cloud.microsoft/webui/plan/{quote(row['planId'], safe='')}/task/{quote(row['id'], safe='')}",
            }
    return list(mail.values()) + list(events.values()) + list(tasks.values()), list(agenda.values())
