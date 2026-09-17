import tkinter as tk
from models.database import init_db
from views.login_view import LoginWindow
from views.hardware_view import HardwareWindow


def main():
    init_db()
    root = tk.Tk()

    def show_hardware(user_data):
        for widget in root.winfo_children():
            widget.destroy()
        HardwareWindow(root, user_data=user_data,
                       on_logout_callback=show_login)

    def show_login():
        for widget in root.winfo_children():
            widget.destroy()
        LoginWindow(root, on_login_success=show_hardware)

    show_login()
    root.mainloop()


if __name__ == "__main__":
    main()
