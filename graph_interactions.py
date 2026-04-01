class GraphInteractionMixin:
    def on_graph_canvas_click(self, event=None):
        ref = self.graph_ref_from_event(event)
        if not ref:
            return
        underlying = self.graph_group_map.get(ref, [ref])
        self.selected_line_ref = underlying[0]
        self.local_relation_jump_state = None
        self.status_var.set(f"Selected {self.selected_line_ref} in Graph view.")
        self.update_neighborhood()
        self.update_questions_source_hint()
        # Passive selection only: do not mutate graph mode or layout.
        self.render_graph()

    def on_graph_canvas_double_click(self, event=None):
        """Double-click toggles local collapse of a rephrase chain or example column.
        Single-click selection still fires first via the Button-1 binding."""
        ref = self.graph_ref_from_event(event)
        if not ref:
            return
        # If the node is a local-collapse preview box, expand it.
        if ref in getattr(self, "graph_local_preview_map", {}):
            group_key = self.graph_local_preview_map[ref]
            self.graph_local_collapsed.discard(group_key)
            self.graph_fit_mode = False
            self.render_graph()
            self.status_var.set(f"Expanded {group_key}.")
            return
        # If the node belongs to a collapsible group, collapse that group.
        group_key = getattr(self, "graph_ref_to_group_key", {}).get(ref)
        if group_key:
            self.graph_local_collapsed.add(group_key)
            self.graph_fit_mode = False
            self.render_graph()
            self.status_var.set(f"Collapsed {group_key}.")
            return
        # Fallback: treat as a passive selection click.
        self.on_graph_canvas_click(event)

    def on_graph_canvas_configure(self, event=None):
        if self.active_view() == "Graph" and self.workspace_thread:
            if self.graph_fit_mode or not getattr(self, "graph_positions", None):
                self.render_graph()

    def on_graph_pan_start(self, event=None):
        try:
            self.graph_canvas.scan_mark(event.x, event.y)
        except Exception:
            pass

    def on_graph_pan_drag(self, event=None):
        try:
            self.graph_canvas.scan_dragto(event.x, event.y, gain=1)
        except Exception:
            pass

    def on_graph_shift_mousewheel(self, event=None):
        if event is None:
            return
        delta = 0
        if getattr(event, "delta", 0):
            delta = -1 if event.delta > 0 else 1
        elif getattr(event, "num", None) in (4, 5):
            delta = -1 if event.num == 4 else 1
        if delta:
            self.graph_canvas.xview_scroll(delta * 3, "units")

    def on_graph_mousewheel(self, event=None):
        if event is None:
            return
        delta = 0
        if getattr(event, "delta", 0):
            delta = -1 if event.delta > 0 else 1
        elif getattr(event, "num", None) in (4, 5):
            delta = -1 if event.num == 4 else 1
        if delta:
            self.graph_canvas.yview_scroll(delta * 3, "units")

    def graph_ref_from_event(self, event):
        cx = self.graph_canvas.canvasx(event.x)
        cy = self.graph_canvas.canvasy(event.y)
        items = self.graph_canvas.find_overlapping(cx, cy, cx, cy)
        for item in reversed(items):
            ref = self.graph_item_to_ref.get(item)
            if ref:
                return ref
        return None

    def set_graph_mode(self, mode):
        mode = (mode or "expanded").strip().lower()
        if mode not in ("expanded", "collapsed"):
            mode = "expanded"
        self.graph_mode = mode
        if self.active_view() == "Graph" and self.workspace_thread:
            self.render_graph()

    def adjust_graph_zoom(self, delta):
        self.graph_fit_mode = False
        self.graph_zoom = max(0.25, min(1.6, self.graph_zoom + delta))
        if self.active_view() == "Graph" and self.workspace_thread:
            self.render_graph()

    def reset_graph_zoom(self):
        self.graph_fit_mode = False
        self.graph_zoom = 0.8
        if self.active_view() == "Graph" and self.workspace_thread:
            self.render_graph()

    def fit_graph_to_view(self):
        self.graph_fit_mode = True
        if self.active_view() == "Graph" and self.workspace_thread:
            self.render_graph()
