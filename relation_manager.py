import re
import tkinter as tk
from tkinter import messagebox

from constants import RELATION_OPTIONS, RELATION_HIGHLIGHT_OPTIONS
from dialogs import RelationEditDialog


class RelationMixin:
    def set_relation_source(self):
        if not self.selected_line_ref:
            messagebox.showinfo("Select a line", "Click a transcript line to use as source.")
            return
        self.selected_source_ref = self.selected_line_ref
        active_view = self.active_view()
        if active_view in ("Transcript", "Raw"):
            yview = None
            try:
                yview = self.transcript_text.yview()
            except Exception:
                yview = None
            self.render_transcript()
            if yview is not None:
                try:
                    self.transcript_text.yview_moveto(yview[0])
                except Exception:
                    pass
            self.mark_selected_line(self.selected_line_ref, False)
        self.status_var.set(f"Source set to {self.selected_source_ref}.")

    def clear_relation_source(self):
        self.selected_source_ref = None
        active_view = self.active_view()
        if active_view in ("Transcript", "Raw"):
            yview = None
            try:
                yview = self.transcript_text.yview()
            except Exception:
                yview = None
            self.render_transcript()
            if yview is not None:
                try:
                    self.transcript_text.yview_moveto(yview[0])
                except Exception:
                    pass
            if self.selected_line_ref:
                self.mark_selected_line(self.selected_line_ref, False)
        self.status_var.set("Cleared source.")

    def add_relation(self):
        if self.mode != "workspace" or not self.workspace_thread or not self.selected_source_ref or not self.selected_line_ref:
            return
        if self.selected_source_ref == self.selected_line_ref:
            messagebox.showinfo("Different lines", "Source and target must be different.")
            return
        thread = self.threads[self.workspace_thread]
        rel = {"type": self.relation_var.get(), "source_ref": self.selected_source_ref, "target_ref": self.selected_line_ref, "source": "manual"}
        if rel in thread["relations"]:
            self.status_var.set("Relation already exists.")
            return

        active_view = self.active_view()
        current_ref = self.selected_line_ref
        yview = None
        if active_view in ("Transcript", "Raw") and hasattr(self, "transcript_text"):
            try:
                yview = self.transcript_text.yview()
            except Exception:
                yview = None

        thread["relations"].append(rel)
        self.update_left_summary()
        self.render_current_view()

        if active_view in ("Transcript", "Raw") and current_ref and hasattr(self, "transcript_text"):
            if yview is not None:
                try:
                    self.transcript_text.yview_moveto(yview[0])
                except Exception:
                    pass
            self.mark_selected_line(current_ref, False)

        self.status_var.set(f"Added relation {rel['type']}.")

    def edit_relation(self):
        if self.mode != "workspace" or not self.workspace_thread:
            return
        info = self.selected_relation_info
        if not info:
            messagebox.showinfo("Select relation", "Double-click a relation in Relations view first.")
            return
        rel_type, source_ref, target_ref, rel_source = info
        if rel_source == "auto":
            messagebox.showinfo("Auto relation", "Edit is currently for manual relations only.")
            return
        thread = self.threads[self.workspace_thread]
        rel = None
        for r in thread["relations"]:
            if r["type"] == rel_type and r["source_ref"] == source_ref and r["target_ref"] == target_ref:
                rel = r
                break
        if not rel:
            return
        def save(new_type, new_target):
            if not re.match(r"^C\d+:L\d+$", new_target):
                messagebox.showinfo("Invalid ref", "Use format like C1:L12.")
                return
            rel["type"] = new_type
            rel["target_ref"] = new_target
            self.update_left_summary()
            self.render_current_view()
            self.status_var.set("Updated relation.")
        RelationEditDialog(self.root, rel, save)

    def remove_relation(self):
        if self.mode != "workspace" or not self.workspace_thread:
            return
        info = self.selected_relation_info
        if not info:
            messagebox.showinfo("Select relation", "Double-click a relation in Relations view first.")
            return
        rel_type, source_ref, target_ref, rel_source = info
        thread = self.threads[self.workspace_thread]
        pool = "auto_relations" if rel_source == "auto" else "relations"
        before = len(thread[pool])
        thread[pool] = [r for r in thread[pool] if not (r["type"] == rel_type and r["source_ref"] == source_ref and r["target_ref"] == target_ref)]
        self.update_left_summary()
        self.render_current_view()
        self.status_var.set("Removed relation." if len(thread[pool]) < before else "No relation removed.")

    def ref_matches_relation_filter(self, ref):
        selected = self.relation_filter_var.get()
        if selected == "none":
            return False
        rels = self.relations_for_ref(ref)
        if selected == "all":
            return bool(rels)
        return any(r["type"] == selected for r in rels)

    def build_relation_groups(self):
        if not self.workspace_thread:
            return []
        selected = self.relation_filter_var.get()
        if selected in ("none", "all"):
            return []
        items = []
        for rel in self.ordered_relations(self.threads[self.workspace_thread]):
            if rel["type"] == selected:
                items.append((rel["source_ref"], rel["target_ref"]))
        return items

    def current_relation_group(self):
        groups = self.build_relation_groups()
        if not groups:
            return None
        self.relation_group_index %= len(groups)
        return groups[self.relation_group_index]

    def step_relation_group(self, step):
        groups = self.build_relation_groups()
        if not groups:
            return
        self.relation_group_index = (self.relation_group_index + step) % len(groups)
        self.render_transcript()

    def relation_edges_for_selected_line(self, direction):
        if not self.workspace_thread or not self.selected_line_ref:
            return [], None
        rel_type = self.chains_view_var.get().strip() or "none"
        visible_rel = self.relation_display_var.get().strip()
        if visible_rel in RELATION_OPTIONS:
            rel_type = visible_rel
            self.chains_view_var.set(rel_type)
        if rel_type in ("none", "all"):
            return [], rel_type
        matches = []
        for rel in self.ordered_relations(self.threads[self.workspace_thread]):
            if rel["type"] != rel_type:
                continue
            if direction == "back" and rel["target_ref"] == self.selected_line_ref:
                matches.append(rel)
            elif direction == "forward" and rel["source_ref"] == self.selected_line_ref:
                matches.append(rel)
        return matches, rel_type

    def outgoing_relations_for_ref(self, ref, rel_type_filter=None):
        if not self.workspace_thread:
            return []
        items = []
        for rel in self.ordered_relations(self.threads[self.workspace_thread]):
            if rel["source_ref"] != ref:
                continue
            if rel_type_filter not in (None, "all") and rel["type"] != rel_type_filter:
                continue
            items.append(rel)
        items.sort(key=lambda r: (self.ref_sort_key(r["target_ref"]), r["type"], r.get("source", "manual")))
        return items

    def incoming_relations_for_ref(self, ref, rel_type_filter=None):
        if not self.workspace_thread:
            return []
        items = []
        for rel in self.ordered_relations(self.threads[self.workspace_thread]):
            if rel["target_ref"] != ref:
                continue
            if rel_type_filter not in (None, "all") and rel["type"] != rel_type_filter:
                continue
            items.append(rel)
        items.sort(key=lambda r: (self.ref_sort_key(r["source_ref"]), r["type"], r.get("source", "manual")))
        return items

    def relation_graph_for_type(self, rel_type):
        incoming = {}
        outgoing = {}
        if not self.workspace_thread:
            return incoming, outgoing
        for rel in self.ordered_relations(self.threads[self.workspace_thread]):
            if rel["type"] != rel_type:
                continue
            s = rel["source_ref"]
            t = rel["target_ref"]
            outgoing.setdefault(s, []).append(t)
            incoming.setdefault(t, []).append(s)
            incoming.setdefault(s, incoming.get(s, []))
            outgoing.setdefault(t, outgoing.get(t, []))
        return incoming, outgoing

    def mixed_chains_for_thread(self, include_types=None):
        """DFS across all (or specified) relation types. Returns list of
        {"nodes": [ref, ...], "edges": [rtype, ...]} where len(edges) == len(nodes)-1."""
        if not self.workspace_thread:
            return []

        relations = self.ordered_relations(self.threads[self.workspace_thread])
        if include_types:
            relations = [r for r in relations if r["type"] in include_types]
        if not relations:
            return []

        # outgoing: ref -> list of (target_ref, rel_type), sorted by target ref
        outgoing = {}
        all_nodes = set()
        for rel in relations:
            s, t, rtype = rel["source_ref"], rel["target_ref"], rel["type"]
            outgoing.setdefault(s, []).append((t, rtype))
            all_nodes.add(s)
            all_nodes.add(t)
        for ref in outgoing:
            outgoing[ref].sort(key=lambda x: self.ref_sort_key(x[0]))

        # Only start DFS from true roots: nodes with no incoming edges.
        # This prevents generating redundant sub-chains from intermediate nodes.
        all_targets = {t for (t, _) in (pair for pairs in outgoing.values() for pair in pairs)}
        root_nodes = sorted([n for n in all_nodes if n not in all_targets], key=self.ref_sort_key)
        if not root_nodes:
            root_nodes = sorted(all_nodes, key=self.ref_sort_key)  # fallback if graph has cycles

        chains = []

        def dfs(node, path_nodes, path_edges, seen):
            outs = [(t, rt) for (t, rt) in outgoing.get(node, []) if t not in seen]
            if not outs:
                if len(path_nodes) >= 2:
                    chains.append({"nodes": list(path_nodes), "edges": list(path_edges)})
                return
            for (nxt, rtype) in outs:
                dfs(nxt, path_nodes + [nxt], path_edges + [rtype], seen | {nxt})

        for node in root_nodes:
            dfs(node, [node], [], {node})

        # De-duplicate
        seen_keys = set()
        unique = []
        for chain in chains:
            key = tuple(chain["nodes"])
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(chain)

        # Keep only maximal (not a prefix of a longer chain)
        node_tuples = [tuple(c["nodes"]) for c in unique]
        maximal = []
        for i, chain in enumerate(unique):
            ct = node_tuples[i]
            is_prefix = any(len(ot) > len(ct) and ot[:len(ct)] == ct for ot in node_tuples)
            if not is_prefix:
                maximal.append(chain)

        maximal.sort(key=lambda c: tuple(self.ref_sort_key(x) for x in c["nodes"]))
        return maximal

    def maximal_chains_for_relation_type(self, rel_type):
        if not self.workspace_thread:
            return []

        relations = [
            r for r in self.ordered_relations(self.threads[self.workspace_thread])
            if r["type"] == rel_type
        ]
        if not relations:
            return []

        outgoing = {}
        incoming = {}

        for rel in relations:
            s = rel["source_ref"]
            t = rel["target_ref"]
            outgoing.setdefault(s, []).append(t)
            incoming.setdefault(t, []).append(s)
            outgoing.setdefault(t, [])
            incoming.setdefault(s, [])

        for node in outgoing:
            outgoing[node] = sorted(outgoing[node], key=self.ref_sort_key)
        for node in incoming:
            incoming[node] = sorted(incoming[node], key=self.ref_sort_key)

        nodes = sorted(set(outgoing.keys()) | set(incoming.keys()), key=self.ref_sort_key)
        chains = []

        def dfs(node, path, seen):
            outs = outgoing.get(node, [])
            if not outs:
                chains.append(path[:])
                return

            extended = False
            for nxt in outs:
                if nxt in seen:
                    continue
                extended = True
                dfs(nxt, path + [nxt], seen | {nxt})

            if not extended:
                chains.append(path[:])

        # Start from all nodes so short valid paths also count.
        for node in nodes:
            dfs(node, [node], {node})

        # Keep only actual relation paths (length >= 2).
        chains = [c for c in chains if len(c) >= 2]

        # De-duplicate exact duplicates.
        unique = []
        seen = set()
        for chain in chains:
            key = tuple(chain)
            if key not in seen:
                seen.add(key)
                unique.append(chain)

        # Keep only sink-maximal paths: paths that cannot be extended further
        # on the right. This preserves chains like L2→L3→L4 while also keeping
        # branching examples such as L7→L8 and L7→L9.
        maximal = []
        for chain in unique:
            is_prefix_of_longer = False
            for other in unique:
                if len(other) > len(chain) and other[:len(chain)] == chain:
                    is_prefix_of_longer = True
                    break
            if not is_prefix_of_longer:
                maximal.append(chain)

        maximal.sort(key=lambda c: tuple(self.ref_sort_key(x) for x in c))
        return maximal

    def refresh_after_relation_edit(self):
        self.relation_group_index = 0
        if self.relation_filter_var.get() in ("none", "all"):
            self.selected_source_ref = None
            self.current_highlight_ref = None
            self.clear_relation_highlights()

        view = self.active_view()
        if view in ("Transcript", "Raw"):
            self.render_transcript()
        elif view == "Chains":
            self.render_chains()
        else:
            self.render_main()

        if self.relation_filter_var.get() in ("none", "all"):
            self.clear_relation_highlights()

    def on_relation_filter_selected(self, event=None):
        # Use the widget's visible value as the source of truth.
        if event is not None:
            try:
                self.relation_display_var.set(event.widget.get().strip())
            except Exception:
                pass
        self.apply_visible_relation_selection()

    def apply_visible_relation_selection(self):
        selected = self.relation_display_var.get().strip()
        if not selected:
            try:
                selected = self.relation_filter_combo.get().strip()
            except Exception:
                selected = ""

        view = self.active_view()
        self.relation_group_index = 0
        self.local_relation_jump_state = None
        self.clear_relation_highlights()

        if view == "Chains":
            allowed = ["none", "mixed"] + RELATION_OPTIONS
            selected = selected if selected in allowed else "none"
            self.chains_view_var.set(selected)
            self.render_current_view()
            return

        if view == "Tree":
            allowed = ["all"] + RELATION_OPTIONS
            selected = selected if selected in allowed else "all"
            self.tree_view_var.set(selected)
            self.render_current_view()
            return

        if view == "Relations":
            allowed = ["all"] + RELATION_OPTIONS
            selected = selected if selected in allowed else "all"
            self.relations_view_var.set(selected)
            self.render_current_view()
            return

        allowed = RELATION_HIGHLIGHT_OPTIONS
        self.relation_filter_var.set(selected if selected in allowed else "none")
        self.sync_relation_controls_for_view()
        self.on_highlight_changed()

    def on_relation_display_var_changed(self, *_):
        return

    def clear_relation_highlights(self):
        if not hasattr(self, "transcript_text"):
            return
        for tag in ("relationmatch", "relationmatch_prefix", "relation_source", "relation_source_prefix"):
            try:
                self.transcript_text.tag_remove(tag, "1.0", tk.END)
            except Exception:
                pass
