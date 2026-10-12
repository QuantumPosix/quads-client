import pytest
from unittest.mock import MagicMock, patch

from quads_client.commands.server import ServerCommands
from quads_client.connection import ConnectionManager


def _wire_connection(mock_shell, servers):
    """Wire a real ConnectionManager so server commands build APIs through it.

    API construction goes through ConnectionManager.build_api so the
    per-server proxy is honored; quads_lib.QuadsApi is patched at the
    quads_client.connection seam the other connection tests already use.
    """
    mock_shell.config.get_all_servers.return_value = servers
    mock_shell.config.get_default_server.return_value = None
    mock_shell.config.get_server_url.side_effect = lambda name: servers[name]["url"]
    mock_shell.config.get_server_verify.side_effect = lambda name: servers[name].get("verify", True)
    mock_shell.config.get_server_api_token.side_effect = lambda name: servers[name].get("api_token", "")
    mock_shell.config.get_server_proxy.side_effect = lambda name: servers[name].get("proxy", "")
    mock_shell.config.get_server_credentials.side_effect = lambda name: (
        servers[name].get("username", ""),
        servers[name].get("password", ""),
    )
    mock_shell.connection = ConnectionManager(mock_shell.config)


def test_servers_command_no_credentials(mock_shell):
    """Test servers command shows version even without credentials"""
    servers = {"test_server": {"url": "https://test.example.com", "username": "", "password": "", "verify": True}}
    _wire_connection(mock_shell, servers)

    # Mock public version check (no auth required)
    mock_api_class = MagicMock()
    mock_api = MagicMock()
    mock_api.get_version.return_value = {"version": "2.2.6"}
    mock_api_class.return_value = mock_api

    with patch("quads_client.connection.QuadsApi", mock_api_class):
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_servers("")

    # Should call version endpoint without credentials
    mock_api_class.assert_called_with(base_url="https://test.example.com", username="", password="", verify=True)
    mock_api.get_version.assert_called_once()
    # Should not try to login
    mock_api.login.assert_not_called()


def test_servers_command_auth_failed(mock_shell):
    """Test servers command shows version but indicates auth failure"""
    servers = {
        "test_server": {
            "url": "https://test.example.com",
            "username": "user@example.com",
            "password": "wrongpassword",
            "verify": True,
        }
    }
    _wire_connection(mock_shell, servers)

    # Public version check succeeds
    mock_api_public = MagicMock()
    mock_api_public.get_version.return_value = {"version": "2.2.6"}

    # Auth check fails
    mock_api_auth = MagicMock()
    mock_api_auth.login.return_value = {"status": "failure"}

    # Return different mocks for public vs auth calls
    call_count = [0]

    def api_factory(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:  # First call is public
            return mock_api_public
        else:  # Second call is auth
            return mock_api_auth

    mock_api_class = MagicMock(side_effect=api_factory)

    with patch("quads_client.connection.QuadsApi", mock_api_class):
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_servers("")

    # Should show version (from public endpoint)
    mock_api_public.get_version.assert_called_once()
    # Should attempt login (which fails)
    mock_api_auth.login.assert_called_once()


def test_servers_command_with_auth_success(mock_shell):
    """Test servers command shows version and capacity with valid auth"""
    servers = {
        "test_server": {
            "url": "https://test.example.com",
            "username": "user@example.com",
            "password": "correctpassword",
            "verify": True,
        }
    }
    _wire_connection(mock_shell, servers)

    # Public version check succeeds
    mock_api_public = MagicMock()
    mock_api_public.get_version.return_value = {"version": "2.2.6"}

    # Auth check succeeds
    mock_api_auth = MagicMock()
    mock_api_auth.login.return_value = {"status": "success"}
    mock_api_auth.get_hosts.return_value = [{"name": "host1"}, {"name": "host2"}]
    mock_api_auth.get_current_schedules.return_value = [{"host": {"name": "host1"}}]

    call_count = [0]

    def api_factory(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_api_public
        else:
            return mock_api_auth

    mock_api_class = MagicMock(side_effect=api_factory)

    with patch("quads_client.connection.QuadsApi", mock_api_class):
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_servers("")

    # Should show version (from public endpoint)
    mock_api_public.get_version.assert_called_once()
    # Should login and get capacity
    mock_api_auth.login.assert_called_once()
    mock_api_auth.get_hosts.assert_called_once()
    mock_api_auth.get_current_schedules.assert_called_once()


def test_servers_command_server_offline(mock_shell):
    """Test servers command when server is offline"""
    servers = {"test_server": {"url": "https://offline.example.com", "username": "", "password": "", "verify": True}}
    _wire_connection(mock_shell, servers)

    mock_api = MagicMock()
    mock_api.get_version.side_effect = Exception("Connection refused")
    mock_api_class = MagicMock(return_value=mock_api)

    with patch("quads_client.connection.QuadsApi", mock_api_class):
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_servers("")

    # Should try version check
    mock_api.get_version.assert_called_once()
    # Should not try to login if version check fails
    mock_api.login.assert_not_called()


def test_servers_command_version_string_format(mock_shell):
    """Test servers command handles string version format"""
    servers = {"test_server": {"url": "https://test.example.com", "username": "", "password": "", "verify": True}}
    _wire_connection(mock_shell, servers)

    mock_api = MagicMock()
    # Some servers return version as string
    mock_api.get_version.return_value = "QUADS version 2.2.6 maximilian"
    mock_api_class = MagicMock(return_value=mock_api)

    with patch("quads_client.connection.QuadsApi", mock_api_class):
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_servers("")

    mock_api.get_version.assert_called_once()
