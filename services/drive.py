from __future__ import annotations

import logging
from typing import Optional

from googleapiclient.discovery import build

from services.google_auth import GoogleAuthManager

logger = logging.getLogger(__name__)


class DriveClient:
    """Google Drive client — create and read only.

    No share, delete, or permissions methods.  The bot has zero ability to
    communicate outward through Google Drive.
    """

    def __init__(self, auth_manager: GoogleAuthManager):
        self._auth = auth_manager
        self._drive_service = None
        self._docs_service = None

    def _get_drive_service(self):
        if self._drive_service is None:
            creds = self._auth.get_credentials()
            self._drive_service = build("drive", "v3", credentials=creds)
        return self._drive_service

    def _get_docs_service(self):
        if self._docs_service is None:
            creds = self._auth.get_credentials()
            self._docs_service = build("docs", "v1", credentials=creds)
        return self._docs_service

    def create_document(self, title: str, content: str = "") -> dict:
        """Create a Google Doc with optional initial content.

        Returns ``{id, title, url}``.
        """
        docs = self._get_docs_service()
        doc = docs.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]

        if content:
            docs.documents().batchUpdate(
                documentId=doc_id,
                body={
                    "requests": [
                        {
                            "insertText": {
                                "location": {"index": 1},
                                "text": content,
                            }
                        }
                    ]
                },
            ).execute()

        return {
            "id": doc_id,
            "title": title,
            "url": f"https://docs.google.com/document/d/{doc_id}/edit",
        }

    def list_files(
        self, query: Optional[str] = None, max_results: int = 20
    ) -> list[dict]:
        """List files in Drive.

        *query* uses `Drive query syntax`_.  Returns a list of file dicts with
        ``id``, ``name``, ``mimeType``, ``webViewLink``, and ``modifiedTime``.

        .. _Drive query syntax:
            https://developers.google.com/drive/api/guides/search-files
        """
        service = self._get_drive_service()
        kwargs = {
            "pageSize": max_results,
            "fields": "files(id, name, mimeType, webViewLink, modifiedTime)",
        }
        if query:
            kwargs["q"] = query
        result = service.files().list(**kwargs).execute()
        return result.get("files", [])

    def get_file_metadata(self, file_id: str) -> dict:
        """Get metadata for a single file."""
        service = self._get_drive_service()
        return (
            service.files()
            .get(
                fileId=file_id,
                fields="id, name, mimeType, webViewLink, modifiedTime",
            )
            .execute()
        )
