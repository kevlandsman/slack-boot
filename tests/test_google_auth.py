from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from services.google_auth import GoogleAuthManager, SCOPES


@pytest.fixture
def auth_manager(tmp_path):
    return GoogleAuthManager(
        token_path=str(tmp_path / "token.json"),
        credentials_path=str(tmp_path / "credentials.json"),
    )


class TestGoogleAuthManager:
    def test_defaults(self):
        auth = GoogleAuthManager()
        assert "google_token.json" in str(auth.token_path)
        assert "google_credentials.json" in str(auth.credentials_path)

    def test_custom_paths(self, tmp_path):
        auth = GoogleAuthManager(
            token_path=str(tmp_path / "tok.json"),
            credentials_path=str(tmp_path / "cred.json"),
        )
        assert auth.token_path == tmp_path / "tok.json"
        assert auth.credentials_path == tmp_path / "cred.json"

    def test_get_credentials_no_token_file_raises(self, auth_manager):
        with pytest.raises(RuntimeError, match="No valid Google credentials"):
            auth_manager.get_credentials()

    def test_is_configured_false_when_no_token(self, auth_manager):
        assert auth_manager.is_configured() is False

    @patch("services.google_auth.Credentials")
    def test_get_credentials_loads_from_file(self, mock_creds_cls, auth_manager):
        # Create a fake token file
        auth_manager.token_path.write_text('{"token": "fake"}')

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        result = auth_manager.get_credentials()
        assert result is mock_creds
        mock_creds_cls.from_authorized_user_file.assert_called_once_with(
            str(auth_manager.token_path), SCOPES
        )

    @patch("services.google_auth.Request")
    @patch("services.google_auth.Credentials")
    def test_get_credentials_refreshes_expired(self, mock_creds_cls, mock_request, auth_manager):
        auth_manager.token_path.write_text('{"token": "fake"}')

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh-tok"
        mock_creds.to_json.return_value = '{"refreshed": true}'
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        # After refresh, valid should be True
        def set_valid(*args):
            mock_creds.valid = True

        mock_creds.refresh.side_effect = set_valid

        result = auth_manager.get_credentials()
        assert result is mock_creds
        mock_creds.refresh.assert_called_once()
        # Token should be saved after refresh
        assert auth_manager.token_path.exists()

    def test_get_credentials_returns_cached_valid(self, auth_manager):
        mock_creds = MagicMock()
        mock_creds.valid = True
        auth_manager._credentials = mock_creds

        result = auth_manager.get_credentials()
        assert result is mock_creds

    @patch("services.google_auth.Request")
    def test_get_credentials_refreshes_cached_expired(self, mock_request, auth_manager):
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh-tok"
        mock_creds.to_json.return_value = '{"refreshed": true}'

        def set_valid(*args):
            mock_creds.valid = True

        mock_creds.refresh.side_effect = set_valid
        auth_manager._credentials = mock_creds

        result = auth_manager.get_credentials()
        assert result is mock_creds
        mock_creds.refresh.assert_called_once()

    @patch("services.google_auth.Credentials")
    def test_is_configured_true_with_valid_token(self, mock_creds_cls, auth_manager):
        auth_manager.token_path.write_text('{"token": "fake"}')
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        assert auth_manager.is_configured() is True

    def test_run_interactive_flow_missing_credentials_file(self, auth_manager):
        with pytest.raises(FileNotFoundError, match="OAuth client credentials"):
            auth_manager.run_interactive_flow()

    @patch("services.google_auth.InstalledAppFlow")
    def test_run_interactive_flow_success(self, mock_flow_cls, auth_manager):
        # Create the credentials file
        auth_manager.credentials_path.write_text('{"installed": {}}')

        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "new"}'
        mock_flow.run_local_server.return_value = mock_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        auth_manager.run_interactive_flow()

        mock_flow_cls.from_client_secrets_file.assert_called_once_with(
            str(auth_manager.credentials_path), SCOPES
        )
        mock_flow.run_local_server.assert_called_once_with(port=0)
        assert auth_manager._credentials is mock_creds
        assert auth_manager.token_path.exists()

    def test_save_token_creates_parent_dirs(self, tmp_path):
        auth = GoogleAuthManager(
            token_path=str(tmp_path / "nested" / "deep" / "token.json"),
        )
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "test"}'
        auth._credentials = mock_creds

        auth._save_token()
        assert (tmp_path / "nested" / "deep" / "token.json").exists()

    def test_scopes_are_read_only(self):
        """Verify scopes enforce zero outbound communication."""
        for scope in SCOPES:
            assert "send" not in scope
            assert "compose" not in scope
            assert "modify" not in scope
        assert "https://www.googleapis.com/auth/gmail.readonly" in SCOPES
        assert "https://www.googleapis.com/auth/drive.file" in SCOPES
