# Power Automate designer cards

Start with [the setup walkthrough](../SCHEDULED-SETUP.md). This reference lists each card and the branch or loop where it belongs. Start at the top and add the cards in the listed order. Rename every card as shown before referring to it in an expression. Preserve the default **Run after → is successful** sequencing.

Use the **Expression** editor for formulas, then confirm the editor entry. The backticks in this guide mark code and are excluded from pasted values. If a field picker hides an expression or folder option, choose **Enter custom value** first.

- [Set up the connection and time window](#settings)
- [Initialize the variables](#init_next_page)
- [Build the feed and paging loops](#for_each_feed)
- [Publish the verified run](#publish_only_if_verified)

### `Settings`

**Placement** **Top level**

**Card** Data Operation → Compose

Paste the following in **Inputs** as an expression. Replace the email address with your work mailbox, then adjust the settings as needed.

```text
json('{"work_account":"your.name@example.com","mail_aliases":[],"time_zone":"Central Standard Time","planner_mode":"off","planner_plans":[],"planner_user_id":"","excerpt_chars":360,"review_max_records":20,"review_max_bytes":24000}')
```

### `Window_end`

**Placement** **Top level**

**Card** Data Operation → Compose

**Inputs** expression

```text
formatDateTime(utcNow(),'yyyy-MM-ddTHH:mm:ssZ')
```

### `Read_latest_metadata`

**Placement** **Top level**

**Card** OneDrive for Business → Get file metadata using path

- **File Path** `/WorkMailMorning/Current/WorkMailMorningInput.txt`

### `Read_latest_file`

**Placement** **Top level**

**Card** OneDrive for Business → Get file content using path

- **File Path** `/WorkMailMorning/Current/WorkMailMorningInput.txt`
- **Infer Content Type** `false` (No)

### `Read_checkpoint_line`

**Placement** **Top level**

**Card** Data Operation → Compose

**Inputs** expression

```text
trim(first(split(base64ToString(body('Read_latest_file')?['$content']),decodeUriComponent('%0A'))))
```

### `Validate_checkpoint_marker`

**Placement** **Top level**

**Card** Control → Condition

**Left side** expression

```text
and(startsWith(outputs('Read_checkpoint_line'),'checkpoint_utc='),equals(length(split(outputs('Read_checkpoint_line'),'=')),2))
```

Set the operator to **is equal to** and the right side to the expression `true`.

Leave **True** empty.

### `Fail_checkpoint`

**Placement** **Top level** → `Validate_checkpoint_marker` → **False**

**Card** Control → Terminate

- **Status** `Failed`
- **Code** `WorkMailVerification`
- **Message** `The first line of the morning input must start with checkpoint_utc=. Restore the prior verified file or the seed.`

### `Previous_checkpoint`

**Placement** **Top level**

**Card** Data Operation → Compose

**Inputs** expression

```text
last(split(outputs('Read_checkpoint_line'),'='))
```

### `Window_start`

**Placement** **Top level**

**Card** Data Operation → Compose

**Inputs** expression

```text
if(empty(outputs('Previous_checkpoint')),addDays(outputs('Window_end'),-1,'yyyy-MM-ddTHH:mm:ssZ'),addMinutes(outputs('Previous_checkpoint'),-15,'yyyy-MM-ddTHH:mm:ssZ'))
```

### `Local_day`

**Placement** **Top level**

**Card** Data Operation → Compose

**Inputs** expression

```text
convertTimeZone(outputs('Window_end'),'UTC',outputs('Settings')?['time_zone'],'yyyy-MM-dd')
```

### `Calendar_start`

**Placement** **Top level**

**Card** Data Operation → Compose

**Inputs** expression

```text
convertToUtc(concat(outputs('Local_day'),'T00:00:00'),outputs('Settings')?['time_zone'],'yyyy-MM-ddTHH:mm:ssZ')
```

### `Calendar_end`

**Placement** **Top level**

**Card** Data Operation → Compose

**Inputs** expression

```text
convertToUtc(addDays(concat(outputs('Local_day'),'T00:00:00'),1,'yyyy-MM-ddTHH:mm:ss'),outputs('Settings')?['time_zone'],'yyyy-MM-ddTHH:mm:ssZ')
```

### `Mail_received_query`

**Placement** **Top level**

**Card** Data Operation → Compose

**Inputs** expression

```text
concat('https://graph.microsoft.com/v1.0/me/messages?$top=75&$filter=',uriComponent(concat('receivedDateTime ge ',outputs('Window_start'),' and receivedDateTime lt ',outputs('Window_end'))))
```

### `Mail_sent_query`

**Placement** **Top level**

**Card** Data Operation → Compose

**Inputs** expression

```text
concat('https://graph.microsoft.com/v1.0/me/messages?$top=75&$filter=',uriComponent(concat('sentDateTime ge ',outputs('Window_start'),' and sentDateTime lt ',outputs('Window_end'))))
```

### `Calendar_query`

**Placement** **Top level**

**Card** Data Operation → Compose

**Inputs** expression

```text
concat('https://graph.microsoft.com/v1.0/me/calendar/calendarView?$top=75&startDateTime=',uriComponent(outputs('Calendar_start')),'&endDateTime=',uriComponent(outputs('Calendar_end')))
```

### `Read_calendar_owner`

**Placement** **Top level**

**Card** Office 365 Outlook → Send an HTTP request

Add **CustomHeader1** under advanced parameters. Leave **Body** blank.

- **URI** `https://graph.microsoft.com/v1.0/me/calendar?$select=owner`
- **Method** `GET`
- **CustomHeader1** `Prefer: IdType="ImmutableId", outlook.body-content-type="text", outlook.timezone="UTC"`

### `Read_sent_folder`

**Placement** **Top level**

**Card** Office 365 Outlook → Send an HTTP request

Add **CustomHeader1** under advanced parameters. Leave **Body** blank.

- **URI** `https://graph.microsoft.com/v1.0/me/mailFolders/sentitems?$select=id`
- **Method** `GET`
- **CustomHeader1** `Prefer: IdType="ImmutableId", outlook.body-content-type="text", outlook.timezone="UTC"`

### `Sent_folder_id`

**Placement** **Top level**

**Card** Data Operation → Compose

**Inputs** expression

```text
json(string(body('Read_sent_folder')))?['id']
```

### `Known_addresses`

**Placement** **Top level**

**Card** Data Operation → Compose

**Inputs** expression

```text
union(createArray(toLower(outputs('Settings')?['work_account'])),outputs('Settings')?['mail_aliases'])
```

### `Validate_setup`

**Placement** **Top level**

**Card** Control → Condition

**Left side** expression

```text
and(contains(outputs('Known_addresses'),toLower(coalesce(json(string(body('Read_calendar_owner')))?['owner']?['address'],''))),not(empty(outputs('Sent_folder_id'))),less(ticks(outputs('Window_start')),ticks(outputs('Window_end'))),or(empty(outputs('Previous_checkpoint')),less(ticks(if(empty(outputs('Previous_checkpoint')),outputs('Window_start'),outputs('Previous_checkpoint'))),ticks(outputs('Window_end')))),contains(createArray('off','assigned','plans'),outputs('Settings')?['planner_mode']),or(not(equals(outputs('Settings')?['planner_mode'],'plans')),not(empty(outputs('Settings')?['planner_plans']))),greater(outputs('Settings')?['excerpt_chars'],0),lessOrEquals(outputs('Settings')?['excerpt_chars'],1000),greaterOrEquals(outputs('Settings')?['review_max_records'],1),lessOrEquals(outputs('Settings')?['review_max_records'],20),greaterOrEquals(outputs('Settings')?['review_max_bytes'],1024),lessOrEquals(outputs('Settings')?['review_max_bytes'],24000))
```

Set the operator to **is equal to** and the right side to the expression `true`.

Leave **True** empty.

### `Fail_setup`

**Placement** **Top level** → `Validate_setup` → **False**

**Card** Control → Terminate

- **Status** `Failed`
- **Code** `WorkMailVerification`
- **Message** `Check the Outlook identity, time window, Planner settings, excerpt length, and review size limits.`

### `Build_plan_feeds`

**Placement** **Top level**

**Card** Data Operation → Select

**From** expression

```text
outputs('Settings')?['planner_plans']
```

In **Map**, type each key as plain text. Enter each value beginning with `@` using **Expression** without the `@`. Enter other values as plain text.

```json
{
  "key": "@concat('planner-',item()?['plan_id'])",
  "kind": "plan",
  "group_id": "@item()?['group_id']",
  "plan_id": "@item()?['plan_id']",
  "full_url": "planner",
  "check_url": "planner"
}
```

### `Build_feeds`

**Placement** **Top level**

**Card** Data Operation → Compose

**Inputs** expression

```text
union(createArray(setProperty(setProperty(json('{"key":"received","kind":"outlook"}'),'full_url',concat(outputs('Mail_received_query'),'&$select=','id,subject,from,sender,toRecipients,ccRecipients,bodyPreview,uniqueBody,receivedDateTime,sentDateTime,isDraft,conversationId,internetMessageId,parentFolderId,webLink,importance,hasAttachments')),'check_url',concat(outputs('Mail_received_query'),'&$select=id')),setProperty(setProperty(json('{"key":"sent","kind":"outlook"}'),'full_url',concat(outputs('Mail_sent_query'),'&$select=','id,subject,from,sender,toRecipients,ccRecipients,bodyPreview,uniqueBody,receivedDateTime,sentDateTime,isDraft,conversationId,internetMessageId,parentFolderId,webLink,importance,hasAttachments')),'check_url',concat(outputs('Mail_sent_query'),'&$select=id')),setProperty(setProperty(json('{"key":"calendar","kind":"outlook"}'),'full_url',concat(outputs('Calendar_query'),'&$select=','id,subject,start,end,isAllDay,isCancelled,responseStatus,organizer,webLink,location,bodyPreview,body,showAs,iCalUId,isOrganizer')),'check_url',concat(outputs('Calendar_query'),'&$select=id'))),if(equals(outputs('Settings')?['planner_mode'],'assigned'),createArray(json('{"key":"planner-assigned","kind":"assigned","full_url":"planner","check_url":"planner"}')),if(equals(outputs('Settings')?['planner_mode'],'plans'),body('Build_plan_feeds'),json('[]'))))
```

### `Init_Next_page`

**Placement** **Top level**

**Card** Variables → Initialize variable

- **Name** `Next_page`
- **Type** `string`
- **Value** `` (leave blank or use the expression `''` if required)

### `Init_Page_ok`

**Placement** **Top level**

**Card** Variables → Initialize variable

- **Name** `Page_ok`
- **Type** `boolean`
- **Value** `false`

### `Init_Page_body`

**Placement** **Top level**

**Card** Variables → Initialize variable

- **Name** `Page_body`
- **Type** `object`
**Value** expression

```text
json('{}')
```

### `Init_Scan_ids`

**Placement** **Top level**

**Card** Variables → Initialize variable

- **Name** `Scan_ids`
- **Type** `array`
**Value** expression

```text
json('[]')
```

### `Init_Scan_rows`

**Placement** **Top level**

**Card** Variables → Initialize variable

- **Name** `Scan_rows`
- **Type** `array`
**Value** expression

```text
json('[]')
```

### `Init_Scan_count`

**Placement** **Top level**

**Card** Variables → Initialize variable

- **Name** `Scan_count`
- **Type** `integer`
- **Value** `0`

### `Init_Scan_pages`

**Placement** **Top level**

**Card** Variables → Initialize variable

- **Name** `Scan_pages`
- **Type** `integer`
- **Value** `0`

### `Init_Feed_passes`

**Placement** **Top level**

**Card** Variables → Initialize variable

- **Name** `Feed_passes`
- **Type** `array`
**Value** expression

```text
json('[]')
```

### `Init_Verified_feeds`

**Placement** **Top level**

**Card** Variables → Initialize variable

- **Name** `Verified_feeds`
- **Type** `array`
**Value** expression

```text
json('[]')
```

### `Init_Morning_groups`

**Placement** **Top level**

**Card** Variables → Initialize variable

- **Name** `Morning_groups`
- **Type** `array`
**Value** expression

```text
json('[]')
```

Add the review variables listed in [the review-file cards](REVIEW-BATCH-CARDS.md) before adding `For_each_feed`.

### `For_each_feed`

**Placement** **Top level**

**Card** Control → Apply to each

**Select an output from previous steps** expression

```text
outputs('Build_feeds')
```

Leave **Concurrency Control** off for this loop.

### `Reset_feed_passes`

**Placement** **Top level** → `For_each_feed`

**Card** Variables → Set variable

- **Name** `Feed_passes`
**Value** expression

```text
json('[]')
```

### `For_each_pass`

**Placement** **Top level** → `For_each_feed`

**Card** Control → Apply to each

**Select an output from previous steps** expression

```text
createArray('content','verification')
```

Leave **Concurrency Control** off for this loop.

### `Set_first_page`

**Placement** **Top level** → `For_each_feed` → `For_each_pass`

**Card** Variables → Set variable

- **Name** `Next_page`
**Value** expression

```text
if(equals(items('For_each_pass'),'content'),items('For_each_feed')?['full_url'],items('For_each_feed')?['check_url'])
```

### `Reset_scan_ids`

**Placement** **Top level** → `For_each_feed` → `For_each_pass`

**Card** Variables → Set variable

- **Name** `Scan_ids`
**Value** expression

```text
json('[]')
```

### `Reset_scan_rows`

**Placement** **Top level** → `For_each_feed` → `For_each_pass`

**Card** Variables → Set variable

- **Name** `Scan_rows`
**Value** expression

```text
json('[]')
```

### `Reset_scan_count`

**Placement** **Top level** → `For_each_feed` → `For_each_pass`

**Card** Variables → Set variable

- **Name** `Scan_count`
- **Value** `0`

### `Reset_scan_pages`

**Placement** **Top level** → `For_each_feed` → `For_each_pass`

**Card** Variables → Set variable

- **Name** `Scan_pages`
- **Value** `0`

### `Reset_scan_page_ok`

**Placement** **Top level** → `For_each_feed` → `For_each_pass`

**Card** Variables → Set variable

- **Name** `Page_ok`
- **Value** `false`

### `Read_pages`

**Placement** **Top level** → `For_each_feed` → `For_each_pass`

**Card** Control → Do until

**Left side** expression

```text
or(empty(variables('Next_page')),not(variables('Page_ok')))
```

Set the operator to **is equal to** and the right side to the expression `true`. Set **Count** to `1000` and **Timeout** to `PT1H` in the loop limits.

### `Current_page`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Data Operation → Compose

**Inputs** expression

```text
variables('Next_page')
```

### `Reset_page_ok`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Variables → Set variable

- **Name** `Page_ok`
- **Value** `false`

### `Clear_page_body`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Variables → Set variable

- **Name** `Page_body`
**Value** expression

```text
json('{}')
```

### `Read_source`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Control → Switch

**On** expression

```text
items('For_each_feed')?['kind']
```

Leave the **Default** branch empty. Create the cases below inside the Switch. You can omit the two Planner cases if Planner stays off, or build only the Planner case you use.

### `Read_Outlook`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages` → `Read_source` → case `outlook`

**Card** Office 365 Outlook → Send an HTTP request

Add **CustomHeader1** under advanced parameters. Leave **Body** blank.

**URI** expression

```text
outputs('Current_page')
```

- **Method** `GET`
- **CustomHeader1** `Prefer: IdType="ImmutableId", outlook.body-content-type="text", outlook.timezone="UTC"`

### `Save_Outlook_body`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages` → `Read_source` → case `outlook`

**Card** Variables → Set variable

- **Name** `Page_body`
**Value** expression

```text
json(string(body('Read_Outlook')))
```

### `Read_assigned`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages` → `Read_source` → case `assigned`

**Card** Planner → List my tasks

### `Save_assigned_body`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages` → `Read_source` → case `assigned`

**Card** Variables → Set variable

- **Name** `Page_body`
**Value** expression

```text
body('Read_assigned')
```

### `Read_plan`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages` → `Read_source` → case `plan`

**Card** Planner → List tasks

Choose **Enter custom value** for the picker field(s), then enter the expression(s).

**Group Id** expression

```text
items('For_each_feed')?['group_id']
```

**Plan Id** expression

```text
items('For_each_feed')?['plan_id']
```

### `Save_plan_body`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages` → `Read_source` → case `plan`

**Card** Variables → Set variable

- **Name** `Page_body`
**Value** expression

```text
body('Read_plan')
```

### `Check_page_shape`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Data Operation → Parse JSON

**Content** expression

```text
variables('Page_body')
```

**Schema**

```json
{
  "type": "object",
  "required": [
    "value"
  ],
  "properties": {
    "value": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "id"
        ],
        "properties": {
          "id": {
            "type": "string",
            "minLength": 1
          }
        }
      }
    },
    "@odata.nextLink": {
      "type": [
        "string",
        "null"
      ]
    }
  },
  "not": {
    "required": [
      "error"
    ]
  }
}
```

### `Select_page_ids`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Data Operation → Select

**From** expression

```text
body('Check_page_shape')?['value']
```

In **Map**, type each key as plain text. Enter each value beginning with `@` using **Expression** without the `@`. Enter other values as plain text.

```json
{
  "id": "@item()?['id']"
}
```

### `Merge_page_ids`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Data Operation → Compose

**Inputs** expression

```text
union(variables('Scan_ids'),body('Select_page_ids'))
```

### `Set_scan_ids`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Variables → Set variable

- **Name** `Scan_ids`
**Value** expression

```text
outputs('Merge_page_ids')
```

### `Count_page_records`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Variables → Increment variable

- **Name** `Scan_count`
**Value** expression

```text
length(body('Select_page_ids'))
```

### `Merge_page_rows`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Data Operation → Compose

**Inputs** expression

```text
if(equals(items('For_each_pass'),'content'),union(variables('Scan_rows'),body('Check_page_shape')?['value']),variables('Scan_rows'))
```

### `Set_scan_rows`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Variables → Set variable

- **Name** `Scan_rows`
**Value** expression

```text
outputs('Merge_page_rows')
```

### `Count_page`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Variables → Increment variable

- **Name** `Scan_pages`
- **Value** `1`

### `Continuation`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Data Operation → Compose

**Inputs** expression

```text
coalesce(body('Check_page_shape')?['@odata.nextLink'],'')
```

### `Save_continuation`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Variables → Set variable

- **Name** `Next_page`
**Value** expression

```text
outputs('Continuation')
```

### `Mark_page_result`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Read_pages`

**Card** Variables → Set variable

- **Name** `Page_ok`
**Value** expression

```text
or(empty(outputs('Continuation')),and(equals(items('For_each_feed')?['kind'],'outlook'),startsWith(toLower(outputs('Continuation')),'https://graph.microsoft.com/v1.0/me/'),not(equals(outputs('Continuation'),outputs('Current_page')))))
```

### `Save_complete_scan`

**Placement** **Top level** → `For_each_feed` → `For_each_pass`

**Card** Control → Condition

**Left side** expression

```text
and(variables('Page_ok'),empty(variables('Next_page')),greater(variables('Scan_pages'),0),equals(variables('Scan_count'),length(variables('Scan_ids'))))
```

Set the operator to **is equal to** and the right side to the expression `true`.

### `Append_complete_scan`

**Placement** **Top level** → `For_each_feed` → `For_each_pass` → `Save_complete_scan` → **True**

**Card** Variables → Append to array variable

- **Name** `Feed_passes`
**Value** expression

```text
setProperty(setProperty(setProperty(setProperty(json('{}'),'ids',variables('Scan_ids')),'rows',variables('Scan_rows')),'count',variables('Scan_count')),'pages',variables('Scan_pages'))
```

Leave **False** empty.

### `Has_two_complete_scans`

**Placement** **Top level** → `For_each_feed`

**Card** Control → Condition

**Left side** expression

```text
equals(length(variables('Feed_passes')),2)
```

Set the operator to **is equal to** and the right side to the expression `true`.

### `Full_scan`

**Placement** **Top level** → `For_each_feed` → `Has_two_complete_scans` → **True**

**Card** Data Operation → Compose

**Inputs** expression

```text
first(variables('Feed_passes'))
```

### `Audit_scan`

**Placement** **Top level** → `For_each_feed` → `Has_two_complete_scans` → **True**

**Card** Data Operation → Compose

**Inputs** expression

```text
last(variables('Feed_passes'))
```

### `Compare_id_sets`

**Placement** **Top level** → `For_each_feed` → `Has_two_complete_scans` → **True**

**Card** Control → Condition

**Left side** expression

```text
and(equals(length(outputs('Full_scan')?['ids']),length(outputs('Audit_scan')?['ids'])),equals(length(outputs('Full_scan')?['ids']),length(intersection(outputs('Full_scan')?['ids'],outputs('Audit_scan')?['ids']))))
```

Set the operator to **is equal to** and the right side to the expression `true`.

### `Keep_verified_feed`

**Placement** **Top level** → `For_each_feed` → `Has_two_complete_scans` → **True** → `Compare_id_sets` → **True**

**Card** Variables → Append to array variable

- **Name** `Verified_feeds`
**Value** expression

```text
setProperty(setProperty(setProperty(setProperty(setProperty(json('{}'),'feed',items('For_each_feed')?['key']),'verified_count',length(outputs('Full_scan')?['ids'])),'content_pages',outputs('Full_scan')?['pages']),'verification_pages',outputs('Audit_scan')?['pages']),'records',outputs('Full_scan')?['rows'])
```

### `Filter_morning_rows`

**Placement** **Top level** → `For_each_feed` → `Has_two_complete_scans` → **True** → `Compare_id_sets` → **True**

**Card** Data Operation → Filter array

**From** expression

```text
outputs('Full_scan')?['rows']
```

Use **Edit in advanced mode**, if available, and paste this as written. In the expression editor use the same value without the initial `@`.

```text
@if(contains(createArray('received','sent'),items('For_each_feed')?['key']),and(not(equals(item()?['isDraft'],true)),if(equals(items('For_each_feed')?['key'],'sent'),or(equals(item()?['parentFolderId'],outputs('Sent_folder_id')),contains(outputs('Known_addresses'),toLower(coalesce(item()?['from']?['emailAddress']?['address'],''))),contains(outputs('Known_addresses'),toLower(coalesce(item()?['sender']?['emailAddress']?['address'],'')))),not(equals(item()?['parentFolderId'],outputs('Sent_folder_id'))))),if(equals(items('For_each_feed')?['key'],'calendar'),and(not(equals(item()?['isCancelled'],true)),not(equals(item()?['responseStatus']?['response'],'declined'))),true))
```

If your designer shows a condition builder instead, put the expression on the left, select **is equal to**, and enter the expression `true` on the right.

### `Project_morning_rows`

**Placement** **Top level** → `For_each_feed` → `Has_two_complete_scans` → **True** → `Compare_id_sets` → **True**

**Card** Data Operation → Select

**From** expression

```text
body('Filter_morning_rows')
```

In **Map**, type each key as plain text. Enter each value beginning with `@` using **Expression** without the `@`. Enter other values as plain text.

```json
{
  "id": "@item()?['id']",
  "subject": "@coalesce(item()?['subject'],item()?['title'],'(no subject)')",
  "from": "@coalesce(item()?['from']?['emailAddress']?['address'],item()?['organizer']?['emailAddress']?['address'],'')",
  "to": "@if(contains(createArray('received','sent'),items('For_each_feed')?['key']),coalesce(item()?['toRecipients'],json('[]')),null)",
  "when": "@if(equals(items('For_each_feed')?['key'],'calendar'),item()?['start']?['dateTime'],if(equals(items('For_each_feed')?['key'],'sent'),item()?['sentDateTime'],item()?['receivedDateTime']))",
  "end": "@item()?['end']?['dateTime']",
  "all_day": "@item()?['isAllDay']",
  "due": "@item()?['dueDateTime']",
  "percent_complete": "@item()?['percentComplete']",
  "assignments": "@coalesce(item()?['_assignments'],item()?['assignments'])",
  "assigned_to_me": "@if(equals(items('For_each_feed')?['kind'],'outlook'),null,if(equals(items('For_each_feed')?['kind'],'assigned'),true,if(empty(outputs('Settings')?['planner_user_id']),null,or(contains(coalesce(item()?['assignments'],json('{}')),outputs('Settings')?['planner_user_id']),contains(string(coalesce(item()?['_assignments'],json('[]'))),concat('\"userId\":\"',outputs('Settings')?['planner_user_id'],'\"'))))))",
  "thread": "@item()?['conversationId']",
  "message_type": "@item()?['@odata.type']",
  "importance": "@item()?['importance']",
  "link": "@if(equals(items('For_each_feed')?['kind'],'outlook'),coalesce(item()?['webLink'],''),concat('https://planner.cloud.microsoft/webui/plan/',uriComponent(coalesce(item()?['planId'],'')),'/task/',uriComponent(item()?['id'])))",
  "excerpt": "@take(coalesce(item()?['bodyPreview'],item()?['body']?['content'],''),outputs('Settings')?['excerpt_chars'])",
  "excerpt_truncated": "@greater(length(coalesce(item()?['bodyPreview'],item()?['body']?['content'],'')),outputs('Settings')?['excerpt_chars'])"
}
```

### `Keep_morning_group`

**Placement** **Top level** → `For_each_feed` → `Has_two_complete_scans` → **True** → `Compare_id_sets` → **True**

**Card** Variables → Append to array variable

- **Name** `Morning_groups`
**Value** expression

```text
setProperty(setProperty(setProperty(json('{}'),'feed',items('For_each_feed')?['key']),'verified_count',length(outputs('Full_scan')?['ids'])),'records',body('Project_morning_rows'))
```

Leave **False** empty.

Leave **False** empty.

### `Publish_only_if_verified`

**Placement** **Top level**

**Card** Control → Condition

**Left side** expression

```text
and(equals(length(variables('Verified_feeds')),length(outputs('Build_feeds'))),equals(length(variables('Morning_groups')),length(outputs('Build_feeds'))))
```

Set the operator to **is equal to** and the right side to the expression `true`.

### `Coverage_counts`

**Placement** **Top level** → `Publish_only_if_verified` → **True**

**Card** Data Operation → Select

**From** expression

```text
variables('Verified_feeds')
```

In **Map**, type each key as plain text. Enter each value beginning with `@` using **Expression** without the `@`. Enter other values as plain text.

```json
{
  "feed": "@item()?['feed']",
  "records": "@item()?['verified_count']",
  "content_pages": "@item()?['content_pages']",
  "verification_pages": "@item()?['verification_pages']"
}
```

### `Run_metadata`

**Placement** **Top level** → `Publish_only_if_verified` → **True**

**Card** Data Operation → Compose

**Inputs** expression

```text
setProperty(setProperty(setProperty(setProperty(setProperty(setProperty(setProperty(setProperty(json('{}'),'status','verified'),'window_start_utc',outputs('Window_start')),'checkpoint_utc',outputs('Window_end')),'local_day',outputs('Local_day')),'time_zone',outputs('Settings')?['time_zone']),'planner_mode',outputs('Settings')?['planner_mode']),'work_account',outputs('Settings')?['work_account']),'mail_aliases',outputs('Settings')?['mail_aliases'])
```

### `Archive_name`

**Placement** **Top level** → `Publish_only_if_verified` → **True**

**Card** Data Operation → Compose

**Inputs** expression

```text
concat('verified-',formatDateTime(outputs('Window_end'),'yyyyMMddTHHmmssZ'),'-',workflow()?['run']?['name'],'.json')
```

### `Create_verified_archive`

**Placement** **Top level** → `Publish_only_if_verified` → **True**

**Card** OneDrive for Business → Create file

- **Folder Path** `/WorkMailMorning/Archive`
**File Name** expression

```text
outputs('Archive_name')
```

**File Content** expression

```text
string(setProperty(outputs('Run_metadata'),'feeds',variables('Verified_feeds')))
```

After `Create_verified_archive`, continue with [the review-file cards](REVIEW-BATCH-CARDS.md). Keep the **False** branch below.

### `Fail_coverage`

**Placement** **Top level** → `Publish_only_if_verified` → **False**

**Card** Control → Terminate

- **Status** `Failed`
- **Code** `WorkMailVerification`
- **Message** `Coverage did not verify for every configured feed. Inspect the first incomplete or mismatched feed in run history. The prior checkpoint stays in effect.`
