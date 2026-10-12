from tabulate import tabulate
import yaml
from pathlib import Path

from quads_client.config import ConfigError
from quads_client.connection import ConnectionManager
from quads_client.proxies import ProxyError, normalize_proxy, parse_proxy
from quads_client.utils import fetch_server_version, get_ssl_status_text


class ServerCommands:
    def __init__(self, shell):
        self.shell = shell
        self.rich_console = shell.rich_console if hasattr(shell, "rich_console") else None

    def _shorten_server_name(self, name):
        """Shorten server name by stripping last 2 segments (e.g. quads2-dev.rdu2.scalelab)"""
        parts = name.split(".")
        if len(parts) > 3:
            return ".".join(parts[:-2])
        return name

    def cmd_servers(self, args):
        """List all configured servers with status"""
        if not self.shell.config:
            self.shell.perror("Configuration not loaded")
            return

        servers = self.shell.config.get_all_servers()
        default = self.shell.config.get_default_server()
        current = self.shell.connection.current_server if self.shell.connection else None

        table_data = []
        for i, (name, server_config) in enumerate(servers.items(), 1):
            url = server_config.get("url", "")
            verify = server_config.get("verify", True)
            # Get both status/version and info in one call to avoid double connection overhead
            status, version, info = self._get_server_info_combined(name, server_config)

            is_default = "✓" if name == default else ""
            is_connected = "Connected" if name == current else status
            short_name = self._shorten_server_name(name)
            ssl_status = get_ssl_status_text(url, verify)

            table_data.append([i, short_name, ssl_status, version, info, is_connected, is_default])

        headers = ["#", "Server Name", "SSL", "Version", "Capacity", "Status", "Default"]
        if self.rich_console:
            self.rich_console.print_table(headers, table_data, title="Configured Servers")
            if current:
                short_current = self._shorten_server_name(current)
                self.rich_console.print_info(f"\n[bold cyan]Current connection:[/bold cyan] {short_current}")
        else:
            self.shell.poutput(tabulate(table_data, headers=headers, tablefmt="simple"))
            if current:
                short_current = self._shorten_server_name(current)
                self.shell.poutput(f"\nCurrent connection: {short_current}")

    def _get_server_info_combined(self, name, server_config):
        """Get server status, version, and capacity. Version check requires no auth (public endpoint)."""
        try:
            import urllib3

            # 'servers' is usable before any session exists, so build a
            # throwaway manager when there is no active connection.
            connection = self.shell.connection or ConnectionManager(self.shell.config)

            username = server_config.get("username", "")
            password = server_config.get("password", "")
            verify = server_config.get("verify", True)

            # Suppress SSL warnings when certificate verification is disabled
            if not verify:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            # STEP 1: Try to get version WITHOUT auth (public endpoint)
            version = "unknown"
            try:
                # Create API instance without credentials for public version check
                api_public = connection.build_api(name, username="", password="")
                version_info = api_public.get_version()

                if isinstance(version_info, dict):
                    version = version_info.get("version", "unknown")
                    if not version or version == "":
                        version = "unknown"
                elif isinstance(version_info, str):
                    # API returns string like "QUADS version 2.2.6 maximilian"
                    # Extract just the version number
                    import re

                    version_match = re.search(r"(\d+\.\d+\.\d+)", version_info)
                    if version_match:
                        version = version_match.group(1)
                    else:
                        version = version_info if version_info else "unknown"
            except (ConfigError, ProxyError):
                # Proxy misconfiguration (bad URL, or PySocks missing)
                return "Proxy error", "N/A", "N/A"
            except Exception:
                # Version check failed - server offline or unreachable
                return "Offline", "N/A", "N/A"

            # Server is online (version check succeeded)
            # STEP 2: Try to get capacity info (requires auth)
            capacity = "N/A"
            status = "Available"
            api_token = server_config.get("api_token", "")

            if not api_token and (not username or not password):
                return status, version, "No credentials"

            # Try authenticated API calls for capacity
            try:
                if api_token:
                    api = connection.build_api(name, username="", password="", api_token=api_token)
                else:
                    api = connection.build_api(name, username=username, password=password)
                    login_result = api.login()
                    if not login_result or login_result.get("status") == "failure":
                        return "Auth failed", version, "N/A"

                # Authenticated, get capacity
                try:
                    all_hosts = api.get_hosts()
                    total_hosts = sum(1 for h in all_hosts if not h.get("broken") and not h.get("retired"))

                    if total_hosts > 0:
                        current_schedules = api.get_current_schedules({})
                        scheduled_hosts = len(
                            set(s.get("host", {}).get("name", "") for s in current_schedules if s.get("host"))
                        )
                        percent_used = int((scheduled_hosts / total_hosts) * 100)
                        free_hosts = total_hosts - scheduled_hosts
                        capacity = f"{percent_used}% ({free_hosts}/{total_hosts})"
                    else:
                        capacity = "0% (0/0)"
                except Exception:
                    capacity = "N/A"

                return "Online", version, capacity
            except Exception:
                # Auth failed but server is online
                return "Auth failed", version, "N/A"

        except (ConfigError, ProxyError):
            return "Proxy error", "N/A", "N/A"
        except Exception:
            return "Offline", "N/A", "N/A"

    def cmd_add_quads_server(self, args):
        """Interactive command to add a new QUADS server to configuration"""
        if not self.shell.config:
            self.shell.perror("Configuration not loaded")
            return

        self.shell.poutput("\n=== Add New QUADS Server ===\n")

        # Prompt for friendly name
        server_name = input("Enter a friendly name for this server (e.g., my-quads, scalelab): ").strip()
        if not server_name:
            self.shell.perror("Server name cannot be empty")
            return

        # Check if server already exists
        config_path = Path(self.shell.config.config_path).expanduser()
        try:
            with open(config_path, "r") as f:
                config_data = yaml.safe_load(f) or {}

            if "servers" not in config_data:
                config_data["servers"] = {}

            if server_name in config_data["servers"]:
                self.shell.perror(f"Server '{server_name}' already exists. Use edit-server to modify.")
                return
        except Exception as e:
            self.shell.perror(f"Failed to read configuration: {e}")
            return

        # Prompt for URL
        server_url = input("Enter server URL (e.g., https://quads1.example.com): ").strip()
        if not server_url:
            self.shell.perror("Server URL cannot be empty")
            return

        # Ensure URL starts with http:// or https://
        if not server_url.startswith(("http://", "https://")):
            self.shell.pwarning("URL should start with https:// (or http:// for testing)")
            server_url = f"https://{server_url}"
            self.shell.poutput(f"Using URL: {server_url}")

        # Ask about SSL verification
        verify_input = input("Enable SSL certificate verification? [Y/n]: ").strip().lower()
        verify = verify_input != "n"

        # Optional per-server proxy for proxy-only environments
        # Reject a typo'd proxy here rather than letting the probe report a
        # connection failure and writing the bad value when the user confirms.
        while True:
            proxy = normalize_proxy(input("Proxy URL [none] (e.g. socks5h://127.0.0.1:1080): "))
            if not proxy:
                break
            try:
                parse_proxy(proxy)
                break
            except ProxyError as e:
                self.shell.perror(f"Invalid proxy: {e}")

        # Authentication method
        import getpass

        self.shell.poutput("\nAuthentication method:")
        self.shell.poutput("  1) Username & Password")
        self.shell.poutput("  2) SSO Token")
        self.shell.poutput("  3) None (register later)")
        auth_choice = input("Choice [1/2/3]: ").strip()
        if auth_choice not in ("1", "2", "3"):
            self.shell.perror("Invalid choice. Please enter 1, 2, or 3.")
            return

        username = ""
        password = ""
        api_token = ""

        if auth_choice == "1":
            username = input("Email: ").strip()
            password = getpass.getpass("Password: ").strip()
        elif auth_choice == "2":
            username = input("Email: ").strip()
            api_token = getpass.getpass("SSO Token: ").strip()
            if api_token and not api_token.startswith("qat_"):
                self.shell.perror("Invalid token format: must start with qat_")
                return

        # Test connection (without credentials - just check if server is reachable)
        self.shell.poutput(f"\nTesting connection to {server_url}...")
        try:
            status_code, _version = fetch_server_version(server_url, verify, proxy)
            if status_code in (200, 401, 403):
                # 200 = success, 401/403 = needs auth (but server is reachable)
                self.shell.poutput("Server is reachable")
            else:
                self.shell.pwarning(f"Server returned status code: {status_code}")
        except Exception as e:
            self.shell.pwarning(f"Could not connect to server: {e}")
            response = input("Add server anyway? [y/N]: ")
            if response.lower() != "y":
                self.shell.poutput("Server not added")
                return

        is_first_server = len(config_data["servers"]) == 0

        config_data["servers"][server_name] = {
            "url": server_url,
            "username": username,
            "password": password,
            "api_token": api_token,
            "verify": verify,
            "proxy": proxy,
        }

        if is_first_server:
            config_data["default_server"] = server_name

        try:
            with open(config_path, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            # Automatically reload config so tab completion works immediately
            self.cmd_config_reload("")

            if self.rich_console:
                self.rich_console.print_success(f"\nServer '{server_name}' added successfully!")
                self.rich_console.print_info("\nNext steps:")
                self.rich_console.print_info(f"  1. Connect to server: connect {server_name}")
                if not username and not api_token:
                    self.rich_console.print_info("  2. Authenticate:")
                    self.rich_console.print_info("     token-login              (SSO token)")
                    self.rich_console.print_info("     register <email> <pass>  (new account)")
            else:
                self.shell.poutput(f"\nOK: Server '{server_name}' added successfully!")
                self.shell.poutput("\nNext steps:")
                self.shell.poutput(f"  1. Connect to server: connect {server_name}")
                if not username and not api_token:
                    self.shell.poutput("  2. Authenticate:")
                    self.shell.poutput("     token-login              (SSO token)")
                    self.shell.poutput("     register <email> <pass>  (new account)")
        except Exception as e:
            self.shell.perror(f"Failed to save configuration: {e}")

    def add_server_programmatic(
        self, name, url, username="", password="", verify=True, test_connection=True, proxy=""
    ):
        """
        Non-interactive server add for GUI and scripting.

        Args:
            name: Server name (e.g., quads1.example.com)
            url: Server URL (e.g., https://quads1.example.com)
            username: Username (optional, empty string for registration mode)
            password: Password (optional, empty string for registration mode)
            verify: Enable SSL verification (default: True)
            test_connection: Test connection before adding (default: True)
            proxy: Proxy URL for outbound connections (optional, e.g. socks5h://127.0.0.1:1080)

        Returns:
            (success: bool, message: str, version: str or None)
        """
        if not self.shell.config:
            return (False, "Configuration not loaded", None)

        # Normalize the documented 'none'/'-' sentinel and reject typo'd proxies
        # up front, so a bad value is never stored (and is not reported as a
        # connection failure, which the GUI would offer to override).
        proxy = normalize_proxy(proxy)
        if proxy:
            try:
                parse_proxy(proxy)
            except ProxyError as e:
                return (False, f"Invalid proxy: {e}", None)

        # Ensure URL starts with http:// or https://
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        config_path = Path(self.shell.config.config_path).expanduser()

        try:
            with open(config_path, "r") as f:
                config_data = yaml.safe_load(f) or {}

            if "servers" not in config_data:
                config_data["servers"] = {}

            if name in config_data["servers"]:
                return (False, f"Server '{name}' already exists. Use edit-server to modify.", None)
        except Exception as e:
            return (False, f"Failed to read configuration: {e}", None)

        version_info = None
        if test_connection:
            try:
                status_code, probed_version = fetch_server_version(url, verify, proxy)
                if status_code == 200:
                    version_info = probed_version or "unknown"
                elif status_code not in (401, 403):
                    return (False, f"Server returned status code: {status_code}", None)
            except Exception as e:
                return (False, f"Could not connect to server: {e}", None)

        is_first_server = len(config_data["servers"]) == 0

        config_data["servers"][name] = {
            "url": url,
            "username": username,
            "password": password,
            "api_token": "",
            "verify": verify,
            "proxy": proxy,
        }

        # First server added becomes the default
        if is_first_server:
            config_data["default_server"] = name

        try:
            with open(config_path, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            # Automatically reload config so tab completion works immediately
            self.cmd_config_reload("")

            return (True, f"Server '{name}' added successfully", version_info)

        except Exception as e:
            return (False, f"Failed to save configuration: {e}", None)

    def edit_server_programmatic(
        self, name, url=None, username=None, password=None, verify=None, api_token=None, proxy=None
    ):
        """
        Non-interactive server edit for GUI and scripting.

        Args:
            name: Server name to edit
            url: New URL (optional, None = no change)
            username: New username (optional, None = no change)
            password: New password (optional, None = no change)
            verify: New SSL verification setting (optional, None = no change)
            api_token: New API token (optional, None = no change)
            proxy: New proxy URL (optional, None = no change, empty string = disable proxy)

        Returns:
            (success: bool, message: str)
        """
        if not self.shell.config:
            return (False, "Configuration not loaded")

        config_path = Path(self.shell.config.config_path).expanduser()

        try:
            with open(config_path, "r") as f:
                config_data = yaml.safe_load(f) or {}

            if "servers" not in config_data or name not in config_data["servers"]:
                return (False, f"Server '{name}' not found")

            server = config_data["servers"][name]

            # Update only provided fields
            if url is not None:
                server["url"] = url
            if username is not None:
                server["username"] = username
            if password is not None:
                server["password"] = password
            if api_token is not None:
                server["api_token"] = api_token
                server["password"] = ""
            if verify is not None:
                server["verify"] = verify
            if proxy is not None:
                # 'none'/'-' (and blanks) clear the proxy; anything else must be usable
                proxy = normalize_proxy(proxy)
                if proxy:
                    try:
                        parse_proxy(proxy)
                    except ProxyError as e:
                        return (False, f"Invalid proxy: {e}")
                server["proxy"] = proxy

            config_data["servers"][name] = server

            with open(config_path, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            # Automatically reload config
            self.cmd_config_reload("")

            return (True, f"Server '{name}' updated successfully")

        except Exception as e:
            return (False, f"Failed to edit server: {e}")

    def rm_server_programmatic(self, name):
        """
        Non-interactive server removal for GUI and scripting.

        Args:
            name: Server name to remove

        Returns:
            (success: bool, message: str)
        """
        if not self.shell.config:
            return (False, "Configuration not loaded")

        if self.shell.connection and self.shell.connection.current_server == name:
            return (False, f"Cannot remove '{name}' - currently connected. Disconnect first.")

        config_path = Path(self.shell.config.config_path).expanduser()

        try:
            with open(config_path, "r") as f:
                config_data = yaml.safe_load(f) or {}

            if "servers" not in config_data or name not in config_data["servers"]:
                return (False, f"Server '{name}' not found")

            del config_data["servers"][name]

            if config_data.get("default_server") == name:
                config_data["default_server"] = None

            with open(config_path, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            self.cmd_config_reload("")

            return (True, f"Server '{name}' removed successfully")

        except Exception as e:
            return (False, f"Failed to remove server: {e}")

    def cmd_add_server(self, args):
        """Add a new server to configuration. Usage: add-server <name> <url> <username> <password> [--no-verify]"""
        parts = args.split()
        if len(parts) < 4:
            self.shell.perror("Usage: add-server <name> <url> <username> <password> [--no-verify]")
            return

        name = parts[0]
        url = parts[1]
        username = parts[2]
        password = parts[3]
        verify = "--no-verify" not in parts

        success, message, version = self.add_server_programmatic(name, url, username, password, verify)

        if success:
            if self.rich_console:
                self.rich_console.print_success(message)
                if version:
                    self.rich_console.print_info(f"QUADS version: {version}")
            else:
                self.shell.poutput(f"OK: {message}")
                if version:
                    self.shell.poutput(f"  QUADS version: {version}")
        else:
            self.shell.perror(message)

    def cmd_edit_server(self, args):
        """Edit an existing server.

        Usage: edit-server <name> [url URL] [username USER] [password PASS] [token TOKEN]
        [verify true|false] [proxy URL]
        """
        parts = args.split()
        if len(parts) < 1:
            self.shell.perror(
                "Usage: edit-server <name> [url URL] [username USER] [password PASS] [token TOKEN] "
                "[verify true|false] [proxy URL]"
            )
            return

        name = parts[0]

        # Parse updates
        updates = {}
        i = 1
        while i < len(parts):
            if parts[i] == "url" and i + 1 < len(parts):
                updates["url"] = parts[i + 1]
                i += 2
            elif parts[i] == "username" and i + 1 < len(parts):
                updates["username"] = parts[i + 1]
                i += 2
            elif parts[i] == "password" and i + 1 < len(parts):
                updates["password"] = parts[i + 1]
                i += 2
            elif parts[i] == "token" and i + 1 < len(parts):
                updates["api_token"] = parts[i + 1]
                i += 2
            elif parts[i] == "verify" and i + 1 < len(parts):
                updates["verify"] = parts[i + 1].lower() == "true"
                i += 2
            elif parts[i] == "proxy" and i + 1 < len(parts):
                # Accept 'none' (or '-') as the documented way to clear the proxy
                updates["proxy"] = normalize_proxy(parts[i + 1])
                i += 2
            else:
                i += 1

        if not updates:
            self.shell.perror("No updates specified")
            return

        # Use programmatic method
        success, message = self.edit_server_programmatic(
            name,
            url=updates.get("url"),
            username=updates.get("username"),
            password=updates.get("password"),
            verify=updates.get("verify"),
            proxy=updates.get("proxy"),
            api_token=updates.get("api_token"),
        )

        if success:
            self.shell.poutput(f"OK: {message}")
        else:
            self.shell.perror(message)

    def cmd_rm_server(self, args):
        """Remove a server from configuration. Usage: rm-server <name>"""
        if not args.strip():
            self.shell.perror("Usage: rm-server <name>")
            return

        name = args.strip()

        if not self.shell.config:
            self.shell.perror("Configuration not loaded")
            return

        if self.shell.connection and self.shell.connection.current_server == name:
            self.shell.perror(f"Cannot remove '{name}' - currently connected. Disconnect first.")
            return

        config_path = Path(self.shell.config.config_path).expanduser()
        try:
            with open(config_path, "r") as f:
                config_data = yaml.safe_load(f) or {}
            if "servers" not in config_data or name not in config_data["servers"]:
                self.shell.perror(f"Server '{name}' not found")
                return
        except Exception as e:
            self.shell.perror(f"Failed to remove server: {e}")
            return

        response = input(f"Remove server '{name}'? [y/N]: ")
        if response.lower() != "y":
            self.shell.poutput("Server not removed")
            return

        success, message = self.rm_server_programmatic(name)
        if success:
            self.shell.poutput(f"OK: {message}")
        else:
            self.shell.perror(message)

    def cmd_config_reload(self, args):
        """Reload configuration from file"""
        try:
            from quads_client.config import QuadsClientConfig

            self.shell.config = QuadsClientConfig()

            # Update config for all sessions
            if self.shell.session_manager:
                self.shell.session_manager.config = self.shell.config
                for session in self.shell.session_manager.sessions.values():
                    session.connection.config = self.shell.config

            self.shell.poutput("OK: Configuration reloaded successfully")
        except Exception as e:
            self.shell.perror(f"Failed to reload configuration: {e}")
