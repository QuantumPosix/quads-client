import pytest
from unittest.mock import MagicMock, patch, mock_open
from quads_client.commands.server import ServerCommands


def test_servers_success(mock_shell):
    """Test servers command shows server list"""
    mock_shell.config.get_all_servers.return_value = {
        "quads1": {"url": "https://quads1.example.com", "username": "admin", "password": "pass", "verify": True},
        "quads2": {"url": "https://quads2.example.com", "username": "admin", "password": "pass", "verify": True},
    }
    mock_shell.config.get_default_server.return_value = "quads1"
    mock_shell.connection.current_server = "quads2"

    with patch("quads_lib.QuadsApi") as mock_api:
        mock_api.return_value.get_version.return_value = {"version": "2.2.6"}
        mock_api.return_value.get_summary.return_value = [{"name": "cloud01"}, {"name": "cloud02"}]

        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_servers("")

        assert mock_shell.poutput.call_count >= 2
        mock_shell.config.get_all_servers.assert_called_once()


def test_servers_no_config(mock_shell):
    """Test servers command with no config"""
    mock_shell.config = None

    server_cmd = ServerCommands(mock_shell)
    server_cmd.cmd_servers("")

    mock_shell.perror.assert_called_with("Configuration not loaded")


def test_servers_offline_status(mock_shell):
    """Test servers command shows offline status for unreachable servers"""
    mock_shell.config.get_all_servers.return_value = {
        "quads1": {"url": "https://quads1.example.com", "username": "admin", "password": "pass", "verify": True},
    }
    mock_shell.config.get_default_server.return_value = "quads1"
    mock_shell.connection.current_server = None

    with patch("quads_lib.QuadsApi") as mock_api:
        mock_api.return_value.get_version.side_effect = Exception("Connection failed")

        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_servers("")

        assert mock_shell.poutput.call_count >= 1


def test_add_server_success(mock_shell):
    """Test add-server command"""
    server_cmd = ServerCommands(mock_shell)

    # Mock the programmatic method
    with patch.object(server_cmd, "add_server_programmatic") as mock_add:
        mock_add.return_value = (True, "Server added successfully", "2.2.6")

        server_cmd.cmd_add_server("quads3 https://quads3.example.com admin pass")

        # Verify the programmatic method was called
        mock_add.assert_called_once_with("quads3", "https://quads3.example.com", "admin", "pass", True)
        # Verify output was called
        assert mock_shell.poutput.call_count >= 1


def test_add_server_already_exists(mock_shell):
    """Test add-server with existing server name"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"

    yaml_content = {"servers": {"quads3": {"url": "https://quads3.example.com"}}}

    with patch("builtins.open", mock_open(read_data="servers:\n  quads3: {}\n")):
        with patch("quads_client.commands.server.yaml.safe_load", return_value=yaml_content):
            server_cmd = ServerCommands(mock_shell)
            server_cmd.cmd_add_server("quads3 https://quads3.example.com admin pass")

            mock_shell.perror.assert_called_with("Server 'quads3' already exists. Use edit-server to modify.")


def test_add_server_connection_failed_reject(mock_shell):
    """Test add-server with connection test failure"""
    server_cmd = ServerCommands(mock_shell)

    # Mock the programmatic method to return failure
    with patch.object(server_cmd, "add_server_programmatic") as mock_add:
        mock_add.return_value = (False, "Could not connect to server: Connection failed", None)

        server_cmd.cmd_add_server("quads3 https://quads3.example.com admin pass")

        # Verify error was reported
        mock_shell.perror.assert_called()


def test_add_server_missing_args(mock_shell):
    """Test add-server with missing arguments"""
    server_cmd = ServerCommands(mock_shell)
    server_cmd.cmd_add_server("quads3")

    mock_shell.perror.assert_called_with("Usage: add-server <name> <url> <username> <password> [--no-verify]")


def test_add_server_no_verify_flag(mock_shell):
    """Test add-server with --no-verify flag"""
    server_cmd = ServerCommands(mock_shell)

    # Mock the programmatic method
    with patch.object(server_cmd, "add_server_programmatic") as mock_add:
        mock_add.return_value = (True, "Server added successfully", "2.2.6")

        server_cmd.cmd_add_server("quads3 https://quads3.example.com admin pass --no-verify")

        # Verify the programmatic method was called with verify=False
        mock_add.assert_called_once_with("quads3", "https://quads3.example.com", "admin", "pass", False)


def test_edit_server_success(mock_shell):
    """Test edit-server command"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"

    yaml_content = {
        "servers": {"quads3": {"url": "https://quads3.example.com", "username": "admin", "password": "pass"}}
    }

    with patch("builtins.open", mock_open(read_data="servers:\n  quads3: {}\n")):
        with patch("quads_client.commands.server.yaml.safe_load", return_value=yaml_content):
            with patch("quads_client.commands.server.yaml.dump") as mock_dump:
                with patch.object(ServerCommands, "cmd_config_reload"):
                    server_cmd = ServerCommands(mock_shell)
                    server_cmd.cmd_edit_server("quads3 url https://new.example.com")

                    mock_dump.assert_called_once()
                    assert mock_shell.poutput.call_count >= 1


