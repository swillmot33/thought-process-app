import tkinter as tk

from constants import RELATION_OPTIONS, RELATION_COLORS
from utils import choose_meaningful_label, clean_tag_markers


class GraphRendererMixin:
    def render_graph(self):
        if not hasattr(self, "graph_canvas"):
            return
        canvas = self.graph_canvas
        canvas.delete("all")
        self.graph_positions = {}
        self.graph_item_to_ref = {}
        self.graph_node_bounds = {}
        self.graph_group_map = {}
        self.graph_edges = []

        if hasattr(self, "neighborhood_text"):
            self.neighborhood_text.configure(state="normal")
            self.neighborhood_text.delete("1.0", tk.END)

        if not self.workspace_thread:
            if hasattr(self, "neighborhood_text"):
                self.neighborhood_text.insert(tk.END, "Graph view active. No thread open.")
                self.neighborhood_text.configure(height=6)
                self.neighborhood_text.configure(state="disabled")
            self.status_var.set("Graph view. No thread open.")
            return

        thread = self.threads[self.workspace_thread]
        ordered = self.ordered_lines(thread)
        if not ordered:
            if hasattr(self, "neighborhood_text"):
                self.neighborhood_text.insert(tk.END, "Graph view active. No transcript lines available.")
                self.neighborhood_text.configure(height=6)
                self.neighborhood_text.configure(state="disabled")
            self.status_var.set("Graph view. No transcript lines available.")
            return

        valid_refs = {line["ref"] for line in ordered}
        root_ref = self.graph_root_ref if self.graph_root_ref in valid_refs else ordered[0]["ref"]
        if self.selected_line_ref not in valid_refs:
            self.selected_line_ref = root_ref
        rel_type = self.graph_relation_filter()
        rel_filter = None if rel_type == "all" else rel_type

        nodes, edges, used_fallback = self.collect_graph_component(root_ref, rel_filter, max_nodes=60)
        if edges and not any(root_ref in (sref, tref) for sref, tref, _ in edges):
            connected = sorted({sref for sref, _tref, _rtype in edges} | {tref for _sref, tref, _rtype in edges}, key=self.ref_sort_key)
            if connected:
                root_ref = connected[0]
                nodes, edges, used_fallback = self.collect_graph_component(root_ref, rel_filter, max_nodes=60)
        self.graph_root_ref = root_ref  # always store the real underlying ref
        node_infos = {}

        if self.graph_mode == "collapsed":
            ordered_nodes, edges, node_infos, collapsed_root, concept_nodes = self.build_collapsed_graph(root_ref, nodes, edges)
            rank, xslot = self.collapsed_graph_layout(root_ref, ordered_nodes, edges, node_infos, collapsed_root, concept_nodes)
            render_nodes = ordered_nodes
            root_render_ref = collapsed_root
        else:
            # --- Local collapse in expanded mode ---
            # Build lookup maps for local-collapse double-click routing.
            rephrase_chains, example_groups = self._collect_local_collapse_groups(nodes, edges)
            # graph_ref_to_group_key: any member ref -> the group key it belongs to (for collapsing on dbl-click)
            self.graph_ref_to_group_key = {}
            for gk, chain in rephrase_chains.items():
                for r in chain:
                    self.graph_ref_to_group_key[r] = gk
            for gk, info in example_groups.items():
                for r in info["refs"]:
                    self.graph_ref_to_group_key[r] = gk
            # graph_local_preview_map: preview_placeholder_id -> group_key (populated during draw, used in dbl-click)
            self.graph_local_preview_map = {}

            # Build the effective node/edge set for this render pass.
            # Nodes suppressed by local collapse are removed; a placeholder preview node takes their place.
            suppressed_refs = set()       # raw refs hidden behind a preview node
            preview_nodes = {}            # placeholder_key -> {"label": str, "refs": [raw refs], "group_key": str,
                                          #                     "type": "rephrase_preview"|"example_preview",
                                          #                     "anchor_ref": ref that stays visible for edge routing}
            # For rephrase chains: collapse all members to a single preview at the position of chain[0].
            for gk, chain in rephrase_chains.items():
                if gk not in self.graph_local_collapsed:
                    continue
                label = self._rephrase_preview_label(chain)
                pk = f"LOCAL_PREVIEW:{gk}"
                anchor = chain[0]
                preview_nodes[pk] = {"label": label, "refs": list(chain), "group_key": gk,
                                     "type": "rephrase_preview", "anchor_ref": anchor}
                for r in chain:
                    suppressed_refs.add(r)

            # For example groups: collapse all example children to a single preview below the concept.
            for gk, info in example_groups.items():
                if gk not in self.graph_local_collapsed:
                    continue
                label = self._example_preview_label(info["concept"], info["refs"])
                pk = f"LOCAL_PREVIEW:{gk}"
                preview_nodes[pk] = {"label": label, "refs": list(info["refs"]), "group_key": gk,
                                     "type": "example_preview", "anchor_ref": info["concept"],
                                     "concept": info["concept"]}
                for r in info["refs"]:
                    suppressed_refs.add(r)

            # Effective nodes: original minus suppressed, plus preview placeholders.
            effective_nodes = [n for n in nodes if n not in suppressed_refs] + list(preview_nodes.keys())

            # Rewrite edges: any edge touching a suppressed ref is rerouted through the preview placeholder.
            def remap(ref):
                """Return the placeholder key if ref is suppressed, else ref itself."""
                for pk, pinfo in preview_nodes.items():
                    if ref in pinfo["refs"]:
                        return pk
                return ref

            effective_edges = []
            seen_edges = set()
            for sref, tref, rtype in edges:
                ns = remap(sref)
                nt = remap(tref)
                if ns == nt:
                    continue  # internal to a collapsed group — drop
                ek = (ns, nt, rtype)
                if ek not in seen_edges:
                    effective_edges.append(ek)
                    seen_edges.add(ek)

            # Merge preview node infos into node_infos for drawing.
            for pk, pinfo in preview_nodes.items():
                node_infos[pk] = {"type": pinfo["type"], "refs": pinfo["refs"], "label": pinfo["label"]}

            # Layout using effective nodes/edges.
            # If root_ref was suppressed into a preview, use that preview as the layout root.
            if root_ref in suppressed_refs:
                layout_root = next(
                    (pk for pk, pinfo in preview_nodes.items() if root_ref in pinfo["refs"]),
                    effective_nodes[0] if effective_nodes else root_ref
                )
            else:
                layout_root = root_ref
            rank, xslot = self.semantic_graph_layout(layout_root, effective_nodes, effective_edges)
            render_nodes = sorted(
                effective_nodes,
                key=lambda r: self.ref_sort_key(r) if not r.startswith("LOCAL_PREVIEW:") else (999, hash(r) & 0xFFFF)
            )
            root_render_ref = layout_root
            edges = effective_edges

        zoom = self.effective_graph_zoom(rank, xslot)
        slot_x_gap = max(95, int(180 * zoom))
        slot_y_gap = max(28, int(72 * zoom))
        top_margin = max(16, int(34 * zoom))
        left_margin = max(32, int(58 * zoom))

        min_slot = min(xslot.values(), default=0)
        ordered_for_draw = sorted(render_nodes, key=lambda r: (rank.get(r, 0), xslot.get(r, 0), str(r)))
        for ref in ordered_for_draw:
            x = left_margin + (xslot[ref] - min_slot) * slot_x_gap + max(42, int(70 * zoom))
            y = top_margin + rank[ref] * slot_y_gap
            self.graph_positions[ref] = (x, y)

        for ref, (x, y) in self.graph_positions.items():
            if ref in node_infos:
                node_text = node_infos[ref]["label"]
            else:
                node_text = self.graph_node_text(ref)

            # Determine visual style: preview nodes get a distinct collapsed appearance.
            ntype = node_infos.get(ref, {}).get("type", "line")
            is_preview = ntype in ("rephrase_preview", "example_preview")
            preview_font = ("TkDefaultFont", max(8, int(10 * zoom)), "italic") if is_preview else ("Menlo", max(7, int(10 * zoom)))
            text_id = canvas.create_text(x, y, text=node_text, width=max(100, int(175 * zoom)), justify="center", font=preview_font, tags=("graph_node",))
            bbox = canvas.bbox(text_id)
            if not bbox:
                continue
            pad_x = max(6, int(10 * zoom))
            pad_y = max(4, int(8 * zoom))
            underlying_refs = node_infos.get(ref, {}).get("refs", [ref])
            is_selected = self.selected_line_ref in underlying_refs
            if is_preview:
                fill = "#e8d8f5" if is_selected else "#f0e8fb"   # soft lavender for preview boxes
                outline = "#7a46b5" if is_selected else "#a07acc"
                dash = (4, 3)
            else:
                fill = "#d8efff" if is_selected else "#f4f6fb"
                outline = "#3489c9" if is_selected else "#8693a5"
                dash = None
            rect_kwargs = dict(fill=fill, outline=outline, width=2, tags=("graph_node",))
            if dash:
                rect_kwargs["dash"] = dash
            rect_id = canvas.create_rectangle(bbox[0]-pad_x, bbox[1]-pad_y, bbox[2]+pad_x, bbox[3]+pad_y, **rect_kwargs)
            canvas.tag_raise(text_id, rect_id)
            self.graph_item_to_ref[text_id] = ref
            self.graph_item_to_ref[rect_id] = ref
            self.graph_node_bounds[ref] = (bbox[0]-pad_x, bbox[1]-pad_y, bbox[2]+pad_x, bbox[3]+pad_y)
            self.graph_group_map[ref] = underlying_refs
            # Register preview placeholder so double-click can expand it.
            if is_preview and self.graph_mode != "collapsed":
                gk = node_infos[ref].get("group_key") or (ref.replace("LOCAL_PREVIEW:", "") if ref.startswith("LOCAL_PREVIEW:") else None)
                if gk is None and ref.startswith("LOCAL_PREVIEW:"):
                    gk = ref[len("LOCAL_PREVIEW:"):]
                if gk:
                    self.graph_local_preview_map[ref] = gk

        ordered_edges = sorted(edges, key=lambda edge: ({"rephrase": 0, "split-from": 1, "example": 2, "supports": 3}.get(edge[2], 9), rank.get(edge[0], 0), str(edge[0]), str(edge[1])))
        for sref, tref, rtype in ordered_edges:
            sbox = self.graph_node_bounds.get(sref)
            tbox = self.graph_node_bounds.get(tref)
            if not sbox or not tbox:
                continue
            color = self.relation_label_color(rtype)
            points, label_pt = self._edge_anchor_points(sbox, tbox, rtype, sref=sref, tref=tref)
            line_id = canvas.create_line(*points, width=max(1.4, 2.2 * zoom), fill=color, arrow=tk.LAST, arrowshape=(max(8, int(13 * zoom)), max(9, int(15 * zoom)), max(4, int(6 * zoom))), smooth=False)
            self.graph_edges.append(line_id)
            lx, ly = label_pt
            label_id = canvas.create_text(lx, ly - max(5, int(8 * zoom)), text=rtype, font=("TkDefaultFont", max(7, int(9 * zoom)), "bold"), fill=color)
            lb = canvas.bbox(label_id)
            if lb:
                bg = canvas.create_rectangle(lb[0]-4, lb[1]-2, lb[2]+4, lb[3]+2, fill="#ffffff", outline="")
                canvas.tag_lower(bg, label_id)
                canvas.tag_lower(bg, line_id)
            canvas.tag_lower(line_id)

        if rank:
            grouped = {}
            root_rank = rank.get(root_render_ref)
            for ref, ref_rank in rank.items():
                grouped.setdefault(ref_rank, []).append(ref)
            for ref_rank, refs in grouped.items():
                visible = [ref for ref in refs if ref in self.graph_node_bounds]
                if not visible:
                    continue
                y = min(self.graph_node_bounds[ref][1] for ref in visible) - 16
                label = "Selected" if ref_rank == root_rank else f"Level {ref_rank}"
                canvas.create_text(28, y, text=label, anchor="w", font=("TkDefaultFont", max(8, int(10 * zoom)), "bold"), fill="#5b5b5b")

        all_boxes = list(self.graph_node_bounds.values())
        if all_boxes:
            min_x = min(b[0] for b in all_boxes) - 70
            min_y = min(b[1] for b in all_boxes) - 28
            max_x = max(b[2] for b in all_boxes) + 70
            max_y = max(b[3] for b in all_boxes) + 54
            canvas.configure(scrollregion=(min_x, min_y, max_x, max_y))
            if self.graph_fit_mode:
                total_width = max_x - min_x
                viewport_width = max(canvas.winfo_width(), 700)
                x_offset = max(0, ((min_x + max_x) / 2 - viewport_width / 2 - min_x) / max(1, total_width))
                canvas.xview_moveto(x_offset)
                canvas.yview_moveto(0.0)

        if hasattr(self, "neighborhood_text"):
            # Show selected node's relations, falling back to root if nothing selected
            display_ref = self.selected_line_ref if self.selected_line_ref in (nodes if isinstance(nodes, set) else set(render_nodes)) else root_ref
            incoming = self.incoming_relations_for_ref(display_ref, rel_filter)
            outgoing = self.outgoing_relations_for_ref(display_ref, rel_filter)
            self.neighborhood_text.insert(tk.END, f"Graph root: {root_ref}\n")
            self.neighborhood_text.insert(tk.END, f"Selected: {display_ref}\n")
            self.neighborhood_text.insert(tk.END, f"Relation filter: {rel_type}\n")
            self.neighborhood_text.insert(tk.END, f"Visible nodes: {len(render_nodes)}    Visible edges: {len(edges)}\n")
            if used_fallback:
                self.neighborhood_text.insert(tk.END, "Selected line has no direct graph edges; showing thread graph.\n")
            self.neighborhood_text.insert(tk.END, f"Incoming: {len(incoming)}    Outgoing: {len(outgoing)}\n")
            if incoming:
                for r in incoming:
                    self.neighborhood_text.insert(tk.END, f"  ← ({r['type']}) {r['source_ref']}\n")
            if outgoing:
                for r in outgoing:
                    self.neighborhood_text.insert(tk.END, f"  → ({r['type']}) {r['target_ref']}\n")
            self.neighborhood_text.insert(tk.END, f"\nZoom: {zoom:.2f}x\n")
            collapsed_count = len(self.graph_local_collapsed) if self.graph_mode == "expanded" else 0
            hint = f"Double-click to collapse/expand. ({collapsed_count} locally collapsed)" if self.graph_mode == "expanded" else "Use Expand button to return to expanded mode."
            self.neighborhood_text.insert(tk.END, hint + "\n")
            self.neighborhood_text.configure(height=8)
            self.neighborhood_text.configure(state="disabled")

        suffix = " (thread graph)" if used_fallback else ""
        self.status_var.set(f"Graph: {rel_type} from {root_ref}{suffix} | {self.graph_mode} | {zoom:.2f}x")

    def semantic_graph_layout(self, root_ref, nodes, edges):
        outgoing_by_type = {rtype: {} for rtype in RELATION_OPTIONS}
        incoming_by_type = {rtype: {} for rtype in RELATION_OPTIONS}
        for sref, tref, rtype in edges:
            outgoing_by_type.setdefault(rtype, {}).setdefault(sref, []).append(tref)
            incoming_by_type.setdefault(rtype, {}).setdefault(tref, []).append(sref)

        for rtype in list(outgoing_by_type.keys()):
            for ref in outgoing_by_type[rtype]:
                outgoing_by_type[rtype][ref] = sorted(outgoing_by_type[rtype][ref], key=self.ref_sort_key)
        for rtype in list(incoming_by_type.keys()):
            for ref in incoming_by_type[rtype]:
                incoming_by_type[rtype][ref] = sorted(incoming_by_type[rtype][ref], key=self.ref_sort_key)

        def rephrase_chain_from_focus(focus_ref):
            chain = [focus_ref]
            cursor = focus_ref
            visited = {focus_ref}
            while True:
                prevs = incoming_by_type.get('rephrase', {}).get(cursor, [])
                if not prevs:
                    break
                prev_ref = prevs[0]
                if prev_ref in visited:
                    break
                chain.insert(0, prev_ref)
                visited.add(prev_ref)
                cursor = prev_ref
            cursor = focus_ref
            while True:
                nxts = outgoing_by_type.get('rephrase', {}).get(cursor, [])
                if not nxts:
                    break
                next_ref = nxts[0]
                if next_ref in visited:
                    break
                chain.append(next_ref)
                visited.add(next_ref)
                cursor = next_ref
            return chain

        rephrase_nodes = {sref for sref, _tref, rtype in edges if rtype == 'rephrase'} | {tref for _sref, tref, rtype in edges if rtype == 'rephrase'}
        chain = rephrase_chain_from_focus(root_ref)
        if len(chain) == 1 and root_ref not in rephrase_nodes and rephrase_nodes:
            starts = [ref for ref in rephrase_nodes if not incoming_by_type.get('rephrase', {}).get(ref)]
            starts = sorted(starts, key=self.ref_sort_key)
            best = []
            for start in starts:
                candidate = rephrase_chain_from_focus(start)
                if len(candidate) > len(best):
                    best = candidate
            if best:
                chain = best
        if not chain:
            chain = [root_ref]

        rank = {}
        xslot = {}
        branch_side = {}
        parent_group = {}
        example_parent = {}
        example_order = {}
        occupied = set()

        REPHRASE_GAP = 3
        SPLIT_GAP = 2
        EXAMPLE_STEP = 1
        EXAMPLE_INDENT = 0.6

        def reserve(ref, x, y, side=None, group=None):
            xslot[ref] = x
            rank[ref] = y
            if side is not None:
                branch_side[ref] = side
            if group is not None:
                parent_group[ref] = group
            occupied.add((round(x, 2), y))

        def next_free_x(target_x, target_rank, preferred_step=0.45):
            x = target_x
            if (round(x, 2), target_rank) not in occupied:
                return x
            attempt = 1
            while attempt < 60:
                for sign in (1, -1):
                    candidate = target_x + sign * preferred_step * attempt
                    if (round(candidate, 2), target_rank) not in occupied:
                        return candidate
                attempt += 1
            return target_x

        for idx, ref in enumerate(chain):
            reserve(ref, 0.0, idx * REPHRASE_GAP, side=0, group=ref)

        def max_example_rank_for(source_ref):
            ranks = [rank[ref] for ref, parent in example_parent.items() if parent == source_ref and ref in rank]
            return max(ranks) if ranks else rank[source_ref]

        def place_example_children(source_ref):
            kids = [ref for ref in outgoing_by_type.get('example', {}).get(source_ref, []) if ref not in rank]
            if not kids:
                return
            side = branch_side.get(source_ref, 0)
            if side == 0:
                side = 1
            target_x = xslot[source_ref] + (EXAMPLE_INDENT if side > 0 else -EXAMPLE_INDENT)
            base_rank = rank[source_ref] + EXAMPLE_STEP
            for idx, ref in enumerate(kids):
                target_rank = base_rank + idx * EXAMPLE_STEP
                reserve(ref, next_free_x(target_x, target_rank, 0.15), target_rank, side=side, group=parent_group.get(source_ref, source_ref))
                example_parent[ref] = source_ref
                example_order[ref] = idx

        def place_split_children(source_ref):
            kids = [ref for ref in outgoing_by_type.get('split-from', {}).get(source_ref, []) if ref not in rank]
            if not kids:
                return
            parent_x = xslot[source_ref]
            child_anchor_rank = max(rank[source_ref] + SPLIT_GAP, max_example_rank_for(source_ref) + SPLIT_GAP)
            offsets = self.spread_offsets(len(kids), 4.8)
            if len(kids) == 2:
                offsets = [-2.4, 2.4]
            for ref, offset in zip(kids, offsets):
                side = -1 if offset < 0 else 1
                reserve(ref, next_free_x(parent_x + offset, child_anchor_rank, 0.55), child_anchor_rank, side=side, group=ref)
                place_example_children(ref)

        for ref in list(chain):
            place_example_children(ref)
            place_split_children(ref)

        changed = True
        loops = 0
        while changed and loops < 10:
            changed = False
            loops += 1
            current_refs = sorted(list(rank.keys()), key=lambda r: (rank[r], xslot[r], self.ref_sort_key(r)))
            for ref in current_refs:
                before = len(rank)
                place_example_children(ref)
                place_split_children(ref)
                if len(rank) != before:
                    changed = True

        support_targets = sorted({tref for sref, tref, rtype in edges if rtype == 'supports' and sref in rank}, key=self.ref_sort_key)
        for tref in support_targets:
            if tref in rank:
                continue
            sources = [sref for sref in incoming_by_type.get('supports', {}).get(tref, []) if sref in rank]
            if not sources:
                continue
            source_depths = []
            for sref in sources:
                source_depths.append(max(rank[sref], max_example_rank_for(sref)))
            target_rank = max(source_depths) + SPLIT_GAP
            target_x = sum(xslot[sref] for sref in sources) / max(1, len(sources))
            reserve(tref, next_free_x(target_x, target_rank, 0.35), target_rank, side=0, group=tref)

        remaining = [ref for ref in sorted(nodes, key=self.ref_sort_key) if ref not in rank]
        safety = 0
        while remaining and safety < 24:
            safety += 1
            progressed = False
            for ref in list(remaining):
                placed = False
                for sref, tref, rtype in edges:
                    if tref != ref or sref not in rank:
                        continue
                    if rtype == 'rephrase':
                        reserve(ref, next_free_x(xslot[sref], rank[sref] + REPHRASE_GAP, 0.35), rank[sref] + REPHRASE_GAP, side=branch_side.get(sref, 0), group=parent_group.get(sref, sref))
                    elif rtype == 'split-from':
                        side = -1 if branch_side.get(sref, 0) <= 0 else 1
                        reserve(ref, next_free_x(xslot[sref] + (2.4 * side), rank[sref] + SPLIT_GAP, 0.45), rank[sref] + SPLIT_GAP, side=side, group=ref)
                    elif rtype == 'example':
                        side = branch_side.get(sref, 0) or 1
                        target_x = xslot[sref] + (EXAMPLE_INDENT if side > 0 else -EXAMPLE_INDENT)
                        target_rank = max_example_rank_for(sref) + EXAMPLE_STEP
                        reserve(ref, next_free_x(target_x, target_rank, 0.15), target_rank, side=side, group=parent_group.get(sref, sref))
                        example_parent[ref] = sref
                        example_order[ref] = len([x for x, p in example_parent.items() if p == sref and x in rank]) - 1
                    elif rtype == 'supports':
                        reserve(ref, next_free_x(xslot[sref], max(rank[sref], max_example_rank_for(sref)) + SPLIT_GAP, 0.35), max(rank[sref], max_example_rank_for(sref)) + SPLIT_GAP, side=0, group=ref)
                    else:
                        reserve(ref, next_free_x(xslot[sref], rank[sref] + SPLIT_GAP, 0.35), rank[sref] + SPLIT_GAP, side=branch_side.get(sref, 0), group=parent_group.get(sref, sref))
                    placed = True
                    break
                if not placed:
                    for sref, tref, rtype in edges:
                        if sref != ref or tref not in rank:
                            continue
                        reserve(ref, next_free_x(xslot[tref], rank[tref] - REPHRASE_GAP, 0.35), rank[tref] - REPHRASE_GAP, side=branch_side.get(tref, 0), group=parent_group.get(tref, tref))
                        placed = True
                        break
                if placed:
                    remaining.remove(ref)
                    progressed = True
            if not progressed:
                for idx, ref in enumerate(remaining):
                    reserve(ref, float(idx) * 2.5, max(rank.values(), default=0) + REPHRASE_GAP, side=0, group=ref)
                break

        min_rank = min(rank.values()) if rank else 0
        if min_rank < 0:
            for ref in rank:
                rank[ref] -= min_rank

        self.graph_example_parent = example_parent
        self.graph_example_order = example_order
        return rank, xslot

    def collapsed_graph_layout(self, root_ref, ordered_nodes, edges, node_infos, rephrase_node, concept_nodes):
        rank = {}
        xslot = {}
        # Root rephrase summary centered at top
        if rephrase_node in node_infos:
            rank[rephrase_node] = 0
            xslot[rephrase_node] = 0

        # Concepts from split arranged left/right under rephrase summary
        concepts = [n for n in ordered_nodes if node_infos.get(n, {}).get('type') == 'line' and any(e[0] == rephrase_node and e[1] == n and e[2] == 'split-from' for e in edges)]
        if concepts:
            if len(concepts) == 1:
                offsets = [0]
            elif len(concepts) == 2:
                offsets = [-3, 3]
            else:
                offsets = [i*3 for i in range(-(len(concepts)//2), len(concepts)-len(concepts)//2)]
            for c, off in zip(concepts, offsets):
                rank[c] = 2
                xslot[c] = off

        # Example nodes below each concept.
        for n in ordered_nodes:
            info = node_infos.get(n, {})
            if info.get('type') == 'example_group':
                parent = info.get('parent')
                if parent in xslot:
                    rank[n] = 3
                    xslot[n] = xslot[parent] + (1.5 if xslot[parent] <= 0 else -1.5)
        for s, t, r in edges:
            if r == 'example' and node_infos.get(t, {}).get('type') == 'line':
                if s in xslot and t not in xslot:
                    rank[t] = 3
                    xslot[t] = xslot[s] + (1.5 if xslot[s] <= 0 else -1.5)

        # Supports target(s) centered lower. If multiple, spread lightly.
        supports = [n for n in ordered_nodes if any(e[1] == n and e[2] == 'supports' for e in edges)]
        unique_supports = []
        for s in supports:
            if s not in unique_supports and s not in concepts and node_infos.get(s, {}).get('type') == 'line':
                unique_supports.append(s)
        if unique_supports:
            if len(unique_supports) == 1:
                offsets = [0]
            else:
                offsets = [i*3 for i in range(-(len(unique_supports)//2), len(unique_supports)-len(unique_supports)//2)]
            for s, off in zip(unique_supports, offsets):
                rank[s] = 5
                xslot[s] = off

        # Any remaining nodes go under their incoming parent deterministically.
        changed = True
        while changed:
            changed = False
            for s, t, r in edges:
                if s in xslot and t not in xslot:
                    base_rank = rank[s] + (1 if r == 'example' else 2 if r == 'supports' else 2)
                    delta = 0 if r in ('rephrase', 'supports') else (1.5 if xslot[s] <= 0 else -1.5)
                    rank[t] = base_rank
                    xslot[t] = xslot[s] + delta
                    changed = True

        for idx, n in enumerate(ordered_nodes):
            if n not in xslot:
                rank[n] = 7 + idx
                xslot[n] = idx * 2
        return rank, xslot

    def build_collapsed_graph(self, root_ref, nodes, edges):
        """Build a conservative collapsed graph with one global rephrase summary and
        one summary node per multi-example branch. The output is stable and does
        not depend on transient selection state."""
        out = {}
        inc = {}
        for sref, tref, rtype in edges:
            out.setdefault((sref, rtype), []).append(tref)
            inc.setdefault((tref, rtype), []).append(sref)

        # Rephrase chain containing the root, if any.
        chain = [root_ref]
        seen = {root_ref}
        cur = root_ref
        while True:
            prevs = sorted(inc.get((cur, 'rephrase'), []), key=self.ref_sort_key)
            if not prevs or prevs[0] in seen:
                break
            cur = prevs[0]
            chain.insert(0, cur)
            seen.add(cur)
        cur = root_ref
        while True:
            nxts = sorted(out.get((cur, 'rephrase'), []), key=self.ref_sort_key)
            if not nxts or nxts[0] in seen:
                break
            cur = nxts[0]
            chain.append(cur)
            seen.add(cur)

        if len(chain) == 1:
            rephrase_node = root_ref
            node_infos = {root_ref: {"type": "line", "refs": [root_ref], "label": self.graph_node_text(root_ref)}}
        else:
            start_ref = chain[0]
            end_ref = chain[-1]
            key_ref = next((r for r in chain if any(t.get('tag') == 'key phrasing' for t in self.tags_for_ref(r))), chain[-1])
            key_body = choose_meaningful_label(self.line_text_from_ref(key_ref)) or clean_tag_markers(self.line_text_from_ref(key_ref)) or key_ref
            summary = f"{start_ref}–{end_ref}\n{key_body}"
            rephrase_node = f"GROUP:REPHRASE:{start_ref}:{end_ref}"
            node_infos = {rephrase_node: {"type": "rephrase_group", "refs": list(chain), "label": summary}}

        node_order = []
        node_order.append(rephrase_node)
        collapsed_edges = []
        added_edges = set()

        def ensure_line_node(ref):
            if ref not in node_infos:
                node_infos[ref] = {"type": "line", "refs": [ref], "label": self.graph_node_text(ref)}
                node_order.append(ref)
            return ref

        # Split children from any node in the rephrase chain should hang from the single summary node.
        split_children = []
        for cref in chain:
            split_children.extend(out.get((cref, 'split-from'), []))
        split_children = sorted(set(split_children), key=self.ref_sort_key)
        concept_nodes = []
        for child in split_children:
            ensure_line_node(child)
            concept_nodes.append(child)
            ek = (rephrase_node, child, 'split-from')
            if ek not in added_edges:
                collapsed_edges.append(ek)
                added_edges.add(ek)

        # Example summaries per concept.
        for concept in list(concept_nodes):
            kids = sorted(out.get((concept, 'example'), []), key=self.ref_sort_key)
            if not kids:
                continue
            if len(kids) == 1:
                child = ensure_line_node(kids[0])
                ek = (concept, child, 'example')
                if ek not in added_edges:
                    collapsed_edges.append(ek)
                    added_edges.add(ek)
            else:
                first = kids[0]
                first_body = choose_meaningful_label(self.line_text_from_ref(first)) or clean_tag_markers(self.line_text_from_ref(first)) or first
                label = f"{concept}\nExamples [{len(kids)}]\n• {first_body}"
                gid = f"GROUP:EXAMPLE:{concept}"
                node_infos[gid] = {"type": "example_group", "refs": kids, "label": label, "parent": concept}
                node_order.append(gid)
                ek = (concept, gid, 'example')
                if ek not in added_edges:
                    collapsed_edges.append(ek)
                    added_edges.add(ek)

        # Supports target(s) from concepts only.
        support_targets = set()
        for concept in concept_nodes:
            support_targets.update(out.get((concept, 'supports'), []))
        for tgt in sorted(support_targets, key=self.ref_sort_key):
            ensure_line_node(tgt)
            for concept in concept_nodes:
                if tgt in out.get((concept, 'supports'), []):
                    ek = (concept, tgt, 'supports')
                    if ek not in added_edges:
                        collapsed_edges.append(ek)
                        added_edges.add(ek)

        # Preserve any isolated supports from the rephrase chain.
        for cref in chain:
            for tgt in sorted(out.get((cref, 'supports'), []), key=self.ref_sort_key):
                ensure_line_node(tgt)
                ek = (rephrase_node, tgt, 'supports')
                if ek not in added_edges:
                    collapsed_edges.append(ek)
                    added_edges.add(ek)

        ordered_nodes = node_order + [ref for ref in sorted(node_infos.keys(), key=str) if ref not in node_order]
        return ordered_nodes, collapsed_edges, node_infos, rephrase_node, concept_nodes

    def build_graph_neighborhood(self, root_ref, rel_type_filter=None, depth_limit=2):
        nodes, edges = self.collect_graph_component(root_ref, rel_type_filter, max_nodes=max(20, depth_limit * 12))
        levels = {0: [root_ref]}
        seen = {root_ref}
        frontier = [root_ref]
        for depth in range(1, depth_limit + 1):
            next_nodes = []
            for ref in frontier:
                for sref, tref, _rtype in edges:
                    if sref == ref and tref not in seen:
                        next_nodes.append(tref)
                        seen.add(tref)
                    elif tref == ref and sref not in seen:
                        next_nodes.append(sref)
                        seen.add(sref)
            if next_nodes:
                levels[depth] = sorted(next_nodes, key=self.ref_sort_key)
                frontier = levels[depth]
            else:
                break
        return levels, edges

    def collect_graph_component(self, root_ref, rel_type_filter=None, max_nodes=60):
        queue = [root_ref]
        seen = set()
        edge_keys = set()
        edges = []
        while queue and len(seen) < max_nodes:
            ref = queue.pop(0)
            if ref in seen:
                continue
            seen.add(ref)
            rels = self.incoming_relations_for_ref(ref, rel_type_filter) + self.outgoing_relations_for_ref(ref, rel_type_filter)
            rels = sorted(rels, key=lambda r: (self.ref_sort_key(r["source_ref"]), self.ref_sort_key(r["target_ref"]), r["type"]))
            for rel in rels:
                sref = rel["source_ref"]
                tref = rel["target_ref"]
                key = (sref, tref, rel["type"])
                if key not in edge_keys:
                    edge_keys.add(key)
                    edges.append(key)
                other = sref if tref == ref else tref
                if other not in seen and other not in queue and len(seen) + len(queue) < max_nodes:
                    queue.append(other)
        edges = [edge for edge in edges if edge[0] in seen and edge[1] in seen]
        if edges:
            return seen, edges, False
        # Fallback: if the selected line is structurally isolated, show the thread graph instead.
        if self.workspace_thread:
            thread = self.threads[self.workspace_thread]
            all_edges = []
            for rel in self.ordered_relations(thread):
                if rel_type_filter and rel.get("type") != rel_type_filter:
                    continue
                key = (rel["source_ref"], rel["target_ref"], rel["type"])
                if key not in all_edges:
                    all_edges.append(key)
            if all_edges:
                node_set = set()
                trimmed = []
                for key in all_edges:
                    trimmed.append(key)
                    node_set.add(key[0])
                    node_set.add(key[1])
                    if len(node_set) >= max_nodes:
                        break
                trimmed = [edge for edge in trimmed if edge[0] in node_set and edge[1] in node_set]
                return node_set, trimmed, True
        return seen, edges, False

    def graph_relation_filter(self):
        rel_type = self.graph_view_var.get().strip() or "all"
        return rel_type if rel_type in (["all"] + RELATION_OPTIONS) else "all"

    def graph_node_text(self, ref):
        body = choose_meaningful_label(self.line_text_from_ref(ref)) or clean_tag_markers(self.line_text_from_ref(ref)) or ref
        words = body.split()
        if len(words) > 12:
            body = " ".join(words[:12]) + " ..."
        return f"{ref}\n{body}"

    def effective_graph_zoom(self, rank, xslot):
        if not self.graph_fit_mode:
            return self.graph_zoom
        viewport_w = max(self.graph_canvas.winfo_width(), 700)
        viewport_h = max(self.graph_canvas.winfo_height(), 500)
        if not rank or not xslot:
            return self.graph_zoom
        min_slot = min(xslot.values())
        max_slot = max(xslot.values())
        min_rank = min(rank.values())
        max_rank = max(rank.values())
        base_width = (max_slot - min_slot + 1) * 200 + 260
        base_height = (max_rank - min_rank + 1) * 78 + 150
        zoom_w = (viewport_w - 80) / max(base_width, 1)
        zoom_h = (viewport_h - 80) / max(base_height, 1)
        self.graph_zoom = max(0.25, min(1.1, min(zoom_w, zoom_h)))
        return self.graph_zoom

    def spread_offsets(self, count, spacing):
        if count <= 0:
            return []
        if count == 1:
            return [0]
        start = -spacing * (count - 1) / 2
        return [start + i * spacing for i in range(count)]

    def _edge_anchor_points(self, sbox, tbox, rtype, sref=None, tref=None):
        sx = (sbox[0] + sbox[2]) / 2
        sy_top = sbox[1]
        sy_bot = sbox[3]
        tx = (tbox[0] + tbox[2]) / 2
        ty_top = tbox[1]
        ty_bot = tbox[3]

        if rtype == 'rephrase':
            return [sx, sy_bot, tx, ty_top], ((sx + tx) / 2, (sy_bot + ty_top) / 2)

        if rtype == 'split-from':
            mid_y = sy_bot + max(22, (ty_top - sy_bot) * 0.45)
            return [sx, sy_bot, sx, mid_y, tx, mid_y, tx, ty_top], ((sx + tx) / 2, mid_y - 8)

        if rtype == 'example':
            source_side = 1
            if tref in getattr(self, 'graph_example_parent', {}):
                side = self.graph_positions.get(tref, (tx, 0))[0] - self.graph_positions.get(sref, (sx, 0))[0]
                source_side = -1 if side < 0 else 1
            start_x = sbox[2] if source_side > 0 else sbox[0]
            branch_x = start_x + (26 if source_side > 0 else -26)
            end_x = tbox[0] if source_side > 0 else tbox[2]
            start_y = sy_bot - 2
            end_y = (tbox[1] + tbox[3]) / 2
            return [start_x, start_y, branch_x, start_y, branch_x, end_y, end_x, end_y], ((branch_x + end_x) / 2, end_y - 10)

        if rtype == 'supports':
            mid_y = sy_bot + max(28, (ty_top - sy_bot) * 0.55)
            return [sx, sy_bot, sx, mid_y, tx, mid_y, tx, ty_top], ((sx + tx) / 2, mid_y - 8)

        if abs(sx - tx) < 18:
            return [sx, sy_bot, tx, ty_top], ((sx + tx) / 2, (sy_bot + ty_top) / 2)

        mid_y = (sy_bot + ty_top) / 2
        return [sx, sy_bot, sx, mid_y, tx, mid_y, tx, ty_top], ((sx + tx) / 2, mid_y)

    def _collect_local_collapse_groups(self, nodes, edges):
        """Return two dicts describing collapsible groups in the expanded graph.

        rephrase_chains: group_key -> list of refs in the chain (sorted)
        example_groups:  group_key -> {"concept": concept_ref, "refs": [example_refs]}

        group_key format:
          "REPHRASE:<start>:<end>"  for a rephrase chain of length >= 2
          "EXAMPLE:<concept_ref>"   for a concept with >= 2 example children
        """
        out_map = {}
        for sref, tref, rtype in edges:
            out_map.setdefault((sref, rtype), []).append(tref)
        inc_map = {}
        for sref, tref, rtype in edges:
            inc_map.setdefault((tref, rtype), []).append(sref)

        # Find every maximal rephrase chain touching nodes in this graph component.
        node_set = set(nodes)
        visited_rephrase = set()
        rephrase_chains = {}
        for start in sorted(nodes, key=self.ref_sort_key):
            if start in visited_rephrase:
                continue
            # Walk backwards to find the true start of the chain.
            cur = start
            while True:
                prevs = [r for r in inc_map.get((cur, 'rephrase'), []) if r in node_set]
                if not prevs:
                    break
                cur = sorted(prevs, key=self.ref_sort_key)[0]
                if cur in visited_rephrase:
                    break
            chain = [cur]
            visited_rephrase.add(cur)
            while True:
                nxts = [r for r in out_map.get((chain[-1], 'rephrase'), []) if r in node_set and r not in visited_rephrase]
                if not nxts:
                    break
                nxt = sorted(nxts, key=self.ref_sort_key)[0]
                chain.append(nxt)
                visited_rephrase.add(nxt)
            if len(chain) >= 2:
                key = f"REPHRASE:{chain[0]}:{chain[-1]}"
                rephrase_chains[key] = chain

        # Find every concept node that has >= 2 example children.
        example_groups = {}
        for ref in nodes:
            kids = sorted([r for r in out_map.get((ref, 'example'), []) if r in node_set], key=self.ref_sort_key)
            if len(kids) >= 2:
                key = f"EXAMPLE:{ref}"
                example_groups[key] = {"concept": ref, "refs": kids}

        return rephrase_chains, example_groups

    def _rephrase_preview_label(self, chain):
        """Build the preview text for a collapsed rephrase column."""
        # Prefer a #key phrasing line, else the first in the chain.
        key_ref = next(
            (r for r in chain if any(t.get("type") == "key phrasing" for t in self.tags_for_ref(r))),
            chain[0]
        )
        body = choose_meaningful_label(self.line_text_from_ref(key_ref)) or \
               clean_tag_markers(self.line_text_from_ref(key_ref)) or key_ref
        marker = "◆ " if key_ref != chain[0] else ""
        return f"↕ Rephrases [{len(chain)}]\n{marker}{body}"

    def _example_preview_label(self, concept_ref, example_refs):
        """Build the preview text for a collapsed example column."""
        return f"↕ Examples [{len(example_refs)}]"

    def relation_label_color(self, rel_type):
        return RELATION_COLORS.get(rel_type, "#666666")
