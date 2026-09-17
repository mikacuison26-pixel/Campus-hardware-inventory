from controllers.auth_controller import AuthController
from tkinter import ttk, messagebox
import tkinter as tk
import sys
from datetime import datetime
from pathlib import Path

# Add project root directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))


class LoginWindow:
    def __init__(self, root, on_login_success):
        self.root = root
        self.on_login_success = on_login_success
        self.auth = AuthController()

        self.root.title("System Access - Hardware Portal")
        self.root.resizable(False, False)
        self.root.configure(bg="#F7DFEA")

        # Title Header
        tk.Label(
            self.root,
            text="Campus Hardware Inventory System Access",
            font=("Segoe UI", 11, "bold"),
            bg="#F7DFEA",
            fg="#C2185B",
        ).pack(pady=(12, 6))

        # Notebook Configuration
        style = ttk.Style()
        style.theme_use('default')
        style.configure('TNotebook', background="#F7DFEA", borderwidth=0)
        style.configure(
            'TNotebook.Tab',
            padding=[8, 3],
            font=('Segoe UI', 8, 'bold'),
            background="#E0E0E0"
        )
        style.map(
            'TNotebook.Tab',
            background=[('selected', '#EC407A')],
            foreground=[('selected', 'white')]
        )

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        # Create Pages
        self.page_login = tk.Frame(self.notebook, bg="#F7DFEA")
        self.page_register = tk.Frame(self.notebook, bg="#F7DFEA")
        self.page_reset = tk.Frame(self.notebook, bg="#F7DFEA")

        # Add Tabs Side-by-Side
        self.notebook.add(self.page_login, text=" Login ")
        self.notebook.add(self.page_register, text=" Register ")
        self.notebook.add(self.page_reset, text=" Reset / Unlock ")

        # Build Page Contents
        self.build_login_page()
        self.build_register_page()
        self.build_reset_page()

        # Dynamic Window Geometry Event
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

        # Initial window size
        self.root.geometry("400x290")

    def on_tab_change(self, event):
        selected_tab = self.notebook.index(self.notebook.select())
        if selected_tab == 0:
            # Login Tab
            self.root.geometry("400x290")
        elif selected_tab == 1:
            # Register Tab
            self.root.geometry("400x350")
        else:
            # Reset/Unlock Tab
            self.root.geometry("400x390")

    # --- TAB 1: LOGIN ---
    def build_login_page(self):
        tk.Label(
            self.page_login, text="Username or Email:", font=("Segoe UI", 9), bg="#F7DFEA"
        ).pack(anchor="w", padx=20, pady=(10, 2))
        self.entry_login_user = tk.Entry(self.page_login, width=32)
        self.entry_login_user.pack(padx=20, pady=(0, 6))

        tk.Label(
            self.page_login, text="Password:", font=("Segoe UI", 9), bg="#F7DFEA"
        ).pack(anchor="w", padx=20, pady=(0, 2))
        self.entry_login_pass = tk.Entry(self.page_login, show="*", width=32)
        self.entry_login_pass.pack(padx=20, pady=(0, 2))

        self.login_show_var = tk.BooleanVar(value=False)
        self.chk_login_show = tk.Checkbutton(
            self.page_login,
            text="Show Password",
            variable=self.login_show_var,
            command=self.toggle_login_password,
            bg="#F7DFEA",
            activebackground="#F7DFEA",
            font=("Segoe UI", 8)
        )
        self.chk_login_show.pack(anchor="w", padx=18, pady=(0, 8))

        tk.Button(
            self.page_login,
            text="Login",
            command=self.handle_login,
            bg="#4CAF50",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            width=16,
        ).pack(pady=4)

    def toggle_login_password(self):
        if self.login_show_var.get():
            self.entry_login_pass.config(show="")
        else:
            self.entry_login_pass.config(show="*")

    # --- TAB 2: REGISTER ---
    def build_register_page(self):
        tk.Label(
            self.page_register, text="Username:", font=("Segoe UI", 9), bg="#F7DFEA"
        ).pack(anchor="w", padx=20, pady=(6, 2))
        self.entry_reg_user = tk.Entry(self.page_register, width=32)
        self.entry_reg_user.pack(padx=20, pady=(0, 4))

        tk.Label(
            self.page_register, text="Email:", font=("Segoe UI", 9), bg="#F7DFEA"
        ).pack(anchor="w", padx=20, pady=(0, 2))
        self.entry_reg_email = tk.Entry(self.page_register, width=32)
        self.entry_reg_email.pack(padx=20, pady=(0, 4))

        tk.Label(
            self.page_register, text="Password:", font=("Segoe UI", 9), bg="#F7DFEA"
        ).pack(anchor="w", padx=20, pady=(0, 2))
        self.entry_reg_pass = tk.Entry(self.page_register, show="*", width=32)
        self.entry_reg_pass.pack(padx=20, pady=(0, 4))

        tk.Label(
            self.page_register, text="Role:", font=("Segoe UI", 9), bg="#F7DFEA"
        ).pack(anchor="w", padx=20, pady=(0, 2))
        self.combo_reg_role = ttk.Combobox(
            self.page_register, values=["USER", "ADMIN"], state="readonly", width=29
        )
        self.combo_reg_role.set("USER")
        self.combo_reg_role.pack(padx=20, pady=(0, 8))

        tk.Button(
            self.page_register,
            text="Create Account",
            command=self.handle_register,
            bg="#2196F3",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            width=16,
        ).pack(pady=4)

    # --- TAB 3: RESET / UNLOCK PASSWORD ---
    def build_reset_page(self):
        tk.Label(
            self.page_reset, text="Account Username:", font=("Segoe UI", 9), bg="#F7DFEA"
        ).pack(anchor="w", padx=20, pady=(6, 2))
        self.entry_reset_user = tk.Entry(self.page_reset, width=32)
        self.entry_reset_user.pack(padx=20, pady=(0, 4))

        tk.Label(
            self.page_reset, text="Registered Email:", font=("Segoe UI", 9), bg="#F7DFEA"
        ).pack(anchor="w", padx=20, pady=(0, 2))
        self.entry_reset_email = tk.Entry(self.page_reset, width=32)
        self.entry_reset_email.pack(padx=20, pady=(0, 4))

        tk.Label(
            self.page_reset, text="Desired New Password:", font=("Segoe UI", 9), bg="#F7DFEA"
        ).pack(anchor="w", padx=20, pady=(0, 2))
        self.entry_reset_pass = tk.Entry(self.page_reset, show="*", width=32)
        self.entry_reset_pass.pack(padx=20, pady=(0, 4))

        tk.Label(
            self.page_reset, text="Confirm New Password:", font=("Segoe UI", 9), bg="#F7DFEA"
        ).pack(anchor="w", padx=20, pady=(0, 2))
        self.entry_reset_confirm = tk.Entry(
            self.page_reset, show="*", width=32)
        self.entry_reset_confirm.pack(padx=20, pady=(0, 8))

        tk.Button(
            self.page_reset,
            text="Submit Reset/Unlock Request",
            command=self.handle_reset_request,
            bg="#FF9800",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            width=24,
        ).pack(pady=4)

    # --- EVENT HANDLERS ---
    def handle_login(self):
        u = self.entry_login_user.get().strip()
        p = self.entry_login_pass.get().strip()

        success, msg, user_data = self.auth.login_user(u, p)
        if success:
            messagebox.showinfo("Success", msg)
            self.on_login_success(user_data)
        else:
            messagebox.showerror("Authentication Error", msg)

    def handle_register(self):
        u = self.entry_reg_user.get().strip()
        e = self.entry_reg_email.get().strip()
        p = self.entry_reg_pass.get().strip()
        r = self.combo_reg_role.get()

        success, msg = self.auth.register_user(u, e, p, r)
        if success:
            messagebox.showinfo("Success", msg)
            self.notebook.select(self.page_login)
        else:
            messagebox.showwarning("Registration Alert", msg)

    def handle_reset_request(self):
        username = self.entry_reset_user.get().strip()
        email = self.entry_reset_email.get().strip()
        new_pass = self.entry_reset_pass.get().strip()
        confirm_pass = self.entry_reset_confirm.get().strip()

        if not username or not email or not new_pass or not confirm_pass:
            messagebox.showwarning(
                "Input Warning", "Please fill in all fields.")
            return

        if new_pass != confirm_pass:
            messagebox.showerror(
                "Password Mismatch", "Desired new password and confirmation password do not match.")
            return

        # Pass 'username' as the first argument along with email and new_pass
        success, msg = self.auth.request_password_reset(
            username, email, new_pass)
        if success:
            timestamp = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
            success_msg = f"Reset request submitted at \"{timestamp}\". Once an Admin approves it, your account will unlock."

            messagebox.showinfo("Request Submitted", success_msg)
            self.entry_reset_user.delete(0, tk.END)
            self.entry_reset_email.delete(0, tk.END)
            self.entry_reset_pass.delete(0, tk.END)
            self.entry_reset_confirm.delete(0, tk.END)
            self.notebook.select(self.page_login)
        else:
            messagebox.showerror("Reset Error", msg)