def test_edit_server_not_found(mock_shell):
    """Test edit-server with non-existent server"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"

    yaml_content = {"servers": {}}

    with patch("builtins.open", mock_open(read_data="servers: {}\n")):
        with patch("quads_client.commands.server.yaml.safe_load", return_value=yaml_content):
            server_cmd = ServerCommands(mock_shell)
            server_cmd.cmd_edit_server("quads3 url https://new.example.com")

            mock_shell.perror.assert_called_with("Server 'quads3' not found")


def test_edit_server_no_updates(mock_shell):
    """Test edit-server with no update flags"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"

    yaml_content = {"servers": {"quads3": {"url": "https://quads3.example.com"}}}

    with patch("builtins.open", mock_open(read_data="servers:\n  quads3: {}\n")):
        with patch("quads_client.commands.server.yaml.safe_load", return_value=yaml_content):
            server_cmd = ServerCommands(mock_shell)
            server_cmd.cmd_edit_server("quads3")

            mock_shell.perror.assert_called_with("No updates specified")


def test_edit_server_missing_name(mock_shell):
    """Test edit-server with no server name"""
    server_cmd = ServerCommands(mock_shell)
    server_cmd.cmd_edit_server("")

    mock_shell.perror.assert_called()


def test_edit_server_verify_flag(mock_shell):
    """Test edit-server with verify flag"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"

    yaml_content = {"servers": {"quads3": {"url": "https://quads3.example.com", "verify": True}}}

    with patch("builtins.open", mock_open(read_data="servers:\n  quads3: {}\n")):
        with patch("quads_client.commands.server.yaml.safe_load", return_value=yaml_content):
            with patch("quads_client.commands.server.yaml.dump") as mock_dump:
                with patch.object(ServerCommands, "cmd_config_reload"):
                    server_cmd = ServerCommands(mock_shell)
                    server_cmd.cmd_edit_server("quads3 verify false")

                    call_args = mock_dump.call_args[0][0]
                    assert call_args["servers"]["quads3"]["verify"] is False


def test_rm_server_success(mock_shell):
    """Test rm-server command with confirmation"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"
    mock_shell.connection.current_server = "quads1"

    yaml_content = {
        "servers": {"quads3": {"url": "https://quads3.example.com"}},
        "default_server": "quads1",
    }

    with patch("builtins.open", mock_open(read_data="servers:\n  quads3: {}\n")):
        with patch("quads_client.commands.server.yaml.safe_load", return_value=yaml_content):
            with patch("quads_client.commands.server.yaml.dump") as mock_dump:
                with patch("builtins.input", return_value="y"):
                    with patch.object(ServerCommands, "cmd_config_reload"):
                        server_cmd = ServerCommands(mock_shell)
                        server_cmd.cmd_rm_server("quads3")

                        mock_dump.assert_called_once()
                        assert mock_shell.poutput.call_count >= 1


