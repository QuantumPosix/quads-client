"""Connection and server management view"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

from quads_client.gui.widgets.dialogs import show_error_dialog
from quads_client.proxies import normalize_proxy
from quads_client.utils import fetch_server_version


class ConnectionView(ttk.Frame):
    """View for managing servers and connections"""

    def __init__(self, parent, shell):
        super().__init__(parent)
        self.shell = shell
        self.selected_server = None

        self._create_ui()
        self._refresh_server_list()

    def _create_ui(self):
        """Create the UI"""
        title_frame = ttk.Frame(self)
        title_frame.pack(fill=tk.X, padx=20, pady=10)

        ttk.Label(
            title_frame,
            text="Servers & Connections",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(side=tk.LEFT)

        ttk.Button(title_frame, text="+ Add Server", command=self._add_server).pack(side=tk.RIGHT)
        ttk.Button(title_frame, text="🔄 Refresh", command=self._refresh_server_list).pack(side=tk.RIGHT, padx=5)

        # Scrollable container for all content below the title
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

        style = ttk.Style()
        bg_color = style.lookup("TFrame", "background")
        self._canvas = tk.Canvas(container, highlightthickness=0, bg=bg_color)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self._canvas.yview)
        scrollable_frame = ttk.Frame(self._canvas)

        scrollable_frame.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        canvas_window = self._canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(canvas_window, width=e.width))
        self._canvas.configure(yscrollcommand=scrollbar.set)

        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Mouse wheel scrolling (guarded to avoid errors if canvas is destroyed)
        def _on_scroll_up(event):
            if self._canvas.winfo_exists():
                self._canvas.yview_scroll(-1, "units")

        def _on_scroll_down(event):
            if self._canvas.winfo_exists():
                self._canvas.yview_scroll(1, "units")

        self._canvas.bind_all("<Button-4>", _on_scroll_up)
        self._canvas.bind_all("<Button-5>", _on_scroll_down)

        content_frame = scrollable_frame

        # --- Configured Servers ---
        ttk.Label(content_frame, text="Configured Servers:", font=("TkDefaultFont", 10)).pack(anchor=tk.W, pady=(0, 5))

        tree_frame = ttk.Frame(content_frame)
        tree_frame.pack(fill=tk.X)

        tree_scrollbar = ttk.Scrollbar(tree_frame)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.server_tree = ttk.Treeview(
            tree_frame,
            columns=("name", "url", "version", "status"),
            show="headings",
            yscrollcommand=tree_scrollbar.set,
            height=5,
        )
        tree_scrollbar.config(command=self.server_tree.yview)

        self.server_tree.heading("name", text="Name")
        self.server_tree.heading("url", text="URL")
        self.server_tree.heading("version", text="QUADS Version")
        self.server_tree.heading("status", text="Status")

        self.server_tree.column("name", width=150)
        self.server_tree.column("url", width=250)
        self.server_tree.column("version", width=120)
        self.server_tree.column("status", width=100)

        self.server_tree.pack(fill=tk.X)
        self.server_tree.bind("<<TreeviewSelect>>", self._on_server_selected)

        # --- Server Details ---
        details_frame = ttk.LabelFrame(content_frame, text="Server Details", padding=10)
        details_frame.pack(fill=tk.X, pady=(15, 10))

        self.details_text = tk.Text(
            details_frame,
            height=5,
            width=60,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=self.shell.gui_app.theme_manager.get_color("text_bg"),
            fg=self.shell.gui_app.theme_manager.get_color("text_fg"),
        )
        self.details_text.pack(fill=tk.X)

        self.details_text.tag_config("connected", foreground=self.shell.gui_app.theme_manager.get_color("success"))
        self.details_text.tag_config("disconnected", foreground=self.shell.gui_app.theme_manager.get_color("fg"))

        button_frame = ttk.Frame(details_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        self.connect_button = ttk.Button(button_frame, text="Connect", command=self._connect_server, state=tk.DISABLED)
        self.connect_button.pack(side=tk.LEFT, padx=5)

        self.disconnect_button = ttk.Button(
            button_frame, text="Disconnect", command=self._disconnect_server, state=tk.DISABLED
        )
        self.disconnect_button.pack(side=tk.LEFT, padx=5)

        self.edit_button = ttk.Button(button_frame, text="Edit", command=self._edit_server, state=tk.DISABLED)
        self.edit_button.pack(side=tk.LEFT, padx=5)

        self.remove_button = ttk.Button(button_frame, text="Remove", command=self._remove_server, state=tk.DISABLED)
        self.remove_button.pack(side=tk.LEFT, padx=5)

        # --- Active Sessions ---
        sessions_frame = ttk.LabelFrame(content_frame, text="Active Sessions", padding=10)
        sessions_frame.pack(fill=tk.X, pady=(10, 10))

        self.sessions_tree = ttk.Treeview(
            sessions_frame,
            columns=("id", "server", "label", "status", "last_active"),
            show="headings",
            height=4,
        )

        self.sessions_tree.heading("id", text="ID")
        self.sessions_tree.heading("server", text="Server")
        self.sessions_tree.heading("label", text="Label")
        self.sessions_tree.heading("status", text="Status")
        self.sessions_tree.heading("last_active", text="Last Active")

        self.sessions_tree.column("id", width=50)
        self.sessions_tree.column("server", width=150)
        self.sessions_tree.column("label", width=100)
        self.sessions_tree.column("status", width=100)
        self.sessions_tree.column("last_active", width=100)

        self.sessions_tree.pack(fill=tk.X)

        session_button_frame = ttk.Frame(sessions_frame)
        session_button_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(session_button_frame, text="Switch", command=self._switch_session).pack(side=tk.LEFT, padx=5)
        ttk.Button(session_button_frame, text="Close Session", command=self._close_session).pack(side=tk.LEFT, padx=5)

    def _clear_status(self):
        """Clear the status bar error message"""
        if hasattr(self.shell, "gui_app"):
            self.shell.gui_app.update_status("")

    def _refresh_server_list(self):
        """Refresh the server list"""
        for item in self.server_tree.get_children():
            self.server_tree.delete(item)

        if not self.shell.config:
            return

        active_session = self.shell.session_manager.active_session if self.shell.session_manager else None
        active_server = (
            active_session.connection.current_server if active_session and active_session.connection else None
        )

        servers = self.shell.config.get_all_servers()
        for name, server_config in servers.items():
            url = server_config.get("url", "")

            is_connected = False
            is_active_server = False
            if self.shell.session_manager:
                for session in self.shell.session_manager.sessions.values():
                    if session.connection and session.connection.current_server == name:
                        is_connected = True
                        if name == active_server:
                            is_active_server = True
                        break

            if is_active_server:
                status = "✓ Connected"
            elif is_connected:
                status = "● Idle"
            else:
                status = "○ Disconnected"

            item_id = self.server_tree.insert("", tk.END, values=(name, url, "-", status))

            if is_active_server:
                self.server_tree.item(item_id, tags=("active",))
                self.server_tree.tag_configure(
                    "active", foreground=self.shell.gui_app.theme_manager.get_color("success")
                )
            elif is_connected:
                self.server_tree.item(item_id, tags=("idle",))
                self.server_tree.tag_configure(
                    "idle", foreground=self.shell.gui_app.theme_manager.get_color("provisioning")
                )

        self._refresh_session_list()

        # Fetch versions in background thread to avoid blocking UI
        self._fetch_versions_async()

    def _get_server_version(self, name, server_config):
        """Fetch QUADS version from server using public endpoint only (no login)"""
        try:
            url = server_config.get("url", "")
            verify = server_config.get("verify", True)
            proxy = normalize_proxy(server_config.get("proxy", ""))
            if not url:
                return "-"

            status_code, version = fetch_server_version(url, verify, proxy)
            if status_code == 200 and version:
                return version
            return "-"
        except Exception:
            return "-"

    def _fetch_versions_async(self):
        """Fetch server versions in background thread"""
        if not self.shell.config:
            return

        servers = dict(self.shell.config.get_all_servers())

        def fetch():
            versions = {}
            for name, config in servers.items():
                versions[name] = self._get_server_version(name, config)
            self.after(0, lambda: self._update_versions(versions))

        threading.Thread(target=fetch, daemon=True).start()

    def _update_versions(self, versions):
        """Update version column from background fetch results"""
        try:
            for item in self.server_tree.get_children():
                values = list(self.server_tree.item(item, "values"))
                name = values[0]
                if name in versions:
                    values[2] = versions[name]
                    self.server_tree.item(item, values=values)
        except Exception:
            pass

    def _refresh_session_list(self):
        """Refresh the session list (matches TUI session-list format)"""
        from datetime import datetime

        for item in self.sessions_tree.get_children():
            self.sessions_tree.delete(item)

        if not self.shell.session_manager:
            return

        active_id = self.shell.session_manager.active_session_id if self.shell.session_manager.active_session else None

        for session_id, session in self.shell.session_manager.sessions.items():
            server_name = session.server_name or (session.connection.current_server if session.connection else "N/A")
            label = session.label or "-"

            if session.connection and session.connection.is_connected:
                if session_id == active_id:
                    status = "✓ Active"
                else:
                    status = "● Idle"
            else:
                status = "✗ Offline"

            now = datetime.now()
            delta = now - session.last_active
            if delta.total_seconds() < 60:
                last_active = "now"
            elif delta.total_seconds() < 3600:
                minutes = int(delta.total_seconds() / 60)
                last_active = f"{minutes}m ago"
            elif delta.total_seconds() < 86400:
                hours = int(delta.total_seconds() / 3600)
                last_active = f"{hours}h ago"
            else:
                days = int(delta.total_seconds() / 86400)
                last_active = f"{days}d ago"

            session_marker = f"{session_id} (*)" if session_id == active_id else str(session_id)

            item_id = self.sessions_tree.insert(
                "", tk.END, values=(session_marker, server_name, label, status, last_active)
            )

            if session_id == active_id:
                self.sessions_tree.item(item_id, tags=("active",))
                self.sessions_tree.tag_configure(
                    "active", foreground=self.shell.gui_app.theme_manager.get_color("success")
                )
            elif session.connection and session.connection.is_connected:
                self.sessions_tree.item(item_id, tags=("idle",))
                self.sessions_tree.tag_configure(
                    "idle", foreground=self.shell.gui_app.theme_manager.get_color("provisioning")
                )

    def _on_server_selected(self, event):
        """Handle server selection"""
        selection = self.server_tree.selection()
        if not selection:
            return

        item = selection[0]
        values = self.server_tree.item(item, "values")
        server_name = values[0]

        self.selected_server = server_name
        self._update_server_details()

    def _update_server_details(self):
        """Update server details display"""
        if not self.selected_server or not self.shell.config:
            return

        try:
            server_config = self.shell.config.get_server(self.selected_server)
        except Exception:
            server_config = {}

        url = server_config.get("url", "N/A")
        verify = server_config.get("verify", True)

        is_connected = False
        is_active_server = False
        user = "N/A"
        role = "N/A"
        active_session = self.shell.session_manager.active_session if self.shell.session_manager else None
        active_server = (
            active_session.connection.current_server if active_session and active_session.connection else None
        )

        if self.shell.session_manager:
            for session in self.shell.session_manager.sessions.values():
                if session.connection and session.connection.current_server == self.selected_server:
                    is_connected = True
                    is_active_server = self.selected_server == active_server
                    if session.connection.username:
                        user = session.connection.username
                    if session.connection.user_role:
                        role = session.connection.user_role.capitalize()
                    elif session.connection.is_authenticated:
                        role = "User"
                    break

        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete("1.0", tk.END)

        self.details_text.insert(tk.END, f"URL: {url}\n")
        self.details_text.insert(tk.END, f"SSL Verification: {'Enabled' if verify else 'Disabled'}\n")
        self.details_text.insert(tk.END, "Status: ")

        if is_active_server:
            self.details_text.insert(tk.END, "Connected (active)\n", "connected")
        elif is_connected:
            self.details_text.insert(tk.END, "Idle\n", "connected")
        else:
            self.details_text.insert(tk.END, "Disconnected\n", "disconnected")

        if is_connected:
            self.details_text.insert(tk.END, f"User: {user}\n")
            self.details_text.insert(tk.END, f"Role: {role}\n")

        self.details_text.config(state=tk.DISABLED)

        self.connect_button.config(state=tk.NORMAL if not is_connected else tk.DISABLED)
        self.disconnect_button.config(state=tk.NORMAL if is_connected else tk.DISABLED)
        self.edit_button.config(state=tk.NORMAL)
        self.remove_button.config(state=tk.NORMAL if not is_connected else tk.DISABLED)

    def _add_server(self):
        """Add a new server"""
        dialog = tk.Toplevel(self)
        dialog.title("Add Server")
        dialog.geometry("500x460")
        dialog.minsize(500, 460)
        dialog.transient(self)
        dialog.grab_set()

        if hasattr(self.shell, "gui_app") and hasattr(self.shell.gui_app, "theme_manager"):
            self.shell.gui_app.theme_manager.configure_toplevel(dialog)

        ttk.Label(dialog, text="Server Name:").grid(row=0, column=0, sticky=tk.W, padx=20, pady=8)
        name_entry = ttk.Entry(dialog, width=30)
        name_entry.grid(row=0, column=1, padx=20, pady=8)

        ttk.Label(dialog, text="Server URL:").grid(row=1, column=0, sticky=tk.W, padx=20, pady=8)
        url_entry = ttk.Entry(dialog, width=30)
        url_entry.grid(row=1, column=1, padx=20, pady=8)
        url_entry.insert(0, "https://")

        ttk.Label(dialog, text="Username:").grid(row=2, column=0, sticky=tk.W, padx=20, pady=8)
        username_entry = ttk.Entry(dialog, width=30)
        username_entry.grid(row=2, column=1, padx=20, pady=8)

        ttk.Label(dialog, text="Password:").grid(row=3, column=0, sticky=tk.W, padx=20, pady=8)
        password_entry = ttk.Entry(dialog, width=30, show="*")
        password_entry.grid(row=3, column=1, padx=20, pady=8)

        verify_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(dialog, text="Verify SSL certificate", variable=verify_var).grid(
            row=4, column=1, sticky=tk.W, padx=20, pady=8
        )

        ttk.Label(dialog, text="Proxy URL (optional):").grid(row=5, column=0, sticky=tk.W, padx=20, pady=8)
        proxy_entry = ttk.Entry(dialog, width=30)
        proxy_entry.grid(row=5, column=1, padx=20, pady=8)

        tip_label = ttk.Label(
            dialog,
            text="💡 Username and password can be left blank.\nYou'll be prompted to login after connecting.",
            font=("TkDefaultFont", 8),
            foreground="gray",
            justify=tk.LEFT,
        )
        tip_label.grid(row=6, column=0, columnspan=2, padx=20, pady=(2, 8), sticky=tk.W)

        def save_server():
            name = name_entry.get().strip()
            url = url_entry.get().strip()
            username = username_entry.get().strip()
            password = password_entry.get()
            proxy = proxy_entry.get().strip()

            if not name or not url:
                messagebox.showerror("Error", "Name and URL are required")
                return

            user = username if username else ""
            pwd = password if password else ""

            success, message, version_info = self.shell.server_commands.add_server_programmatic(
                name=name,
                url=url,
                username=user,
                password=pwd,
                verify=verify_var.get(),
                proxy=proxy,
                test_connection=True,
            )

            if not success:
                if "Could not connect" in message or "returned status code" in message:
                    result = messagebox.askyesno(
                        "Connection Failed",
                        f"{message}\n\n"
                        f"Add server anyway?\n\n"
                        f"You can try connecting later with different credentials.",
                        icon="warning",
                    )
                    if result:
                        success, message, version_info = self.shell.server_commands.add_server_programmatic(
                            name=name,
                            url=url,
                            username=user,
                            password=pwd,
                            verify=verify_var.get(),
                            proxy=proxy,
                            test_connection=False,
                        )
                        if not success:
                            messagebox.showerror("Error", message)
                            return
                    else:
                        return
                else:
                    messagebox.showerror("Error", message)
                    return

            self._clear_status()
            dialog.destroy()
            self._refresh_server_list()
            self.update_idletasks()

            if version_info and version_info != "unknown":
                messagebox.showinfo("Success", f"Server '{name}' added successfully\n\nQUADS version: {version_info}")
            else:
                messagebox.showinfo(
                    "Server Added",
                    f"Server '{name}' added to configuration\n\nYou can now connect to this server.",
                )

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=7, column=0, columnspan=2, pady=(10, 15))

        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Add", command=save_server).pack(side=tk.LEFT, padx=5)

    def _connect_server(self):
        """Connect to selected server (one session per server, zombie cleanup on failure)"""
        if not self.selected_server:
            return

        success, error = self.shell.connect_to_server(self.selected_server)

        if not success:
            show_error_dialog(self, "Connection Failed", f"Could not connect to {self.selected_server}", error or "")

        self._refresh_server_list()
        self._update_server_details()
        if success:
            self._clear_status()
        if hasattr(self.shell, "gui_app"):
            self.shell.gui_app.update_role_visibility()

        if success and self.shell.connection and self.shell.connection.registration_mode:
            self._show_login_register_dialog()

    def _show_login_register_dialog(self):
        """Show login/register dialog when connected with blank credentials"""
        server_name = self.shell.connection.current_server

        dialog = tk.Toplevel(self)
        dialog.title(f"Authenticate - {server_name}")
        dialog.geometry("500x380")
        dialog.minsize(500, 380)
        dialog.transient(self)
        dialog.grab_set()

        try:
            if hasattr(self.shell, "gui_app") and hasattr(self.shell.gui_app, "theme_manager"):
                self.shell.gui_app.theme_manager.configure_toplevel(dialog)
        except Exception:
            pass

        ttk.Label(
            dialog,
            text=f"Connected to {server_name}",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(pady=(10, 5))
        ttk.Label(dialog, text="Please login or register to continue").pack(pady=(0, 10))

        notebook = ttk.Notebook(dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # Login tab
        login_frame = ttk.Frame(notebook, padding=15)
        notebook.add(login_frame, text="Login")

        ttk.Label(login_frame, text="Email:").grid(row=0, column=0, sticky=tk.W, pady=5)
        login_email = ttk.Entry(login_frame, width=30)
        login_email.grid(row=0, column=1, pady=5, sticky=tk.W)

        ttk.Label(login_frame, text="Password:").grid(row=1, column=0, sticky=tk.W, pady=5)
        login_pass = ttk.Entry(login_frame, width=30, show="*")
        login_pass.grid(row=1, column=1, pady=5, sticky=tk.W)

        def do_login():
            email = login_email.get().strip()
            password = login_pass.get().strip()
            if not email or not password:
                messagebox.showerror("Error", "Email and password are required", parent=dialog)
                return

            success, message, role = self.shell.user_commands.login_programmatic(email, password)
            if success:
                self.shell.config.update_server_credentials(server_name, email, password)
                dialog.destroy()
                self._refresh_server_list()
                self._update_server_details()
                if hasattr(self.shell, "gui_app"):
                    self.shell.gui_app.update_role_visibility()
                messagebox.showinfo("Success", f"Logged in as {email}")
            else:
                messagebox.showerror("Login Failed", message, parent=dialog)

        ttk.Button(login_frame, text="Login", command=do_login).grid(row=2, column=1, pady=15, sticky=tk.W)
        login_email.focus()

        # Register tab
        reg_frame = ttk.Frame(notebook, padding=15)
        notebook.add(reg_frame, text="Register")

        ttk.Label(reg_frame, text="Email:").grid(row=0, column=0, sticky=tk.W, pady=5)
        reg_email = ttk.Entry(reg_frame, width=30)
        reg_email.grid(row=0, column=1, pady=5, sticky=tk.W)

        ttk.Label(reg_frame, text="Password:").grid(row=1, column=0, sticky=tk.W, pady=5)
        reg_pass = ttk.Entry(reg_frame, width=30, show="*")
        reg_pass.grid(row=1, column=1, pady=5, sticky=tk.W)

        ttk.Label(reg_frame, text="Confirm:").grid(row=2, column=0, sticky=tk.W, pady=5)
        reg_confirm = ttk.Entry(reg_frame, width=30, show="*")
        reg_confirm.grid(row=2, column=1, pady=5, sticky=tk.W)

        ttk.Label(
            reg_frame, text="Admin accounts must be created server-side", font=("TkDefaultFont", 8), foreground="gray"
        ).grid(row=3, column=0, columnspan=2, pady=(5, 0))

        def do_register():
            email = reg_email.get().strip()
            password = reg_pass.get().strip()
            confirm = reg_confirm.get().strip()

            if not email or not password:
                messagebox.showerror("Error", "Email and password are required", parent=dialog)
                return
            if "@" not in email or "." not in email:
                messagebox.showerror("Error", "Please enter a valid email address", parent=dialog)
                return
            if len(password) < 6:
                messagebox.showerror("Error", "Password must be at least 6 characters", parent=dialog)
                return
            if password != confirm:
                messagebox.showerror("Error", "Passwords do not match", parent=dialog)
                return

            success, message, role = self.shell.user_commands.register_programmatic(email, password)
            if success:
                self.shell.config.update_server_credentials(server_name, email, password)
                dialog.destroy()
                self._refresh_server_list()
                self._update_server_details()
                if hasattr(self.shell, "gui_app"):
                    self.shell.gui_app.update_role_visibility()
                messagebox.showinfo("Success", f"Registered and logged in as {email}")
            else:
                messagebox.showerror("Registration Failed", message, parent=dialog)

        ttk.Button(reg_frame, text="Register", command=do_register).grid(row=4, column=1, pady=10, sticky=tk.W)

    def _disconnect_server(self):
        """Disconnect the session connected to the selected server"""
        if not self.selected_server or not self.shell.session_manager:
            return

        # Find the session connected to the selected server
        target_session = None
        for session in self.shell.session_manager.sessions.values():
            if session.connection and session.connection.current_server == self.selected_server:
                target_session = session
                break

        if not target_session:
            messagebox.showwarning("Not Connected", f"No active connection to '{self.selected_server}'")
            return

        try:
            server = target_session.connection.current_server
            target_session.connection.disconnect()
            self.shell.poutput(f"Disconnected from {server}")
            self._refresh_server_list()
            self._update_server_details()
            self._clear_status()
            if hasattr(self.shell, "gui_app"):
                self.shell.gui_app.update_role_visibility()
        except Exception as e:
            import traceback

            details = traceback.format_exc()
            show_error_dialog(self, "Disconnect Failed", str(e), details)

    def _edit_server(self):
        """Edit selected server"""
        if not self.selected_server or not self.shell.config:
            return

        try:
            server_config = self.shell.config.get_server(self.selected_server)
        except Exception:
            messagebox.showerror("Error", f"Server '{self.selected_server}' not found in configuration")
            return

        dialog = tk.Toplevel(self)
        dialog.title(f"Edit Server: {self.selected_server}")
        dialog.geometry("500x410")
        dialog.minsize(500, 410)
        dialog.transient(self)
        dialog.grab_set()

        if hasattr(self.shell, "gui_app") and hasattr(self.shell.gui_app, "theme_manager"):
            self.shell.gui_app.theme_manager.configure_toplevel(dialog)

        ttk.Label(dialog, text="Server Name:").grid(row=0, column=0, sticky=tk.W, padx=20, pady=8)
        ttk.Label(dialog, text=self.selected_server, font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=1, padx=20, pady=8, sticky=tk.W
        )

        ttk.Label(dialog, text="Server URL:").grid(row=1, column=0, sticky=tk.W, padx=20, pady=8)
        url_entry = ttk.Entry(dialog, width=30)
        url_entry.grid(row=1, column=1, padx=20, pady=8)
        url_entry.insert(0, server_config.get("url", ""))

        ttk.Label(dialog, text="Username:").grid(row=2, column=0, sticky=tk.W, padx=20, pady=8)
        username_entry = ttk.Entry(dialog, width=30)
        username_entry.grid(row=2, column=1, padx=20, pady=8)
        username_entry.insert(0, server_config.get("username", ""))

        ttk.Label(dialog, text="Password:").grid(row=3, column=0, sticky=tk.W, padx=20, pady=8)
        password_entry = ttk.Entry(dialog, width=30, show="*")
        password_entry.grid(row=3, column=1, padx=20, pady=8)
        password_entry.insert(0, server_config.get("password", ""))

        verify_var = tk.BooleanVar(value=server_config.get("verify", True))
        ttk.Checkbutton(dialog, text="Verify SSL certificate", variable=verify_var).grid(
            row=4, column=1, sticky=tk.W, padx=20, pady=8
        )

        ttk.Label(dialog, text="Proxy URL (optional):").grid(row=5, column=0, sticky=tk.W, padx=20, pady=8)
        proxy_entry = ttk.Entry(dialog, width=30)
        proxy_entry.grid(row=5, column=1, padx=20, pady=8)
        proxy_entry.insert(0, server_config.get("proxy", ""))

        server_name = self.selected_server

        def on_save():
            new_url = url_entry.get().strip()
            if not new_url:
                messagebox.showerror("Error", "URL is required", parent=dialog)
                return

            old_url = server_config.get("url", "")
            old_proxy = server_config.get("proxy", "")
            proxy = proxy_entry.get().strip()

            success, message = self.shell.server_commands.edit_server_programmatic(
                name=server_name,
                url=new_url,
                username=username_entry.get().strip(),
                password=password_entry.get(),
                verify=verify_var.get(),
                proxy=proxy,
            )

            if not success:
                messagebox.showerror("Error", message, parent=dialog)
                return

            is_connected = False
            if self.shell.session_manager:
                for session in self.shell.session_manager.sessions.values():
                    if session.connection and session.connection.current_server == server_name:
                        is_connected = True
                        break

            dialog.destroy()

            if (old_url != new_url or old_proxy != proxy) and is_connected:
                if messagebox.askyesno(
                    "Reconnect?",
                    f"Server settings changed.\n\nReconnect to '{server_name}' with the new settings?",
                ):
                    try:
                        # Disconnect the specific session for this server
                        for s in self.shell.session_manager.sessions.values():
                            if s.connection and s.connection.current_server == server_name:
                                s.connection.disconnect()
                                break
                        # Reconnect using centralized method
                        success, error = self.shell.connect_to_server(server_name)
                        if not success:
                            messagebox.showwarning("Reconnect Failed", f"Could not reconnect: {error}")
                    except Exception as e:
                        messagebox.showwarning("Reconnect Failed", f"Could not reconnect: {e}")

            self._refresh_server_list()
            self._update_server_details()
            self._clear_status()
            messagebox.showinfo("Success", message)

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=6, column=0, columnspan=2, pady=(10, 15))

        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Save", command=on_save).pack(side=tk.LEFT, padx=5)

    def _remove_server(self):
        """Remove selected server"""
        if not self.selected_server:
            return

        if messagebox.askyesno(
            "Confirm",
            f"Are you sure you want to remove server '{self.selected_server}'?",
        ):
            success, message = self.shell.server_commands.rm_server_programmatic(self.selected_server)
            if success:
                self._refresh_server_list()
                self.selected_server = None
                self._clear_status()
                messagebox.showinfo("Success", message)
            else:
                messagebox.showerror("Error", message)

    def _switch_session(self):
        """Switch to selected session (matches TUI: does not auto-reconnect)"""
        selection = self.sessions_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a session to switch to")
            return

        item = selection[0]
        values = self.sessions_tree.item(item, "values")
        session_id_str = values[0].replace(" (*)", "").strip()

        try:
            self.shell.session_commands.cmd_session_switch(session_id_str)

            self._refresh_session_list()
            self._refresh_server_list()
            self._clear_status()
            if hasattr(self.shell, "gui_app"):
                self.shell.gui_app.update_role_visibility()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to switch session: {e}")

    def _close_session(self):
        """Close selected session"""
        selection = self.sessions_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a session to close")
            return

        item = selection[0]
        values = self.sessions_tree.item(item, "values")
        session_id_str = values[0].replace(" (*)", "").strip()

        if messagebox.askyesno("Confirm", f"Close session {session_id_str}?"):
            try:
                self.shell.session_commands.cmd_session_close(session_id_str)
                self._refresh_session_list()
                self._refresh_server_list()
                self._clear_status()
            except Exception as e:
                import traceback

                details = traceback.format_exc()
                show_error_dialog(self, "Close Session Failed", str(e), details)

    def refresh(self):
        """Public method to refresh the view"""
        self._refresh_server_list()

    def refresh_theme(self):
        """Update colors when theme changes"""
        self.details_text.config(
            bg=self.shell.gui_app.theme_manager.get_color("text_bg"),
            fg=self.shell.gui_app.theme_manager.get_color("text_fg"),
        )
        self.details_text.tag_config("connected", foreground=self.shell.gui_app.theme_manager.get_color("success"))
        self.details_text.tag_config("disconnected", foreground=self.shell.gui_app.theme_manager.get_color("fg"))

        # Update canvas background for theme
        style = ttk.Style()
        bg_color = style.lookup("TFrame", "background")
        if hasattr(self, "_canvas"):
            self._canvas.config(bg=bg_color)
