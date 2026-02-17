from __future__ import annotations

import base64
import pytest
from unittest.mock import MagicMock, patch

from services.gmail import GmailClient


@pytest.fixture
def mock_auth():
    auth = MagicMock()
    auth.get_credentials.return_value = MagicMock()
    return auth


def _make_client_with_service(mock_auth):
    """Create a GmailClient with a pre-injected mock service."""
    client = GmailClient(mock_auth)
    mock_service = MagicMock()
    client._service = mock_service
    return client, mock_service


def _encode(text: str) -> str:
    """Base64url-encode a string (matches Gmail API format)."""
    return base64.urlsafe_b64encode(text.encode()).decode()


class TestGmailClient:
    def test_no_send_methods(self, mock_auth):
        """Verify the class has no outbound communication methods."""
        client = GmailClient(mock_auth)
        for forbidden in ["send", "draft", "compose", "modify", "delete", "trash"]:
            assert not hasattr(client, forbidden), f"GmailClient should not have '{forbidden}' method"
            assert not hasattr(client, f"send_{forbidden}"), f"GmailClient should not have 'send_{forbidden}'"

    @patch("services.gmail.build")
    def test_lazy_service_init(self, mock_build, mock_auth):
        client = GmailClient(mock_auth)
        assert client._service is None
        client._get_service()
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_auth.get_credentials())

    def test_search_messages(self, mock_auth):
        client, mock_service = _make_client_with_service(mock_auth)

        # Mock messages().list()
        mock_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1"}, {"id": "msg2"}]
        }

        # Mock messages().get() for summaries
        mock_service.users().messages().get().execute.return_value = {
            "id": "msg1",
            "snippet": "Hello there...",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "alice@example.com"},
                    {"name": "Date", "value": "Mon, 1 Jan 2025 12:00:00"},
                ]
            },
        }

        results = client.search_messages("from:alice", max_results=5)
        assert len(results) == 2
        assert results[0]["subject"] == "Test Subject"
        assert results[0]["from"] == "alice@example.com"

    def test_get_message_plain_text(self, mock_auth):
        client, mock_service = _make_client_with_service(mock_auth)

        body_text = "Hello, this is the email body."
        mock_service.users().messages().get().execute.return_value = {
            "id": "msg1",
            "snippet": "Hello...",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Subject", "value": "Plain Text Email"},
                    {"name": "From", "value": "bob@example.com"},
                    {"name": "To", "value": "bot@example.com"},
                    {"name": "Date", "value": "Tue, 2 Jan 2025 10:00:00"},
                ],
                "body": {"data": _encode(body_text)},
            },
        }

        result = client.get_message("msg1")
        assert result["id"] == "msg1"
        assert result["subject"] == "Plain Text Email"
        assert result["body"] == body_text

    def test_get_message_multipart(self, mock_auth):
        client, mock_service = _make_client_with_service(mock_auth)

        plain_body = "Plain text version"
        html_body = "<html><body><p>HTML version</p></body></html>"

        mock_service.users().messages().get().execute.return_value = {
            "id": "msg2",
            "snippet": "Plain text...",
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [
                    {"name": "Subject", "value": "Multipart"},
                    {"name": "From", "value": "carol@example.com"},
                    {"name": "To", "value": "bot@example.com"},
                    {"name": "Date", "value": "Wed, 3 Jan 2025"},
                ],
                "body": {},
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": _encode(plain_body)},
                    },
                    {
                        "mimeType": "text/html",
                        "body": {"data": _encode(html_body)},
                    },
                ],
            },
        }

        result = client.get_message("msg2")
        # Should prefer text/plain
        assert result["body"] == plain_body

    def test_get_message_html_fallback(self, mock_auth):
        client, mock_service = _make_client_with_service(mock_auth)

        html_body = "<p>Only HTML here</p>"

        mock_service.users().messages().get().execute.return_value = {
            "id": "msg3",
            "snippet": "Only HTML...",
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [
                    {"name": "Subject", "value": "HTML Only"},
                    {"name": "From", "value": "dave@example.com"},
                    {"name": "To", "value": "bot@example.com"},
                    {"name": "Date", "value": "Thu, 4 Jan 2025"},
                ],
                "body": {},
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {"data": _encode(html_body)},
                    },
                ],
            },
        }

        result = client.get_message("msg3")
        assert "Only HTML here" in result["body"]
        assert "<p>" not in result["body"]

    def test_list_recent(self, mock_auth):
        client = GmailClient(mock_auth)
        client.search_messages = MagicMock(return_value=[])
        client.list_recent(max_results=5)
        client.search_messages.assert_called_once_with("in:inbox", max_results=5)

    def test_list_unread(self, mock_auth):
        client = GmailClient(mock_auth)
        client.search_messages = MagicMock(return_value=[])
        client.list_unread(max_results=15)
        client.search_messages.assert_called_once_with("is:unread", max_results=15)

    def test_search_empty_results(self, mock_auth):
        client, mock_service = _make_client_with_service(mock_auth)
        mock_service.users().messages().list().execute.return_value = {}
        results = client.search_messages("from:nobody")
        assert results == []

    def test_missing_headers(self, mock_auth):
        client, mock_service = _make_client_with_service(mock_auth)
        mock_service.users().messages().get().execute.return_value = {
            "id": "msg4",
            "snippet": "",
            "payload": {"headers": []},
        }
        result = client._get_message_summary("msg4")
        assert result["subject"] == "(no subject)"
        assert result["from"] == "unknown"

    def test_extract_body_empty_payload(self, mock_auth):
        client = GmailClient(mock_auth)
        assert client._extract_body({}) == ""

    def test_strip_html(self, mock_auth):
        client = GmailClient(mock_auth)
        html = "<p>Hello&nbsp;&amp;&lt;World&gt;</p><br/>Next"
        result = client._strip_html(html)
        assert "Hello" in result
        assert "&" in result
        assert "<World>" in result
        assert "<p>" not in result

    def test_decode_body_invalid(self, mock_auth):
        client = GmailClient(mock_auth)
        # Should not raise on invalid base64 — returns empty or garbage gracefully
        result = client._decode_body("!@#$%^&*()")
        assert isinstance(result, str)  # just verify it doesn't crash

    def test_body_truncation(self, mock_auth):
        client = GmailClient(mock_auth)
        long_text = "A" * 5000
        payload = {
            "mimeType": "text/plain",
            "body": {"data": _encode(long_text)},
        }
        result = client._extract_body(payload, max_length=100)
        assert len(result) == 100
