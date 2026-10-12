"""Tests for programmatic command variants (GUI/scripting support)"""

import time

import pytest
from unittest.mock import MagicMock, patch, mock_open
import yaml


class TestServerCommandsProgrammatic:
    """Test programmatic server management methods"""

    @pytest.fixture
    def mock_shell(self):
        """Create mock shell"""
        shell = MagicMock()
        shell.config = MagicMock()
        shell.config.config_path = "/tmp/test_config.yml"
        shell.config.get_all_servers.return_value = {}
        shell.poutput = MagicMock()
        shell.perror = MagicMock()
        shell.pwarning = MagicMock()
        return shell

    @pytest.fixture
    def server_commands(self, mock_shell):
        """Create ServerCommands instance"""
        from quads_client.commands.server import ServerCommands

        return ServerCommands(mock_shell)

    def test_add_server_programmatic_success(self, server_commands, mock_shell):
        """Test adding server programmatically succeeds"""
        # Mock config file operations
        mock_config_data = {"servers": {}}

        with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
            with patch("yaml.safe_load", return_value=mock_config_data):
                with patch("yaml.dump"):
                    with patch("requests.get") as mock_get:
                        # Mock successful server connection
                        mock_response = MagicMock()
                        mock_response.status_code = 200
                        mock_response.json.return_value = {"version": "2.2.6"}
                        mock_get.return_value = mock_response

                        success, message, version = server_commands.add_server_programmatic(
                            name="test-server",
                            url="https://test.example.com",
                            username="test@example.com",
                            password="testpass",
                            verify=True,
                            test_connection=True,
                        )

                        assert success is True
                        assert "successfully" in message.lower()
                        assert version == "2.2.6"

    def test_add_server_programmatic_connection_failure(self, server_commands):
        """Test adding server with connection failure"""
        with patch("builtins.open", mock_open(read_data=yaml.dump({"servers": {}}))):
            with patch("yaml.safe_load", return_value={"servers": {}}):
                with patch("requests.get") as mock_get:
                    # Mock connection failure
                    mock_get.side_effect = Exception("Connection timeout")

                    success, message, version = server_commands.add_server_programmatic(
                        name="test-server",
                        url="https://test.example.com",
                        username="",
                        password="",
                        verify=True,
                        test_connection=True,
                    )

                    assert success is False
                    assert "Could not connect" in message
                    assert version is None

    def test_add_server_programmatic_skip_connection_test(self, server_commands):
        """Test adding server without connection test"""
        mock_config_data = {"servers": {}}

        with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
            with patch("yaml.safe_load", return_value=mock_config_data):
                with patch("yaml.dump"):
                    success, message, version = server_commands.add_server_programmatic(
                        name="test-server",
                        url="https://test.example.com",
                        username="",
                        password="",
                        verify=True,
                        test_connection=False,
                    )

                    assert success is True
                    assert version is None  # No connection test = no version

    def test_add_server_programmatic_positional_test_connection_false(self, server_commands):
        """'test_connection' stays the 6th positional arg, so old positional callers still skip the probe"""
        mock_config_data = {"servers": {}}

        with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
            with patch("yaml.safe_load", return_value=mock_config_data):
                with patch("yaml.dump"):
                    with patch("requests.get") as mock_get:
                        success, message, version = server_commands.add_server_programmatic(
                            "test-server",
                            "https://test.example.com",
                            "user@example.com",
                            "pass",
                            True,
                            False,
                        )

                        assert success is True
                        assert version is None
                        assert mock_get.call_count == 0

    def test_add_server_programmatic_duplicate(self, server_commands):
        """Test adding duplicate server"""
        mock_config_data = {
            "servers": {"test-server": {"url": "https://existing.example.com", "username": "", "password": ""}}
        }

        with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
            with patch("yaml.safe_load", return_value=mock_config_data):
                success, message, version = server_commands.add_server_programmatic(
                    name="test-server",
                    url="https://test.example.com",
                    username="",
                    password="",
                    verify=True,
                    test_connection=False,
                )

                assert success is False
                assert "already exists" in message.lower()

    def test_rm_server_programmatic_success(self, server_commands, mock_shell):
        """Test removing server programmatically succeeds"""
        mock_config_data = {
            "servers": {"test-server": {"url": "https://test.example.com", "username": "", "password": ""}},
            "default_server": "other-server",
        }
        mock_shell.connection = None

        with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
            with patch("yaml.safe_load", return_value=mock_config_data):
                with patch("yaml.dump"):
                    success, message = server_commands.rm_server_programmatic("test-server")

                    assert success is True
                    assert "removed successfully" in message.lower()

    def test_rm_server_programmatic_not_found(self, server_commands, mock_shell):
        """Test removing non-existent server"""
        mock_config_data = {"servers": {}}
        mock_shell.connection = None

        with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
            with patch("yaml.safe_load", return_value=mock_config_data):
                success, message = server_commands.rm_server_programmatic("nonexistent")

                assert success is False
                assert "not found" in message.lower()

    def test_rm_server_programmatic_currently_connected(self, server_commands, mock_shell):
        """Test removing currently connected server is prevented"""
        mock_shell.connection = MagicMock()
        mock_shell.connection.current_server = "test-server"

        success, message = server_commands.rm_server_programmatic("test-server")

        assert success is False
        assert "currently connected" in message.lower()

    def test_rm_server_programmatic_clears_default(self, server_commands, mock_shell):
        """Test removing default server clears default_server"""
        mock_config_data = {
            "servers": {"test-server": {"url": "https://test.example.com", "username": "", "password": ""}},
            "default_server": "test-server",
        }
        mock_shell.connection = None

        with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
            with patch("yaml.safe_load", return_value=mock_config_data):
                with patch("yaml.dump"):
                    success, message = server_commands.rm_server_programmatic("test-server")

                    assert success is True
                    assert mock_config_data["default_server"] is None
                    assert "test-server" not in mock_config_data["servers"]

    def test_rm_server_programmatic_no_config(self, server_commands, mock_shell):
        """Test removing server when config not loaded"""
        mock_shell.config = None

        success, message = server_commands.rm_server_programmatic("test-server")

        assert success is False
        assert "configuration not loaded" in message.lower()


