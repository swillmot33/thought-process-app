import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from constants import TAG_HIGHLIGHT_OPTIONS, RELATION_HIGHLIGHT_OPTIONS
from utils import (
    clean_tag_markers, next_chunk_id, extract_transcript_body, extract_thread_title,
    detect_tags_from_section, detect_explicit_tags,
)
from dialogs import ImportDialog


class ThreadMixin:
    def refresh_thread_list(self):
        for _name, _thread in self.threads.items():
            _thread.setdefault("open_questions", [])
        self.thread_list.delete(0, tk.END)
        for name in self.threads.keys():
            self.thread_list.insert(tk.END, name)
        names = list(self.threads.keys())
        if self.preview_thread in names:
            idx = names.index(self.preview_thread)
            self.thread_list.selection_clear(0, tk.END)
            self.thread_list.selection_set(idx)
            self.thread_list.activate(idx)
        self.update_left_summary()

    def update_left_summary(self):
        name = self.current_preview_name()
        thread = self.threads.get(name)
        if not thread:
            return
        preview = self.make_thread_preview(thread) if thread["chunks"] else "No summary yet."
        blocks = [name, "", preview]
        questions = thread.get("open_questions", [])
        if questions:
            blocks += ["", "Open questions:"]
            for q in questions[:5]:
                ref = q.get("ref")
                label = f" ({ref})" if ref else ""
                blocks.append(f"- {q.get('text','').strip()[:110]}{label}")
        self.left_summary.configure(state="normal")
        self.left_summary.delete("1.0", tk.END)
        self.left_summary.insert("1.0", "\n".join(blocks))
        self.left_summary.configure(state="disabled")

    def create_thread(self):
        name = self.new_thread_var.get().strip()
        if not name:
            return
        if name in self.threads:
            messagebox.showinfo("Thread exists", f"'{name}' already exists.")
            return
        self.threads[name] = {"title": name, "chunks": [], "tags": [], "relations": [], "auto_relations": [], "open_questions": []}
        self.preview_thread = name
        self.new_thread_var.set("")
        self.refresh_thread_list()
        self.show_home()
        self.status_var.set(f"Created thread '{name}'.")

    def open_selected_thread(self):
        sel = self.thread_list.curselection()
        if not sel:
            return
        self.workspace_thread = self.thread_list.get(sel[0])
        self.preview_thread = self.workspace_thread
        self.mode = "workspace"

        # Preserve the user's current workspace view/filter choices when possible.
        current_view = self.view_var.get()
        if current_view not in ("Preview", "Transcript", "Raw", "Tags", "Relations", "Chains", "Tree"):
            current_view = "Transcript"
        if current_view == "Preview":
            current_view = "Transcript"

        current_tag_filter = self.tag_filter_var.get() if self.tag_filter_var.get() in TAG_HIGHLIGHT_OPTIONS else "none"
        current_relation_filter = self.relation_filter_var.get() if self.relation_filter_var.get() in RELATION_HIGHLIGHT_OPTIONS else "none"

        self.tag_filter_var.set(current_tag_filter)
        self.relation_filter_var.set(current_relation_filter)
        self.view_var.set(current_view)

        self.selected_line_ref = None
        self.local_relation_jump_state = None
        self.relation_group_index = 0
        self.tree_root_ref = None
        if hasattr(self, "neighborhood_text"):
            self.neighborhood_text.configure(state="normal")
            self.neighborhood_text.delete("1.0", tk.END)
            self.neighborhood_text.insert(tk.END, "No line selected.")
            self.neighborhood_text.configure(height=8)
            self.neighborhood_text.configure(state="disabled")
        self.update_left_summary()
        self.render_main()

        if self.view_var.get() in ("Chains", "Tree"):
            self.status_var.set(f"Opened thread '{self.workspace_thread}' in Chains view.")
        else:
            self.status_var.set(f"Opened thread '{self.workspace_thread}'.")

    def show_home(self):
        self.mode = "home"
        self.workspace_thread = None
        self.view_var.set("Preview")
        self.selected_line_ref = None
        self.selected_source_ref = None
        self.graph_root_ref = None
        self.tree_root_ref = None
        self.update_left_summary()
        self.render_main()

    def save_project(self):
        path = filedialog.asksaveasfilename(
            title="Save Companion Research Console Project",
            defaultextension=".crc.json",
            filetypes=[("Companion Research Console", "*.crc.json"), ("JSON", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return
        if not path.lower().endswith((".crc.json", ".json")):
            path = path + ".crc.json"
        data = {
            "app_version": 142,
            "threads": self.threads,
            "preview_thread": self.preview_thread,
            "workspace_thread": self.workspace_thread,
            "mode": self.mode,
            "selected_line_ref": self.selected_line_ref,
            "graph_root_ref": self.graph_root_ref,
            "selected_source_ref": self.selected_source_ref,
            "active_view": self.view_var.get(),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.status_var.set(f"Saved project to {path}.")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def load_project(self, path=None):
        if path is None:
            path = filedialog.askopenfilename(
                title="Load Companion Research Console Project",
                filetypes=[("All Files", "*.*"), ("Companion Research Console", "*.crc.json"), ("JSON", "*.json")],
            )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc))
            return

        threads = data.get("threads")
        if not isinstance(threads, dict) or not threads:
            messagebox.showerror("Load failed", "This file does not contain a valid project.")
            return

        for name, thread in threads.items():
            thread.setdefault("title", name)
            thread.setdefault("chunks", [])
            thread.setdefault("tags", [])
            thread.setdefault("relations", [])
            thread.setdefault("auto_relations", [])
            thread.setdefault("open_questions", [])

        self.threads = threads
        names = list(self.threads.keys())
        self.preview_thread = data.get("preview_thread") if data.get("preview_thread") in self.threads else names[0]
        ws = data.get("workspace_thread")
        self.workspace_thread = ws if ws in self.threads else None
        self.mode = "workspace" if self.workspace_thread else "home"
        self.selected_line_ref = data.get("selected_line_ref")
        self.graph_root_ref = data.get("graph_root_ref")
        self.selected_source_ref = data.get("selected_source_ref")
        current_view = data.get("active_view") or self.view_var.get()
        if current_view not in ("Preview", "Transcript", "Raw", "Tags", "Relations", "Chains", "Tree", "Graph"):
            current_view = "Transcript"

        self.refresh_thread_list()
        if self.mode == "workspace":
            self.set_active_view(current_view if current_view != "Preview" else "Transcript", render=False)
            self.render_main()
            if self.selected_line_ref:
                try:
                    if self.active_view() in ("Transcript", "Raw"):
                        self.mark_selected_line(self.selected_line_ref, True)
                except Exception:
                    pass
        else:
            self.show_home()
        self.status_var.set(f"Loaded project from {path}.")

    def import_text(self):
        if self.mode != "workspace" or not self.workspace_thread:
            messagebox.showinfo("Open a thread", "Double-click a thread or click Open Thread before importing.")
            return
        def do_import(raw, target_mode, thread_name):
            target_thread = self.workspace_thread
            if target_mode == "new":
                name = thread_name or extract_thread_title(raw) or f"Imported {len(self.threads) + 1}"
                if name not in self.threads:
                    self.threads[name] = {"title": name, "chunks": [], "tags": [], "relations": [], "auto_relations": [], "open_questions": []}
                target_thread = name
                self.workspace_thread = name
                self.preview_thread = name
                self.mode = "workspace"
            body_lines = extract_transcript_body(raw)
            if not body_lines:
                messagebox.showinfo("Nothing imported", "No usable transcript lines were found in the pasted text.")
                return
            chunk_id = next_chunk_id(self.threads[target_thread])
            chunk = {"id": chunk_id, "lines": [{"line": i + 1, "text": line} for i, line in enumerate(body_lines)]}
            self.threads[target_thread]["chunks"].append(chunk)
            explicit_tags = detect_explicit_tags(body_lines, chunk_id)
            imported_tags = detect_tags_from_section(raw, chunk_id, body_lines)
            existing_keys = {(t["type"], t["ref"]) for t in explicit_tags}
            merged_tags = explicit_tags + [t for t in imported_tags if (t["type"], t["ref"]) not in existing_keys]
            self.threads[target_thread]["tags"].extend(merged_tags)
            self.refresh_thread_list()
            self.set_active_view("Transcript", render=False)
            self.update_left_summary()
            self.render_main()
            self.status_var.set(f"Imported {chunk_id} into {target_thread}: {len(body_lines)} lines, {len(merged_tags)} tags.")
        ImportDialog(self.root, self.workspace_thread, do_import)

    def make_thread_preview(self, thread):
        latest = thread["chunks"][-1] if thread["chunks"] else {"lines": []}
        starters = []
        for item in latest["lines"]:
            txt = clean_tag_markers(item["text"].strip())
            if txt:
                starters.append(txt)
            if len(starters) == 3:
                break
        branches = self.build_branch_structures(thread)
        phrases = [t["clean_text"] for t in thread["tags"] if t["type"] == "key phrasing"][:4]
        flags = [t["clean_text"] for t in thread["tags"] if t["type"] == "flag"][:4]
        out = [f"# {thread['title']}", ""]
        if starters:
            out += ["Start:"] + [f"- {s[:110]}" for s in starters]
        if branches:
            out += ["", "Thought paths:"]
            for b in branches[:10]:
                out.append(f"{b['id']}. {b['name']}")
                filtered_points = [kp for kp in b["key_points"] if kp[1].strip() != b["name"].strip()]
                for typ, label, ref in filtered_points[:3]:
                    out.append(f"   - [{typ}] {label}")
                if b["splits"]:
                    out.append("   forks:")
                    for label, ref in b["splits"][:2]:
                        out.append(f"   - {label}")
        if phrases:
            out += ["", "Key claims:"] + [f"- {p[:110]}" for p in phrases]
        if flags:
            out += ["", "Important moments:"] + [f"- {f[:110]}" for f in flags]
        counts = {}
        for tag in thread["tags"]:
            counts[tag["type"]] = counts.get(tag["type"], 0) + 1
        if counts:
            out += ["", "Top tags:"] + [f"- {k}: {v}" for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        return "\n".join(out) if out else "No summary yet."

    def on_thread_single_click(self, event=None):
        sel = self.thread_list.curselection()
        if not sel:
            return
        self.preview_thread = self.thread_list.get(sel[0])
        self.update_left_summary()
        if self.mode == "home":
            self.set_active_view("Preview")

    def on_thread_double_click(self, event=None):
        self.open_selected_thread()