def test_rm_server_reject(mock_shell):
    """Test rm-server command with rejection"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"
    mock_shell.connection.current_server = "quads1"

    yaml_content = {"servers": {"quads3": {"url": "https://quads3.example.com"}}}

    with patch("builtins.open", mock_open(read_data="servers:\n  quads3: {}\n")):
        with patch("quads_client.commands.server.yaml.safe_load", return_value=yaml_content):
            with patch("builtins.input", return_value="n"):
                server_cmd = ServerCommands(mock_shell)
                server_cmd.cmd_rm_server("quads3")

                mock_shell.poutput.assert_called_with("Server not removed")


def test_rm_server_currently_connected(mock_shell):
    """Test rm-server prevents removing connected server"""
    mock_shell.connection.current_server = "quads3"

    server_cmd = ServerCommands(mock_shell)
    server_cmd.cmd_rm_server("quads3")

    mock_shell.perror.assert_called_with("Cannot remove 'quads3' - currently connected. Disconnect first.")


def test_rm_server_not_found(mock_shell):
    """Test rm-server with non-existent server"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"
    mock_shell.connection.current_server = "quads1"

    yaml_content = {"servers": {}}

    with patch("builtins.open", mock_open(read_data="servers: {}\n")):
        with patch("quads_client.commands.server.yaml.safe_load", return_value=yaml_content):
            server_cmd = ServerCommands(mock_shell)
            server_cmd.cmd_rm_server("quads3")

            mock_shell.perror.assert_called_with("Server 'quads3' not found")


def test_rm_server_clears_default(mock_shell):
    """Test rm-server clears default_server if removing default"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"
    mock_shell.connection.current_server = "quads1"

    yaml_content = {
        "servers": {"quads3": {"url": "https://quads3.example.com"}},
        "default_server": "quads3",
    }

    with patch("builtins.open", mock_open(read_data="servers:\n  quads3: {}\n")):
        with patch("quads_client.commands.server.yaml.safe_load", return_value=yaml_content):
            with patch("quads_client.commands.server.yaml.dump") as mock_dump:
                with patch("builtins.input", return_value="y"):
                    with patch.object(ServerCommands, "cmd_config_reload"):
                        server_cmd = ServerCommands(mock_shell)
                        server_cmd.cmd_rm_server("quads3")

                        call_args = mock_dump.call_args[0][0]
                        assert call_args["default_server"] is None


def test_rm_server_no_args(mock_shell):
    """Test rm-server with no arguments"""
    server_cmd = ServerCommands(mock_shell)
    server_cmd.cmd_rm_server("")

    mock_shell.perror.assert_called_with("Usage: rm-server <name>")


def test_config_reload_success(mock_shell):
    """Test config-reload command"""
    with patch("quads_client.config.QuadsClientConfig") as mock_config_class:
        mock_new_config = MagicMock()
        mock_config_class.return_value = mock_new_config

        # Mock session with connection
        mock_session = MagicMock()
        mock_session.connection = MagicMock()
        mock_shell.session_manager.sessions = {"1": mock_session}

        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_config_reload("")

        mock_config_class.assert_called_once()
        assert mock_shell.config == mock_new_config
        assert mock_shell.session_manager.config == mock_new_config
        assert mock_session.connection.config == mock_new_config
        mock_shell.poutput.assert_called_with("OK: Configuration reloaded successfully")


def test_config_reload_failure(mock_shell):
    """Test config-reload with failure"""
    with patch("quads_client.config.QuadsClientConfig", side_effect=Exception("Config error")):
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_config_reload("")

        mock_shell.perror.assert_called_with("Failed to reload configuration: Config error")


def test_config_reload_no_connection(mock_shell):
    """Test config-reload when session_manager is None"""
    mock_shell.session_manager = None
    with patch("quads_client.config.QuadsClientConfig") as mock_config_class:
        mock_new_config = MagicMock()
        mock_config_class.return_value = mock_new_config

        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_config_reload("")

        mock_config_class.assert_called_once()
        assert mock_shell.config == mock_new_config
        mock_shell.poutput.assert_called_with("OK: Configuration reloaded successfully")


def test_add_quads_server_success(mock_shell):
    """Test interactive add-quads-server command"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"

    yaml_content = {"servers": {}}

    with patch("builtins.input", side_effect=["quads3.example.com", "https://quads3.example.com", "y", "", "3"]):
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            with patch("builtins.open", mock_open(read_data="servers: {}\n")):
                with patch("yaml.safe_load", return_value=yaml_content):
                    with patch("yaml.dump") as mock_dump:
                        with patch.object(ServerCommands, "cmd_config_reload"):
                            server_cmd = ServerCommands(mock_shell)
                            server_cmd.cmd_add_quads_server("")

                            mock_dump.assert_called_once()
                            call_args = mock_dump.call_args[0][0]
                            assert call_args["servers"]["quads3.example.com"]["username"] == ""
                            assert call_args["servers"]["quads3.example.com"]["password"] == ""
                            assert call_args["default_server"] == "quads3.example.com"
                            assert mock_shell.poutput.call_count >= 2