class TestUserCommandsProgrammatic:
    """Test programmatic user command methods"""

    @pytest.fixture
    def mock_shell(self):
        """Create mock shell with connection"""
        shell = MagicMock()
        shell.config = MagicMock()
        shell.config.config_path = "/tmp/test_config.yml"
        shell.config.get_server_url.return_value = "https://test.example.com"
        shell.config.get_server_verify.return_value = True
        shell.config.get_server_proxy.return_value = ""

        # Mock connection
        mock_connection = MagicMock()
        mock_connection.is_connected = True
        mock_connection.is_authenticated = False
        mock_connection.current_server = "test-server"
        mock_connection.api = MagicMock()
        mock_connection._decode_role_from_token = MagicMock(return_value="user")

        shell.connection = mock_connection
        shell.session_manager = MagicMock()
        shell.session_manager.active_connection = mock_connection

        shell.poutput = MagicMock()
        shell.perror = MagicMock()
        shell.pwarning = MagicMock()
        shell._update_visible_commands = MagicMock()

        return shell

    @pytest.fixture
    def user_commands(self, mock_shell):
        """Create UserCommands instance"""
        from quads_client.commands.user import UserCommands

        return UserCommands(mock_shell)

    def test_login_programmatic_success(self, user_commands, mock_shell):
        """Test programmatic login succeeds"""
        with patch("quads_lib.QuadsApi") as mock_api_class:
            # Mock QuadsApi instance
            mock_api = MagicMock()
            mock_api.login.return_value = {"auth_token": "test_token_123", "status": "success"}
            mock_api.token = "test_token_123"
            mock_api_class.return_value = mock_api

            success, message, role = user_commands.login_programmatic(email="test@example.com", password="testpass")

            assert success is True
            assert "successfully" in message.lower()
            # Verify connection was updated
            assert mock_shell.connection._api == mock_api
            assert mock_shell.connection._token == "test_token_123"
            assert mock_shell.connection._username == "test@example.com"
            assert mock_shell.connection._registration_mode is False

    def test_login_programmatic_failure(self, user_commands, mock_shell):
        """Test programmatic login fails"""
        with patch("quads_lib.QuadsApi") as mock_api_class:
            # Mock failed login
            mock_api = MagicMock()
            mock_api.login.side_effect = Exception("Invalid credentials")
            mock_api_class.return_value = mock_api

            success, message, role = user_commands.login_programmatic(email="test@example.com", password="wrongpass")

            assert success is False
            assert "Failed to login" in message
            assert role is None

    def test_login_programmatic_not_connected(self, user_commands, mock_shell):
        """Test programmatic login when not connected"""
        mock_shell.connection = None

        success, message, role = user_commands.login_programmatic(email="test@example.com", password="testpass")

        assert success is False
        assert "Not connected" in message
        assert role is None

    def test_login_programmatic_updates_role(self, user_commands, mock_shell):
        """Test programmatic login updates user role"""
        with patch("quads_lib.QuadsApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.login.return_value = {"auth_token": "test_token_123", "status": "success"}
            mock_api.token = "test_token_123"
            mock_api_class.return_value = mock_api

            # Mock role detection
            mock_shell.connection._decode_role_from_token.return_value = "admin"

            success, message, role = user_commands.login_programmatic(email="admin@example.com", password="adminpass")

            assert success is True
            assert role == "admin"
            assert mock_shell.connection._user_role == "admin"
            mock_shell._update_visible_commands.assert_called_once()


class TestUserCommandsRegister:
    """Test programmatic user registration methods"""

    @pytest.fixture
    def mock_shell(self):
        """Create mock shell with connection"""
        shell = MagicMock()
        shell.config = MagicMock()
        shell.config.config_path = "/tmp/test_config.yml"
        shell.config.get_server_url.return_value = "https://test.example.com"
        shell.config.get_server_verify.return_value = True
        shell.config.get_server_proxy.return_value = ""

        mock_connection = MagicMock()
        mock_connection.is_connected = True
        mock_connection.is_authenticated = False
        mock_connection.current_server = "test-server"
        mock_connection.api = MagicMock()
        mock_connection._decode_role_from_token = MagicMock(return_value="user")

        shell.connection = mock_connection
        shell.session_manager = MagicMock()
        shell.session_manager.active_connection = mock_connection
        shell.poutput = MagicMock()
        shell.perror = MagicMock()
        shell.pwarning = MagicMock()
        shell._update_visible_commands = MagicMock()

        return shell

    @pytest.fixture
    def user_commands(self, mock_shell):
        """Create UserCommands instance"""
        from quads_client.commands.user import UserCommands

        return UserCommands(mock_shell)

    def test_register_programmatic_success(self, user_commands, mock_shell):
        """Test registration followed by auto-login"""
        mock_shell.connection.api.register.return_value = {"message": "User created"}

        with patch("quads_lib.QuadsApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.login.return_value = {"auth_token": "new_token", "status": "success"}
            mock_api.token = "new_token"
            mock_api_class.return_value = mock_api

            success, message, role = user_commands.register_programmatic("new@example.com", "password123")

            assert success is True
            assert "successfully" in message.lower()
            mock_shell.connection.api.register.assert_called_once()

    def test_register_programmatic_already_exists(self, user_commands, mock_shell):
        """Test registration when user already exists"""
        mock_shell.connection.api.register.return_value = {"message": "User already exists"}

        success, message, role = user_commands.register_programmatic("existing@example.com", "password123")

        assert success is False
        assert "already registered" in message.lower()
        assert role is None

    def test_register_programmatic_not_connected(self, user_commands, mock_shell):
        """Test registration when not connected"""
        mock_shell.connection = None

        success, message, role = user_commands.register_programmatic("new@example.com", "password123")

        assert success is False
        assert "not connected" in message.lower()
        assert role is None


class TestGuiShellMetadataCache:
    """Test metadata caching in GuiShell"""

    @pytest.fixture
    def gui_shell(self):
        """Create a GuiShell with mocked dependencies"""
        from quads_client.gui.controllers.gui_shell import GuiShell

        mock_app = MagicMock()
        mock_app.theme_manager = MagicMock()

        with patch("quads_client.gui.controllers.gui_shell.QuadsClientConfig"):
            with patch("quads_client.gui.controllers.gui_shell.SessionManager"):
                shell = GuiShell(mock_app)

        mock_connection = MagicMock()
        mock_connection.is_connected = True
        mock_connection.is_authenticated = True
        mock_connection.api = MagicMock()
        shell.session_manager = MagicMock()
        shell.session_manager.active_connection = mock_connection
        return shell

    def test_get_available_models_caches_result(self, gui_shell):
        """Second call returns cached result without re-fetching"""
        gui_shell.connection.api.get_hosts.return_value = [
            {"model": "1029P", "name": "host1"},
            {"model": "6049P", "name": "host2"},
        ]

        result1 = gui_shell.get_available_models()
        result2 = gui_shell.get_available_models()

        assert result1 == ["1029P", "6049P"]
        assert result2 == result1
        assert gui_shell.connection.api.get_hosts.call_count == 1

    def test_get_available_models_cache_expires(self, gui_shell):
        """Cache expires after TTL and re-fetches"""
        gui_shell.connection.api.get_hosts.return_value = [{"model": "1029P", "name": "host1"}]

        gui_shell.get_available_models()
        gui_shell._models_cache_time = time.monotonic() - gui_shell._metadata_cache_ttl - 1
        gui_shell._hosts_cache_time = time.monotonic() - gui_shell._metadata_cache_ttl - 1
        gui_shell.get_available_models()

        assert gui_shell.connection.api.get_hosts.call_count == 2

    def test_invalidate_metadata_cache_clears(self, gui_shell):
        """invalidate_metadata_cache clears all caches"""
        gui_shell.connection.api.get_hosts.return_value = [{"model": "1029P", "name": "host1"}]

        gui_shell.get_available_models()
        gui_shell.get_available_nic_vendors()
        gui_shell.invalidate_metadata_cache()

        assert gui_shell._models_cache is None
        assert gui_shell._nic_vendors_cache is None
        assert gui_shell._hosts_cache is None

        gui_shell.get_available_models()
        assert gui_shell.connection.api.get_hosts.call_count == 2


@pytest.fixture
def server_commands(mock_shell):
    """Create ServerCommands instance with the module mock shell"""
    from quads_client.commands.server import ServerCommands

    return ServerCommands(mock_shell)


@pytest.fixture
def mock_shell():
    """Create mock shell for server command tests"""
    shell = MagicMock()
    shell.config = MagicMock()
    shell.config.config_path = "/tmp/test_config.yml"
    shell.config.get_all_servers.return_value = {}
    shell.poutput = MagicMock()
    shell.perror = MagicMock()
    shell.pwarning = MagicMock()
    return shell


def test_add_server_programmatic_persists_proxy(server_commands, mock_shell):
    """Test adding a server with a proxy URL writes it to the config"""
    mock_config_data = {"servers": {}}

    with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
        with patch("yaml.safe_load", return_value=mock_config_data):
            with patch("yaml.dump") as mock_dump:
                with patch("requests.get") as mock_get:
                    mock_get.return_value.status_code = 200
                    mock_get.return_value.json.return_value = {"version": "2.2.6"}
                    # Keep the reload off the real ~/.config path (fresh CI runners have none)
                    with patch.object(server_commands, "cmd_config_reload"):
                        success, message, version = server_commands.add_server_programmatic(
                            name="test-server",
                            url="https://test.example.com",
                            proxy="socks5h://127.0.0.1:1080",
                            test_connection=True,
                        )

    assert success is True
    written = mock_dump.call_args[0][0]
    assert written["servers"]["test-server"]["proxy"] == "socks5h://127.0.0.1:1080"
    assert mock_get.call_args.kwargs["proxies"] == {
        "http": "socks5h://127.0.0.1:1080",
        "https": "socks5h://127.0.0.1:1080",
    }


def test_add_server_programmatic_without_proxy_probes_directly(server_commands, mock_shell):
    """Test the reachability probe stays direct when no proxy is configured"""
    mock_config_data = {"servers": {}}

    with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
        with patch("yaml.safe_load", return_value=mock_config_data):
            with patch("yaml.dump"):
                with patch("requests.get") as mock_get:
                    mock_get.return_value.status_code = 200
                    mock_get.return_value.json.return_value = {"version": "2.2.6"}
                    with patch.object(server_commands, "cmd_config_reload"):
                        server_commands.add_server_programmatic(
                            name="test-server", url="https://test.example.com", test_connection=True
                        )

    assert mock_get.call_args.kwargs["proxies"] is None


def test_edit_server_programmatic_sets_proxy(server_commands, mock_shell):
    """Test edit_server_programmatic stores a new proxy URL"""
    mock_config_data = {"servers": {"test-server": {"url": "https://test.example.com", "verify": True}}}

    with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
        with patch("yaml.safe_load", return_value=mock_config_data):
            with patch("yaml.dump") as mock_dump:
                with patch.object(server_commands, "cmd_config_reload"):
                    success, message = server_commands.edit_server_programmatic(
                        "test-server", proxy="socks5h://127.0.0.1:1080"
                    )

    assert success is True
    written = mock_dump.call_args[0][0]
    assert written["servers"]["test-server"]["proxy"] == "socks5h://127.0.0.1:1080"


def test_edit_server_programmatic_positional_api_token(server_commands, mock_shell):
    """'api_token' stays the 6th positional arg, so old positional callers still pass the token"""
    mock_config_data = {"servers": {"test-server": {"url": "https://test.example.com"}}}

    with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
        with patch("yaml.safe_load", return_value=mock_config_data):
            with patch("yaml.dump") as mock_dump:
                with patch.object(server_commands, "cmd_config_reload"):
                    success, message = server_commands.edit_server_programmatic(
                        "test-server", None, None, None, None, "qat_token123"
                    )

    assert success is True
    written = mock_dump.call_args[0][0]
    assert written["servers"]["test-server"]["api_token"] == "qat_token123"
    assert written["servers"]["test-server"].get("proxy", "") == ""


def test_edit_server_programmatic_clears_proxy(server_commands, mock_shell):
    """Test an empty proxy string disables the proxy (None leaves it unchanged)"""
    mock_config_data = {
        "servers": {"test-server": {"url": "https://test.example.com", "proxy": "socks5h://127.0.0.1:1080"}}
    }

    with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
        with patch("yaml.safe_load", return_value=mock_config_data):
            with patch("yaml.dump") as mock_dump:
                with patch.object(server_commands, "cmd_config_reload"):
                    success, message = server_commands.edit_server_programmatic("test-server", proxy="")

    assert success is True
    written = mock_dump.call_args[0][0]
    assert written["servers"]["test-server"]["proxy"] == ""


def test_edit_server_programmatic_none_leaves_proxy(server_commands, mock_shell):
    """Test proxy=None does not touch an existing proxy setting"""
    mock_config_data = {
        "servers": {"test-server": {"url": "https://test.example.com", "proxy": "socks5h://127.0.0.1:1080"}}
    }

    with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
        with patch("yaml.safe_load", return_value=mock_config_data):
            with patch("yaml.dump") as mock_dump:
                with patch.object(server_commands, "cmd_config_reload"):
                    success, message = server_commands.edit_server_programmatic(
                        "test-server", verify=False, proxy=None
                    )

    assert success is True
    written = mock_dump.call_args[0][0]
    assert written["servers"]["test-server"]["proxy"] == "socks5h://127.0.0.1:1080"


def test_edit_server_programmatic_none_sentinel_clears_proxy(server_commands, mock_shell):
    """Test the GUI 'none' sentinel clears the proxy just like edit-server proxy none"""
    mock_config_data = {
        "servers": {"test-server": {"url": "https://test.example.com", "proxy": "socks5h://127.0.0.1:1080"}}
    }

    with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
        with patch("yaml.safe_load", return_value=mock_config_data):
            with patch("yaml.dump") as mock_dump:
                with patch.object(server_commands, "cmd_config_reload"):
                    success, message = server_commands.edit_server_programmatic("test-server", proxy="none")

    assert success is True
    written = mock_dump.call_args[0][0]
    assert written["servers"]["test-server"]["proxy"] == ""


def test_edit_server_programmatic_rejects_malformed_proxy(server_commands, mock_shell):
    """Test a typo'd proxy fails at edit time and leaves the stored proxy untouched"""
    mock_config_data = {
        "servers": {"test-server": {"url": "https://test.example.com", "proxy": "socks5h://127.0.0.1:1080"}}
    }

    with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
        with patch("yaml.safe_load", return_value=mock_config_data):
            with patch("yaml.dump") as mock_dump:
                with patch.object(server_commands, "cmd_config_reload"):
                    success, message = server_commands.edit_server_programmatic(
                        "test-server", proxy="socks://127.0.0.1:1080"
                    )

    assert success is False
    assert "Unsupported proxy scheme 'socks'" in message
    mock_dump.assert_not_called()
    assert mock_config_data["servers"]["test-server"]["proxy"] == "socks5h://127.0.0.1:1080"


def test_edit_server_programmatic_proxy_error_hides_credentials(server_commands, mock_shell):
    """Test the malformed proxy message redacts userinfo credentials"""
    mock_config_data = {"servers": {"test-server": {"url": "https://test.example.com"}}}

    with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
        with patch("yaml.safe_load", return_value=mock_config_data):
            with patch("yaml.dump") as mock_dump:
                with patch.object(server_commands, "cmd_config_reload"):
                    success, message = server_commands.edit_server_programmatic(
                        "test-server", proxy="socks5h://alice:sekret@proxy.local:notaport"
                    )

    assert success is False
    assert "sekret" not in message
    assert "proxy.local:notaport" in message
    mock_dump.assert_not_called()


def test_add_server_programmatic_none_sentinel_stores_empty_proxy(server_commands, mock_shell):
    """Test the GUI 'none' sentinel is normalized to an empty proxy on add (no probe)"""
    mock_config_data = {"servers": {}}

    with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
        with patch("yaml.safe_load", return_value=mock_config_data):
            with patch("yaml.dump") as mock_dump:
                with patch.object(server_commands, "cmd_config_reload"):
                    success, message, version = server_commands.add_server_programmatic(
                        name="test-server",
                        url="https://test.example.com",
                        proxy="none",
                        test_connection=False,
                    )

    assert success is True
    written = mock_dump.call_args[0][0]
    assert written["servers"]["test-server"]["proxy"] == ""


def test_add_server_programmatic_rejects_malformed_proxy_without_probe(server_commands, mock_shell):
    """Test a malformed proxy is rejected on add even when the reachability probe is off"""
    mock_config_data = {"servers": {}}

    with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
        with patch("yaml.safe_load", return_value=mock_config_data):
            with patch("yaml.dump") as mock_dump:
                with patch.object(server_commands, "cmd_config_reload"):
                    success, message, version = server_commands.add_server_programmatic(
                        name="test-server",
                        url="https://test.example.com",
                        proxy="ftp://127.0.0.1:21",
                        test_connection=False,
                    )

    assert success is False
    assert "Unsupported proxy scheme 'ftp'" in message
    mock_dump.assert_not_called()


def test_add_server_programmatic_malformed_proxy_is_not_a_connection_failure(server_commands, mock_shell):
    """Test a bad proxy is reported as a proxy error, so the GUI does not offer 'add anyway'"""
    mock_config_data = {"servers": {}}

    with patch("builtins.open", mock_open(read_data=yaml.dump(mock_config_data))):
        with patch("yaml.safe_load", return_value=mock_config_data):
            with patch("yaml.dump") as mock_dump:
                with patch("requests.get") as mock_get:
                    with patch.object(server_commands, "cmd_config_reload"):
                        success, message, version = server_commands.add_server_programmatic(
                            name="test-server",
                            url="https://test.example.com",
                            proxy="ftp://127.0.0.1:21",
                            test_connection=True,
                        )

    assert success is False
    assert "Unsupported proxy scheme 'ftp'" in message
    assert "Could not connect" not in message
    mock_get.assert_not_called()
    mock_dump.assert_not_called()


def test_login_programmatic_applies_proxy(mock_shell):
    """Test login_programmatic routes the new API session through the configured proxy"""
    from requests import Session

    mock_shell.config.get_server_proxy.return_value = "socks5h://127.0.0.1:1080"
    mock_api = MagicMock()
    mock_api.session = Session()
    mock_api.login.return_value = {"auth_token": "tok", "status": "success"}
    mock_api.token = "tok"

    from quads_client.commands.user import UserCommands

    user_cmd = UserCommands(mock_shell)
    with patch("quads_lib.QuadsApi", return_value=mock_api):
        success, message, role = user_cmd.login_programmatic("a@example.com", "pw")

    assert success is True
    assert mock_api.session.proxies["https"] == "socks5h://127.0.0.1:1080"


def test_token_login_programmatic_applies_proxy(mock_shell):
    """Test token_login_programmatic routes the new API session through the configured proxy"""
    from requests import Session

    mock_shell.config.get_server_proxy.return_value = "socks5h://127.0.0.1:1080"
    mock_api = MagicMock()
    mock_api.session = Session()
    mock_api.get_version.return_value = {"version": "2.2.6"}

    from quads_client.commands.user import UserCommands

    user_cmd = UserCommands(mock_shell)
    with patch("quads_lib.QuadsApi", return_value=mock_api):
        success, message, role = user_cmd.token_login_programmatic("a@example.com", "qat_token_123")

    assert success is True
    assert mock_api.session.proxies["https"] == "socks5h://127.0.0.1:1080"
