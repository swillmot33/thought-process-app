class KeyboardMixin:
    def navigate_selected_line(self, delta):
        if not self.workspace_thread:
            return None
        view = self.active_view()

        # In Tree view: arrow keys step through tree sequence depth-first
        if view == "Tree" and self.tree_nav_sequence:
            nav_idx = self.tree_ref_to_nav_idx.get(self.selected_line_ref, 0)
            new_idx = max(0, min(len(self.tree_nav_sequence) - 1, nav_idx + delta))
            new_ref, depth, edge_label = self.tree_nav_sequence[new_idx]
            self.select_in_tree(new_ref)
            return "break"

        ordered = self.ordered_lines(self.threads[self.workspace_thread])
        if not ordered:
            return None
        refs = [item["ref"] for item in ordered]
        current = self.selected_line_ref if self.selected_line_ref in refs else refs[0]
        idx = refs.index(current)
        new_idx = max(0, min(len(refs) - 1, idx + delta))
        new_ref = refs[new_idx]
        self.selected_line_ref = new_ref
        self.local_relation_jump_state = None
        if view in ("Transcript", "Raw"):
            self.render_transcript()
            self.mark_selected_line(new_ref, False)
            self.ensure_ref_visible(new_ref)
            self.update_neighborhood()
        elif view == "Relations":
            self.render_relations()
        elif view == "Chains":
            self.render_chains()
        elif view == "Graph":
            self.render_graph()
        else:
            self.render_preview()
        self.update_questions_source_hint()
        self.status_var.set(f"Selected {new_ref}.")
        return "break"

    def on_global_arrow_up(self, event):
        if self._focus_allows_global_nav():
            return self.navigate_selected_line(-1)

    def on_global_arrow_down(self, event):
        if self._focus_allows_global_nav():
            return self.navigate_selected_line(1)

    def _focus_allows_global_nav(self):
        widget = self.root.focus_get()
        if widget is None:
            return False
        cls = widget.winfo_class()
        return cls not in {"Entry", "TEntry", "Text", "TCombobox", "Listbox", "Spinbox"}

    def _focus_allows_global_shortcuts(self):
        widget = self.root.focus_get()
        if widget is None:
            return True
        cls = widget.winfo_class()
        return cls not in {"Entry", "TEntry", "Text", "TCombobox", "Listbox", "Spinbox"}

    def on_shortcut_set_source(self, event=None):
        if self._focus_allows_global_shortcuts() and self.mode == "workspace":
            self.set_relation_source()
            return "break"

    def on_shortcut_add_relation(self, event=None):
        if self._focus_allows_global_shortcuts() and self.mode == "workspace":
            self.add_relation()
            return "break"

    def on_shortcut_clear_source(self, event=None):
        if self._focus_allows_global_shortcuts() and self.mode == "workspace":
            self.clear_relation_source()
            return "break"

    def jump_selected_line_along_relation(self, direction):
        if not self.selected_line_ref:
            self.status_var.set("Select a line first.")
            return

        view = self.active_view()

        # In Tree view: Follow forward/back steps through the tree nav sequence (mixed chain)
        if view == "Tree" and self.tree_nav_sequence:
            nav_idx = self.tree_ref_to_nav_idx.get(self.selected_line_ref)
            if nav_idx is None:
                # Fall back to first node
                nav_idx = 0
            if direction == "forward":
                new_idx = min(nav_idx + 1, len(self.tree_nav_sequence) - 1)
            else:
                new_idx = max(nav_idx - 1, 0)
            new_ref, depth, edge_label = self.tree_nav_sequence[new_idx]
            self.select_in_tree(new_ref)
            edge_info = f" via {edge_label}" if edge_label else ""
            self.status_var.set(f"Tree: {direction} → {new_ref}{edge_info} (depth {depth})  [{new_idx+1}/{len(self.tree_nav_sequence)}]")
            return

        # Standard single-type follow for other views
        matches, rel_type = self.relation_edges_for_selected_line(direction)
        if rel_type in ("none", "all"):
            self.status_var.set("Choose a specific relation type first.")
            return
        if not matches:
            self.status_var.set(f"No {rel_type} relation to follow {direction} from {self.selected_line_ref}.")
            return

        key = (self.selected_line_ref, rel_type, direction)
        if self.local_relation_jump_state and self.local_relation_jump_state.get("key") == key:
            idx = (self.local_relation_jump_state.get("idx", -1) + 1) % len(matches)
        else:
            idx = 0
        self.local_relation_jump_state = {"key": key, "idx": idx}

        rel = matches[idx]
        dest = rel["source_ref"] if direction == "back" else rel["target_ref"]
        self.selected_line_ref = dest
        self.render_transcript()
        if self.selected_line_ref in self.row_to_ref:
            self.mark_selected_line(self.selected_line_ref, True)
        self.status_var.set(f"Follow {direction} {rel_type}: {key[0]} → {dest} [{idx+1}/{len(matches)}].")
