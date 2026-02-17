from __future__ import annotations

import base64
import logging
import re
from typing import Optional

from googleapiclient.discovery import build

from services.google_auth import GoogleAuthManager

logger = logging.getLogger(__name__)


class GmailClient:
    """Read-only Gmail client.  No send, draft, compose, or modify methods."""

    def __init__(self, auth_manager: GoogleAuthManager):
        self._auth = auth_manager
        self._service = None

    def _get_service(self):
        if self._service is None:
            creds = self._auth.get_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def search_messages(self, query: str, max_results: int = 10) -> list[dict]:
        """Search Gmail with a query string (same syntax as the Gmail search bar).

        Returns a list of message summaries:
        ``{id, subject, from, date, snippet}``
        """
        service = self._get_service()
        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        messages = result.get("messages", [])
        return [self._get_message_summary(m["id"]) for m in messages]

    def get_message(self, message_id: str) -> dict:
        """Get full message content by ID.

        Returns ``{id, subject, from, to, date, body, snippet}``.
        """
        service = self._get_service()
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        return self._parse_message(msg)

    def list_recent(self, max_results: int = 10) -> list[dict]:
        """List recent inbox messages."""
        return self.search_messages("in:inbox", max_results=max_results)

    def list_unread(self, max_results: int = 20) -> list[dict]:
        """List unread messages."""
        return self.search_messages("is:unread", max_results=max_results)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_message_summary(self, message_id: str) -> dict:
        service = self._get_service()
        msg = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            )
            .execute()
        )
        headers = {
            h["name"]: h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }
        return {
            "id": message_id,
            "subject": headers.get("Subject", "(no subject)"),
            "from": headers.get("From", "unknown"),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
        }

    def _parse_message(self, msg: dict) -> dict:
        headers = {
            h["name"]: h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }
        body = self._extract_body(msg.get("payload", {}))
        return {
            "id": msg["id"],
            "subject": headers.get("Subject", "(no subject)"),
            "from": headers.get("From", "unknown"),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "body": body,
            "snippet": msg.get("snippet", ""),
        }

    def _extract_body(self, payload: dict, max_length: int = 3000) -> str:
        """Extract plain-text body from a message payload.

        Prefers ``text/plain`` parts; falls back to ``text/html`` with tags
        stripped.  Handles multipart messages recursively.
        """
        # Direct body (non-multipart)
        mime = payload.get("mimeType", "")
        body_data = payload.get("body", {}).get("data")

        if body_data and mime == "text/plain":
            return self._decode_body(body_data)[:max_length]

        # Multipart — recurse into parts
        parts = payload.get("parts", [])

        # First pass: look for text/plain only
        plain = self._find_part(parts, "text/plain")
        if plain:
            return self._decode_body(plain)[:max_length]

        # Second pass: fall back to text/html (strip tags)
        html = self._find_part(parts, "text/html")
        if html:
            return self._strip_html(self._decode_body(html))[:max_length]

        # Last resort: top-level body data of any type
        if body_data:
            return self._decode_body(body_data)[:max_length]

        return ""

    def _find_part(self, parts: list, target_mime: str) -> str | None:
        """Recursively search parts for the first matching MIME type.

        Returns the base64url data string or ``None``.
        """
        for part in parts:
            if part.get("mimeType") == target_mime:
                data = part.get("body", {}).get("data")
                if data:
                    return data
            # Recurse into nested multipart
            nested_parts = part.get("parts", [])
            if nested_parts:
                found = self._find_part(nested_parts, target_mime)
                if found:
                    return found
        return None

    @staticmethod
    def _decode_body(data: str) -> str:
        """Decode a base64url-encoded body part."""
        try:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        except Exception:
            return ""

    @staticmethod
    def _strip_html(html: str) -> str:
        """Crude HTML tag stripper for fallback body extraction."""
        text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        return text.strip()
