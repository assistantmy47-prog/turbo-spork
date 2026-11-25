# Set up the two-pass morning review

Use the **same private Work Morning Brief agent** for both passes. In the first pass, it reviews the actual attached batch records, including matching history. In the second, it writes a brief from the independently checked results.

The scheduled Power Automate flow still collects and validates mail, calendar and optional Planner. The **Work Mail Review** page locally prepares batches, applies your rules, and checks Copilot's returned IDs. It is a single HTML file with no installation, network calls, or Terminal commands. Use it only on your approved work device. Routing exports copies into named queues and records the rule match. Mailbox moves are outside this setup.

## One-time setup

1. Keep the [scheduled Power Automate flow](../SCHEDULED-SETUP.md). Enable Planner there if you want it included in future archives. Start with **assigned** to review your own tasks. Selected basic plans are also supported.
2. Download [index.html](index.html) with GitHub's **Download raw file** button. Save it as `Work-Mail-Review.html` in an approved work location. Open it in your desktop browser. The page also works with the browser offline.
3. In **Microsoft 365 Copilot → your private agent → Configure → Instructions**, replace the instructions with [COPILOT-AGENT.md](../morning-flow/COPILOT-AGENT.md).
4. Add two suggested prompts if useful. Attach the appropriate JSON file to the prompt in the work agent, using the same file attachment control you used for the test export.

| Suggested prompt | Message | Attachment |
|---|---|---|
| **Review email batch** | `REVIEW. Parse the attached review batch and return the required JSON dispositions.` | A downloaded `batch-NNN.json` |
| **Build verified brief** | `BRIEF. Parse the attached verified review and give me my morning priorities and next steps.` | `verified-review-brief.json` |

Your existing **Morning brief** prompt can stay for a quick view from OneDrive. The updated instructions label that view as a preview. For verified mode, the direct attachments carry the records and IDs into the chat. Availability of this attachment and Code Interpreter workflow needs to be tested in your tenant.

## Daily use

1. **Prepare.** Open the dated `verified-*.json` named in today's `WorkMailMorningInput.txt`. In Work Mail Review, select that JSON as **Current verified archive**. Optionally select earlier scheduled JSON files or the original monthly `*.jsonl.gz` files from the same work mailbox. Click **Prepare batches**. Compare the source feed counts and the queued total. Combined mail is deduplicated by stable message ID and drafts are excluded, so the queued total can differ from a single raw feed count.
2. **Pass 1 · Review.** Download the first batch in Work Mail Review, attach it to the same Copilot agent, and send **Review email batch**. Paste the full returned JSON into **Copilot JSON response** and click **Check results**. You can also choose one or more saved result files. Continue with the batches that remain. Ten emails per batch is the initial setting. Related emails stay together where possible, and long conversations can span more than one batch.
3. **Check gaps.** Work Mail Review will show how many of the expected IDs have valid dispositions. It rejects IDs from another run or batch, duplicate IDs in a response, and conflicting results. When Copilot returns a valid partial batch, accepted records are retained, and the remaining batch download contains only outstanding IDs with applicable thread context. If you need to close the browser partway through, save **checked dispositions** and reopen them after preparing the same archive with the same rules and batch size.
4. **Pass 2 · Brief.** When coverage is complete, click **Download brief input**. Attach the resulting file to the **same** Copilot agent and send **Build verified brief**. The input contains verified counts, actions and flagged developments, today's calendar, open Planner tasks, and routing totals. It excludes routine `no_action` items from the narrative input. Save **checked dispositions** if you need every email's result, including routine no-action decisions.

The morning review requires a manual handoff between the browser and Copilot. The scheduled flow continues to run independently and has no AI actions. There is no Python or Terminal step. The daily archive's 15-minute overlap can cause a message to be queued on successive days. Within each run, it is queued once. Coverage confirms a disposition exists for every queued ID. It still takes judgment to verify any proposed action.

## Add routing rules and confirmed decisions

Download [rules.example.json](rules.example.json), make a work copy, and select it in **Routing rules and confirmed decisions**.

- A rule needs an `id`, an exact sender email address, `subject_contains`, and a `destination`. Add `except_subject_contains` for cases that should go to review, such as error or action-required subjects. Rules are evaluated in file order, and the first matching rule wins. A match applies only to received records, with the sender and subject checked case-insensitively. The example rule starts disabled.
- Leave **Apply routing** unchecked for the first runs. Review the **routing audit** and spot-check both a matching routine message and an exception. In this mode, every eligible message still goes to Copilot. When the matches look right, check **Apply routing** before preparing a new run. The page then excludes those IDs from the review queue and offers a separate download for each destination, with a log of every routed ID. The verified archive still holds the source records.
- Put confirmed precedents in `decisions`, newest first. Each object needs `id`, `references` (a nonempty array of reference IDs or distinctive phrases), `action_taken`, and `source_link`. Optional fields are `date`, `topic`, and `outcome`. The page includes matching precedents based on subject and supplied body excerpts. Treat a precedent as evidence for the current decision and consult the source when the situation differs.
- For history, select files from the **same work mailbox**. Scheduled JSON files include account metadata and are checked when the current archive declares its account. Older monthly gzip files lack that metadata, so select those from the corresponding old Mac archive. Matching same-conversation evidence includes the latest known sent reply where available. Planner candidates are selected by overlapping subject terms, with all open tasks included separately in the brief input. These are bounded context matches. The page does not search across every past topic semantically.

## Test with the run that exposed the gap

Use your existing 94-record feed run and leave routing in dry-run. Review the first batch in Copilot. In a test result, remove one disposition before submitting it. Confirm the page reports the missing ID as outstanding and keeps **Download brief input** disabled. Then download the remaining batch, review it, and submit the result. Continue until all batches reconcile, and confirm the brief reports the checked coverage. If Copilot says it cannot access the actual attachment, try it in work Copilot Chat with the same private agent and verify your tenant's attachment support before relying on the workflow.
