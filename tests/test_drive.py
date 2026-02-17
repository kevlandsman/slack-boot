from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from services.drive import DriveClient


@pytest.fixture
def mock_auth():
    auth = MagicMock()
    auth.get_credentials.return_value = MagicMock()
    return auth


def _make_client_with_services(mock_auth):
    """Create a DriveClient with pre-injected mock services."""
    client = DriveClient(mock_auth)
    mock_drive = MagicMock()
    mock_docs = MagicMock()
    client._drive_service = mock_drive
    client._docs_service = mock_docs
    return client, mock_drive, mock_docs


class TestDriveClient:
    def test_no_share_or_delete_methods(self, mock_auth):
        """Verify the class has no outbound communication or destructive methods."""
        client = DriveClient(mock_auth)
        for forbidden in [
            "share_file", "share_document", "share",
            "delete", "delete_file", "trash",
            "set_permissions", "update_permissions",
        ]:
            assert not hasattr(client, forbidden), (
                f"DriveClient should not have '{forbidden}' method"
            )

    @patch("services.drive.build")
    def test_lazy_drive_service_init(self, mock_build, mock_auth):
        client = DriveClient(mock_auth)
        assert client._drive_service is None
        client._get_drive_service()
        mock_build.assert_called_once_with(
            "drive", "v3", credentials=mock_auth.get_credentials()
        )

    @patch("services.drive.build")
    def test_lazy_docs_service_init(self, mock_build, mock_auth):
        client = DriveClient(mock_auth)
        assert client._docs_service is None
        client._get_docs_service()
        mock_build.assert_called_once_with(
            "docs", "v1", credentials=mock_auth.get_credentials()
        )

    def test_create_document_without_content(self, mock_auth):
        client, mock_drive, mock_docs = _make_client_with_services(mock_auth)

        mock_docs.documents().create().execute.return_value = {
            "documentId": "doc123",
        }

        result = client.create_document("My Document")

        assert result["id"] == "doc123"
        assert result["title"] == "My Document"
        assert "docs.google.com/document/d/doc123" in result["url"]
        # batchUpdate should NOT be called when no content
        mock_docs.documents().batchUpdate.assert_not_called()

    def test_create_document_with_content(self, mock_auth):
        client, mock_drive, mock_docs = _make_client_with_services(mock_auth)

        mock_docs.documents().create().execute.return_value = {
            "documentId": "doc456",
        }
        mock_docs.documents().batchUpdate().execute.return_value = {}

        result = client.create_document("Notes", content="Hello world")

        assert result["id"] == "doc456"
        assert result["title"] == "Notes"
        # batchUpdate should be called to insert content
        mock_docs.documents().batchUpdate.assert_called()

    def test_list_files_no_query(self, mock_auth):
        client, mock_drive, mock_docs = _make_client_with_services(mock_auth)

        mock_drive.files().list().execute.return_value = {
            "files": [
                {
                    "id": "f1",
                    "name": "File One",
                    "mimeType": "application/vnd.google-apps.document",
                    "webViewLink": "https://docs.google.com/document/d/f1",
                    "modifiedTime": "2025-01-01T00:00:00.000Z",
                },
            ]
        }

        result = client.list_files()
        assert len(result) == 1
        assert result[0]["name"] == "File One"

    def test_list_files_with_query(self, mock_auth):
        client, mock_drive, mock_docs = _make_client_with_services(mock_auth)
        mock_drive.files().list().execute.return_value = {"files": []}

        result = client.list_files(query="name contains 'test'", max_results=5)
        assert result == []

    def test_list_files_empty(self, mock_auth):
        client, mock_drive, mock_docs = _make_client_with_services(mock_auth)
        mock_drive.files().list().execute.return_value = {}

        result = client.list_files()
        assert result == []

    def test_get_file_metadata(self, mock_auth):
        client, mock_drive, mock_docs = _make_client_with_services(mock_auth)

        mock_drive.files().get().execute.return_value = {
            "id": "f2",
            "name": "Report",
            "mimeType": "application/vnd.google-apps.document",
            "webViewLink": "https://docs.google.com/document/d/f2",
            "modifiedTime": "2025-06-15T10:30:00.000Z",
        }

        result = client.get_file_metadata("f2")
        assert result["name"] == "Report"
        assert result["id"] == "f2"
