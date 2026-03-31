import tkinter as tk
from tkinter import ttk

from constants import RELATION_OPTIONS

class ImportDialog(tk.Toplevel):
    def __init__(self, parent, on_import):
        super().__init__(parent)
        self.title("Import text")
        self.geometry("900x700")
        self.transient(parent)
        self.grab_set()
        self.on_import = on_import
        ttk.Label(self, text="Paste raw transcript or a consolidate block.").pack(anchor="w", padx=12, pady=(12, 6))
        self.text = tk.Text(self, wrap="word")
        self.text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        row = ttk.Frame(self)
        row.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(row, text="Import", command=self.submit).pack(side="right", padx=(0, 8))
    def submit(self):
        raw = self.text.get("1.0", tk.END).strip("\n")
        if raw.strip():
            self.on_import(raw)
        self.destroy()

class RelationEditDialog(tk.Toplevel):
    def __init__(self, parent, relation, on_save):
        super().__init__(parent)
        self.title("Edit relation")
        self.geometry("520x220")
        self.transient(parent)
        self.grab_set()
        self.on_save = on_save
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"Source: {relation['source_ref']}").pack(anchor="w", pady=(0, 8))
        ttk.Label(frm, text="Relation type:").pack(anchor="w")
        self.rel_var = tk.StringVar(value=relation["type"])
        ttk.Combobox(frm, textvariable=self.rel_var, values=RELATION_OPTIONS, state="readonly", width=20).pack(anchor="w", pady=(0, 8))
        ttk.Label(frm, text="Target ref:").pack(anchor="w")
        self.target_var = tk.StringVar(value=relation["target_ref"])
        ttk.Entry(frm, textvariable=self.target_var, width=24).pack(anchor="w", pady=(0, 12))
        row = ttk.Frame(frm)
        row.pack(fill="x")
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(row, text="Save", command=self.submit).pack(side="right", padx=(0, 8))
    def submit(self):
        self.on_save(self.rel_var.get(), self.target_var.get().strip())
        self.destroy()
