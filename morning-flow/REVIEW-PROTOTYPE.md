# Run the multiple-file review prototype

Use the same private Copilot agent for both passes. Power Automate prepares and size-checks the files without AI. Copilot reviews the batches and writes the brief.

## Set up once

1. Follow [Add size-checked review files](REVIEW-BATCH-CARDS.md) to update the scheduled flow. If you are starting from scratch, follow the [scheduled setup](../SCHEDULED-SETUP.md) first.
2. Replace the agent's instructions with [COPILOT-AGENT.md](COPILOT-AGENT.md). Keep the stable `WorkMailMorningInput.txt` knowledge source. It now points you to the run manifest and shows the queue count.
3. Save these prompts in the same agent if you want shortcuts:

| Prompt | Attachments |
|---|---|
| `REVIEW. Parse the attached batch and return one JSON disposition per expected email ID.` | One numbered email file with `kind: review_batch`. Optionally attach the specific context file the batch needs. |
| `CHECK. Reconcile these results against the attached run manifest. Export the combined results as JSON and list any gaps.` | The manifest and the actual saved batch result files. |
| `BRIEF. Generate my morning brief from these checked results and context. State the reviewed and expected counts.` | The manifest, the combined result JSON, and the calendar or Planner context files you want included. |

You can use one agent conversation for repeated batch reviews. Attach each batch by name. Save each response as JSON in your approved work location if Copilot supports a downloadable result, or use its copy control and save the JSON yourself. Use the actual result files for CHECK so the run does not depend on chat retaining earlier messages.

## First test

1. Run the updated flow once. Open `WorkMailMorningInput.txt` in work OneDrive, then find the manifest and numbered files in `WorkMailMorning/Review`.
2. Check that each numbered file reports `record_count <= 20` and `utf8_bytes <= 24000` in the manifest. These are the prototype limits. The flow measures the final UTF-8 JSON, including metadata and escaping. Context is split into separate calendar or Planner files. The raw archive and manifest are retained separately from this batch cap.
3. Attach one email batch to the agent. Compare the response IDs against that batch's `expected_ids` or use the CHECK prompt after running all batches. If only a few IDs are missing, ask the agent to review those IDs using the same attachment, then save the corrected result.
4. After all email batches, run CHECK and then BRIEF. For an independent test of the result, use [the optional Power Automate ID check](CHECK-REVIEW.md). Remove one result from a test copy and confirm the checker reports the missing ID. Restore it and confirm the check passes.

The 94-record count from the original failure can be used as a reference, or you can use the first fresh scheduled run. The prototype keeps raw feed counts and counts distinct queued mail separately. The existing filters remove drafts and separate mail directions before cross-feed deduplication. For the first prototype, custom routing and automatically selected historical context are outside the scheduled pack. You can attach a relevant prior record when it affects a decision. No local Python or browser helper is needed.
