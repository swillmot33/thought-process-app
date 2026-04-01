import tkinter as tk
from tkinter import ttk

from constants import RELATION_OPTIONS, RELATION_HIGHLIGHT_OPTIONS
from utils import choose_meaningful_label


class ViewRendererMixin:
    def active_view(self):
        value = getattr(self, "current_view_name", "").strip()
        if value:
            return value
        try:
            value = self.view_var.get().strip()
            if value:
                return value
        except Exception:
            pass
        try:
            value = self.view_combo.get().strip()
            if value:
                return value
        except Exception:
            pass
        return "Preview"

    def set_active_view(self, view, render=True):
        if not view:
            return
        self.current_view_name = view
        self._syncing_view_var = True
        try:
            if self.view_var.get() != view:
                self.view_var.set(view)
            try:
                if self.view_combo.get().strip() != view:
                    self.view_combo.set(view)
            except Exception:
                pass
        finally:
            self._syncing_view_var = False
        if render:
            self.render_current_view()

    def render_current_view(self):
        view = self.active_view()
        self.current_view_name = view
        self.clear_main_frames()
        self.clear_view_outputs()
        self.sync_relation_controls_for_view()

        if view == "Preview":
            self.preview_frame.pack(fill="both", expand=True)
            self.render_preview()
        elif view in ("Transcript", "Raw"):
            self.transcript_frame.pack(fill="both", expand=True)
            self.render_transcript()
            # After rendering, scroll to and highlight the selected line if one exists
            if self.selected_line_ref and self.selected_line_ref in self.row_to_ref:
                self.mark_selected_line(self.selected_line_ref, scroll=True)
                self.update_neighborhood()
        elif view == "Chains":
            self.transcript_frame.pack(fill="both", expand=True)
            self.render_chains()
        elif view == "Tree":
            self.transcript_frame.pack(fill="both", expand=True)
            self.render_tree()
        elif view == "Graph":
            self.graph_frame.pack(fill="both", expand=True)
            self.render_graph()
        elif view == "Tags":
            self.tags_frame.pack(fill="both", expand=True)
            self.render_tags()
        elif view == "Relations":
            self.relations_frame.pack(fill="both", expand=True)
            self.render_relations()
        else:
            self.preview_frame.pack(fill="both", expand=True)
            self.render_preview()

    def clear_main_frames(self):
        for frame in (self.preview_frame, self.transcript_frame, self.tags_frame, self.relations_frame, self.graph_frame):
            frame.pack_forget()

    def clear_view_outputs(self):
        for attr in ("transcript_text", "relations_text", "tags_text", "preview_text", "neighborhood_text"):
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            try:
                widget.configure(state="normal")
            except Exception:
                pass
            try:
                widget.delete("1.0", tk.END)
            except Exception:
                pass
        if hasattr(self, "graph_canvas"):
            try:
                self.graph_canvas.delete("all")
                self.graph_canvas.configure(scrollregion=(0, 0, 1, 1))
            except Exception:
                pass
        self.row_to_ref = {}
        self.ref_to_row = {}
        self.line_ref_to_data = {}
        self.relation_line_lookup = {}
        self.tag_line_lookup = {}
        self.neighborhood_jump_map = {}
        self.graph_item_to_ref = {}
        self.graph_node_bounds = {}
        self.graph_positions = {}

    def on_view_combo_selected(self, event=None):
        try:
            value = event.widget.get().strip() if event is not None else self.view_combo.get().strip()
        except Exception:
            value = self.view_var.get().strip()
        self.set_active_view(value, render=True)

    def on_view_var_changed(self, *_):
        if getattr(self, "_syncing_view_var", False):
            return
        try:
            value = self.view_var.get().strip()
        except Exception:
            value = ""
        if not value:
            return
        if value == getattr(self, "current_view_name", ""):
            return
        self.set_active_view(value, render=True)

    def render_main(self):
        self.clear_main_frames()
        if self.mode == "home":
            self.current_view_name = "Preview"
            self.view_var.set("Preview")
            try:
                self.view_combo.set("Preview")
            except Exception:
                pass
            self.sync_relation_controls_for_view()
            self.preview_frame.pack(fill="both", expand=True)
            self.render_preview()
            return
        self.render_current_view()

    def sync_relation_controls_for_view(self):
        view = self.active_view()
        if view in ("Transcript", "Raw", "Tags", "Preview"):
            values = RELATION_HIGHLIGHT_OPTIONS
            current = self.relation_filter_var.get() if self.relation_filter_var.get() in values else "none"
        elif view == "Relations":
            values = ["all"] + RELATION_OPTIONS
            current = self.relations_view_var.get().strip() or "all"
            if current not in values:
                current = "all"
        elif view == "Chains":
            values = ["none", "mixed"] + RELATION_OPTIONS
            current = self.chains_view_var.get().strip() or "none"
            if current not in values:
                current = "none"
        elif view == "Tree":
            values = ["all"] + RELATION_OPTIONS
            current = self.tree_view_var.get().strip() or "all"
            if current not in values:
                current = "all"
        elif view == "Graph":
            values = ["all"] + RELATION_OPTIONS
            current = self.graph_view_var.get().strip() or "all"
            if current not in values:
                current = "all"
        else:
            values = RELATION_HIGHLIGHT_OPTIONS
            current = "none"

        try:
            self.relation_filter_combo.configure(values=values)
        except Exception:
            pass

        self._syncing_relation_display = True
        try:
            self.relation_display_var.set(current)
            try:
                self.relation_filter_combo.set(current)
            except Exception:
                pass
        finally:
            self._syncing_relation_display = False

    def active_relation_filter(self):
        view = self.active_view()
        if view == "Relations":
            value = self.relations_view_var.get().strip()
            return value if value else "all"
        if view == "Chains":
            value = self.chains_view_var.get().strip()
            return value if value else "none"
        if view == "Tree":
            value = self.tree_view_var.get().strip()
            return value if value else "all"
        value = self.relation_filter_var.get().strip()
        return value if value else "none"

    def render_chains(self):
        # Chains always renders into the transcript pane.
        self.clear_relation_highlights()
        self.transcript_text.configure(state="normal")
        self.transcript_text.delete("1.0", tk.END)
        if hasattr(self, "neighborhood_text"):
            self.neighborhood_text.configure(state="normal")
            self.neighborhood_text.delete("1.0", tk.END)

        if not self.workspace_thread:
            self.transcript_text.insert(tk.END, "Open a thread to view chains.")
            self.transcript_text.configure(state="disabled")
            if hasattr(self, "neighborhood_text"):
                self.neighborhood_text.configure(state="normal")
                self.neighborhood_text.delete("1.0", tk.END)
                self.neighborhood_text.insert(tk.END, "Chains view active. No thread open.")
                self.neighborhood_text.configure(height=8)
                self.neighborhood_text.configure(state="disabled")
            self.status_var.set("Chains view. No thread open.")
            return

        rel_type = self.chains_view_var.get().strip() or "none"
        valid_chain_options = ["mixed"] + RELATION_OPTIONS
        if rel_type not in valid_chain_options:
            rel_type = "none"

        if rel_type == "none":
            self.transcript_text.insert(tk.END, 'Choose "mixed" for full thought-process chains, or a specific relation type.')
            self.transcript_text.configure(state="disabled")
            if hasattr(self, "neighborhood_text"):
                self.neighborhood_text.configure(state="normal")
                self.neighborhood_text.delete("1.0", tk.END)
                self.neighborhood_text.insert(tk.END, 'Chains view. Choose "mixed" or a specific relation type.')
                self.neighborhood_text.configure(height=8)
                self.neighborhood_text.configure(state="disabled")
            self.status_var.set('Chains view. Choose "mixed" or a specific relation type.')
            return

        is_mixed = (rel_type == "mixed")

        if is_mixed:
            raw_chains = self.mixed_chains_for_thread()
            # Normalise to {"nodes": [...], "edges": [...]} — mixed_chains already returns this format.
        else:
            flat = self.maximal_chains_for_relation_type(rel_type)
            # Wrap single-type chains into the unified dict format.
            raw_chains = [{"nodes": c, "edges": [rel_type] * (len(c) - 1)} for c in flat]

        # Neighbourhood: index all chains, highlight those containing selected line.
        selected_chain_indices = set()
        if self.selected_line_ref:
            for i, chain in enumerate(raw_chains):
                if self.selected_line_ref in chain["nodes"]:
                    selected_chain_indices.add(i)

        if hasattr(self, "neighborhood_text"):
            self.neighborhood_text.configure(state="normal")
            self.neighborhood_text.delete("1.0", tk.END)
            label = "mixed" if is_mixed else rel_type
            self.neighborhood_text.insert(tk.END, f"Chains view: {label}\n")
            self.neighborhood_text.insert(tk.END, f"Total chains: {len(raw_chains)}\n")
            if selected_chain_indices:
                self.neighborhood_text.insert(tk.END, f"Selected line appears in: {sorted(selected_chain_indices)}\n\n")
            else:
                self.neighborhood_text.insert(tk.END, "\n")
            for idx, chain in enumerate(raw_chains, 1):
                parts = []
                for i, node in enumerate(chain["nodes"]):
                    parts.append(node)
                    if i < len(chain["edges"]):
                        parts.append(f"--{chain['edges'][i]}-->")
                self.neighborhood_text.insert(tk.END, f"{idx}. " + " ".join(parts) + "\n")
            self.neighborhood_text.configure(height=8)
            self.neighborhood_text.configure(state="disabled")

        if not raw_chains:
            label = "mixed" if is_mixed else rel_type
            self.transcript_text.insert(tk.END, f"No {label} chains found.")
            self.transcript_text.configure(state="disabled")
            self.transcript_text.yview_moveto(0.0)
            self.status_var.set(f"Chains view: {label} (0 chains).")
            return

        self.transcript_text.tag_configure("chain_header", font=("TkDefaultFont", 11, "bold"))
        self.transcript_text.tag_configure("chain_arrow", foreground="#555555")
        self.transcript_text.tag_configure("chain_member", background="#f5f5f5")
        self.transcript_text.tag_configure("chain_selected_member", background="#bbdefb")
        self.transcript_text.tag_configure("chain_active_member", background="#fff3b0")

        # Pre-compute per-relation-type colours for edge labels in mixed view.
        from constants import RELATION_COLORS
        for rtype, color in RELATION_COLORS.items():
            self.transcript_text.tag_configure(f"edge_{rtype}", foreground=color, font=("TkDefaultFont", 9, "bold"))

        line_no = 1
        first_selected_chain_line = None

        for idx, chain in enumerate(raw_chains, 1):
            nodes = chain["nodes"]
            edges = chain["edges"]
            is_selected_chain = idx - 1 in selected_chain_indices
            label = "mixed" if is_mixed else rel_type

            # Header
            header = f"[{label}] Chain {idx}  ({len(nodes)} nodes)"
            if is_selected_chain:
                header += "  ← selected"
            start = self.transcript_text.index(tk.END)
            self.transcript_text.insert(tk.END, header + "\n")
            self.transcript_text.tag_add("chain_header", start, self.transcript_text.index(tk.END))
            line_no += 1

            # Arrow summary line with typed edges
            parts = []
            for i, node in enumerate(nodes):
                parts.append(node)
                if i < len(edges):
                    parts.append(f"--{edges[i]}-->")
            start = self.transcript_text.index(tk.END)
            self.transcript_text.insert(tk.END, " ".join(parts) + "\n")
            self.transcript_text.tag_add("chain_arrow", start, self.transcript_text.index(tk.END))
            line_no += 1

            # Node lines
            for i, ref in enumerate(nodes):
                edge_label = edges[i - 1] if i > 0 else None
                chunk_id, line_index = self.parse_ref(ref)
                text = self.lookup_line_text(chunk_id, line_index)

                # Edge connector line (not selectable)
                if edge_label:
                    connector = f"  └─{edge_label}─▶"
                    es = self.transcript_text.index(tk.END)
                    self.transcript_text.insert(tk.END, connector + "\n")
                    etag = f"edge_{edge_label}"
                    if etag in RELATION_COLORS:
                        self.transcript_text.tag_add(etag, es, self.transcript_text.index(tk.END))
                    else:
                        self.transcript_text.tag_add("chain_arrow", es, self.transcript_text.index(tk.END))
                    line_no += 1

                rendered = f"  {ref}  {text}".rstrip()
                start = self.transcript_text.index(tk.END)
                self.transcript_text.insert(tk.END, rendered + "\n")
                end = self.transcript_text.index(tk.END)

                self.row_to_ref[line_no] = ref
                self.ref_to_row[ref] = line_no
                self.line_ref_to_data[ref] = (chunk_id, line_index, text)

                is_active_node = ref == self.selected_line_ref
                if is_active_node:
                    self.transcript_text.tag_add("chain_active_member", start, end)
                    if first_selected_chain_line is None:
                        first_selected_chain_line = start
                elif is_selected_chain:
                    self.transcript_text.tag_add("chain_selected_member", start, end)
                else:
                    self.transcript_text.tag_add("chain_member", start, end)

                line_no += 1

            self.transcript_text.insert(tk.END, "\n")
            line_no += 1

        self.transcript_text.configure(state="disabled")

        # Scroll so the first chain containing the selected line is visible from its header.
        if first_selected_chain_line:
            self.transcript_text.see(first_selected_chain_line)
            self.transcript_text.update_idletasks()
            # Step back a few lines so the chain header is visible above the highlighted node.
            try:
                self.transcript_text.yview_scroll(-4, "units")
            except Exception:
                pass
        else:
            self.transcript_text.yview_moveto(0.0)

        label = "mixed" if is_mixed else rel_type
        self.status_var.set(f"Chains view: {label} ({len(raw_chains)} chains).")

    def render_tree(self):
        from utils import clean_tag_markers
        self.clear_relation_highlights()
        self.transcript_text.configure(state="normal")
        self.transcript_text.delete("1.0", tk.END)
        if hasattr(self, "neighborhood_text"):
            self.neighborhood_text.configure(state="normal")
            self.neighborhood_text.delete("1.0", tk.END)

        if not self.workspace_thread:
            self.transcript_text.insert(tk.END, "Open a thread to view the tree.")
            self.transcript_text.configure(state="disabled")
            if hasattr(self, "neighborhood_text"):
                self.neighborhood_text.insert(tk.END, "Tree view active. No thread open.")
                self.neighborhood_text.configure(height=8)
                self.neighborhood_text.configure(state="disabled")
            self.status_var.set("Tree view. No thread open.")
            return

        thread = self.threads[self.workspace_thread]
        ordered = self.ordered_lines(thread)
        if not ordered:
            self.transcript_text.insert(tk.END, "No transcript lines available.")
            self.transcript_text.configure(state="disabled")
            if hasattr(self, "neighborhood_text"):
                self.neighborhood_text.insert(tk.END, "Tree view active. No transcript lines available.")
                self.neighborhood_text.configure(height=8)
                self.neighborhood_text.configure(state="disabled")
            self.status_var.set("Tree view. No transcript lines available.")
            return

        rel_type = self.tree_view_var.get().strip() or "all"
        if rel_type not in (["all"] + RELATION_OPTIONS):
            rel_type = "all"

        valid_refs = {line["ref"] for line in ordered}
        rel_filter = None if rel_type == "all" else rel_type

        # Re-evaluate tree root whenever the current root has no outgoing edges under
        # the active filter — this handles filter changes that strand the existing root.
        current_root_useful = (
            self.tree_root_ref in valid_refs and
            bool(self.outgoing_relations_for_ref(self.tree_root_ref, rel_filter))
        )
        if not current_root_useful:
            # Find first line with outgoing relations under this filter.
            self.tree_root_ref = next(
                (line["ref"] for line in ordered
                 if self.outgoing_relations_for_ref(line["ref"], rel_filter)),
                ordered[0]["ref"]
            )
        root_ref = self.tree_root_ref
        if self.selected_line_ref not in valid_refs:
            self.selected_line_ref = root_ref

        self.transcript_text.tag_configure("tree_node", lmargin1=8, lmargin2=8, spacing3=2)
        self.transcript_text.tag_configure("tree_root", font=("TkDefaultFont", 11, "bold"))
        self.transcript_text.tag_configure("tree_cycle", foreground="#aa0000")
        self.transcript_text.tag_configure("tree_selected", background="#8fd0ff")

        self.row_to_ref = {}
        self.ref_to_row = {}
        self.line_ref_to_data = {}
        # Reset tree nav sequence
        self.tree_nav_sequence = []
        self.tree_ref_to_nav_idx = {}

        max_depth = 8
        line_no = 1

        def insert_node(ref, depth, edge_label=None, is_last=True, path=None):
            nonlocal line_no
            if path is None:
                path = set()

            prefix = ""
            if depth > 0:
                branch = "└──" if is_last else "├──"
                prefix = "    " * (depth - 1) + f"{branch} "
                if edge_label:
                    prefix += f"({edge_label}) → "

            text = clean_tag_markers(self.line_text_from_ref(ref))
            line = f"{prefix}{ref}  {text}".rstrip()
            start = self.transcript_text.index(tk.END)
            self.transcript_text.insert(tk.END, line + "\n")
            end = self.transcript_text.index(tk.END)
            self.transcript_text.tag_add("tree_node", start, end)
            if depth == 0:
                self.transcript_text.tag_add("tree_root", start, end)
            if ref in path:
                self.transcript_text.tag_add("tree_cycle", start, end)

            self.row_to_ref[ref] = line_no
            self.ref_to_row[line_no] = ref
            if ref not in self.line_ref_to_data:
                chunk_id, line_index = self.parse_ref(ref)
                self.line_ref_to_data[ref] = {
                    "chunk_id": chunk_id,
                    "line": line_index,
                    "text": self.line_text_from_ref(ref),
                }

            # Build nav sequence (depth-first, in render order)
            nav_idx = len(self.tree_nav_sequence)
            self.tree_nav_sequence.append((ref, depth, edge_label))
            # Map ref to first occurrence in tree (for navigation)
            if ref not in self.tree_ref_to_nav_idx:
                self.tree_ref_to_nav_idx[ref] = nav_idx

            current_row = line_no
            line_no += 1

            if depth >= max_depth or ref in path:
                return current_row

            children = self.outgoing_relations_for_ref(ref, None if rel_type == "all" else rel_type)
            for idx, rel in enumerate(children):
                insert_node(rel["target_ref"], depth + 1, rel["type"], idx == len(children) - 1, path | {ref})
            return current_row

        insert_node(root_ref, 0, None, True, set())

        if hasattr(self, "neighborhood_text"):
            incoming = self.incoming_relations_for_ref(root_ref, None if rel_type == "all" else rel_type)
            outgoing = self.outgoing_relations_for_ref(root_ref, None if rel_type == "all" else rel_type)
            self.neighborhood_text.insert(tk.END, f"Tree root: {root_ref}\n")
            self.neighborhood_text.insert(tk.END, f"Relation filter: {rel_type}\n")
            self.neighborhood_text.insert(tk.END, f"Incoming: {len(incoming)}    Outgoing: {len(outgoing)}\n\n")
            if incoming:
                self.neighborhood_text.insert(tk.END, "Parents\n")
                for rel in incoming:
                    self.neighborhood_text.insert(tk.END, f"- ({rel['type']}) {rel['source_ref']}\n")
                self.neighborhood_text.insert(tk.END, "\n")
            self.neighborhood_text.insert(tk.END, "Click to select. Follow fwd/back or arrow keys navigate. Double-click to re-root tree here.\n")
            self.neighborhood_text.configure(height=8)
            self.neighborhood_text.configure(state="disabled")

        self.transcript_text.configure(state="disabled")
        if self.selected_line_ref in self.row_to_ref:
            self.mark_selected_line(self.selected_line_ref, True)
        edge_desc = "all relation types" if rel_type == "all" else rel_type
        self.status_var.set(f"Tree view: {edge_desc} from {root_ref}. {len(self.tree_nav_sequence)} nodes.")

    def render_tags(self):
        self.tags_text.configure(state="normal")
        self.tags_text.delete("1.0", tk.END)
        self.tag_line_lookup = {}
        if not self.workspace_thread:
            self.tags_text.configure(state="disabled")
            return
        row = 1
        current_type = None
        for tag in self.ordered_tags_grouped(self.threads[self.workspace_thread]):
            if tag["type"] != current_type:
                if current_type is not None:
                    self.tags_text.insert(tk.END, "\n")
                    row += 1
                current_type = tag["type"]
                self.tags_text.insert(tk.END, f"{current_type.upper()}\n")
                row += 1
            text = tag.get("display_text") if tag["type"] in ("concept", "shift", "split") else tag["clean_text"]
            self.tags_text.insert(tk.END, f"  - {tag['ref']} [{tag.get('source', 'explicit')}] {text}\n")
            self.tag_line_lookup[row] = (tag["type"], tag["ref"], tag.get("source", "explicit"))
            row += 1
        self.tags_text.configure(state="disabled")

    def render_relations(self):
        if hasattr(self, "neighborhood_text"):
            self.neighborhood_text.configure(state="normal")
            self.neighborhood_text.delete("1.0", tk.END)
        self.relations_text.configure(state="normal")
        self.relations_text.delete("1.0", tk.END)
        if hasattr(self, "transcript_text"):
            self.transcript_text.configure(state="normal")
            self.transcript_text.delete("1.0", tk.END)
        self.relation_line_lookup = {}
        thread = self.threads.get(self.workspace_thread) if self.workspace_thread else None
        if not thread:
            self.relations_text.configure(state="disabled")
            return

        selected_type = self.relations_view_var.get().strip() or "all"
        relations = self.ordered_relations(thread)
        if selected_type not in ("all", "none"):
            relations = [r for r in relations if r["type"] == selected_type]

        row = 1
        current_type = None
        if not relations:
            if selected_type in ("all", "none"):
                self.relations_text.insert(tk.END, "No relations found.\n")
            else:
                self.relations_text.insert(tk.END, f"No {selected_type} relations found.\n")
            self.relations_text.configure(state="disabled")
            if hasattr(self, "neighborhood_text"):
                self.neighborhood_text.insert(tk.END, "Relations view active.\n")
                self.neighborhood_text.insert(tk.END, self.relations_text.get("1.0", "end").strip())
                self.neighborhood_text.configure(height=8)
                self.neighborhood_text.configure(state="disabled")
            self.status_var.set(self.relations_text.get("1.0", "end").strip())
            return

        for rel in relations:
            if rel["type"] != current_type:
                if current_type is not None:
                    self.relations_text.insert(tk.END, "\n")
                    row += 1
                current_type = rel["type"]
                self.relations_text.insert(tk.END, f"{current_type.upper()}\n")
                row += 1
            stext = choose_meaningful_label(self.line_text_from_ref(rel["source_ref"])) or self.line_text_from_ref(rel["source_ref"])
            ttext = choose_meaningful_label(self.line_text_from_ref(rel["target_ref"])) or self.line_text_from_ref(rel["target_ref"])
            source_kind = rel.get("source", "manual")
            self.relations_text.insert(tk.END, f"  - [{source_kind}] {rel['source_ref']} \"{stext}\" -> {rel['target_ref']} \"{ttext}\"\n")
            self.relation_line_lookup[row] = (rel["type"], rel["source_ref"], rel["target_ref"], source_kind)
            row += 1
        self.relations_text.configure(state="disabled")
        if hasattr(self, "neighborhood_text"):
            self.neighborhood_text.insert(tk.END, "Relations view active.\n")
            if selected_type in ("all", "none"):
                self.neighborhood_text.insert(tk.END, f"Showing all relation types ({len(relations)} edges).")
            else:
                self.neighborhood_text.insert(tk.END, f"Showing {selected_type} relations ({len(relations)} edges).")
            self.neighborhood_text.configure(height=8)
            self.neighborhood_text.configure(state="disabled")
        if selected_type in ("all", "none"):
            self.status_var.set(f"Relations view. Showing all relation types ({len(relations)} edges).")
        else:
            self.status_var.set(f"Relations view. Showing {selected_type} relations ({len(relations)} edges).")

    def render_preview(self):
        thread = self.current_thread()
        content = [self.make_thread_preview(thread)] if thread["chunks"] else [f"# {thread['title']}\n\nNo transcript imported yet."]
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", "\n".join(content))
        self.preview_text.configure(state="disabled")
