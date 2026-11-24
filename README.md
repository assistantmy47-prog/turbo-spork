# Work Mail Assistant for macOS

A read-only collector verifies Microsoft Graph coverage, writes a local archive, and prepares batches for a private Microsoft 365 Copilot agent. The Mac verifies each Copilot response and builds the daily brief.

## 1. Get work-tenant access

Use an approved managed Mac and confirm your company permits the local copies and use of selected excerpts in work Copilot. Ask your Microsoft 365 / Entra administrator for a **single-tenant public client app** with the **Mobile and desktop applications** redirect URI `http://localhost` and Microsoft Graph **delegated** permissions `User.Read`, `Mail.Read`, and `Calendars.Read`. Add `Tasks.Read` if enabling Planner. Request the **tenant ID** and **application (client) ID**. No client secret or application permissions are needed. The collector opens your browser for interactive sign-in. If tenant consent or Conditional Access blocks it, ask IT to approve this path. [Microsoft sign-in documentation](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens)

## 2. Install on the Mac

Use your approved Python 3.11+ and Git installations. Run in Terminal:

```bash
git clone https://github.com/assistantmy47-prog/turbo-spork.git
cd turbo-spork
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python assistant.py init
open -e "$HOME/Library/Application Support/Work Mail Assistant/config.json"
open -e "$HOME/Library/Application Support/Work Mail Assistant/rules.md"
```

In `config.json`, fill in `tenant_id`, `client_id` and `work_account` (your work sign-in address). The sample uses Central time and the default Outlook calendar. Add calendar IDs or mail aliases as needed. For Planner, set `mode` to `assigned` or `plans`. For `plans`, fill `plan_ids` with the IDs from the Planner plan URLs. `off` is the default. [Planner API coverage](https://learn.microsoft.com/en-us/graph/api/resources/planner-overview)

## 3. Create the Copilot agent

1. In your **work** Microsoft 365 Copilot app, choose **New agent → Skip to configure**.
2. Name it **Work Mail Assistant**. Paste [AGENT-INSTRUCTIONS.md](AGENT-INSTRUCTIONS.md) into **Instructions**.
3. Leave knowledge sources empty and web search off. Create the agent and keep it private. The collector supplies the data and your current local rules in every batch. Researcher and Analyst are optional for separate ad hoc work.

## 4. Smoke test and backfill

Start with a small, completed interval and compare the coverage manifest and archive with Outlook. In this example, replace both dates with a completed day in your tenant. The end date is exclusive, and dates without offsets use the configured timezone.

```bash
python assistant.py collect --from 2026-11-23 --to 2026-11-24
python assistant.py status
```

Review this batch using step 5, then run `python assistant.py collect` for the six-month backfill. This first regular run creates the checkpoint. Subsequent regular collections resume from it with a 15-minute overlap. Explicit date-range runs leave the regular checkpoint unchanged. Add `--recheck` to an explicit range to review previously classified records under updated rules. The run manifest records both passes for each source and date segment, plus the total eligible records and batch count. Pagination or reconciliation failures leave the checkpoint in place. Retry the run after resolving the reported issue.

## 5. Daily routine on the Mac

```bash
source .venv/bin/activate
python assistant.py collect
python assistant.py next --copy
```

1. Paste the batch into your work Copilot agent. Copy the returned JSON and run `python assistant.py import-result --paste`. You can also use `--file /path/to/result.json`. If validation fails, ask the agent to return the entire result again. Use a fresh agent chat for each batch.
2. Repeat `next --copy` and `import-result --paste` until all batches are reviewed. The six-month backfill can create many batches. To tune the workload, change `batch_chars`, `batch_records`, and `body_chars` before collection. Larger batches can hit Copilot input or output limits.
3. Run `python assistant.py brief` to generate and save the brief. While work remains, the brief reports pending batches or a failed collection. Run `python assistant.py status` to locate the coverage report.
4. Edit your local `rules.md` whenever priorities, ownership rules or writing preferences change. The new rules apply when the next batch is generated. Review drafts before sending them.

## Data and coverage

The local folder contains monthly compressed JSONL archives, run manifests, temporary review batches, validated dispositions, a commitment register and daily Markdown briefs. The archive stores normalized unique message text and calendar descriptions where Graph supplies them. Attachments remain in Outlook. Configurable excerpts, related records and register context supplied to Copilot are processed in your work tenant. Keep the working directory and any copied output in approved locations.

Regular collections apply rolling retention (12 months by default). `python assistant.py prune` applies it on demand. Expired source data and reports are removed, with minimal entries retained for open commitments. This pruning affects only local assistant files. Planner reflects the state visible at fetch time, including during a historical mailbox backfill. Calendar snapshots show visible occurrences. Meeting-message traffic is captured separately.

Verification compares complete sets of IDs across two Graph passes. The manifest covers accessible items returned by the configured primary mailbox and calendars. It cannot establish mail transport delivery, recover permanently deleted items, or enumerate an Exchange Online archive or shared mailbox. Direction is inferred from the Sent Items folder and the signed-in account's addresses. Configure sending aliases if needed. Analysis verification checks that every record was classified. Review material conclusions against the linked sources.

See [synthetic review examples](examples/) for Copilot input and output. For an offline smoke test use `python -m unittest discover -s tests -v`. The tests use synthetic records and require neither Graph credentials nor a Copilot session.
