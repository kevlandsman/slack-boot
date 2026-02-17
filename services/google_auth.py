from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

# Read-only Gmail + app-owned Drive files only. Zero outbound communication.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
]

DEFAULT_TOKEN_PATH = Path.home() / ".slack-booty" / "google_token.json"
DEFAULT_CREDENTIALS_PATH = Path.home() / ".slack-booty" / "google_credentials.json"


class GoogleAuthManager:
    """Manages OAuth2 credentials for Google APIs.

    Token is stored at ``~/.slack-booty/google_token.json`` and auto-refreshed
    on every ``get_credentials()`` call.  Run ``python -m services.google_auth``
    once to perform the interactive browser-based OAuth flow.
    """

    def __init__(
        self,
        token_path: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ):
        self.token_path = Path(token_path) if token_path else DEFAULT_TOKEN_PATH
        self.credentials_path = (
            Path(credentials_path) if credentials_path else DEFAULT_CREDENTIALS_PATH
        )
        self._credentials: Optional[Credentials] = None

    def get_credentials(self) -> Credentials:
        """Return valid credentials, refreshing if needed.

        Raises ``RuntimeError`` if no token file exists (user must run the
        interactive flow first).
        """
        # Return cached valid credentials
        if self._credentials and self._credentials.valid:
            return self._credentials

        # Try refreshing cached expired credentials
        if (
            self._credentials
            and self._credentials.expired
            and self._credentials.refresh_token
        ):
            self._credentials.refresh(Request())
            self._save_token()
            return self._credentials

        # Try loading from disk
        if self.token_path.exists():
            self._credentials = Credentials.from_authorized_user_file(
                str(self.token_path), SCOPES
            )
            if self._credentials.valid:
                return self._credentials
            if self._credentials.expired and self._credentials.refresh_token:
                self._credentials.refresh(Request())
                self._save_token()
                return self._credentials

        raise RuntimeError(
            "No valid Google credentials found. "
            "Run: python -m services.google_auth"
        )

    def run_interactive_flow(self):
        """One-time interactive OAuth flow.  Opens a browser window."""
        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"OAuth client credentials not found at {self.credentials_path}. "
                "Download them from the Google Cloud Console."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.credentials_path), SCOPES
        )
        self._credentials = flow.run_local_server(port=0)
        self._save_token()
        logger.info("Google credentials saved to %s", self.token_path)

    def is_configured(self) -> bool:
        """Check whether valid (or refreshable) credentials exist."""
        try:
            self.get_credentials()
            return True
        except Exception:
            return False

    def _save_token(self):
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(self._credentials.to_json())
