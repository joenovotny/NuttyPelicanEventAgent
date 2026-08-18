import os

import requests

from .guardrails import validate_outbound

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


class GraphNotConfigured(RuntimeError):
    pass


class GraphEmailClient:
    def __init__(self):
        self.enabled = os.getenv("GRAPH_ENABLED", "false").lower() == "true"
        self.tenant_id = os.getenv("GRAPH_TENANT_ID", "")
        self.client_id = os.getenv("GRAPH_CLIENT_ID", "")
        self.client_secret = os.getenv("GRAPH_CLIENT_SECRET", "")
        self.mailbox = os.getenv("GRAPH_MAILBOX_USER", "")

    def _require_config(self):
        if not self.enabled or not all((self.tenant_id, self.client_id, self.client_secret, self.mailbox)):
            raise GraphNotConfigured("Microsoft Graph is not enabled or is missing configuration.")

    def _token(self):
        self._require_config()
        response = requests.post(
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def send(self, recipient, subject, body):
        validate_outbound(body)
        response = requests.post(
            f"{GRAPH_ROOT}/users/{self.mailbox}/sendMail",
            headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"},
            json={
                "message": {
                    "subject": subject,
                    "body": {"contentType": "Text", "content": body},
                    "toRecipients": [{"emailAddress": {"address": recipient}}],
                    "from": {"emailAddress": {"address": os.getenv("OUTREACH_FROM_ADDRESS", self.mailbox)}},
                },
                "saveToSentItems": True,
            },
            timeout=20,
        )
        response.raise_for_status()

    def recent_messages(self, since_iso):
        token = self._token()
        response = requests.get(
            f"{GRAPH_ROOT}/users/{self.mailbox}/mailFolders/inbox/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "$filter": f"receivedDateTime ge {since_iso}",
                "$select": "id,subject,body,from,receivedDateTime",
                "$orderby": "receivedDateTime asc",
                "$top": "50",
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("value", [])

