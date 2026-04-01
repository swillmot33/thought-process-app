import tkinter as tk
from tkinter import ttk

from constants import TAG_OPTIONS, TAG_PRIORITY, TAG_COLORS
from utils import make_tag_entry


class TagMixin:
    def add_manual_tag(self):
        if self.mode != "workspace" or not self.workspace_thread or not self.selected_line_ref:
            return
        data = self.line_ref_to_data.get(self.selected_line_ref)
        thread = self.threads[self.workspace_thread]
        tag_type = self.manual_tag_var.get()
        if any(t["ref"] == self.selected_line_ref and t["type"] == tag_type for t in thread["tags"]):
            self.status_var.set(f"{tag_type} already exists on {self.selected_line_ref}.")
            return
        current_ref = self.selected_line_ref
        thread["tags"].append(make_tag_entry(tag_type, data["chunk_id"], data["line"], data["text"], "manual"))
        self.update_left_summary()
        self.set_active_view("Transcript", render=False)
        self.refresh_transcript_preserve_view(current_ref)
        self.status_var.set(f"Added manual '{tag_type}' tag.")

    def replace_line_tag(self):
        if self.mode != "workspace" or not self.workspace_thread or not self.selected_line_ref:
            return
        tag_type = self.manual_tag_var.get()
        thread = self.threads[self.workspace_thread]
        same_ref = [t for t in thread["tags"] if t["ref"] == self.selected_line_ref]
        if not same_ref:
            self.add_manual_tag()
            return
        replaced = False
        newtags = []
        for t in thread["tags"]:
            if not replaced and t["ref"] == self.selected_line_ref:
                data = self.line_ref_to_data[self.selected_line_ref]
                newtags.append(make_tag_entry(tag_type, data["chunk_id"], data["line"], data["text"], "manual"))
                replaced = True
                continue
            newtags.append(t)
        current_ref = self.selected_line_ref
        thread["tags"] = newtags
        self.update_left_summary()
        self.refresh_transcript_preserve_view(current_ref)
        self.status_var.set(f"Replaced first tag with '{tag_type}'.")

    def remove_line_tag(self):
        if self.mode != "workspace" or not self.workspace_thread or not self.selected_line_ref:
            return
        tag_type = self.manual_tag_var.get()
        thread = self.threads[self.workspace_thread]
        removed = False
        newtags = []
        for t in thread["tags"]:
            if not removed and t["ref"] == self.selected_line_ref and t["type"] == tag_type:
                removed = True
                continue
            newtags.append(t)
        current_ref = self.selected_line_ref
        thread["tags"] = newtags
        self.update_left_summary()
        self.refresh_transcript_preserve_view(current_ref)
        self.status_var.set(f"Removed '{tag_type}'." if removed else f"No '{tag_type}' found.")

    def auto_tag_current_thread(self):
        if self.mode != "workspace" or not self.workspace_thread:
            from tkinter import messagebox
            messagebox.showinfo("Open a thread", "Open a thread first.")
            return
        thread = self.threads[self.workspace_thread]
        manual_tags = [t for t in thread["tags"] if t.get("source") == "manual"]
        from utils import detect_explicit_tags
        explicit = []
        for chunk in thread["chunks"]:
            explicit.extend(detect_explicit_tags([item["text"] for item in chunk["lines"]], chunk["id"]))
        thread["tags"] = explicit + manual_tags
        self.update_left_summary()
        self.render_transcript()
        self.render_tags()
        self.status_var.set(f"Found {len(explicit)} explicit tags from inline markers. AI auto-tag suggestions are not enabled yet.")

    def choose_custom_tags(self):
        top = tk.Toplevel(self.root)
        top.title("Select tags")
        top.transient(self.root)
        top.grab_set()

        vars_map = {}
        body = ttk.Frame(top, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Choose one or more tag types to highlight.").pack(anchor="w", pady=(0, 8))
        for tag in TAG_OPTIONS:
            var = tk.BooleanVar(value=(tag in self.custom_tag_selection))
            vars_map[tag] = var
            ttk.Checkbutton(body, text=tag, variable=var).pack(anchor="w")

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(10, 0))

        def apply():
            self.custom_tag_selection = [t for t, v in vars_map.items() if v.get()]
            self.tag_filter_var.set("custom" if self.custom_tag_selection else "none")
            top.destroy()
            self.on_highlight_changed()

        ttk.Button(btns, text="Apply", command=apply).pack(side="right")
        ttk.Button(btns, text="Cancel", command=top.destroy).pack(side="right", padx=(0, 6))

    def selected_tag_types(self):
        selected = self.tag_filter_var.get()
        if selected == "custom":
            return list(self.custom_tag_selection)
        if selected in ("none", "all"):
            return []
        return [selected]

    def winning_tag_type(self, tag_types):
        if not tag_types:
            return None
        return sorted(tag_types, key=lambda t: (TAG_PRIORITY.get(t, 999), t))[0]

    def ref_matches_tag_filter(self, ref):
        selected = self.tag_filter_var.get()
        if selected == "none":
            return False
        tags = self.tags_for_ref(ref)
        if selected == "all":
            return bool(tags)
        if selected == "custom":
            chosen = set(self.custom_tag_selection)
            return any(t["type"] in chosen for t in tags)
        return any(t["type"] == selected for t in tags)

    def on_highlight_changed(self, event=None):
        visible_rel = self.active_relation_filter()
        if self.relation_filter_var.get() != visible_rel:
            self.relation_filter_var.set(visible_rel)
            return

        self.sync_relation_controls_for_view()
        if self.mode == "workspace":
            self.relation_group_index = 0
            self.local_relation_jump_state = None
            self.clear_relation_highlights()
            if visible_rel in ("none", "all"):
                self.selected_source_ref = None
                self.current_highlight_ref = None

            view = self.active_view()
            if view in ("Transcript", "Raw"):
                self.render_transcript()
            elif view == "Chains":
                self.render_chains()
            elif view == "Relations":
                self.render_relations()
            elif view == "Tree":
                self.render_tree()
            elif view == "Graph":
                self.render_graph()
            elif view == "Tags":
                self.render_tags()
            else:
                self.render_main()

            if visible_rel in ("none", "all"):
                self.clear_relation_highlights()
            if self.selected_line_ref and self.selected_line_ref in self.row_to_ref and view not in ("Chains", "Tree"):
                self.mark_selected_line(self.selected_line_ref, False)