def test_add_quads_server_second_server_no_default_change(mock_shell):
    """Test add-quads-server does not overwrite default_server when servers exist"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"

    yaml_content = {
        "servers": {"existing.example.com": {"url": "https://existing.example.com"}},
        "default_server": "existing.example.com",
    }

    with patch("builtins.input", side_effect=["quads4.example.com", "https://quads4.example.com", "y", "", "3"]):
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            with patch("builtins.open", mock_open(read_data="servers: {}\n")):
                with patch("yaml.safe_load", return_value=yaml_content):
                    with patch("yaml.dump") as mock_dump:
                        with patch.object(ServerCommands, "cmd_config_reload"):
                            server_cmd = ServerCommands(mock_shell)
                            server_cmd.cmd_add_quads_server("")

                            call_args = mock_dump.call_args[0][0]
                            assert call_args["default_server"] == "existing.example.com"


def test_add_quads_server_empty_name(mock_shell):
    """Test add-quads-server with empty server name"""
    with patch("builtins.input", return_value=""):
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_add_quads_server("")

        mock_shell.perror.assert_called_with("Server name cannot be empty")


def test_add_quads_server_already_exists(mock_shell):
    """Test add-quads-server with existing server name"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"

    yaml_content = {"servers": {"quads3.example.com": {"url": "https://quads3.example.com"}}}

    with patch("builtins.input", return_value="quads3.example.com"):
        with patch("builtins.open", mock_open(read_data="servers:\n  quads3.example.com: {}\n")):
            with patch("yaml.safe_load", return_value=yaml_content):
                server_cmd = ServerCommands(mock_shell)
                server_cmd.cmd_add_quads_server("")

                assert any("already exists" in str(call) for call in mock_shell.perror.call_args_list)


