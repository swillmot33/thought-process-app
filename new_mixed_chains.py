import os
import sys
import tkinter as tk

from app import App

root = tk.Tk()
app = App(root)
if len(sys.argv) > 1:
    app.load_project(sys.argv[1])
else:
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Test.crc.json")
    if os.path.exists(default):
        app.load_project(default)
root.mainloop()
