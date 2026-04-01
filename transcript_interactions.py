import tkinter as tk


class TranscriptInteractionMixin:
    def on_transcript_click(self, event):
        idx = self.transcript_text.index(f"@{event.x},{event.y}")
        row = int(idx.split(".")[0])
        chosen = None
        for ref, r in self.row_to_ref.items():
            if r == row:
                chosen = ref
                break
        if chosen:
            self.selected_line_ref = chosen
            self.local_relation_jump_state = None
            view = self.active_view()
            if view == "Chains":
                self.render_chains()
                self.status_var.set(f"Selected {chosen} in Chains view.")
            elif view == "Tree":
                self.select_in_tree(chosen)
            else:
                self.mark_selected_line(chosen, False)
                self.update_neighborhood()
                self.status_var.set(f"Selected {chosen}.")

    def on_transcript_double_click(self, event):
        """In Tree view: double-click re-roots the tree at the clicked node.
        In other views: no special action beyond single-click."""
        if self.active_view() != "Tree":
            return
        idx = self.transcript_text.index(f"@{event.x},{event.y}")
        row = int(idx.split(".")[0])
        chosen = None
        for ref, r in self.row_to_ref.items():
            if r == row:
                chosen = ref
                break
        if chosen:
            self.select_in_tree(chosen, reroot=True)

    def ensure_ref_visible(self, ref):
        row = self.row_to_ref.get(ref)
        if not row or not hasattr(self, "transcript_text"):
            return
        widget = self.transcript_text
        try:
            top_info = widget.dlineinfo("@0,0")
            bottom_info = widget.dlineinfo(f"@0,{max(widget.winfo_height()-4, 0)}")
            target_info = widget.dlineinfo(f"{row}.0")
            if not target_info or not top_info or not bottom_info:
                widget.see(f"{row}.0")
                return
            target_y = target_info[1]
            top_y = top_info[1]
            bottom_y = bottom_info[1]
            if target_y < top_y + 18 or target_y > bottom_y - 18:
                widget.see(f"{row}.0")
        except Exception:
            try:
                widget.see(f"{row}.0")
            except Exception:
                pass

    def mark_selected_line(self, ref, scroll=False):
        row = self.row_to_ref.get(ref)
        if not row:
            return
        self.transcript_text.tag_remove("selectedline", "1.0", tk.END)
        self.transcript_text.tag_add("selectedline", f"{row}.0", f"{row}.end")
        self.transcript_text.tag_raise("selectedline")
        if scroll:
            self.transcript_text.see(f"{row}.0")
        self.update_questions_source_hint()

    def mark_source_line(self, ref, scroll=False):
        row = self.row_to_ref.get(ref)
        if not row:
            return
        self.transcript_text.configure(state="normal")
        self.transcript_text.tag_remove("sourcesel", "1.0", tk.END)
        self.transcript_text.tag_add("sourcesel", f"{row}.0", f"{row}.end")
        self.transcript_text.tag_raise("sourcesel")
        if scroll:
            self.transcript_text.see(f"{row}.0")
        self.update_questions_source_hint()

    def highlight_ref(self, ref, scroll=True):
        row = self.row_to_ref.get(ref)
        if not row:
            self.status_var.set(f"Could not locate {ref}.")
            return
        self.current_highlight_ref = ref
        self.transcript_text.configure(state="normal")
        self.transcript_text.tag_remove("highlight", "1.0", tk.END)
        self.transcript_text.tag_add("highlight", f"{row}.0", f"{row}.end")
        self.transcript_text.tag_raise("highlight")
        if scroll:
            self.transcript_text.see(f"{row}.0")
        self.update_questions_source_hint()
        self.status_var.set(f"Jumped to {ref}.")

    def select_in_tree(self, ref, reroot=False):
        """Select a node in tree view: update selected_line_ref, highlight, update neighborhood.
        If reroot=True, also re-root the tree and graph at this node (double-click behavior)."""
        self.selected_line_ref = ref
        self.local_relation_jump_state = None
        self.mark_selected_line(ref, True)
        self.update_neighborhood()
        if reroot:
            self.tree_root_ref = ref
            self.graph_root_ref = ref
            self.render_tree()
            return
        edge_info = ""
        nav_idx = self.tree_ref_to_nav_idx.get(ref)
        if nav_idx is not None and nav_idx < len(self.tree_nav_sequence):
            _, depth, edge_label = self.tree_nav_sequence[nav_idx]
            if edge_label:
                edge_info = f" via {edge_label}"
        self.status_var.set(f"Tree: selected {ref}{edge_info}. Double-click to re-root here.")
        self.update_questions_source_hint()

    def on_tags_text_double_click(self, event=None):
        idx = self.tags_text.index(f"@{event.x},{event.y}")
        row = int(idx.split(".")[0])
        info = self.tag_line_lookup.get(row)
        if not info:
            return
        _, ref, _ = info
        self.tag_filter_var.set("none")
        self.relation_filter_var.set("none")
        self.set_active_view("Transcript", render=False)
        self.render_main()
        self.selected_line_ref = ref
        self.mark_selected_line(ref, True)
        self.highlight_ref(ref, True)

    def on_relations_double_click(self, event=None):
        idx = self.relations_text.index(f"@{event.x},{event.y}")
        row = int(idx.split(".")[0])
        info = self.relation_line_lookup.get(row)
        if not info:
            return
        self.selected_relation_info = info
        _, sref, tref, _ = info
        self.tag_filter_var.set("none")
        self.relation_filter_var.set("none")
        self.set_active_view("Transcript", render=False)
        self.render_main()
        self.selected_source_ref = sref
        self.selected_line_ref = tref
        self.mark_source_line(sref, True)
        self.mark_selected_line(tref, True)

    def update_neighborhood(self):
        if not hasattr(self, "neighborhood_text"):
            return
        self.neighborhood_text.configure(state="normal")
        self.neighborhood_text.delete("1.0", tk.END)

        if not self.workspace_thread or not self.selected_line_ref:
            self.neighborhood_text.insert(tk.END, "No line selected.")
            self.neighborhood_text.configure(height=4)
            self.neighborhood_text.configure(state="disabled")
            return

        ref = self.selected_line_ref
        incoming = {}
        outgoing = {}

        for rel in self.ordered_relations(self.threads[self.workspace_thread]):
            rtype = rel["type"]
            if rel["target_ref"] == ref:
                incoming.setdefault(rtype, []).append(rel["source_ref"])
            if rel["source_ref"] == ref:
                outgoing.setdefault(rtype, []).append(rel["target_ref"])

        self.neighborhood_jump_map = {}
        self.graph_item_to_ref = {}
        self.graph_node_bounds = {}
        self.graph_positions = {}

        incoming_count = sum(len(v) for v in incoming.values())
        outgoing_count = sum(len(v) for v in outgoing.values())

        self.neighborhood_text.insert(tk.END, f"Selected: {ref}\n")
        self.neighborhood_text.insert(tk.END, f"Incoming: {incoming_count}    Outgoing: {outgoing_count}\n\n")

        self.neighborhood_text.insert(tk.END, "Incoming\n")
        if incoming:
            for rtype in sorted(incoming.keys()):
                refs = incoming[rtype]
                self.neighborhood_text.insert(tk.END, f"- {rtype}: ")
                for i, r in enumerate(refs):
                    start = self.neighborhood_text.index(tk.END)
                    self.neighborhood_text.insert(tk.END, r)
                    end = self.neighborhood_text.index(tk.END)
                    self.neighborhood_jump_map[(start, end)] = r
                    if i < len(refs) - 1:
                        self.neighborhood_text.insert(tk.END, ", ")
                self.neighborhood_text.insert(tk.END, "\n")
        else:
            self.neighborhood_text.insert(tk.END, "- none\n")

        self.neighborhood_text.insert(tk.END, "\nOutgoing\n")
        if outgoing:
            for rtype in sorted(outgoing.keys()):
                refs = outgoing[rtype]
                self.neighborhood_text.insert(tk.END, f"- {rtype}: ")
                for i, r in enumerate(refs):
                    start = self.neighborhood_text.index(tk.END)
                    self.neighborhood_text.insert(tk.END, r)
                    end = self.neighborhood_text.index(tk.END)
                    self.neighborhood_jump_map[(start, end)] = r
                    if i < len(refs) - 1:
                        self.neighborhood_text.insert(tk.END, ", ")
                self.neighborhood_text.insert(tk.END, "\n")
        else:
            self.neighborhood_text.insert(tk.END, "- none\n")

        # Auto-size so longer neighborhoods are actually visible.
        lines = int(float(self.neighborhood_text.index("end-1c").split(".")[0]))
        self.neighborhood_text.configure(height=8)
        self.neighborhood_text.configure(state="disabled")

    def on_neighborhood_double_click(self, event):
        idx = self.neighborhood_text.index(f"@{event.x},{event.y}")
        for (start, end), ref in getattr(self, "neighborhood_jump_map", {}).items():
            if self.neighborhood_text.compare(idx, ">=", start) and self.neighborhood_text.compare(idx, "<", end):
                self.selected_line_ref = ref
                self.local_relation_jump_state = None
                self.render_transcript()
                if self.selected_line_ref in self.row_to_ref:
                    self.mark_selected_line(self.selected_line_ref, True)
                self.update_neighborhood()
                return

    def preserve_transcript_view(self):
        if not hasattr(self, "transcript_text"):
            return None
        try:
            return self.transcript_text.yview()
        except Exception:
            return None

    def restore_transcript_view(self, yview):
        if yview is None or not hasattr(self, "transcript_text"):
            return
        try:
            self.transcript_text.yview_moveto(yview[0])
        except Exception:
            pass

    def refresh_transcript_preserve_view(self, current_ref=None):
        yview = self.preserve_transcript_view()
        self.render_transcript()
        self.restore_transcript_view(yview)
        if current_ref:
            self.mark_selected_line(current_ref, False)