def test_add_quads_server_no_verify(mock_shell):
    """Test add-quads-server with SSL verification disabled"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"

    yaml_content = {"servers": {}}

    with patch("builtins.input", side_effect=["quads3.example.com", "https://quads3.example.com", "n", "", "3"]):
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            with patch("builtins.open", mock_open(read_data="servers: {}\n")):
                with patch("yaml.safe_load", return_value=yaml_content):
                    with patch("yaml.dump") as mock_dump:
                        with patch.object(ServerCommands, "cmd_config_reload"):
                            server_cmd = ServerCommands(mock_shell)
                            server_cmd.cmd_add_quads_server("")

                            # Verify verify was set to False
                            call_args = mock_dump.call_args[0][0]
                            assert call_args["servers"]["quads3.example.com"]["verify"] is False


def test_add_quads_server_with_credentials(mock_shell):
    """Test add-quads-server with username/password credentials"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"

    yaml_content = {"servers": {}}

    with patch(
        "builtins.input",
        side_effect=[
            "quads3.example.com",
            "https://quads3.example.com",
            "y",
            "",
            "1",
            "user@example.com",
        ],
    ):
        with patch("getpass.getpass", return_value="mypassword"):
            with patch("requests.get") as mock_get:
                mock_get.return_value.status_code = 200
                with patch("builtins.open", mock_open(read_data="servers: {}\n")):
                    with patch("yaml.safe_load", return_value=yaml_content):
                        with patch("yaml.dump") as mock_dump:
                            with patch.object(ServerCommands, "cmd_config_reload"):
                                server_cmd = ServerCommands(mock_shell)
                                server_cmd.cmd_add_quads_server("")

                                mock_dump.assert_called_once()
                                call_args = mock_dump.call_args[0][0]
                                assert call_args["servers"]["quads3.example.com"]["username"] == "user@example.com"
                                assert call_args["servers"]["quads3.example.com"]["password"] == "mypassword"


def test_add_quads_server_connection_failed_accept(mock_shell):
    """Test add-quads-server with connection test failure (user accepts)"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"

    yaml_content = {"servers": {}}

    with patch("requests.get") as mock_get:
        mock_get.side_effect = Exception("Connection failed")

        with patch("builtins.open", mock_open(read_data="servers: {}\n")):
            with patch("yaml.safe_load", return_value=yaml_content):
                with patch("yaml.dump") as mock_dump:
                    with patch(
                        "builtins.input",
                        side_effect=["quads3.example.com", "https://quads3.example.com", "y", "", "3", "y"],
                    ):
                        with patch.object(ServerCommands, "cmd_config_reload"):
                            server_cmd = ServerCommands(mock_shell)
                            server_cmd.cmd_add_quads_server("")

                            mock_dump.assert_called_once()
                            call_args = mock_dump.call_args[0][0]
                            assert "quads3.example.com" in call_args["servers"]


def test_edit_server_cli_proxy_argument(mock_shell):
    """Test edit-server accepts a proxy argument"""
    with patch.object(ServerCommands, "edit_server_programmatic") as mock_edit:
        mock_edit.return_value = (True, "Server 'quads3' updated successfully")
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_edit_server("quads3 proxy socks5h://127.0.0.1:1080")

    assert mock_edit.call_args.kwargs["proxy"] == "socks5h://127.0.0.1:1080"


def test_edit_server_cli_without_proxy_keeps_proxy_none(mock_shell):
    """Test edit-server leaves the proxy untouched when no proxy token is given"""
    with patch.object(ServerCommands, "edit_server_programmatic") as mock_edit:
        mock_edit.return_value = (True, "Server 'quads3' updated successfully")
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_edit_server("quads3 verify false")

    assert mock_edit.call_args.kwargs["proxy"] is None


def test_servers_command_without_session_still_probes(mock_shell):
    """Test 'servers' works before any session exists (shell.connection is None)"""
    mock_shell.config.get_all_servers.return_value = {
        "test_server": {"url": "https://test.example.com", "username": "", "password": "", "verify": True}
    }
    mock_shell.config.get_default_server.return_value = None
    mock_shell.config.get_server_url.side_effect = lambda n: "https://test.example.com"
    mock_shell.config.get_server_verify.side_effect = lambda n: True
    mock_shell.config.get_server_api_token.side_effect = lambda n: ""
    mock_shell.config.get_server_proxy.side_effect = lambda n: ""
    mock_shell.connection = None

    mock_api = MagicMock()
    mock_api.get_version.return_value = {"version": "2.2.6"}
    mock_api_class = MagicMock(return_value=mock_api)

    with patch("quads_client.connection.QuadsApi", mock_api_class):
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_servers("")

    # Version must be probed even with no active connection
    mock_api.get_version.assert_called_once()
    assert "2.2.6" in str(mock_shell.poutput.call_args_list)


def test_edit_server_cli_proxy_none_clears(mock_shell):
    """Test edit-server ... proxy none clears the proxy (empty string, not the literal 'none')"""
    with patch.object(ServerCommands, "edit_server_programmatic") as mock_edit:
        mock_edit.return_value = (True, "Server 'quads3' updated successfully")
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_edit_server("quads3 proxy none")

    assert mock_edit.call_args.kwargs["proxy"] == ""


def test_edit_server_cli_proxy_dash_clears(mock_shell):
    """Test edit-server ... proxy - also clears the proxy"""
    with patch.object(ServerCommands, "edit_server_programmatic") as mock_edit:
        mock_edit.return_value = (True, "Server 'quads3' updated successfully")
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_edit_server("quads3 proxy -")

    assert mock_edit.call_args.kwargs["proxy"] == ""


def test_proxy_parse_rejects_port_zero():
    """Test port 0 is rejected as a proxy port"""
    from quads_client.proxies import ProxyError, parse_proxy

    with pytest.raises(ProxyError, match="host and port"):
        parse_proxy("socks5://127.0.0.1:0")


def test_add_quads_server_wizard_persists_proxy(mock_shell):
    """Test the add-quads-server wizard stores a proxy and probes through it"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"
    yaml_content = {"servers": {}}

    inputs = ["quads3.example.com", "https://quads3.example.com", "y", "socks5h://127.0.0.1:1080", "3"]
    with patch("builtins.input", side_effect=inputs):
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            with patch("builtins.open", mock_open(read_data="servers: {}\n")):
                with patch("yaml.safe_load", return_value=yaml_content):
                    with patch("yaml.dump") as mock_dump:
                        with patch.object(ServerCommands, "cmd_config_reload"):
                            server_cmd = ServerCommands(mock_shell)
                            server_cmd.cmd_add_quads_server("")

    written = mock_dump.call_args[0][0]
    assert written["servers"]["quads3.example.com"]["proxy"] == "socks5h://127.0.0.1:1080"
    assert mock_get.call_args.kwargs["proxies"] == {
        "http": "socks5h://127.0.0.1:1080",
        "https": "socks5h://127.0.0.1:1080",
    }


