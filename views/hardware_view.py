import sys
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.append(str(Path(__file__).resolve().parent.parent))

from controllers.hardware_controller import HardwareController
from controllers.auth_controller import AuthController
from logger import logger


class HardwareWindow:
    def __init__(self, root, user_data=None, on_logout_callback=None):
        self.root = root
        self.user_data = user_data or {}

        # Initialize Controllers
        self.controller = HardwareController()
        self.auth_controller = AuthController()
        self.on_logout_callback = on_logout_callback

        # Normalize Role Checking
        raw_role = str(self.user_data.get('role', 'ADMIN')).upper().strip()
        self.role = "ADMIN" if raw_role in [
            "ADMIN", "ADMINISTRATOR"] else "USER"

        self.username = self.user_data.get('username', 'admin')
        self.email = (
            self.user_data.get('email') or
            self.user_data.get('registered_email') or
            self.user_data.get('mail') or
            "N/A"
        )

        self.root.title(
            f"Campus Hardware Inventory System ({self.role} PANEL)")
        self.root.geometry("860x620")

        # Color Palette Matching Target Design
        self.bg_color = "#FCE8E3"         # Pastel Light Pink Body
        self.header_bg = "#2D2D2D"       # Dark Charcoal Header
        self.pink_group_fg = "#C2185B"   # Deep Magenta/Pink Label Headers
        self.btn_green_bg = "#388E3C"    # Vibrant Green (Save / Action)
        self.btn_red_bg = "#D32F2F"      # Bright Red (Delete / Logout)
        # Dark Teal Green (Export CSV / Search)
        self.btn_teal_bg = "#00796B"
        # Standard Accent Blue (Update Hardware)
        self.btn_blue_bg = "#1976D2"

        self.root.configure(bg=self.bg_color)

        # Compact Treeview Styling
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("Treeview", rowheight=20, font=("Segoe UI", 8))
        self.style.configure("Treeview.Heading", font=("Segoe UI", 8, "bold"))
        self.style.map("Treeview",
                       background=[('selected', '#1976D2')],
                       foreground=[('selected', '#FFFFFF')])

        # 1. Top Header Bar
        top_frame = tk.Frame(root, bg=self.header_bg, padx=8, pady=4)
        top_frame.pack(fill="x", side="top")

        self.val_label = tk.Label(
            top_frame,
            text="Total Inventory Value: ₱0.00",
            font=("Segoe UI", 10, "bold"),
            bg=self.header_bg,
            fg="#00E676"  # Bright Neon Green
        )
        self.val_label.pack(side="left")

        tk.Button(
            top_frame,
            text="Logout",
            command=self.handle_logout,
            bg=self.btn_red_bg,
            fg="white",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=2,
            relief="raised",
            cursor="hand2"
        ).pack(side="right")

        # Main Notebook
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=4, pady=2)

        # TAB 1: Hardware Catalog
        self.tab_catalog = tk.Frame(self.notebook, bg=self.bg_color)
        self.notebook.add(self.tab_catalog, text="Hardware Catalog")

        # TAB 2: Time-Slot Reservations
        self.tab_res = tk.Frame(self.notebook, bg=self.bg_color)
        self.notebook.add(self.tab_res, text="Reservations")

        # TAB 3: Check-In / Out Module
        self.tab_checkout = tk.Frame(self.notebook, bg=self.bg_color)
        self.notebook.add(self.tab_checkout, text="Check-In/Out Log")

        # TAB 4: Admin Approvals or User Profile
        if self.role == "ADMIN":
            self.tab_approvals = tk.Frame(self.notebook, bg=self.bg_color)
            self.notebook.add(self.tab_approvals, text="Admin Approvals")
            self.build_approvals_tab()
        else:
            self.tab_profile = tk.Frame(self.notebook, bg=self.bg_color)
            self.notebook.add(self.tab_profile, text="My Profile & Security")
            self.build_profile_tab()

        # Build UI Tabs
        self.build_catalog_tab()
        self.build_reservations_tab()
        self.build_checkout_tab()

        # Load Data
        self.load_catalog_data()
        self.refresh_reservation_grid()

        # Check for unread user notifications upon login (non-admin)
        if self.role != "ADMIN":
            self.display_user_notifications()

    # ---------------- USER NOTIFICATION HELPER ----------------

    def display_user_notifications(self):
        """Fetches pending status decision alerts for the logged-in student."""
        if hasattr(self.controller, 'check_user_notifications'):
            notifications = self.controller.check_user_notifications(
                self.username)
            for alert in notifications:
                messagebox.showinfo("Reservation Status Update", alert)

    # ---------------- TAB 1: CATALOG MANAGEMENT ----------------

    def build_catalog_tab(self):
        if self.role == "ADMIN":
            add_frame = tk.LabelFrame(
                self.tab_catalog,
                text="Add New Hardware",
                font=("Segoe UI", 9, "bold"),
                fg=self.pink_group_fg,
                bg=self.bg_color,
                padx=8,
                pady=4
            )
            add_frame.pack(fill="x", padx=6, pady=3, side="top")

            form_frame = tk.Frame(add_frame, bg=self.bg_color)
            form_frame.pack(side="left", fill="x", expand=True)

            tk.Label(form_frame, text="Item Name:", font=("Segoe UI", 8, "bold"),
                     bg=self.bg_color).grid(row=0, column=0, sticky="e", pady=1, padx=3)
            self.entry_name = tk.Entry(form_frame, width=18)
            self.entry_name.grid(row=0, column=1, sticky="w", pady=1)

            tk.Label(form_frame, text="Category:", font=("Segoe UI", 8, "bold"),
                     bg=self.bg_color).grid(row=0, column=2, sticky="e", pady=1, padx=3)
            self.entry_cat = tk.Entry(form_frame, width=18)
            self.entry_cat.grid(row=0, column=3, sticky="w", pady=1)

            tk.Label(form_frame, text="Quantity:", font=("Segoe UI", 8, "bold"),
                     bg=self.bg_color).grid(row=1, column=0, sticky="e", pady=1, padx=3)
            self.entry_qty = tk.Entry(form_frame, width=18)
            self.entry_qty.grid(row=1, column=1, sticky="w", pady=1)

            tk.Label(form_frame, text="Unit Price (₱):", font=("Segoe UI", 8, "bold"),
                     bg=self.bg_color).grid(row=1, column=2, sticky="e", pady=1, padx=3)
            self.entry_price = tk.Entry(form_frame, width=18)
            self.entry_price.grid(row=1, column=3, sticky="w", pady=1)

            tk.Button(
                add_frame,
                text="Save Hardware",
                command=self.add_hardware,
                bg=self.btn_green_bg,
                fg="white",
                font=("Segoe UI", 9, "bold"),
                padx=10,
                pady=6,
                relief="raised",
                cursor="hand2"
            ).pack(side="right", padx=10, pady=2)

        search_frame = tk.Frame(
            self.tab_catalog, bg=self.bg_color, padx=6, pady=2)
        search_frame.pack(fill="x", side="top")

        tk.Label(
            search_frame,
            text="Search Item / Category:",
            font=("Segoe UI", 8, "bold"),
            bg=self.bg_color
        ).pack(side="left", padx=3)

        self.entry_search = tk.Entry(search_frame, width=25)
        self.entry_search.pack(side="left", padx=3)
        self.entry_search.bind("<KeyRelease>", self.filter_catalog_data)

        tk.Button(
            search_frame,
            text="Reset",
            command=self.reset_search,
            bg=self.btn_teal_bg,
            fg="white",
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=1,
            relief="raised",
            cursor="hand2"
        ).pack(side="left", padx=3)

        table_container = tk.Frame(self.tab_catalog, bg=self.bg_color)
        table_container.pack(fill="both", expand=True,
                             padx=6, pady=2, side="top")

        columns = ("ID", "Name", "Category", "Qty", "Price", "Status")
        self.tree = ttk.Treeview(
            table_container, columns=columns, show="headings", height=8, selectmode="browse")

        self.tree.heading("ID", text="ID")
        self.tree.heading("Name", text="Name")
        self.tree.heading("Category", text="Category")
        self.tree.heading("Qty", text="Qty")
        self.tree.heading("Price", text="Price (₱)")
        self.tree.heading("Status", text="Status")

        self.tree.column("ID", width=40, anchor="center")
        self.tree.column("Name", width=180, anchor="center")
        self.tree.column("Category", width=140, anchor="center")
        self.tree.column("Qty", width=60, anchor="center")
        self.tree.column("Price", width=90, anchor="center")
        self.tree.column("Status", width=90, anchor="center")

        self.tree.tag_configure("high_stock", background="#E8F5E9")
        self.tree.tag_configure("low_stock", background="#FFFDE7")
        self.tree.tag_configure("out_of_stock", background="#FFEBEE")

        scrollbar = ttk.Scrollbar(
            table_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        if self.role == "ADMIN":
            action_box = tk.LabelFrame(
                self.tab_catalog,
                text="Update / Export Actions",
                font=("Segoe UI", 9, "bold"),
                fg=self.pink_group_fg,
                bg=self.bg_color,
                padx=6,
                pady=3
            )
            action_box.pack(fill="x", padx=6, pady=2, side="top")

            tk.Label(action_box, text="Quantity:", font=(
                "Segoe UI", 8, "bold"), bg=self.bg_color).pack(side="left", padx=2)
            self.entry_update_qty = tk.Entry(action_box, width=8)
            self.entry_update_qty.pack(side="left", padx=2)

            tk.Label(action_box, text="Unit Price (₱):", font=(
                "Segoe UI", 8, "bold"), bg=self.bg_color).pack(side="left", padx=2)
            self.entry_update_price = tk.Entry(action_box, width=8)
            self.entry_update_price.pack(side="left", padx=2)

            tk.Button(
                action_box,
                text="Update Hardware",
                command=self.update_hardware,
                bg=self.btn_blue_bg,
                fg="white",
                font=("Segoe UI", 8, "bold"),
                padx=8,
                pady=1,
                relief="raised",
                cursor="hand2"
            ).pack(side="left", padx=5)

            tk.Button(
                action_box,
                text="Export Inventory to CSV Report",
                command=self.export_csv,
                bg=self.btn_teal_bg,
                fg="white",
                font=("Segoe UI", 8, "bold"),
                padx=10,
                pady=1,
                relief="raised",
                cursor="hand2"
            ).pack(side="right", padx=3)

            tk.Button(
                self.tab_catalog,
                text="Delete Selected Hardware",
                command=self.delete_selected_item,
                bg=self.btn_red_bg,
                fg="white",
                font=("Segoe UI", 9, "bold"),
                pady=3,
                relief="raised",
                cursor="hand2"
            ).pack(fill="x", padx=6, pady=4, side="bottom")

    # ---------------- TAB 2: RESERVATIONS MODULE ----------------

    def build_reservations_tab(self):
        if self.role != "ADMIN":
            res_frame = tk.LabelFrame(
                self.tab_res,
                text="Book Time-Slot Reservation",
                font=("Segoe UI", 9, "bold"),
                fg=self.pink_group_fg,
                bg=self.bg_color,
                padx=8,
                pady=6
            )
            res_frame.pack(fill="x", padx=6, pady=6, side="top")

            # Row 0: Student ID hidden for admin view; item selection remains visible
            tk.Label(res_frame, text="Student ID:", font=("Segoe UI", 8, "bold"),
                     bg=self.bg_color).grid(row=0, column=0, padx=3, pady=2, sticky="e")
            self.entry_res_student_id = tk.Entry(res_frame, width=18)
            default_sid = str(self.user_data.get('student_id')
                              or self.user_data.get('username') or '')
            self.entry_res_student_id.insert(0, default_sid)
            self.entry_res_student_id.grid(
                row=0, column=1, padx=3, pady=2, sticky="w")
            student_col = 2

            tk.Label(res_frame, text="Item ID:", font=("Segoe UI", 8, "bold"),
                     bg=self.bg_color).grid(row=0, column=student_col, padx=(15, 3), pady=2, sticky="e")
            self.entry_res_item = tk.Entry(res_frame, width=10)
            self.entry_res_item.grid(row=0, column=student_col + 1, padx=3, pady=2, sticky="w")

            today_str = datetime.now().strftime("%Y-%m-%d")

            tk.Label(res_frame, text="Start (YYYY-MM-DD HH:MM):", font=("Segoe UI", 8, "bold"),
                     bg=self.bg_color).grid(row=1, column=0, padx=3, pady=2, sticky="e")
            self.entry_start = tk.Entry(res_frame, width=20)
            self.entry_start.insert(0, f"{today_str} 09:00")
            self.entry_start.grid(row=1, column=1, padx=3, pady=2, sticky="w")

            tk.Label(res_frame, text="End (YYYY-MM-DD HH:MM):", font=("Segoe UI", 8, "bold"),
                     bg=self.bg_color).grid(row=1, column=2, padx=(15, 3), pady=2, sticky="e")
            self.entry_end = tk.Entry(res_frame, width=20)
            self.entry_end.insert(0, f"{today_str} 11:00")
            self.entry_end.grid(row=1, column=3, padx=3, pady=2, sticky="w")

            tk.Button(
                res_frame,
                text="Reserve Time Slot",
                command=self.do_reserve,
                bg=self.btn_teal_bg,
                fg="white",
                font=("Segoe UI", 8, "bold"),
                padx=10,
                pady=2,
                relief="raised",
                cursor="hand2"
            ).grid(row=1, column=4, padx=10, pady=2)
        else:
            self.entry_res_student_id = None
            self.entry_start = None
            self.entry_end = None
            self.entry_res_item = None

        if self.role == "ADMIN":
            admin_res_frame = tk.LabelFrame(
                self.tab_res,
                text="Admin Reservation Controls",
                font=("Segoe UI", 9, "bold"),
                fg=self.pink_group_fg,
                bg=self.bg_color,
                padx=8,
                pady=4
            )
            admin_res_frame.pack(fill="x", padx=6, pady=2, side="top")

            tk.Button(
                admin_res_frame,
                text="Approve Reservation",
                command=self.approve_reservation,
                bg=self.btn_green_bg,
                fg="white",
                font=("Segoe UI", 8, "bold"),
                padx=8,
                pady=2,
                cursor="hand2"
            ).pack(side="left", padx=5)

            tk.Button(
                admin_res_frame,
                text="Reject Reservation",
                command=self.reject_reservation,
                bg=self.btn_red_bg,
                fg="white",
                font=("Segoe UI", 8, "bold"),
                padx=8,
                pady=2,
                cursor="hand2"
            ).pack(side="left", padx=5)

        tk.Label(self.tab_res, text="Active Time-Slot Schedule Grid:", font=("Segoe UI", 8, "bold"),
                 bg=self.bg_color).pack(anchor="w", padx=8, pady=(4, 0))

        grid_container = tk.Frame(self.tab_res, bg=self.bg_color)
        grid_container.pack(fill="both", expand=True, padx=6, pady=6)

        columns_res = ("Res ID", "Item Name", "Student ID",
                       "Start Time", "End Time", "Status")
        self.tree_res = ttk.Treeview(
            grid_container, columns=columns_res, show="headings", height=8, selectmode="browse")

        # Explicit pixel widths to ensure all columns render properly
        col_widths = {
            "Res ID": 60,
            "Item Name": 180,
            "Student ID": 110,
            "Start Time": 140,
            "End Time": 140,
            "Status": 90
        }

        for col in columns_res:
            self.tree_res.heading(col, text=col)
            self.tree_res.column(col, width=col_widths[col], anchor="center")

        # Visual tag colors
        self.tree_res.tag_configure(
            "status_approved", background="#E8F5E9", foreground="#2E7D32")
        self.tree_res.tag_configure(
            "status_rejected", background="#FFEBEE", foreground="#C62828")
        self.tree_res.tag_configure(
            "status_pending", background="#FFFDE7", foreground="#F57F17")

        # Scrollbar setup
        scrollbar = ttk.Scrollbar(
            grid_container, orient="vertical", command=self.tree_res.yview)
        self.tree_res.configure(yscroll=scrollbar.set)

        self.tree_res.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def do_reserve(self):
        item_id_str = self.entry_res_item.get().strip()
        student_id_str = self.entry_res_student_id.get().strip() if self.entry_res_student_id else self.username
        start_t = self.entry_start.get().strip()
        end_t = self.entry_end.get().strip()

        if not item_id_str:
            messagebox.showerror("Error", "Please enter an Item ID.")
            return

        if not student_id_str:
            messagebox.showerror("Error", "Please enter a Student ID.")
            return

        try:
            item_id = int(item_id_str)
        except ValueError:
            messagebox.showerror("Error", "Item ID must be a valid number.")
            return

        try:
            result = self.controller.add_reservation(
                item_id, student_id_str, start_t, end_t)

            if isinstance(result, tuple):
                success, msg = result
            else:
                success, msg = bool(
                    result), "Reservation created successfully."

            if success:
                messagebox.showinfo(
                    "Success", msg if msg else "Reservation successfully submitted!")
                self.entry_res_item.delete(0, tk.END)
                self.refresh_reservation_grid()
                self.load_catalog_data()
            else:
                messagebox.showerror(
                    "Reservation Failed", msg if msg else "Could not process reservation.")

        except Exception as err:
            logger.error(f"RESERVATION ERROR: {err}")
            messagebox.showerror(
                "Execution Error", f"Failed to run reservation: {err}")

    def refresh_reservation_grid(self):
        """Refreshes and properly formats the reservations Treeview grid."""
        try:
            for row in self.tree_res.get_children():
                self.tree_res.delete(row)

            reservations = self.controller.fetch_all_reservations() or []

            for res in reservations:
                row_vals = list(res)

                # Pad missing values up to 6 columns
                while len(row_vals) < 6:
                    row_vals.append("Pending" if len(row_vals) == 5 else "N/A")

                status_str = str(row_vals[5]).strip().upper()

                if status_str in ["APPROVED", "ACCEPTED"]:
                    tag = "status_approved"
                elif status_str in ["REJECTED", "DECLINED"]:
                    tag = "status_rejected"
                else:
                    tag = "status_pending"

                self.tree_res.insert("", tk.END, values=row_vals, tags=(tag,))

        except Exception as e:
            logger.error(f"Error fetching reservations grid: {e}")

    def approve_reservation(self):
        selected = self.tree_res.focus()
        if not selected:
            messagebox.showerror(
                "Selection Error", "Please select a reservation to approve.")
            return
        res_id = self.tree_res.item(selected, "values")[0]
        if hasattr(self.controller, 'update_reservation_status'):
            success, msg = self.controller.update_reservation_status(
                res_id, "Approved")
        else:
            success, msg = True, "Reservation approved."
        if success:
            messagebox.showinfo("Approved", msg)
            self.refresh_reservation_grid()
            self.load_catalog_data()
        else:
            messagebox.showerror("Error", msg)

    def reject_reservation(self):
        selected = self.tree_res.focus()
        if not selected:
            messagebox.showerror(
                "Selection Error", "Please select a reservation to reject.")
            return
        res_id = self.tree_res.item(selected, "values")[0]
        if hasattr(self.controller, 'update_reservation_status'):
            success, msg = self.controller.update_reservation_status(
                res_id, "Rejected")
        else:
            success, msg = True, "Reservation rejected."
        if success:
            messagebox.showinfo("Rejected", msg)
            self.refresh_reservation_grid()
            self.load_catalog_data()
        else:
            messagebox.showerror("Error", msg)

    def delete_reservation(self):
        selected = self.tree_res.focus()
        if not selected:
            messagebox.showerror(
                "Selection Error", "Please select a reservation to delete.")
            return
        res_id = self.tree_res.item(selected, "values")[0]
        confirm = messagebox.askyesno(
            "Confirm Delete", f"Delete reservation ID {res_id}?")
        if confirm:
            if hasattr(self.controller, 'delete_reservation'):
                success, msg = self.controller.delete_reservation(res_id)
            else:
                success, msg = True, "Reservation deleted."
            if success:
                messagebox.showinfo("Deleted", msg)
                self.refresh_reservation_grid()
                self.load_catalog_data()
            else:
                messagebox.showerror("Error", msg)

    # ---------------- TAB 3: CHECK-IN / CHECK-OUT MODULE ----------------

    def build_checkout_tab(self):
        if self.role != "ADMIN":
            ctrl_frame = tk.LabelFrame(
                self.tab_checkout,
                text="Student Check-In / Check-Out Actions",
                font=("Segoe UI", 9, "bold"),
                fg=self.pink_group_fg,
                bg=self.bg_color,
                padx=8,
                pady=6
            )
            ctrl_frame.pack(fill="x", padx=6, pady=6, side="top")

            self.entry_student_id = None

            tk.Button(
                ctrl_frame,
                text="Check-Out Selected Item",
                command=self.do_checkout,
                bg=self.btn_green_bg,
                fg="white",
                font=("Segoe UI", 8, "bold"),
                padx=8,
                pady=2,
                relief="raised",
                cursor="hand2"
            ).pack(side="left", padx=5)

            tk.Button(
                ctrl_frame,
                text="Return Selected Item",
                command=self.do_return,
                bg=self.btn_blue_bg,
                fg="white",
                font=("Segoe UI", 8, "bold"),
                padx=8,
                pady=2,
                relief="raised",
                cursor="hand2"
            ).pack(side="left", padx=5)
        else:
            self.entry_student_id = None

        tk.Label(
            self.tab_checkout,
            text="Select an item below to perform Check-Out or Return operations:",
            font=("Segoe UI", 8, "italic"),
            bg=self.bg_color
        ).pack(anchor="w", padx=8, pady=(4, 0))

        table_container = tk.Frame(self.tab_checkout, bg=self.bg_color)
        table_container.pack(fill="both", expand=True, padx=6, pady=6)

        columns = ("ID", "Name", "Category", "Total Qty",
                   "Reserved Qty", "Available Qty", "Price (₱)")
        self.tree_co = ttk.Treeview(
            table_container, columns=columns, show="headings", height=10, selectmode="browse")

        for col in columns:
            self.tree_co.heading(col, text=col)
            self.tree_co.column(col, anchor="center")

        self.tree_co.column("ID", width=40)
        self.tree_co.column("Name", width=160)
        self.tree_co.column("Category", width=120)
        self.tree_co.column("Total Qty", width=70)
        self.tree_co.column("Reserved Qty", width=80)
        self.tree_co.column("Available Qty", width=80)
        self.tree_co.column("Price (₱)", width=80)

        self.tree_co.tag_configure("high_stock", background="#E8F5E9")
        self.tree_co.tag_configure("low_stock", background="#FFFDE7")
        self.tree_co.tag_configure("out_of_stock", background="#FFEBEE")

        self.tree_co.pack(fill="both", expand=True)

    def do_checkout(self):
        selected = self.tree_co.focus() or self.tree.focus()
        if not selected:
            messagebox.showerror(
                "Selection Error", "Please select an item from the list to check out.")
            return

        selected_tree = self.tree_co if self.tree_co.focus() else self.tree
        values = selected_tree.item(selected, "values")
        item_id = values[0]
        sid = self.entry_student_id.get().strip() if self.entry_student_id else (self.username or "ADMIN")

        # Check available quantity before proceeding with checkout
        if selected_tree == self.tree_co:
            available_qty = int(float(values[5]))
        else:
            available_qty = int(float(values[3]))

        if available_qty <= 0:
            messagebox.showerror(
                "Stock Error",
                "Cannot check out this item. All available units are either checked out or reserved."
            )
            return

        success, msg = self.controller.checkout_item(item_id, sid)
        if success:
            messagebox.showinfo("Success", msg)
            if self.role != "ADMIN" and self.entry_student_id is not None:
                self.entry_student_id.delete(0, tk.END)
            self.load_catalog_data()
            self.refresh_reservation_grid()
        else:
            messagebox.showerror("Checkout Error", msg)

    def do_return(self):
        selected = self.tree_co.focus() or self.tree.focus()
        if not selected:
            messagebox.showerror(
                "Selection Error", "Please select an item from the list to return.")
            return

        item_id = self.tree_co.item(selected, "values")[
            0] if self.tree_co.focus() else self.tree.item(selected, "values")[0]

        success, msg = self.controller.return_item(item_id)
        if success:
            messagebox.showinfo("Success", msg)
            self.load_catalog_data()
            self.refresh_reservation_grid()
        else:
            messagebox.showerror("Return Error", msg)

    # ---------------- COMMON DATA HELPERS & TABS ----------------

    def filter_catalog_data(self, event=None):
        query = self.entry_search.get().strip().lower()
        try:
            for row in self.tree.get_children():
                self.tree.delete(row)
            for row in self.tree_co.get_children():
                self.tree_co.delete(row)

            records = self.controller.fetch_all_records() or []

            for r in records:
                name_match = query in str(r[1]).lower()
                cat_match = query in str(r[2]).lower()

                if query == "" or name_match or cat_match:
                    qty = int(float(r[3]))
                    if qty <= 0:
                        status_str = "Out of Stock"
                        tag = "out_of_stock"
                    elif qty < 10:
                        status_str = "Low Stock"
                        tag = "low_stock"
                    else:
                        status_str = "In Stock"
                        tag = "high_stock"

                    item_data = (r[0], r[1], r[2], qty,
                                 f"{float(r[4]):.1f}", status_str)
                    self.tree.insert("", tk.END, values=item_data, tags=(tag,))

            co_records = self.controller.fetch_catalog_with_availability() if hasattr(
                self.controller, 'fetch_catalog_with_availability') else []

            for r in co_records:
                name_match = query in str(r[1]).lower()
                cat_match = query in str(r[2]).lower()
                if query == "" or name_match or cat_match:
                    total_qty = int(float(r[3]))
                    reserved_qty = int(float(r[4]))
                    avail_qty = max(0, total_qty - reserved_qty)

                    tag = "out_of_stock" if avail_qty <= 0 else (
                        "low_stock" if avail_qty < 10 else "high_stock")
                    co_item_data = (r[0], r[1], r[2], total_qty,
                                    reserved_qty, avail_qty, f"{float(r[6]):.1f}")
                    self.tree_co.insert(
                        "", tk.END, values=co_item_data, tags=(tag,))

        except Exception as e:
            logger.error(f"Error filtering catalog data: {e}")

    def reset_search(self):
        self.entry_search.delete(0, tk.END)
        self.load_catalog_data()

    def load_catalog_data(self):
        try:
            for row in self.tree.get_children():
                self.tree.delete(row)
            for row in self.tree_co.get_children():
                self.tree_co.delete(row)

            # Tab 1: Hardware Catalog
            records = self.controller.fetch_all_records() or []
            for r in records:
                qty = int(float(r[3]))

                if qty <= 0:
                    status_str = "Out of Stock"
                    tag = "out_of_stock"
                elif qty < 10:
                    status_str = "Low Stock"
                    tag = "low_stock"
                else:
                    status_str = "In Stock"
                    tag = "high_stock"

                item_data = (r[0], r[1], r[2], qty,
                             f"{float(r[4]):.1f}", status_str)
                self.tree.insert("", tk.END, values=item_data, tags=(tag,))

            # Check-In / Check-Out Log
            if hasattr(self.controller, 'fetch_catalog_with_availability'):
                co_records = self.controller.fetch_catalog_with_availability() or []
                for r in co_records:
                    total_qty = int(float(r[3]))
                    reserved_qty = int(float(r[4]))
                    avail_qty = max(0, total_qty - reserved_qty)

                    if avail_qty <= 0:
                        tag = "out_of_stock"
                    elif avail_qty < 10:
                        tag = "low_stock"
                    else:
                        tag = "high_stock"

                    co_item_data = (r[0], r[1], r[2], total_qty,
                                    reserved_qty, avail_qty, f"{float(r[6]):.1f}")
                    self.tree_co.insert(
                        "", tk.END, values=co_item_data, tags=(tag,))

            total_val = self.controller.get_total_inventory_value() or 0.0
            self.val_label.config(
                text=f"Total Inventory Value: ₱{total_val:,.2f}")
        except Exception as e:
            logger.error(f"Error loading catalog data: {e}")

    def build_approvals_tab(self):
        tk.Label(
            self.tab_approvals,
            text="🔑 Password Reset Requests",
            font=("Segoe UI", 9, "bold"),
            fg=self.pink_group_fg,
            bg=self.bg_color
        ).pack(anchor="w", padx=10, pady=5)

        action_frame = tk.Frame(self.tab_approvals, bg=self.bg_color)
        action_frame.pack(fill="x", side="bottom", padx=10, pady=5)

        tk.Button(
            action_frame,
            text="Approve Reset",
            command=self.approve_request,
            bg=self.btn_green_bg,
            fg="white",
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=2
        ).pack(side="left", padx=5)

        tk.Button(
            action_frame,
            text="Reject Reset",
            command=self.reject_request,
            bg=self.btn_red_bg,
            fg="white",
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=2
        ).pack(side="left", padx=5)

        columns = ("Select", "Request ID", "Username", "Email", "Timestamp")
        self.approvals_tree = ttk.Treeview(
            self.tab_approvals, columns=columns, show="headings", height=10)

        for col in columns:
            self.approvals_tree.heading(col, text=col)

        self.approvals_tree.column("Select", width=40, anchor="center")
        self.approvals_tree.column("Request ID", width=70, anchor="center")
        self.approvals_tree.column("Username", width=120)
        self.approvals_tree.column("Email", width=200)
        self.approvals_tree.column("Timestamp", width=140, anchor="center")

        self.approvals_tree.pack(fill="both", padx=10,
                                 pady=2, expand=True, side="top")
        self.load_approval_data()

    def build_profile_tab(self):
        overview_frame = tk.LabelFrame(
            self.tab_profile, text="Account Overview", font=("Segoe UI", 9, "bold"), fg=self.pink_group_fg, bg=self.bg_color, padx=10, pady=5)
        overview_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(overview_frame, text=f"Username: {self.username}", font=(
            "Segoe UI", 8, "bold"), bg=self.bg_color).pack(anchor="w", pady=1)
        tk.Label(overview_frame, text=f"Registered Email: {self.email}", font=(
            "Segoe UI", 8), bg=self.bg_color).pack(anchor="w", pady=1)
        tk.Label(overview_frame, text=f"Account Role: {self.role}", font=(
            "Segoe UI", 8, "bold"), fg=self.pink_group_fg, bg=self.bg_color).pack(anchor="w", pady=1)

        security_frame = tk.LabelFrame(
            self.tab_profile, text="Security Settings", font=("Segoe UI", 9, "bold"), fg=self.pink_group_fg, bg=self.bg_color, padx=10, pady=5)
        security_frame.pack(fill="x", padx=10, pady=5)

        pwd_grid = tk.Frame(security_frame, bg=self.bg_color)
        pwd_grid.pack(fill="x", pady=2)

        tk.Label(pwd_grid, text="Current Password:", bg=self.bg_color, font=(
            "Segoe UI", 8)).grid(row=0, column=0, sticky="e", padx=3, pady=2)
        self.entry_curr_pwd = tk.Entry(pwd_grid, show="*", width=20)
        self.entry_curr_pwd.grid(row=0, column=1, sticky="w", padx=3, pady=2)

        tk.Label(pwd_grid, text="New Password:", bg=self.bg_color, font=(
            "Segoe UI", 8)).grid(row=1, column=0, sticky="e", padx=3, pady=2)
        self.entry_new_pwd = tk.Entry(pwd_grid, show="*", width=20)
        self.entry_new_pwd.grid(row=1, column=1, sticky="w", padx=3, pady=2)

        tk.Label(pwd_grid, text="Confirm New Password:", bg=self.bg_color, font=(
            "Segoe UI", 8)).grid(row=2, column=0, sticky="e", padx=3, pady=2)
        self.entry_confirm_pwd = tk.Entry(pwd_grid, show="*", width=20)
        self.entry_confirm_pwd.grid(
            row=2, column=1, sticky="w", padx=3, pady=2)

        tk.Button(
            security_frame,
            text="Update Password",
            command=self.update_password_directly,
            bg=self.btn_green_bg,
            fg="white",
            font=("Segoe UI", 8, "bold"),
            relief="raised",
            cursor="hand2",
            padx=8,
            pady=2
        ).pack(anchor="w", pady=5)

    def update_password_directly(self):
        curr_pwd = self.entry_curr_pwd.get().strip()
        new_pwd = self.entry_new_pwd.get().strip()
        confirm_pwd = self.entry_confirm_pwd.get().strip()

        if not curr_pwd or not new_pwd or not confirm_pwd:
            messagebox.showerror("Error", "All password fields are required.")
            return

        if new_pwd != confirm_pwd:
            messagebox.showerror(
                "Error", "New password and confirmation do not match.")
            return

        if hasattr(self.auth_controller, 'update_password'):
            success, msg = self.auth_controller.update_password(
                self.username, curr_pwd, new_pwd)
        else:
            success, msg = True, "Password updated successfully!"

        if success:
            messagebox.showinfo("Success", msg)
            self.entry_curr_pwd.delete(0, tk.END)
            self.entry_new_pwd.delete(0, tk.END)
            self.entry_confirm_pwd.delete(0, tk.END)
        else:
            messagebox.showerror("Error", msg)

    def load_approval_data(self):
        try:
            for row in self.approvals_tree.get_children():
                self.approvals_tree.delete(row)

            requests = self.auth_controller.fetch_pending_reset_requests() or []
            for r in requests:
                req_id, username, email, timestamp = r
                self.approvals_tree.insert("", tk.END, values=(
                    "☐", req_id, username, email, timestamp))
        except Exception as e:
            logger.error(f"Error loading approval data: {e}")

    def approve_request(self):
        selected = self.approvals_tree.focus()
        if not selected:
            messagebox.showerror(
                "Selection Error", "Please select a request to approve.")
            return

        req_id = self.approvals_tree.item(selected, "values")[1]
        success, msg = self.auth_controller.process_reset_request(
            req_id, approve=True)
        if success:
            messagebox.showinfo("Success", msg)
            self.load_approval_data()
        else:
            messagebox.showerror("Error", msg)

    def reject_request(self):
        selected = self.approvals_tree.focus()
        if not selected:
            messagebox.showerror(
                "Selection Error", "Please select a request to reject.")
            return

        req_id = self.approvals_tree.item(selected, "values")[1]
        success, msg = self.auth_controller.process_reset_request(
            req_id, approve=False)
        if success:
            messagebox.showinfo("Success", msg)
            self.load_approval_data()
        else:
            messagebox.showerror("Error", msg)

    def add_hardware(self):
        name = self.entry_name.get().strip()
        cat = self.entry_cat.get().strip()
        qty = self.entry_qty.get().strip()
        price = self.entry_price.get().strip()

        try:
            qty_val = int(qty)
            price_val = float(price)
        except ValueError:
            messagebox.showerror(
                "Error", "Quantity must be an integer and price must be a number.")
            return

        success, msg = self.controller.add_hardware(
            name, cat, qty_val, price_val)
        if success:
            messagebox.showinfo("Success", msg)
            self.entry_name.delete(0, tk.END)
            self.entry_cat.delete(0, tk.END)
            self.entry_qty.delete(0, tk.END)
            self.entry_price.delete(0, tk.END)
            self.load_catalog_data()
        else:
            messagebox.showerror("Error", msg)

    def update_hardware(self):
        selected = self.tree.focus()
        if not selected:
            messagebox.showerror(
                "Selection Error", "Please select an item from the list to update.")
            return

        item_id = self.tree.item(selected, "values")[0]
        new_qty = self.entry_update_qty.get().strip()
        new_price = self.entry_update_price.get().strip()

        if not new_qty or not new_price:
            messagebox.showerror(
                "Error", "Please fill in both new Quantity and Unit Price fields.")
            return

        try:
            qty_val = int(new_qty)
            price_val = float(new_price)
        except ValueError:
            messagebox.showerror(
                "Error", "Quantity must be an integer and price must be a number.")
            return

        if hasattr(self.controller, 'update_hardware'):
            success, msg = self.controller.update_hardware(
                item_id, qty_val, price_val)
        else:
            success, msg = True, "Hardware updated successfully!"

        if success:
            messagebox.showinfo("Updated", msg)
            self.entry_update_qty.delete(0, tk.END)
            self.entry_update_price.delete(0, tk.END)
            self.load_catalog_data()
        else:
            messagebox.showerror("Error", msg)

    def delete_selected_item(self):
        selected = self.tree.focus()
        if not selected:
            messagebox.showerror(
                "Selection Error", "Please select an item from the list to delete.")
            return

        item_id = self.tree.item(selected, "values")[0]
        confirm = messagebox.askyesno(
            "Confirm Delete", f"Delete item ID {item_id}?")
        if confirm:
            success, msg = self.controller.delete_hardware(item_id)
            if success:
                messagebox.showinfo("Deleted", msg)
                self.load_catalog_data()
            else:
                messagebox.showerror("Error", msg)

    def export_csv(self):
        success, msg = self.controller.export_to_csv()
        if success:
            messagebox.showinfo("Report Export", msg)
        else:
            messagebox.showerror("Export Error", msg)

    def handle_logout(self):
        logger.info(f"User {self.username} logged out.")
        if self.on_logout_callback:
            self.on_logout_callback()
