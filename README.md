# Work Mail Assistant for macOS

Power Automate exports mail and calendar data from your work Outlook connection. The Mac verifies and archives the export, then checks that the private Microsoft 365 Copilot agent reviewed every record. No registered Entra app, client secret, or Copilot Studio is required.

## 1. Install and configure

Use approved Git and Python 3.11+ installations. There are no Python packages to install.

```bash
git clone https://github.com/assistantmy47-prog/turbo-spork.git
cd turbo-spork
python3 assistant.py init
open -e "$HOME/Library/Application Support/Work Mail Assistant/config.json"
open -e "$HOME/Library/Application Support/Work Mail Assistant/rules.md"
```

For an existing checkout, use `git pull` instead of cloning. Set `work_account` to your primary mailbox address and keep or update the default Central time zone. Add sending aliases to `mail_aliases` if applicable. Start with the default Outlook calendar and Planner `off`. Existing tenant and client ID settings are no longer used.

## 2. Create the flow and agent

- Build the work-tenant flow using the [Power Automate instructions](POWER-AUTOMATE.md). This uses the standard Outlook and OneDrive for Business connectors. The export folder is staging, and the ongoing archive is local on your Mac.
- In work Microsoft 365 Copilot, choose **New agent → Skip to configure**. Name it **Work Mail Assistant** and paste [AGENT-INSTRUCTIONS.md](AGENT-INSTRUCTIONS.md) into **Instructions**. Leave web search and knowledge sources off, and keep the agent private.

## 3. Verify one day, then backfill

Replace the dates below with a recently completed day with sent mail, received mail and at least one meeting. Dates without offsets use the configured time zone. The end is exclusive.

```bash
python3 assistant.py prepare --from 2026-11-23 --to 2026-11-24
```

1. Run the flow and upload the printed `flow-request.json` into its **Request** input. Once it succeeds, sync or download the JSON exports into a local folder.
2. Import the folder. Update the example path to the actual folder.

   ```bash
   python3 assistant.py import-export "$HOME/Downloads/WorkMailExport"
   python3 assistant.py status
   ```

3. Check the successful run's manifest path printed by the import. Compare the sent and received items, invitation messages, and calendar counts with Outlook. Check that a sent reply, an invite update and a recurring meeting are represented as expected.
4. Run `python3 assistant.py prepare` without date options and repeat the flow and import for the six-month backfill. This starts the regular checkpoint. Explicit date ranges leave it unchanged. Add `--recheck` to an explicit range to requeue previously classified items under updated rules.

## 4. Use it daily

| Step | What to do |
|---|---|
| Collect | Run `python3 assistant.py prepare`, upload the request file to the flow and import the result folder. Regular collections resume from the last verified checkpoint with a 15-minute overlap. |
| Review | Run `python3 assistant.py next --copy`, paste into your private work Copilot agent, copy the returned JSON, and run `python3 assistant.py import-result --paste`. Repeat until the pending queue is empty. If a result is rejected, ask Copilot for the entire batch again. |
| Daily brief | Run `python3 assistant.py brief`. It saves today's meetings and prep, important developments, replies and actions, and blocked items to Markdown. |

To include Planner, add the case(s) in the flow tutorial and set `planner.mode` to `assigned` or `plans`. For `plans`, enter the IDs in `plan_ids` and add each plan's Microsoft 365 group ID to the `group_ids` mapping, keyed by plan ID. Optional `user_id` identifies your assignments within a selected plan. Use the `planner` block in [config.example.json](config.example.json) as a guide. This connector supports basic Planner plans and returns the current state, even during a historical mailbox run. [Planner connector reference](https://learn.microsoft.com/en-us/connectors/planner/)

Edit your local `rules.md` whenever priorities, ownership rules or tone change. The next batch will use the updated settings. For a large backfill, `batch_chars`, `batch_records` and `body_chars` control Copilot batch size. Work records and live config stay outside this repository.

## Verification and retention

The Mac checks every planned feed, page number, continuation URL, and record ID set across two reads. Missing or mismatched exports leave the request pending and the checkpoint unchanged. The manifest records counts and scope. Coverage applies to items accessible through the Outlook connection in the configured mailbox and calendars. It cannot establish mail transport delivery or recover permanently deleted messages, and it does not enumerate separate archives or shared mailboxes.

Monthly compressed JSONL stores normalized message and calendar text where Outlook supplies it. Attachments remain in Outlook. The Mac also stores the commitment register, review results and daily briefs. Regular imports apply rolling 12-month retention by default. `python3 assistant.py prune` applies it on demand. OneDrive staging files are separate and can be removed after successful import, subject to company policy.

For an offline smoke test use `python3 -m unittest discover -s tests -v`. Use the one-day work-tenant test to confirm connector access and live output.