def test_servers_command_reports_proxy_error(mock_shell):
    """Test a proxy misconfiguration is surfaced instead of a false 'Offline'"""
    mock_shell.config.get_all_servers.return_value = {
        "test_server": {
            "url": "https://test.example.com",
            "username": "",
            "password": "",
            "verify": True,
            "proxy": "socks5h://127.0.0.1:1080",
        }
    }
    mock_shell.config.get_default_server.return_value = None
    mock_shell.config.get_server_url.side_effect = lambda n: "https://test.example.com"
    mock_shell.config.get_server_verify.side_effect = lambda n: True
    mock_shell.config.get_server_api_token.side_effect = lambda n: ""
    mock_shell.config.get_server_proxy.side_effect = lambda n: "socks5h://127.0.0.1:1080"
    mock_shell.connection = None

    from quads_client.proxies import ProxyError

    mock_api_class = MagicMock(side_effect=ProxyError("The 'PySocks' package is required for 'socks5h' proxies."))

    with patch("quads_client.connection.QuadsApi", mock_api_class):
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_servers("")

    rendered = str(mock_shell.poutput.call_args_list)
    assert "Proxy error" in rendered


def test_servers_command_suppresses_ssl_warning_when_verify_disabled(mock_shell, capsys):
    """Test verify:false keeps InsecureRequestWarning suppressed in the servers table"""
    import urllib3

    mock_shell.config.get_all_servers.return_value = {
        "test_server": {
            "url": "https://test.example.com",
            "username": "",
            "password": "",
            "verify": False,
        }
    }
    mock_shell.config.get_default_server.return_value = None
    mock_shell.config.get_server_url.side_effect = lambda n: "https://test.example.com"
    mock_shell.config.get_server_verify.side_effect = lambda n: False
    mock_shell.config.get_server_api_token.side_effect = lambda n: ""
    mock_shell.config.get_server_proxy.side_effect = lambda n: ""
    mock_shell.connection = None

    def emit_warning():
        import warnings

        warnings.warn("Unverified HTTPS request is being made", urllib3.exceptions.InsecureRequestWarning)

    mock_api = MagicMock()
    mock_api.get_version.side_effect = lambda: (emit_warning(), {"version": "2.2.6"})[1]
    mock_api_class = MagicMock(return_value=mock_api)

    with patch("quads_client.connection.QuadsApi", mock_api_class):
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_servers("")

    captured = capsys.readouterr()
    assert "InsecureRequestWarning" not in captured.err


