from __future__ import annotations

import base64
import os
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]
from googleapiclient.discovery import build  # type: ignore[import-untyped]

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]


class GmailConnector:
    def __init__(self, token_file: str | Path, sender: str = "me") -> None:
        self.token_file = Path(token_file)
        self.sender = sender

    def authenticate(self, client_secret_file: str | Path | None = None) -> None:
        credentials: Credentials | None = None
        if self.token_file.exists():
            credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
                str(self.token_file), SCOPES
            )
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())  # type: ignore[no-untyped-call]
        if not credentials or not credentials.valid:
            secret = Path(client_secret_file or os.environ.get("GMAIL_CLIENT_SECRET_FILE", ""))
            if not secret.exists():
                raise RuntimeError("GMAIL_CLIENT_SECRET_FILE is missing")
            flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
            credentials = flow.run_local_server(port=0)
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(credentials.to_json())
        os.chmod(self.token_file, 0o600)

    def _service(self) -> Any:
        if not self.token_file.exists():
            raise RuntimeError("Gmail is not authenticated; run `reaper gmail-auth`")
        credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
            str(self.token_file), SCOPES
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self.token_file.write_text(credentials.to_json())
            os.chmod(self.token_file, 0o600)
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)

    @staticmethod
    def _raw_message(to: str, subject: str, body: str) -> str:
        message = EmailMessage()
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        return base64.urlsafe_b64encode(message.as_bytes()).decode()

    def create_draft(self, *, to: str, subject: str, body: str) -> dict[str, Any]:
        if not to.strip():
            raise ValueError("Recipient address is empty")
        response = (
            self._service()
            .users()
            .drafts()
            .create(
                userId=self.sender,
                body={"message": {"raw": self._raw_message(to, subject, body)}},
            )
            .execute()
        )
        return {"draft_id": response["id"], "message_id": response["message"]["id"]}

    def send(self, *, to: str, subject: str, body: str) -> dict[str, Any]:
        if not to.strip():
            raise ValueError("Recipient address is empty")
        response = (
            self._service()
            .users()
            .messages()
            .send(
                userId=self.sender,
                body={"raw": self._raw_message(to, subject, body)},
            )
            .execute()
        )
        return {"message_id": response["id"], "thread_id": response.get("threadId")}
