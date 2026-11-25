# Set up the scheduled morning brief

Power Automate collects and verifies work Outlook and optional Planner data. It publishes a dated JSON export and a single current plain-text file to work OneDrive. OneDrive syncs the export to your Mac and the Copilot agent reads the current file. Your daily action is selecting **Morning brief** in Copilot.

Keep the [manual export flow](POWER-AUTOMATE.md) available while you test this setup. The scheduled flow uses its own folder and checkpoint, so it can run alongside your existing setup and six-month archive.

## 1. Prepare work OneDrive

1. In work OneDrive, create a folder named `WorkMailMorning` at the root.
2. Inside it, create two folders named `Archive` and `Current`.
3. Download the [seed file](morning-flow/WorkMailMorningInput.txt) from this repository using GitHub's raw download option and upload it into `Current`. Keep its filename and first line as supplied. The full path is `/WorkMailMorning/Current/WorkMailMorningInput.txt`.
4. Leave access to the folders limited to the intended work account and existing work policy. The JSON exports include work mail and calendar data.

If you already set up the older `.md` file, pause the flow, rename that file to `WorkMailMorningInput.txt` in OneDrive, and keep its contents so the checkpoint carries over. Point both `Read_latest_metadata` and `Read_latest_file` to the new path, set **Infer Content Type** to **No** on the latter, and relink the file in Copilot. The final **Update file** action uses the ID returned by `Read_latest_metadata`.

The first successful run starts with 24 hours of mail history. Each later run starts 15 minutes before the last verified cutoff. Planner is a current snapshot. The calendar covers the current local day, including recurring instances. The prior six-month archive is not needed for this setup.

## 2. Create the scheduled flow