def test_servers_command_reports_malformed_proxy_as_proxy_error(mock_shell):
    """Test a malformed proxy URL surfaces as Proxy error (ConfigError path), not Offline"""
    mock_shell.config.get_all_servers.return_value = {
        "test_server": {
            "url": "https://test.example.com",
            "username": "",
            "password": "",
            "verify": True,
            "proxy": "ftp://127.0.0.1:21",
        }
    }
    mock_shell.config.get_default_server.return_value = None
    mock_shell.config.get_server_url.side_effect = lambda n: "https://test.example.com"
    mock_shell.config.get_server_verify.side_effect = lambda n: True
    mock_shell.config.get_server_api_token.side_effect = lambda n: ""
    mock_shell.config.get_server_proxy.side_effect = lambda n: "ftp://127.0.0.1:21"
    mock_shell.connection = None

    from quads_client.config import ConfigError

    mock_api_class = MagicMock(side_effect=ConfigError("proxy is invalid: Unsupported proxy scheme 'ftp'"))

    with patch("quads_client.connection.QuadsApi", mock_api_class):
        server_cmd = ServerCommands(mock_shell)
        server_cmd.cmd_servers("")

    rendered = str(mock_shell.poutput.call_args_list)
    assert "Proxy error" in rendered


def test_add_quads_server_wizard_none_means_no_proxy(mock_shell):
    """Test typing 'none' at the wizard proxy prompt stores no proxy"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"
    yaml_content = {"servers": {}}

    inputs = ["quads3.example.com", "https://quads3.example.com", "y", "none", "3"]
    with patch("builtins.input", side_effect=inputs):
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            with patch("builtins.open", mock_open(read_data="servers: {}\n")):
                with patch("yaml.safe_load", return_value=yaml_content):
                    with patch("yaml.dump") as mock_dump:
                        with patch.object(ServerCommands, "cmd_config_reload"):
                            server_cmd = ServerCommands(mock_shell)
                            server_cmd.cmd_add_quads_server("")

    written = mock_dump.call_args[0][0]
    assert written["servers"]["quads3.example.com"]["proxy"] == ""


def test_edit_server_cli_proxy_argument_still_redacts_in_errors(mock_shell):
    """Test proxy validation failure messages shown by edit-server hide credentials"""
    mock_shell.config.config_path = "~/.config/quads/quads-client.yml"
    yaml_content = {
        "servers": {
            "quads3": {"url": "https://quads3.example.com", "proxy": "socks5h://alice:sekret@proxy.local:notaport"}
        }
    }

    with patch("builtins.open", mock_open(read_data="servers: {}\n")):
        with patch("yaml.safe_load", return_value=yaml_content):
            with patch.object(ServerCommands, "cmd_config_reload"):
                server_cmd = ServerCommands(mock_shell)
                server_cmd.cmd_edit_server("quads3 proxy socks5h://alice:sekret@proxy.local:9")

    rendered = " ".join(str(c) for c in mock_shell.poutput.call_args_list + mock_shell.perror.call_args_list)
    assert "sekret" not in rendered
