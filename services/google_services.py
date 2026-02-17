from __future__ import annotations

import asyncio
import logging
from typing import Optional

from services.google_auth import GoogleAuthManager
from services.gmail import GmailClient
from services.drive import DriveClient

logger = logging.getLogger(__name__)


class GoogleServices:
    """Unified async facade over Gmail (read-only) and Drive (create/read only).

    All public methods are async and safe to call from the event loop —
    synchronous Google API calls are offloaded via ``asyncio.to_thread``.
    """

    def __init__(self, auth_manager: GoogleAuthManager):
        self._auth = auth_manager
        self._gmail: Optional[GmailClient] = None
        self._drive: Optional[DriveClient] = None

    @property
    def available(self) -> bool:
        """True if Google credentials are configured and valid."""
        return self._auth.is_configured()

    @property
    def gmail(self) -> GmailClient:
        if self._gmail is None:
            self._gmail = GmailClient(self._auth)
        return self._gmail

    @property
    def drive(self) -> DriveClient:
        if self._drive is None:
            self._drive = DriveClient(self._auth)
        return self._drive

    # ------------------------------------------------------------------
    # Gmail (read-only)
    # ------------------------------------------------------------------

    async def search_email(self, query: str, max_results: int = 10) -> list[dict]:
        """Search Gmail.  Uses Gmail query syntax."""
        return await asyncio.to_thread(
            self.gmail.search_messages, query, max_results
        )

    async def read_email(self, message_id: str) -> dict:
        """Get full message content by ID."""
        return await asyncio.to_thread(self.gmail.get_message, message_id)

    async def list_unread_email(self, max_results: int = 20) -> list[dict]:
        """List unread messages."""
        return await asyncio.to_thread(self.gmail.list_unread, max_results)

    async def list_recent_email(self, max_results: int = 10) -> list[dict]:
        """List recent inbox messages."""
        return await asyncio.to_thread(self.gmail.list_recent, max_results)

    # ------------------------------------------------------------------
    # Drive (create + read only — no share, no delete)
    # ------------------------------------------------------------------

    async def create_document(self, title: str, content: str = "") -> dict:
        """Create a Google Doc.  Returns ``{id, title, url}``."""
        return await asyncio.to_thread(
            self.drive.create_document, title, content
        )

    async def list_drive_files(
        self, query: Optional[str] = None, max_results: int = 20
    ) -> list[dict]:
        """List files in Drive."""
        return await asyncio.to_thread(
            self.drive.list_files, query, max_results
        )

    async def get_file_metadata(self, file_id: str) -> dict:
        """Get metadata for a single Drive file."""
        return await asyncio.to_thread(
            self.drive.get_file_metadata, file_id
        )
