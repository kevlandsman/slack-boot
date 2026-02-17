from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from services.google_services import GoogleServices


@pytest.fixture
def mock_auth():
    auth = MagicMock()
    auth.is_configured.return_value = True
    auth.get_credentials.return_value = MagicMock()
    return auth


@pytest.fixture
def services(mock_auth):
    return GoogleServices(mock_auth)


class TestGoogleServices:
    def test_available_true(self, services, mock_auth):
        mock_auth.is_configured.return_value = True
        assert services.available is True

    def test_available_false(self, services, mock_auth):
        mock_auth.is_configured.return_value = False
        assert services.available is False

    def test_lazy_gmail_init(self, services):
        assert services._gmail is None
        gmail = services.gmail
        assert gmail is not None
        # Second access returns same instance
        assert services.gmail is gmail

    def test_lazy_drive_init(self, services):
        assert services._drive is None
        drive = services.drive
        assert drive is not None
        assert services.drive is drive

    def test_no_share_methods(self, services):
        """Verify the facade has no outbound communication methods."""
        for forbidden in [
            "share_document", "share_file", "send_email",
            "delete_file", "set_permissions",
        ]:
            assert not hasattr(services, forbidden), (
                f"GoogleServices should not have '{forbidden}' method"
            )

    @pytest.mark.asyncio
    async def test_search_email(self, services):
        mock_gmail = MagicMock()
        mock_gmail.search_messages.return_value = [
            {"id": "1", "subject": "Test"}
        ]
        services._gmail = mock_gmail

        results = await services.search_email("from:alice")
        assert len(results) == 1
        mock_gmail.search_messages.assert_called_once_with("from:alice", 10)

    @pytest.mark.asyncio
    async def test_read_email(self, services):
        mock_gmail = MagicMock()
        mock_gmail.get_message.return_value = {
            "id": "msg1", "subject": "Hello", "body": "Content"
        }
        services._gmail = mock_gmail

        result = await services.read_email("msg1")
        assert result["subject"] == "Hello"
        mock_gmail.get_message.assert_called_once_with("msg1")

    @pytest.mark.asyncio
    async def test_list_unread_email(self, services):
        mock_gmail = MagicMock()
        mock_gmail.list_unread.return_value = []
        services._gmail = mock_gmail

        results = await services.list_unread_email(max_results=5)
        assert results == []
        mock_gmail.list_unread.assert_called_once_with(5)

    @pytest.mark.asyncio
    async def test_list_recent_email(self, services):
        mock_gmail = MagicMock()
        mock_gmail.list_recent.return_value = [{"id": "1"}]
        services._gmail = mock_gmail

        results = await services.list_recent_email(max_results=3)
        assert len(results) == 1
        mock_gmail.list_recent.assert_called_once_with(3)

    @pytest.mark.asyncio
    async def test_create_document(self, services):
        mock_drive = MagicMock()
        mock_drive.create_document.return_value = {
            "id": "doc1", "title": "Notes", "url": "https://docs.google.com/..."
        }
        services._drive = mock_drive

        result = await services.create_document("Notes", content="Hello")
        assert result["id"] == "doc1"
        mock_drive.create_document.assert_called_once_with("Notes", "Hello")

    @pytest.mark.asyncio
    async def test_list_drive_files(self, services):
        mock_drive = MagicMock()
        mock_drive.list_files.return_value = [{"id": "f1", "name": "File"}]
        services._drive = mock_drive

        results = await services.list_drive_files(query="name contains 'test'")
        assert len(results) == 1
        mock_drive.list_files.assert_called_once_with("name contains 'test'", 20)

    @pytest.mark.asyncio
    async def test_get_file_metadata(self, services):
        mock_drive = MagicMock()
        mock_drive.get_file_metadata.return_value = {
            "id": "f2", "name": "Report"
        }
        services._drive = mock_drive

        result = await services.get_file_metadata("f2")
        assert result["name"] == "Report"
        mock_drive.get_file_metadata.assert_called_once_with("f2")
