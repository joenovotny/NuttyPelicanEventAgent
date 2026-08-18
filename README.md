# Nutty Pelican Event Agent

A local-first event pipeline and organizer-outreach assistant for The Nutty Pelican. V1 tracks opportunities, asks only unanswered organizer questions, records replies, extracts clear facts, and hands every consequential action back to Joe.

## Safety boundary

The application is intentionally unable to autonomously:

- submit or complete vendor applications;
- send or authorize payments;
- accept terms, sign agreements, or enter contracts;
- provide banking, tax, identity, or sensitive information; or
- commit The Nutty Pelican to an event.

Application openings, risky payment requests, unusual terms, and sensitive requests are escalated as **Joe Action Required**. Outbound message validation is a second line of defense, not permission to run the app without human oversight.

## What V1 includes

- SQLite event database and audit-friendly message history
- Pipeline statuses from `Discovered` through `Accepted` or `Declined/Skip`
- Responsive dashboard, event editor, missing-question list, and outreach draft
- Wilmington-area seed candidates from the original planning work
- Conservative organizer-response parser with application and payment flags
- Microsoft Graph send and inbox-import clients
- Business knowledge, question set, outreach templates, and scam checks in `config/`
- Environment-only secrets and automated tests for core guardrails

## Run locally

Python 3.11 or newer is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask --app run seed
flask --app run run --debug
```

Open <http://127.0.0.1:5000>. You can also load seed events from the empty dashboard. The SQLite file is created under `instance/` and is ignored by Git.

Run the tests:

```bash
python -m unittest discover -s tests
```

## Microsoft 365 / Graph setup

Keep `GRAPH_ENABLED=false` until `EventPlanning@thenuttypelican.com` is confirmed able to send as an alias.

1. In Microsoft Entra admin center, register a new single-tenant application.
2. Create a client secret and store its value securely. Never commit it.
3. Do not add tenant-wide Microsoft Graph mail permissions in Entra. Use Exchange Online Application RBAC to assign `Application Mail.Read` and `Application Mail.Send` to the app within a custom resource scope for the owning mailbox.
4. Verify the restriction with `Test-ServicePrincipalAuthorization`; both roles must show `InScope=True` for the owning mailbox and must not authorize unrelated mailboxes.
5. Set `GRAPH_MAILBOX_USER` to the real licensed mailbox that owns the alias. Set `OUTREACH_FROM_ADDRESS=EventPlanning@thenuttypelican.com`.
6. In Exchange Online, confirm send-from-alias is enabled and test the alias manually first.
7. Fill the Graph values in `.env`, set `GRAPH_ENABLED=true`, restart the app, and send a test to an address you control.

The client uses OAuth client credentials; no Microsoft password is stored. The configured mailbox must have permission to send from the alias. If Graph rejects the explicit `from` address in your tenant, use a dedicated licensed mailbox for `EventPlanning@...` or configure the mailbox's send-as permissions; do not work around the restriction with personal credentials.

### Import replies

V1 puts a durable token such as `[NP-EVENT-0011]` in every outgoing subject. Replies are matched by that token. Sender-address matching is used only as a fallback when the address belongs to exactly one event. The app saves the raw message and applies conservative extraction rules:

```bash
flask --app run sync-inbox
```

The same command also reconciles Outlook Sent Items. A manually sent message is attached to an event only when its subject retains the `[NP-EVENT-####]` token. Untagged sent messages and messages from unknown or ambiguous senders remain untouched.

### Background automation

Automation is off by default. Its boundaries are:

- `Qualified` events with a contact email may receive the initial information-only outreach.
- `Waiting` and `Follow-up Needed` events may receive a follow-up after the configured delay.
- No more than `AUTOMATION_MAX_FOLLOW_UPS` are sent for an event.
- Application openings, sensitive requests, send failures, and exhausted follow-ups stop the event at `Joe Action Required` and create a dashboard alert.
- Applications, payments, contracts, commitments, and sensitive information remain prohibited.

After supervised testing, set these values in `.env`:

```text
AUTOMATION_SEND_ENABLED=true
AUTOMATION_POLL_MINUTES=10
AUTOMATION_LOOKBACK_HOURS=72
AUTOMATION_FOLLOW_UP_DAYS=3
AUTOMATION_MAX_FOLLOW_UPS=2
```

Run one cycle first:

```bash
flask --app run.py automation-once
```

Then start the continuous local worker:

```bash
flask --app run.py automation-worker
```

The local worker runs only while the Mac is awake and the process is active. For reliable unattended operation, deploy the web app and worker to an always-on host with encrypted environment settings, authentication, PostgreSQL, backups, and HTTPS.

## Data and workflow notes

- Seed facts are leads, not verified current event data. Confirm dates, fees, contacts, and links through official sources before outreach.
- Add an official contact email to an event before sending.
- Drafts ask only questions whose event fields are blank.
- Parsed values are visible and editable; the parser does not make business decisions.
- For application openings with a link, status becomes `Joe Action Required`. Joe follows the official link and handles the application and payment personally.

## Deployment path

The app can later run on Render, Railway, Azure App Service, or a small container host. Before deployment:

1. switch from SQLite to managed PostgreSQL by setting `DATABASE_URL`;
2. put all secrets in the host's encrypted environment settings;
3. run behind HTTPS with a strong `SECRET_KEY` and authentication;
4. add database migrations and backups;
5. schedule `flask --app run sync-inbox`;
6. restrict Graph access to the event mailbox; and
7. add an explicit review/approval screen before enabling automated sends or follow-ups.

V1 intentionally does not include public deployment, autonomous discovery, AI-generated replies, background sending, applications, or payments. Those should be added only after the local workflow and review controls are proven.