1. Open [Power Automate](https://make.powerautomate.com) in your work environment.
2. Select **Create → Scheduled cloud flow**, name it **Work Mail Morning**, and choose a daily run time. The example uses 6:00 a.m. Central. In the **Recurrence** card set **Frequency** to **Day**, **Interval** to **1**, **Time zone** to Central time, **At these hours** to **6**, and **At these minutes** to **0**. Schedule the first recurrence in the future while building and testing.
3. Open the **Recurrence** card's settings, turn on **Concurrency Control**, and set **Degree of Parallelism** to **1**. Leave concurrency off inside both **Apply to each** loops.
4. Open the [card-by-card reference](morning-flow/DESIGNER-CARDS.md) alongside the designer. Add its cards in order. It includes the exact placement, action names, field values, and copyable expressions. Rename the cards as shown before entering expressions that use their names.
5. In the `Settings` card, replace `your.name@example.com` with your primary work address. Leave `mail_aliases` empty unless you send from other addresses on the same mailbox. Enter aliases in lowercase. Keep `planner_mode` set to `off` for the first Outlook test. Set `time_zone` to the Microsoft time zone name used for your local calendar.
6. When prompted, connect **Office 365 Outlook** and **OneDrive for Business** using your work account. In the Outlook cards, select **Send an HTTP request** from the Outlook connector. The connector supplies the credentials, so this setup needs no personal Entra app registration.
7. Use **Secure inputs** and **Secure outputs** on actions that handle work data where the designer offers them. Retain the default **Run after** settings so dependent actions require success. Save the flow.

The checked-in [workflow definition](morning-flow/definition.json) provides the full action graph and field mappings. Use the designer walkthrough to install it. A Power Automate import package is built by exporting a saved flow from a tenant and binding its connections on import.

## 3. Verify one run before using the schedule

1. In the flow designer select **Test → Manually → Run flow**, or use **Run** from the flow details. Check the completed run in **Run history**.
2. Open the new `verified-*.json` in `Archive`. Confirm the metadata includes `status: verified`, the expected time window, and separate entries for received mail, sent mail and the calendar. Each feed includes the verified record count and the number of content and verification pages. The archive preserves the Graph fields selected in the flow and excludes attachment binaries.
3. Open `Current/WorkMailMorningInput.txt`. Confirm that its first line has the UTC cutoff and that it names the dated archive just created. Spot-check a received message, a sent reply, and a recurring meeting against Outlook if those items are present. The brief input keeps short source excerpts and links where supplied. Its source counts are taken before briefing filters such as excluding drafts, declined meetings and cancellations.
4. Test failure recovery once. Record the current checkpoint and settings, temporarily set `Settings.work_account` to `wrong@example.com` and `mail_aliases` to `[]`, save, and run the test again. It should fail at `Validate_setup` and leave the current file and checkpoint intact. Restore the original settings and save. The next successful run resumes from the previous verified cutoff.
5. If you want an offline copy on your Mac, locate `WorkMailMorning/Archive` in Finder under work OneDrive and select **Always Keep on This Device**, if available. Verify that the dated JSON appears in Finder. This is a synced copy subject to your work OneDrive policies. An independent archive outside OneDrive needs an approved local transfer route.

If you need to reset a test, turn off the flow first. Restore the last verified version of the current file to resume from that cutoff. Replacing it with the seed deliberately restarts at a new 24-hour window.

## 4. Enable Planner

Choose one configuration. The flow supports basic Planner plans through the standard connector.

| Scope | Set in `Settings` | Add to the `Read_source` Switch |
|---|---|---|
| My assigned tasks | `"planner_mode":"assigned"` | Case `assigned` with **List my tasks** and its following **Set variable** card. Connect Planner with your work account. |
| Selected plans | `"planner_mode":"plans"` plus one object per plan in `planner_plans` | Case `plan` with **List tasks** and its following **Set variable** card. Supply both the Microsoft 365 group ID and the plan ID. |
| Outlook only | `"planner_mode":"off"` | Leave Planner cases out, or leave configured cases in place for future use. |

Example value for `planner_plans`:

```json
[
  {"group_id":"your-m365-group-id","plan_id":"your-plan-id"}
]
```

Run another test. Check the Planner feed and task count in the export. The flow fails verification if Planner returns a continuation link. The Planner list actions in this design expose a snapshot, so a partial snapshot cannot advance the mail checkpoint.

For selected plans, optionally fill in `planner_user_id` with your Microsoft 365 user object ID. The flow can then mark which tasks are assigned to you. In assigned mode this is already implied by the connector query.

## 5. Add the one-click brief to Copilot

1. In work Microsoft 365 Copilot, open your private agent in **Agent Builder → Configure**. You can also create a separate private **Work Morning Brief** agent to retain the original batch reviewer.
2. Paste [the morning agent instructions](morning-flow/COPILOT-AGENT.md) into **Instructions**. If you reuse the old agent, replace its JSON batch-review instructions.
3. Under **Knowledge**, use **Attach cloud files** or paste the work OneDrive link to the specific `WorkMailMorningInput.txt` file. Keep the agent private. The file lives at a stable URL because Power Automate updates it in place. Use the linked cloud file so the agent can pick up later changes.
4. Add a suggested prompt titled **Morning brief** with the message `Give me my morning brief from today's verified WorkMailMorningInput.txt.`
5. Save the agent. Once the OneDrive source is ready, run **Morning brief** and check the verified-through time against the UTC timestamp in the file. Check a known meeting or Planner task. Repeat after a later scheduled run to make sure the agent sees updates to the same file.
6. Keep **Morning brief** as the one-click entry point. If your Copilot interface offers scheduling for this agent conversation, schedule the prompt after the flow has time to finish and OneDrive content has time to become available. Verify a scheduled response uses the current file before relying on it.

Microsoft documents [scheduled cloud flows](https://learn.microsoft.com/power-automate/run-scheduled-tasks), [OneDrive knowledge in Agent Builder](https://learn.microsoft.com/microsoft-365/copilot/extensibility/agent-builder-add-knowledge), [scheduled Copilot Chat prompts](https://support.microsoft.com/en-us/microsoft-365-copilot/schedule-your-most-used-copilot-prompts), and [offline OneDrive files on Mac](https://support.microsoft.com/en-us/onedrive/save-disk-space-with-onedrive-files-on-demand-for-mac).

## What to check if something stops

| Symptom | Check |
|---|---|
| Outlook rejects the request | Verify the Outlook connection uses the intended mailbox and that the tenant permits the Outlook connector's **Send an HTTP request** action. |
| The first OneDrive read fails | Verify the exact seed filename and path in OneDrive. If the checkpoint decode fails, inspect the file-content action in a test and confirm it returns the binary `$content` envelope. |
| A feed is missing from the verified export | Check the failed run in Power Automate. A connector failure, unfinished continuation chain, duplicate record IDs, or different IDs in the two reads blocks publication. Run the flow again after resolving the cause. |
| The archive exists but the current file did not update | Check the final OneDrive **Update file** card. The dated archive may exist from the failed attempt. The current file holds the checkpoint, so the next run safely retries the interval. |
| Copilot reports a stale input | Check the flow and OneDrive timestamp first. If OneDrive has the new file, allow the agent source time to refresh. Compare the timestamp reported by Copilot with the first line in OneDrive. |
| An older commitment is absent from the brief | The brief covers the window in the current file and the latest configured Planner snapshot. The historical archive and manual batch reviewer remain available for older mail. |

Validation covers accessible source records and pagination at collection time, with two ID reads for each feed. Copilot prioritises those records in its response. A successful export does not certify that Copilot considered every record. This scheduled flow keeps dated files in work OneDrive. Set retention through your approved work policy if you need automatic pruning.
