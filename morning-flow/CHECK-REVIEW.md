# Independently check a Copilot review in Power Automate

This optional instant flow verifies the combined result against the generated run manifest. It uses no AI. Build it once, then upload the two JSON files when you want an independent coverage check.

1. Create **Instant cloud flow → Manually trigger a flow**. Name it **Check Work Mail Review**. Add two **File** inputs in this order: **Manifest**, then **Combined result**. The input keys below assume the designer generated `file` and `file_1`. Verify the internal keys in the trigger's code view if they differ.
2. Add the two **Compose** cards below. Use the expression editor.

| Card | Expression |
|---|---|
| `Read_manifest` | `json(base64ToString(triggerBody()?['file']?['contentBytes']))` |
| `Read_review_result` | `json(base64ToString(triggerBody()?['file_1']?['contentBytes']))` |

3. Add a **Select** card named `Expected_review_ids`. Set **From** to `outputs('Read_manifest')?['expected_email_ids']`. In **Map**, set the key to `id` and the value to the expression `item()`.
4. Add a **Select** card named `Returned_review_ids`. Set **From** to `outputs('Read_review_result')?['dispositions']`. In **Map**, set the key to `id` and the value to the expression `item()?['id']`.
5. Add a **Filter array** card named `Missing_review_ids`. Set **From** to `body('Expected_review_ids')`. Use this condition in advanced mode, or enter it without the leading `@` as the left side of a condition equal to expression `true`.

   ```text
   @empty(intersection(body('Returned_review_ids'),createArray(item())))
   ```

6. Add a **Condition**. Set the left side to this expression, operator **is equal to**, right side expression `true`.

   ```text
   and(equals(outputs('Read_manifest')?['run_id'],outputs('Read_review_result')?['run_id']),equals(length(body('Expected_review_ids')),outputs('Read_manifest')?['queued_emails']),equals(length(body('Expected_review_ids')),length(body('Returned_review_ids'))),equals(length(body('Expected_review_ids')),length(intersection(body('Expected_review_ids'),body('Returned_review_ids')))),empty(body('Missing_review_ids')))
   ```

7. In **True**, add a Compose named `Coverage_verified`. Its input is the expression `concat('Verified IDs: ',string(length(body('Expected_review_ids'))),' for ',outputs('Read_manifest')?['run_id'])`. In **False**, add **Terminate** with **Status** `Failed` and **Code** `ReviewCoverageMismatch`. Use this expression for **Message**:

   ```text
   concat('Coverage did not match. Check the run ID, duplicate or unexpected IDs, and missing IDs: ',string(body('Missing_review_ids')))
   ```

8. Run the checker with the generated `*-manifest.json` and the combined result JSON returned by Copilot. Open the run history for the result. Use secure inputs and outputs where supported for cards that handle work data.

This is an independent check of run-level ID coverage. The agent's CHECK step additionally reconciles batch membership. The coverage check confirms a disposition was returned for every expected ID. Assess whether the proposed actions are accurate when using the brief.
