import os
import base64
import mimetypes
from pathlib import Path

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

    def send(self, recipient, subject, body, attachments=None):
        validate_outbound(body)
        encoded_attachments = []
        for item in attachments or []:
            path = Path(item)
            data = path.read_bytes()
            if len(data) > 3_000_000:
                raise ValueError(f"Attachment is too large for V1 direct sending: {path.name}")
            encoded_attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": path.name,
                "contentType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "contentBytes": base64.b64encode(data).decode("ascii"),
            })
        message = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": recipient}}],
            "from": {"emailAddress": {"address": os.getenv("OUTREACH_FROM_ADDRESS", self.mailbox)}},
        }
        if encoded_attachments:
            message["attachments"] = encoded_attachments
        response = requests.post(
            f"{GRAPH_ROOT}/users/{self.mailbox}/sendMail",
            headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"},
            json={
                "message": message,
                "saveToSentItems": True,
            },
            timeout=20,
        )
        response.raise_for_status()

    def recent_messages(self, since_iso):
        return self._recent_folder_messages("inbox", since_iso)

    def recent_sent_messages(self, since_iso):
        return self._recent_folder_messages("sentitems", since_iso)

    def _recent_folder_messages(self, folder, since_iso):
        token = self._token()
        response = requests.get(
            f"{GRAPH_ROOT}/users/{self.mailbox}/mailFolders/{folder}/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "$filter": f"{'receivedDateTime' if folder == 'inbox' else 'sentDateTime'} ge {since_iso}",
                "$select": "id,subject,body,from,receivedDateTime,sentDateTime",
                "$orderby": "receivedDateTime asc" if folder == "inbox" else "sentDateTime asc",
                "$top": "50",
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("value", [])
