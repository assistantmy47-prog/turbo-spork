# Create the export flow

Create this once in the work Power Automate environment. The Mac supplies the URLs and run ID each time. The flow reads through the standard **Office 365 Outlook** connector and saves JSON to a work OneDrive folder. It uses the connection you sign in with in Power Automate. There is no custom app registration, premium HTTP action, or credential on the Mac. The Outlook action calls Microsoft Graph inside the Microsoft-managed connector.

## 1. Set up the flow

1. Create a folder named `WorkMailExport` in work OneDrive.
2. At [Power Automate](https://make.powerautomate.com), choose **Create → Instant cloud flow → Manually trigger a flow**. Add one **File** input named `Request`.
3. Add **Data Operation → Compose**, name it `Read_request`, and enter this expression:

   ```text
   json(base64ToString(triggerBody()?['file']?['contentBytes']))
   ```

4. Initialize two variables at the top level. `Next_url` is a **String** with initial value `''` (Expression). `Page_number` is an **Integer** with initial value `1`.
5. Add **Apply to each**, name it `For_each_feed`, and use this expression as the input. Keep concurrency off because the loop shares variables.

   ```text
   outputs('Read_request')?['feeds']
   ```

## 2. Add the Outlook branch

Inside `For_each_feed`, add **Switch** using the expression below. Add a case with value `outlook`.

```text
items('For_each_feed')?['kind']
```

Inside the `outlook` case:

1. Set `Next_url` using the expression `items('For_each_feed')?['url']`. Set `Page_number` to `1`.
2. Add **Do until**. Set its condition to `variables('Next_url')` **is equal to** `''` (Expression). Open **Change limits**, set **Count** to `1000` and **Timeout** to `PT1H`.
3. Inside **Do until**, add **Office 365 Outlook → Send an HTTP request** and name it `Read_outlook_page`. Use the following fields. Choose the Outlook action from that connector, as several connectors have similar action names. [Connector reference](https://learn.microsoft.com/en-us/connectors/office365connector/#send-an-http-request)

   | Field | Value |
   |---|---|
   | URI | Expression `variables('Next_url')` |
   | Method | `GET` |
   | CustomHeader1 | `Prefer: IdType="ImmutableId", outlook.body-content-type="text", outlook.timezone="UTC"` |

4. Add a **Compose** named `Outlook_response` with expression `json(string(body('Read_outlook_page')))`.
5. Add **OneDrive for Business → Create file** inside the same loop. Set **Folder Path** to `/WorkMailExport`. Enter the following expressions in **File Name** and **File Content**.

   ```text
   concat(outputs('Read_request')?['request_id'], '--', items('For_each_feed')?['key'], '--', string(variables('Page_number')), '.json')
   ```

   ```text
   string(setProperty(setProperty(json('{}'), 'url', variables('Next_url')), 'body', outputs('Outlook_response')))
   ```

6. After **Create file**, increment `Page_number` by `1`. Then **Set variable** for `Next_url` using:

   ```text
   coalesce(outputs('Outlook_response')?['@odata.nextLink'], '')
   ```

The action reads the next page exactly as supplied by Outlook. Keep the default action sequencing so a failed read or file write halts page processing. In flow run history, use the connector's action settings for secure inputs and outputs where available. The export files contain work mail and calendar data. Use the approved work OneDrive and delete its staging files after a verified import if company policy permits.

## 3. Add Planner if needed

Planner is optional. For **assigned to me**, add a Switch case named `assigned` containing **Planner → List my tasks**. For selected plans, add a case named `plan` containing **Planner → List tasks**. Set **Group Id** and **Plan Id** to custom values using `items('For_each_feed')?['group_id']` and `items('For_each_feed')?['plan_id']`, respectively. Use the current, non-deprecated actions. [Planner connector reference](https://learn.microsoft.com/en-us/connectors/planner/)

In each enabled Planner case, name the List action `Read_assigned_tasks` or `Read_plan_tasks` and add **OneDrive for Business → Create file** for the same folder. Use:

```text
concat(outputs('Read_request')?['request_id'], '--', items('For_each_feed')?['key'], '--1.json')
```

```text
string(setProperty(setProperty(json('{}'), 'url', ''), 'body', body('Read_assigned_tasks')))
```

For the plan case, substitute `Read_plan_tasks` in the last expression. The Mac reads tasks from the current snapshot and compares the IDs across two connector calls. If the connector exports a continuation instead of a complete array, the import fails visibly. Start with Planner off for the first smoke test.

## 4. Run and verify

Run the flow manually and upload the file printed by `python3 assistant.py prepare` to **Request**. Wait for successful completion and OneDrive sync, or download/extract the files into one local folder. Run `python3 assistant.py import-export /path/to/local/WorkMailExport`.

If an action returns 403 or the flow cannot save to OneDrive, check whether your tenant permits the specific standard connector action and OneDrive destination. Access to **Get emails (V3)** alone does not establish access to **Send an HTTP request**. If there are partial outputs or you need a fresh attempt, run `prepare --replace` with the same date options to get a new request ID. Only complete and reconciled requests advance the collection checkpoint.
