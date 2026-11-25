# Add size-checked review files

This walkthrough updates an existing scheduled flow. New installations build the original collection cards first using [DESIGNER-CARDS.md](DESIGNER-CARDS.md), then complete these same steps. Power Automate uses standard actions throughout.

1. Create a `Review` subfolder under `WorkMailMorning` in work OneDrive. Keep `Current` and `Archive`.
2. Pause the flow while editing it. Open the top-level `Settings` Compose. Keep your existing values and add `"review_max_records":20,"review_max_bytes":24000` inside the JSON object. Copy the updated `Validate_setup` expression from [the base designer cards](DESIGNER-CARDS.md#validate_setup). These are prototype ceilings. Smaller positive values are allowed, with a minimum byte cap of 1024.
3. Add the seven top-level **Initialize variable** cards below, immediately after `Init_Morning_groups` and before `For_each_feed`. Keep the existing feed loop as built.

| Card name | Variable name | Type | Initial value |
|---|---|---|---|
| `Init_Review_rows` | `Review_rows` | array | `expression json('[]')` |
| `Init_Review_email_ids` | `Review_email_ids` | array | `expression json('[]')` |
| `Init_Review_parts` | `Review_parts` | array | `expression json('[]')` |
| `Init_Review_offset` | `Review_offset` | integer | `0` |
| `Init_Review_take` | `Review_take` | integer | `20` |
| `Init_Review_failed` | `Review_failed` | boolean | `false` |
| `Init_Review_written_emails` | `Review_written_emails` | integer | `0` |

4. Open the **True** branch of `Publish_only_if_verified`. Keep everything through `Create_verified_archive`. Remove the two old cards that followed it, `Morning_text` and `Update_morning_input_and_checkpoint`. Recreate them where shown below, inside the new `Publish_complete_review_run` branch.
5. Add the cards below in order, beginning directly after `Create_verified_archive`. Follow the **Placement** line for every card. Paste formulas into the **Expression** editor and keep the default success-only sequencing.
6. Save and test one run. The dated archive remains the full audit copy. The current TXT becomes a short pointer to the matching manifest and numbered files. Check that every numbered file in that manifest exists. If a single projected record still exceeds the size limit, the run fails visibly, and the TXT/checkpoint stays at the prior verified run. Review the oversized record in the archived data or reduce the excerpt setting before retrying.

The manifest is an audit index. Its size is separate from the review-file cap. The raw verified archive is also outside that cap. Mail IDs are deduplicated across the two projected mail feeds. Calendar and Planner are written as separate context files. The checkpoint updates only after all files and the manifest are written.

### `Review_run_id`

**Placement** `Publish_only_if_verified` → **True**

**Card** Data Operation → Compose

**Inputs** expression

```text
replace(outputs('Archive_name'),'.json','')
```

### `For_each_review_group`

**Placement** `Publish_only_if_verified` → **True**

**Card** Control → Apply to each

**Select an output** expression

```text
variables('Morning_groups')
```

Leave **Concurrency Control** off.

### `Is_email_review_group`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group`

**Card** Data Operation → Compose

**Inputs** expression

```text
contains(createArray('received','sent'),items('For_each_review_group')?['feed'])
```

### `Reset_review_rows`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group`

**Card** Variables → Set variable

- **Name** `Review_rows`
**Value** expression

```text
json('[]')
```

### `For_each_review_row`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group`

**Card** Control → Apply to each

**Select an output** expression

```text
items('For_each_review_group')?['records']
```

Leave **Concurrency Control** off.

### `Keep_first_review_id`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `For_each_review_row`

**Card** Control → Condition

**Left side** expression

```text
or(not(outputs('Is_email_review_group')),not(contains(variables('Review_email_ids'),items('For_each_review_row')?['id'])))
```

Operator **is equal to**, right side expression `true`.

### `Add_review_record`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `For_each_review_row` → `Keep_first_review_id` → **True**

**Card** Variables → Append to array variable

- **Name** `Review_rows`
**Value** expression

```text
items('For_each_review_row')
```

### `Record_expected_mail_id`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `For_each_review_row` → `Keep_first_review_id` → **True**

**Card** Control → Condition

**Left side** expression

```text
outputs('Is_email_review_group')
```

Operator **is equal to**, right side expression `true`.

### `Remember_review_mail_id`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `For_each_review_row` → `Keep_first_review_id` → **True** → `Record_expected_mail_id` → **True**

**Card** Variables → Append to array variable

- **Name** `Review_email_ids`
**Value** expression

```text
items('For_each_review_row')?['id']
```

Leave **False** empty.

Leave **False** empty.

### `Has_records_to_pack`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group`

**Card** Control → Condition

**Left side** expression

```text
and(not(variables('Review_failed')),not(empty(variables('Review_rows'))))
```

Operator **is equal to**, right side expression `true`.

### `Reset_review_offset`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True**

**Card** Variables → Set variable

- **Name** `Review_offset`
- **Value** `0`

### `Reset_review_take`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True**

**Card** Variables → Set variable

- **Name** `Review_take`
**Value** expression

```text
outputs('Settings')?['review_max_records']
```

### `Pack_review_parts`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True**

**Card** Control → Do until

**Left side** expression

```text
or(greaterOrEquals(variables('Review_offset'),length(variables('Review_rows'))),variables('Review_failed'))
```

Operator **is equal to**, right side expression `true`.

Set **Count** to `1000` and **Timeout** to `PT1H`.

### `Part_records`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts`

**Card** Data Operation → Compose

**Inputs** expression

```text
take(skip(variables('Review_rows'),variables('Review_offset')),variables('Review_take'))
```

### `Part_ids`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts`

**Card** Data Operation → Select

**From** expression

```text
outputs('Part_records')
```

In **Map**, enter the key id and use the expression item()?['id'] as the value.

### `Part_id`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts`

**Card** Data Operation → Compose

**Inputs** expression

```text
concat('batch-',formatNumber(add(length(variables('Review_parts')),1),'000','en-US'))
```

### `Part_filename`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts`

**Card** Data Operation → Compose

**Inputs** expression

```text
concat(outputs('Review_run_id'),'-',outputs('Part_id'),'.json')
```

### `Review_payload`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts`

**Card** Data Operation → Compose

**Inputs** expression

```text
string(setProperty(setProperty(setProperty(setProperty(setProperty(setProperty(setProperty(setProperty(json('{}'),'kind',if(outputs('Is_email_review_group'),'review_batch','context_batch')),'run_id',outputs('Review_run_id')),'batch_id',outputs('Part_id')),'feed',items('For_each_review_group')?['feed']),'work_account',outputs('Settings')?['work_account']),'mail_aliases',outputs('Known_addresses')),'expected_ids',body('Part_ids')),'records',outputs('Part_records')))
```

### `Encode_review_payload`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts`

**Card** Data Operation → Compose

**Inputs** expression

```text
base64(outputs('Review_payload'))
```

### `Part_bytes`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts`

**Card** Data Operation → Compose

**Inputs** expression

```text
sub(div(mul(length(outputs('Encode_review_payload')),3),4),if(endsWith(outputs('Encode_review_payload'),'=='),2,if(endsWith(outputs('Encode_review_payload'),'='),1,0)))
```

### `Fits_review_file`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts`

**Card** Control → Condition

**Left side** expression

```text
lessOrEquals(outputs('Part_bytes'),outputs('Settings')?['review_max_bytes'])
```

Operator **is equal to**, right side expression `true`.

### `Create_review_part`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts` → `Fits_review_file` → **True**

**Card** OneDrive for Business → Create file

- **Folder Path** `/WorkMailMorning/Review`
**File Name** expression

```text
outputs('Part_filename')
```

**File Content** expression

```text
base64ToBinary(outputs('Encode_review_payload'))
```

### `Remember_review_part`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts` → `Fits_review_file` → **True**

**Card** Variables → Append to array variable

- **Name** `Review_parts`
**Value** expression

```text
setProperty(setProperty(setProperty(setProperty(setProperty(setProperty(setProperty(json('{}'),'batch_id',outputs('Part_id')),'filename',outputs('Part_filename')),'feed',items('For_each_review_group')?['feed']),'kind',if(outputs('Is_email_review_group'),'review_batch','context_batch')),'record_count',length(outputs('Part_records'))),'expected_ids',body('Part_ids')),'utf8_bytes',outputs('Part_bytes'))
```

### `Advance_review_offset`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts` → `Fits_review_file` → **True**

**Card** Variables → Increment variable

- **Name** `Review_offset`
**Value** expression

```text
length(outputs('Part_records'))
```

### `Count_written_emails`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts` → `Fits_review_file` → **True**

**Card** Variables → Increment variable

- **Name** `Review_written_emails`
**Value** expression

```text
if(outputs('Is_email_review_group'),length(outputs('Part_records')),0)
```

### `Restore_review_take`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts` → `Fits_review_file` → **True**

**Card** Variables → Set variable

- **Name** `Review_take`
**Value** expression

```text
outputs('Settings')?['review_max_records']
```

### `Can_split_review_part`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts` → `Fits_review_file` → **False**

**Card** Control → Condition

**Left side** expression

```text
greater(length(outputs('Part_records')),1)
```

Operator **is equal to**, right side expression `true`.

### `Reduce_review_take`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts` → `Fits_review_file` → **False** → `Can_split_review_part` → **True**

**Card** Variables → Set variable

- **Name** `Review_take`
**Value** expression

```text
div(length(outputs('Part_records')),2)
```

### `Flag_oversize_record`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Pack_review_parts` → `Fits_review_file` → **False** → `Can_split_review_part` → **False**

**Card** Variables → Set variable

- **Name** `Review_failed`
- **Value** `true`

### `Verify_group_written`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True**

**Card** Control → Condition

**Left side** expression

```text
equals(variables('Review_offset'),length(variables('Review_rows')))
```

Operator **is equal to**, right side expression `true`.

Leave **True** empty.

### `Flag_unwritten_records`

**Placement** `Publish_only_if_verified` → **True** → `For_each_review_group` → `Has_records_to_pack` → **True** → `Verify_group_written` → **False**

**Card** Variables → Set variable

- **Name** `Review_failed`
- **Value** `true`

Leave **False** empty.

### `Publish_complete_review_run`

**Placement** `Publish_only_if_verified` → **True**

**Card** Control → Condition

**Left side** expression

```text
and(not(variables('Review_failed')),equals(variables('Review_written_emails'),length(variables('Review_email_ids'))))
```

Operator **is equal to**, right side expression `true`.

### `Review_manifest_name`

**Placement** `Publish_only_if_verified` → **True** → `Publish_complete_review_run` → **True**

**Card** Data Operation → Compose

**Inputs** expression

```text
concat(outputs('Review_run_id'),'-manifest.json')
```

### `Create_review_manifest`

**Placement** `Publish_only_if_verified` → **True** → `Publish_complete_review_run` → **True**

**Card** OneDrive for Business → Create file

- **Folder Path** `/WorkMailMorning/Review`
**File Name** expression

```text
outputs('Review_manifest_name')
```

**File Content** expression

```text
string(setProperty(setProperty(setProperty(setProperty(setProperty(setProperty(setProperty(outputs('Run_metadata'),'run_id',outputs('Review_run_id')),'archive',outputs('Archive_name')),'expected_email_ids',variables('Review_email_ids')),'queued_emails',length(variables('Review_email_ids'))),'max_records',outputs('Settings')?['review_max_records']),'max_utf8_bytes',outputs('Settings')?['review_max_bytes']),'files',variables('Review_parts')))
```

### `Morning_text`

**Placement** `Publish_only_if_verified` → **True** → `Publish_complete_review_run` → **True**

**Card** Data Operation → Compose

**Inputs** expression

```text
concat('checkpoint_utc=',outputs('Window_end'),decodeUriComponent('%0A'),decodeUriComponent('%0A'),'# Work Mail Morning Input',decodeUriComponent('%0A'),'Verified collection date: ',outputs('Local_day'),decodeUriComponent('%0A'),'Archive: ',outputs('Archive_name'),decodeUriComponent('%0A'),'Review folder: /WorkMailMorning/Review',decodeUriComponent('%0A'),'Review manifest: ',outputs('Review_manifest_name'),decodeUriComponent('%0A'),'Queued distinct emails: ',string(length(variables('Review_email_ids'))),decodeUriComponent('%0A'),'Review and context files: ',string(length(variables('Review_parts'))),decodeUriComponent('%0A'),'Source counts before review filters: ',string(body('Coverage_counts')),decodeUriComponent('%0A'),'Email review status: pending. Use the numbered JSON files.',decodeUriComponent('%0A'))
```

### `Update_morning_input_and_checkpoint`

**Placement** `Publish_only_if_verified` → **True** → `Publish_complete_review_run` → **True**

**Card** OneDrive for Business → Update file

**File (custom value)** expression

```text
body('Read_latest_metadata')?['Id']
```

**File Content** expression

```text
outputs('Morning_text')
```

### `Fail_review_packing`

**Placement** `Publish_only_if_verified` → **True** → `Publish_complete_review_run` → **False**

**Card** Control → Terminate

- **Status** `Failed`
- **Code** `ReviewPackingIncomplete`
- **Message** `Some review records could not be written within the configured limit. Check the review groups and lower the excerpt length if one record is too large. The previous checkpoint remains current.`
