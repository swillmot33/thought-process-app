import json
import re
import tkinter as tk
from tkinter import filedialog, ttk, messagebox

from constants import (
    TAG_OPTIONS, RELATION_OPTIONS, TAG_HIGHLIGHT_OPTIONS, RELATION_HIGHLIGHT_OPTIONS,
    TAG_COLORS, TAG_PRIORITY, RELATION_COLORS,
    PROTOCOL_SUMMARY, CONSOLIDATE_TEMPLATE, FINAL_CONSOLIDATE_TEMPLATE,
)
from utils import (
    chunk_ref, parse_ref, next_chunk_id, clean_tag_markers, choose_meaningful_label,
    extract_transcript_body, extract_thread_title, detect_tags_from_section,
    make_tag_entry, detect_explicit_tags,
)
from dialogs import ImportDialog, RelationEditDialog

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Companion Research Console v166")
        self.root.geometry("1760x1000")
        self.threads = {"Welcome": {"title": "Welcome", "chunks": [], "tags": [], "relations": [], "auto_relations": []}}
        self.preview_thread = "Welcome"
        self.workspace_thread = None
        self.mode = "home"
        self.current_highlight_ref = None
        self.row_to_ref = {}
        self.line_ref_to_data = {}
        self.selected_line_ref = None
        self.selected_source_ref = None
        self.graph_root_ref = None
        self.selected_relation_info = None
        self.tag_line_lookup = {}
        self.relation_line_lookup = {}
        self.search_var = tk.StringVar()
        self.search_matches = []
        self.search_index = -1
        self.tag_filter_var = tk.StringVar(value="none")
        self.relation_filter_var = tk.StringVar(value="none")
        self.relations_view_var = tk.StringVar(value="all")
        self.chains_view_var = tk.StringVar(value="none")
        self.tree_view_var = tk.StringVar(value="all")
        self.graph_view_var = tk.StringVar(value="all")
        self.relation_display_var = tk.StringVar(value="none")
        self._syncing_relation_display = False
        self.custom_tag_selection = []
        self.local_relation_jump_state = None
        self.graph_zoom = 0.8
        self.graph_fit_mode = False
        self.graph_mode = "expanded"
        self.graph_root_ref = None
        self.graph_group_map = {}
        self.graph_selected_item = None
        # Local collapse state for expanded graph view.
        # Keys are stable group identifiers: "REPHRASE:<start_ref>:<end_ref>" or "EXAMPLE:<concept_ref>"
        self.graph_local_collapsed = set()
        # Tree navigation: ordered flat list of (ref, depth, edge_label) for Follow fwd/back in Tree view
        self.tree_nav_sequence = []
        self.tree_ref_to_nav_idx = {}
        # Tree root is independent from graph root — only changes on explicit re-root (double-click)
        self.tree_root_ref = None
        self.tag_filter_var.trace_add("write", lambda *_: self.on_highlight_changed())
        self.build_ui()
        self.root.bind_all("<Up>", self.on_global_arrow_up, add="+")
        self.root.bind_all("<Down>", self.on_global_arrow_down, add="+")
        self.root.bind_all("<KeyPress-s>", self.on_shortcut_set_source, add="+")
        self.root.bind_all("<KeyPress-a>", self.on_shortcut_add_relation, add="+")
        self.root.bind_all("<KeyPress-d>", self.on_shortcut_clear_source, add="+")
        self.refresh_thread_list()
        self.show_home()

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill="both", expand=True)

        left = ttk.Frame(outer, width=320)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        ttk.Label(left, text="Threads").pack(anchor="w")
        self.thread_list = tk.Listbox(left, width=30, height=30)
        self.thread_list.pack(fill="both", expand=True)
        self.thread_list.bind("<<ListboxSelect>>", self.on_thread_single_click)
        self.thread_list.bind("<Double-Button-1>", self.on_thread_double_click)

        new_row = ttk.Frame(left)
        new_row.pack(fill="x", pady=(8, 0))
        self.new_thread_var = tk.StringVar()
        ttk.Entry(new_row, textvariable=self.new_thread_var).pack(side="left", fill="x", expand=True)
        ttk.Button(new_row, text="New", command=self.create_thread).pack(side="left", padx=(6, 0))

        self.left_summary = tk.Text(left, width=30, height=16, wrap="word")
        self.left_summary.pack(fill="x", expand=False, pady=(8, 0))
        self.left_summary.configure(state="disabled")

        right = ttk.Frame(outer, width=1240)
        right.pack(side="left", fill="both", expand=True)
        right.pack_propagate(False)

        # Row 1: primary workspace actions
        row1 = ttk.Frame(right)
        row1.pack(fill="x")
        ttk.Label(row1, text="View:").pack(side="left")
        self.view_var = tk.StringVar(value="Preview")
        self.current_view_name = "Preview"
        self.view_combo = ttk.Combobox(row1, textvariable=self.view_var, values=["Preview", "Transcript", "Raw", "Tags", "Relations", "Chains", "Tree", "Graph"], state="readonly", width=14)
        self.view_combo.pack(side="left", padx=(4, 10))
        self._syncing_view_var = False
        self.view_combo.bind("<<ComboboxSelected>>", self.on_view_combo_selected)
        self.view_var.trace_add("write", self.on_view_var_changed)
        ttk.Button(row1, text="Open", command=self.open_selected_thread).pack(side="left", padx=(0, 6))
        ttk.Button(row1, text="Import", command=self.import_text).pack(side="left", padx=(0, 6))
        ttk.Button(row1, text="Save", command=self.save_project).pack(side="left", padx=(0, 6))
        ttk.Button(row1, text="Load", command=self.load_project).pack(side="left", padx=(0, 6))
        ttk.Button(row1, text="Auto-tag", command=self.auto_tag_current_thread).pack(side="left", padx=(0, 6))

        # Row 1b: review/tagging and commands live in their own interaction lane
        row1b = ttk.Frame(right)
        row1b.pack(fill="x", pady=(6, 0))
        ttk.Button(row1b, text="Commands", command=self.open_protocol_commands).pack(side="left", padx=(0, 6))
        ttk.Button(row1b, text="Questions", command=self.open_questions_panel).pack(side="left", padx=(0, 12))
        ttk.Label(row1b, text="Review tag:").pack(side="left")
        self.manual_tag_var = tk.StringVar(value=TAG_OPTIONS[0])
        ttk.Combobox(row1b, textvariable=self.manual_tag_var, values=TAG_OPTIONS, state="readonly", width=16).pack(side="left", padx=(4, 6))
        ttk.Button(row1b, text="Add", command=self.add_manual_tag).pack(side="left", padx=(0, 4))
        ttk.Button(row1b, text="Swap", command=self.replace_line_tag).pack(side="left", padx=(0, 4))
        ttk.Button(row1b, text="Drop", command=self.remove_line_tag).pack(side="left", padx=(0, 4))

        row2 = ttk.Frame(right)
        row2.pack(fill="x", pady=(8, 0))
        ttk.Label(row2, text="Search:").pack(side="left")
        ttk.Entry(row2, textvariable=self.search_var, width=24).pack(side="left", padx=(4, 6))
        ttk.Button(row2, text="Find", command=self.search_current).pack(side="left")
        ttk.Button(row2, text="Next", command=lambda: self.step_search(1)).pack(side="left", padx=(6, 0))
        ttk.Button(row2, text="Prev", command=lambda: self.step_search(-1)).pack(side="left", padx=(6, 0))
        ttk.Button(row2, text="Clear", command=self.clear_search).pack(side="left", padx=(6, 10))
        self.search_status_var = tk.StringVar(value="")
        ttk.Label(row2, textvariable=self.search_status_var, width=8).pack(side="left", padx=(0, 10))

        row2b = ttk.Frame(right)
        row2b.pack(fill="x", pady=(4, 0))
        ttk.Label(row2b, text="Tags:").pack(side="left")
        self.tag_filter_combo = ttk.Combobox(row2b, textvariable=self.tag_filter_var, values=TAG_HIGHLIGHT_OPTIONS, state="readonly", width=12)
        self.tag_filter_combo.pack(side="left", padx=(4, 4))
        self.tag_filter_combo.bind("<<ComboboxSelected>>", self.on_highlight_changed)
        ttk.Button(row2b, text="Multi", command=self.choose_custom_tags).pack(side="left", padx=(0, 10))
        ttk.Label(row2b, text="Relations:").pack(side="left")
        self.relation_filter_combo = ttk.Combobox(row2b, textvariable=self.relation_display_var, values=RELATION_HIGHLIGHT_OPTIONS, state="readonly", width=12)
        self.relation_filter_combo.pack(side="left", padx=(4, 12))
        self.relation_filter_combo.bind("<<ComboboxSelected>>", self.on_relation_filter_selected)
        self.status_var = tk.StringVar(value="")
        ttk.Label(row2b, textvariable=self.status_var, anchor="w").pack(side="left", fill="x", expand=True)

        row2c = ttk.Frame(right)
        row2c.pack(fill="x", pady=(4, 0))
        ttk.Button(row2c, text="Skip back", command=lambda: self.step_relation_group(-1)).pack(side="left")
        ttk.Button(row2c, text="Skip forward", command=lambda: self.step_relation_group(1)).pack(side="left", padx=(6, 8))
        ttk.Button(row2c, text="Follow back", command=lambda: self.jump_selected_line_along_relation("back")).pack(side="left")
        ttk.Button(row2c, text="Follow forward", command=lambda: self.jump_selected_line_along_relation("forward")).pack(side="left", padx=(6, 12))
        ttk.Separator(row2c, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(row2c, text="Zoom -", command=lambda: self.adjust_graph_zoom(-0.1)).pack(side="left")
        ttk.Button(row2c, text="Zoom +", command=lambda: self.adjust_graph_zoom(0.1)).pack(side="left", padx=(6, 0))
        ttk.Button(row2c, text="Reset", command=self.reset_graph_zoom).pack(side="left", padx=(6, 0))
        ttk.Button(row2c, text="Fit", command=self.fit_graph_to_view).pack(side="left", padx=(6, 0))
        ttk.Button(row2c, text="Collapse", command=lambda: self.set_graph_mode("collapsed")).pack(side="left", padx=(10, 0))
        ttk.Button(row2c, text="Expand", command=lambda: self.set_graph_mode("expanded")).pack(side="left", padx=(6, 0))

        row3 = ttk.Frame(right)
        row3.pack(fill="x", pady=(8, 0))
        ttk.Label(row3, text="Relation:").pack(side="left")
        self.relation_var = tk.StringVar(value=RELATION_OPTIONS[0])
        ttk.Combobox(row3, textvariable=self.relation_var, values=RELATION_OPTIONS, state="readonly", width=14).pack(side="left", padx=(4, 6))
        ttk.Button(row3, text="Set source", command=self.set_relation_source).pack(side="left", padx=(0, 6))
        ttk.Button(row3, text="Add", command=self.add_relation).pack(side="left", padx=(0, 6))
        ttk.Button(row3, text="Clear", command=self.clear_relation_source).pack(side="left", padx=(0, 6))
        ttk.Button(row3, text="Edit", command=self.edit_relation).pack(side="left", padx=(0, 6))
        ttk.Button(row3, text="Remove", command=self.remove_relation).pack(side="left", padx=(0, 6))

        self.neighborhood_frame = ttk.Frame(right, height=170)
        self.neighborhood_frame.pack(fill="x", pady=(8, 0))
        self.neighborhood_frame.pack_propagate(False)
        ttk.Label(self.neighborhood_frame, text="Neighborhood").pack(anchor="w")
        self.neighborhood_text = tk.Text(self.neighborhood_frame, height=8, wrap="word")
        self.neighborhood_text.pack(fill="x", expand=False)
        self.neighborhood_text.configure(state="disabled")
        self.neighborhood_text.bind("<Double-Button-1>", self.on_neighborhood_double_click)

        main = ttk.Frame(right)
        main.pack(fill="both", expand=True, pady=(8, 0))
        main.pack_propagate(False)

        self.preview_frame = ttk.Frame(main, width=1200, height=700)
        self.preview_text = tk.Text(self.preview_frame, wrap="word")
        self.preview_text.pack(fill="both", expand=True)
        self.preview_text.configure(state="disabled")

        self.transcript_frame = ttk.Frame(main, width=1200, height=700)
        self.transcript_text = tk.Text(
            self.transcript_frame, wrap="word",
            font=("TkDefaultFont", 13), spacing1=4, spacing3=4,
            padx=0, pady=4, borderwidth=0, relief="flat"
        )
        self.transcript_scroll_y = ttk.Scrollbar(self.transcript_frame, orient="vertical", command=self.transcript_text.yview)
        self.transcript_text.configure(yscrollcommand=self.transcript_scroll_y.set)
        self.transcript_text.pack(side="left", fill="both", expand=True)
        self.transcript_scroll_y.pack(side="right", fill="y")
        self.transcript_text.tag_configure("highlight", background="#ffb74d")
        self.transcript_text.tag_configure("searchmatch", background="#fff2a8")
        self.transcript_text.tag_configure("searchactive", background="#ffb74d")
        self.transcript_text.tag_configure("selectedline", background="#cce8ff")
        self.transcript_text.tag_configure("sourcesel", background="#bff4bf")
        self.transcript_text.tag_configure("tag_badge", font=("TkDefaultFont", 10, "bold"))
        # Chat bubble style: You on right with light blue tint, AI on left plain
        self.transcript_text.tag_configure(
            "speaker_you", lmargin1=120, lmargin2=130,
            rmargin=12, background="#eaf4ff", spacing1=6, spacing3=6
        )
        self.transcript_text.tag_configure(
            "speaker_ai", lmargin1=12, lmargin2=22,
            rmargin=80, background="#f8f8f8", spacing1=6, spacing3=6
        )
        self.transcript_text.tag_configure(
            "speaker_you_label", foreground="#1a56a0",
            font=("TkDefaultFont", 11, "bold")
        )
        self.transcript_text.tag_configure(
            "speaker_ai_label", foreground="#2e7d32",
            font=("TkDefaultFont", 11, "bold")
        )
        self.transcript_text.tag_configure(
            "speaker_you_prefix", foreground="#1a56a0"
        )
        self.transcript_text.tag_configure(
            "speaker_ai_prefix", foreground="#2e7d32"
        )
        self.transcript_text.tag_configure(
            "chunk_header", foreground="#aaaaaa",
            font=("TkDefaultFont", 9), spacing1=10, spacing3=4,
            lmargin1=12
        )
        self.transcript_text.configure(state="normal")
        self.transcript_text.bind("<Button-1>", self.on_transcript_click)
        self.transcript_text.bind("<Double-Button-1>", self.on_transcript_double_click)
        self.transcript_text.bind("<Key>", lambda e: "break")
        self.transcript_text.bind("<Up>", lambda e: self.navigate_selected_line(-1))
        self.transcript_text.bind("<Down>", lambda e: self.navigate_selected_line(1))
        self.transcript_text.bind("<<Paste>>", lambda e: "break")
        self.transcript_text.bind("<<Cut>>", lambda e: "break")

        self.tags_frame = ttk.Frame(main, width=1200, height=700)
        self.tags_text = tk.Text(self.tags_frame, wrap="word")
        self.tags_text.pack(fill="both", expand=True)
        self.tags_text.configure(state="disabled")
        self.tags_text.bind("<Double-Button-1>", self.on_tags_text_double_click)

        self.relations_frame = ttk.Frame(main, width=1200, height=700)
        self.relations_text = tk.Text(self.relations_frame, wrap="word")
        self.relations_text.pack(fill="both", expand=True)

        self.graph_frame = ttk.Frame(main, width=1200, height=700)
        self.graph_frame.grid_rowconfigure(0, weight=1)
        self.graph_frame.grid_columnconfigure(0, weight=1)
        self.graph_canvas = tk.Canvas(self.graph_frame, background="#fbfbfb", highlightthickness=0)
        self.graph_scroll_y = ttk.Scrollbar(self.graph_frame, orient="vertical", command=self.graph_canvas.yview)
        self.graph_scroll_x = ttk.Scrollbar(self.graph_frame, orient="horizontal", command=self.graph_canvas.xview)
        self.graph_canvas.configure(yscrollcommand=self.graph_scroll_y.set, xscrollcommand=self.graph_scroll_x.set)
        self.graph_canvas.grid(row=0, column=0, sticky="nsew")
        self.graph_scroll_y.grid(row=0, column=1, sticky="ns")
        self.graph_scroll_x.grid(row=1, column=0, sticky="ew")
        self.graph_canvas.bind("<Button-1>", self.on_graph_canvas_click)
        self.graph_canvas.bind("<Double-Button-1>", self.on_graph_canvas_double_click)
        self.graph_canvas.bind("<Configure>", self.on_graph_canvas_configure)
        self.graph_canvas.bind("<Shift-ButtonPress-1>", self.on_graph_pan_start)
        self.graph_canvas.bind("<Shift-B1-Motion>", self.on_graph_pan_drag)
        self.graph_canvas.bind("<Shift-MouseWheel>", self.on_graph_shift_mousewheel)
        self.graph_canvas.bind("<MouseWheel>", self.on_graph_mousewheel)
        self.graph_item_to_ref = {}
        self.graph_node_bounds = {}
        self.graph_positions = {}
        self.graph_edges = []

        self.preview_frame.pack_propagate(False)
        self.transcript_frame.pack_propagate(False)
        self.tags_frame.pack_propagate(False)
        self.relations_frame.pack_propagate(False)
        self.graph_frame.pack_propagate(False)
        self.relations_text.configure(state="disabled")
        self.relations_text.bind("<Double-Button-1>", self.on_relations_double_click)

    def current_preview_name(self):
        return self.workspace_thread if self.mode == "workspace" and self.workspace_thread else self.preview_thread

    def current_thread(self):
        return self.threads[self.current_preview_name()]

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

    def ordered_lines(self, thread):
        out = []
        for chunk in thread["chunks"]:
            for entry in chunk["lines"]:
                out.append({"chunk_id": chunk["id"], "line": entry["line"], "ref": chunk_ref(chunk["id"], entry["line"]), "text": entry["text"]})
        return out

    def ordered_tags_grouped(self, thread):
        return sorted(thread["tags"], key=lambda t: (t["type"], parse_ref(t["ref"])[0], parse_ref(t["ref"])[1], t.get("source", "explicit")))

    def ordered_tags_linear(self, thread):
        return sorted(thread["tags"], key=lambda t: (parse_ref(t["ref"])[0], parse_ref(t["ref"])[1], t.get("source", "explicit"), t["type"]))

    def ordered_relations(self, thread):
        rels = thread["relations"] + thread.get("auto_relations", [])
        return sorted(rels, key=lambda r: (r["type"], parse_ref(r["source_ref"])[0], parse_ref(r["source_ref"])[1], parse_ref(r["target_ref"])[0], parse_ref(r["target_ref"])[1], r.get("source", "manual")))

    def tags_for_ref(self, ref):
        return [t for t in self.threads[self.workspace_thread]["tags"] if t["ref"] == ref] if self.workspace_thread else []

    def relations_for_ref(self, ref):
        if not self.workspace_thread:
            return []
        allrels = self.threads[self.workspace_thread]["relations"] + self.threads[self.workspace_thread].get("auto_relations", [])
        return [r for r in allrels if r["source_ref"] == ref or r["target_ref"] == ref]

    def line_text_from_ref(self, ref):
        if self.workspace_thread and ref in self.line_ref_to_data:
            return self.line_ref_to_data[ref]["text"]
        thread = self.threads.get(self.workspace_thread) if self.workspace_thread else self.threads.get(self.preview_thread)
        if not thread:
            return ""
        for line in self.ordered_lines(thread):
            if line["ref"] == ref:
                return line["text"]
        return ""

    def parse_ref(self, ref):
        return parse_ref(ref)

    def ref_sort_key(self, ref):
        if isinstance(ref, str) and ref.startswith("LOCAL_PREVIEW:"):
            # Sort after all real refs, using a stable hash-derived order.
            return (99999, hash(ref) & 0xFFFF)
        chunk_id, line_no = parse_ref(ref)
        chunk_num = int(chunk_id[1:]) if chunk_id.startswith("C") and chunk_id[1:].isdigit() else 0
        return (chunk_num, line_no)

    def lookup_line_text(self, chunk_id, line_index):
        ref = f"{chunk_id}:L{line_index}"
        return self.line_text_from_ref(ref)

    def build_branch_structures(self, thread):
        tags_by_ref = {}
        for t in self.ordered_tags_linear(thread):
            tags_by_ref.setdefault(t["ref"], []).append(t)
        rel_by_source = {}
        for r in self.ordered_relations(thread):
            rel_by_source.setdefault(r["source_ref"], []).append(r)
        branches = []
        current = None
        bid = 0
        for line in self.ordered_lines(thread):
            ref = line["ref"]
            line_tags = tags_by_ref.get(ref, [])
            line_rels = rel_by_source.get(ref, [])
            split_tags = [t for t in line_tags if t["type"] == "split"]
            concept_tags = [t for t in line_tags if t["type"] == "concept"]
            shift_tags = [t for t in line_tags if t["type"] == "shift"]
            point_tags = [t for t in line_tags if t["type"] in ("concept", "key phrasing", "flag", "trigger", "interesting")]
            if concept_tags:
                for ct in concept_tags:
                    bid += 1
                    current = {"id": bid, "name": ct.get("display_text") or ct.get("clean_text") or ct["text"], "key_points": [], "splits": [], "relations": []}
                    branches.append(current)
            elif shift_tags:
                st = shift_tags[0]
                bid += 1
                current = {"id": bid, "name": st.get("display_text") or st.get("clean_text") or st["text"], "key_points": [], "splits": [], "relations": []}
                branches.append(current)
            if current is not None:
                for pt in point_tags:
                    item = (pt["type"], pt.get("display_text") or pt.get("clean_text") or pt["text"], ref)
                    if item not in current["key_points"]:
                        current["key_points"].append(item)
                for sp in split_tags:
                    item = (sp.get("display_text") or sp.get("clean_text") or sp["text"], ref)
                    if item not in current["splits"]:
                        current["splits"].append(item)
                for rel in line_rels:
                    item = (rel["type"], rel["target_ref"])
                    if item not in current["relations"]:
                        current["relations"].append(item)
        return branches

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


    def winning_tag_type(self, tag_types):
        if not tag_types:
            return None
        return sorted(tag_types, key=lambda t: (TAG_PRIORITY.get(t, 999), t))[0]

    def selected_tag_types(self):
        selected = self.tag_filter_var.get()
        if selected == "custom":
            return list(self.custom_tag_selection)
        if selected in ("none", "all"):
            return []
        return [selected]

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

    def clear_search_tags(self):
        self.transcript_text.tag_remove("searchmatch", "1.0", tk.END)
        self.transcript_text.tag_remove("searchactive", "1.0", tk.END)

    def apply_search_to_widget(self):
        self.clear_search_tags()
        query = self.search_var.get().strip()
        self.search_matches = []
        self.search_index = -1
        self.search_status_var.set("")
        if not query:
            return
        start = "1.0"
        while True:
            idx = self.transcript_text.search(query, start, stopindex=tk.END, nocase=True)
            if not idx:
                break
            end = f"{idx}+{len(query)}c"
            self.transcript_text.tag_add("searchmatch", idx, end)
            self.search_matches.append((idx, end))
            start = end
        if self.search_matches:
            self.search_index = 0
            self.search_status_var.set(f"1 / {len(self.search_matches)}")
            self.update_active_search_match()
        else:
            self.search_status_var.set("0 / 0")

    def update_active_search_match(self):
        self.transcript_text.tag_remove("searchactive", "1.0", tk.END)
        if 0 <= self.search_index < len(self.search_matches):
            start, end = self.search_matches[self.search_index]
            self.transcript_text.tag_add("searchactive", start, end)
            self.transcript_text.tag_raise("searchactive")
            self.transcript_text.see(start)

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

    def clear_relation_highlights(self):
        if not hasattr(self, "transcript_text"):
            return
        for tag in ("relationmatch", "relationmatch_prefix", "relation_source", "relation_source_prefix"):
            try:
                self.transcript_text.tag_remove(tag, "1.0", tk.END)
            except Exception:
                pass

    def on_relation_filter_selected(self, event=None):
        # Use the widget's visible value as the source of truth.
        if event is not None:
            try:
                self.relation_display_var.set(event.widget.get().strip())
            except Exception:
                pass
        self.apply_visible_relation_selection()

    def on_relation_display_var_changed(self, *_):
        return

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
            allowed = ["none"] + RELATION_OPTIONS
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

    def auto_tag_current_thread(self):
        if self.mode != "workspace" or not self.workspace_thread:
            messagebox.showinfo("Open a thread", "Open a thread first.")
            return
        thread = self.threads[self.workspace_thread]
        manual_tags = [t for t in thread["tags"] if t.get("source") == "manual"]
        explicit = []
        for chunk in thread["chunks"]:
            explicit.extend(detect_explicit_tags([item["text"] for item in chunk["lines"]], chunk["id"]))
        thread["tags"] = explicit + manual_tags
        self.update_left_summary()
        self.render_transcript()
        self.render_tags()
        self.status_var.set(f"Found {len(explicit)} explicit tags from inline markers. AI auto-tag suggestions are not enabled yet.")

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

    def recompute_search_matches(self):
        self.search_matches = []
        self.search_index = -1
        self.search_status_var.set("")

    def search_current(self):
        if self.view_var.get() not in ("Transcript", "Raw"):
            self.set_active_view("Transcript", render=False)
            self.render_main()
        self.apply_search_to_widget()
        if not self.search_matches:
            self.status_var.set("No match found.")
        else:
            self.status_var.set(f"Found {len(self.search_matches)} matches.")

    def step_search(self, step):
        if not self.search_matches:
            self.search_current()
        if not self.search_matches:
            return
        self.search_index = (self.search_index + step) % len(self.search_matches)
        self.search_status_var.set(f"{self.search_index + 1} / {len(self.search_matches)}")
        self.update_active_search_match()

    def goto_search_match(self):
        self.update_active_search_match()

    def clear_search(self):
        self.search_var.set("")
        self.search_matches = []
        self.search_index = -1
        self.search_status_var.set("")
        self.current_highlight_ref = None
        if self.workspace_thread:
            if self.active_view() == "Tree":
                self.render_tree()
            else:
                self.render_transcript()
        self.status_var.set("Cleared search.")

    def clear_main_frames(self):
        for frame in (self.preview_frame, self.transcript_frame, self.tags_frame, self.relations_frame, self.graph_frame):
            frame.pack_forget()



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
            values = ["none"] + RELATION_OPTIONS
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

    def on_view_combo_selected(self, event=None):
        try:
            value = event.widget.get().strip() if event is not None else self.view_combo.get().strip()
        except Exception:
            value = self.view_var.get().strip()
        self.set_active_view(value, render=True)

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

    def render_preview(self):
        thread = self.current_thread()
        content = [self.make_thread_preview(thread)] if thread["chunks"] else [f"# {thread['title']}\n\nNo transcript imported yet."]
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", "\n".join(content))
        self.preview_text.configure(state="disabled")

    def detect_speaker(self, text: str) -> str:
        stripped = text.lstrip()
        if stripped.startswith("You:"):
            return "You"
        if stripped.startswith("AI:"):
            return "AI"
        return "You"


    def format_raw_line(self, ref, text):
        tags = self.tags_for_ref(ref)
        rels = self.relations_for_ref(ref)
        parts = [f"[{ref}]"]
        if tags:
            parts.extend(f"[{t['type']}]" for t in sorted(tags, key=lambda x: TAG_OPTIONS.index(x["type"]) if x["type"] in TAG_OPTIONS else 999))
        if rels:
            rel_parts = []
            for r in rels[:4]:
                role = "src" if r["source_ref"] == ref else "tgt"
                rel_parts.append(f"<{r['type']}:{role}>")
            parts.extend(rel_parts)
        speaker, body = detect_speaker(text)
        return " ".join(parts) + f" {speaker}: {body}"


    def render_transcript(self):
        if not self.workspace_thread:
            return
        thread = self.threads[self.workspace_thread]
        view = self.active_view()

        self.transcript_text.configure(state="normal")
        for name in TAG_COLORS.keys():
            safe_name = name.replace(" ", "_")
            self.transcript_text.tag_remove(f"tagmulti_{safe_name}", "1.0", tk.END)
            self.transcript_text.tag_remove(f"tagmulti_prefix_{safe_name}", "1.0", tk.END)
        self.transcript_text.delete("1.0", tk.END)

        if view == "Raw":
            for name, color in TAG_COLORS.items():
                self.transcript_text.tag_configure(f"accent_{name.replace(' ', '_')}", background=color)
        for name, color in RELATION_COLORS.items():
            self.transcript_text.tag_configure(f"rel_{name.replace('-', '_')}", foreground=color, underline=True)

        selected_tag = self.tag_filter_var.get()
        selected_tag_color = TAG_COLORS.get(selected_tag, "#ffe082")
        self.transcript_text.tag_configure("tagmatch", background=selected_tag_color, foreground="#000000")
        self.transcript_text.tag_configure("tagmatch_prefix", background="#ffca28", foreground="#000000")
        for name, color in TAG_COLORS.items():
            safe = name.replace(" ", "_")
            self.transcript_text.tag_configure(f"tagmulti_{safe}", background=color, foreground="#000000")
            self.transcript_text.tag_configure(f"tagmulti_prefix_{safe}", background=color, foreground="#000000")
        self.transcript_text.tag_configure("relationmatch", background="#c8e6c9", foreground="#000000")
        self.transcript_text.tag_configure("relation_source", background="#d1c4e9", foreground="#000000")
        self.transcript_text.tag_configure("relationmatch_prefix", background="#81c784", foreground="#000000")
        self.transcript_text.tag_configure("relation_source_prefix", background="#9575cd", foreground="#000000")
        self.transcript_text.tag_configure("searchmatch", background="#fff2a8")
        self.transcript_text.tag_configure("searchactive", background="#ffb74d")

        self.row_to_ref = {}
        self.line_ref_to_data = {}
        line_roles = {}
        row = 1
        tag_count = 0
        relation_count = 0
        current_edge = self.current_relation_group() if self.relation_filter_var.get() not in ("none", "all") else None

        for chunk in thread["chunks"]:
            # Subtle chunk header
            chunk_start = self.transcript_text.index(tk.END)
            self.transcript_text.insert(tk.END, f" {chunk['id']}\n")
            chunk_end = self.transcript_text.index(tk.END)
            if view == "Transcript":
                self.transcript_text.tag_add("chunk_header", chunk_start, chunk_end)
            else:
                self.transcript_text.insert(tk.END, "")  # raw gets full header below
                # undo the subtle insert for raw — rebuild
                self.transcript_text.delete(chunk_start, chunk_end)
                raw_start = self.transcript_text.index(tk.END)
                self.transcript_text.insert(tk.END, f"=== {chunk['id']} ===\n")
                raw_end = self.transcript_text.index(tk.END)
            row += 1
            for entry in chunk["lines"]:
                ref = chunk_ref(chunk["id"], entry["line"])
                tags = self.tags_for_ref(ref)
                rels = self.relations_for_ref(ref)

                tag_match = self.ref_matches_tag_filter(ref)
                relation_match = self.ref_matches_relation_filter(ref)
                relation_source_match = False
                relation_target_match = False
                if self.relation_filter_var.get() not in ("none", "all") and current_edge:
                    src_ref, tgt_ref = current_edge
                    relation_source_match = (ref == src_ref)
                    relation_target_match = (ref == tgt_ref)
                    relation_match = relation_source_match or relation_target_match

                line_roles[ref] = {
                    "is_source": relation_source_match,
                    "is_target": relation_target_match,
                    "is_match": relation_match,
                }

                if tag_match:
                    tag_count += 1
                if relation_match:
                    relation_count += 1

                line_start = self.transcript_text.index(tk.END)
                self.transcript_text.insert(tk.END, "▌ ")
                prefix_start = line_start
                prefix_end = self.transcript_text.index(tk.END)

                # In transcript view, color the ▌ bar based on highest-priority tag
                if view == "Transcript" and tags:
                    winning = self.winning_tag_type([t["type"] for t in tags])
                    if winning:
                        bar_color = TAG_COLORS.get(winning, "#cccccc")
                        bar_tag = f"prefix_bar_{winning.replace(' ', '_')}"
                        self.transcript_text.tag_configure(bar_tag, foreground=bar_color, font=("TkDefaultFont", 14, "bold"))
                        self.transcript_text.tag_add(bar_tag, prefix_start, prefix_end)

                # Raw view keeps refs/tags/relations inline
                if view == "Raw":
                    ref_start = self.transcript_text.index(tk.END)
                    self.transcript_text.insert(tk.END, f"[{ref}] ")
                    ref_end = self.transcript_text.index(tk.END)

                    if tags:
                        for t in sorted(tags, key=lambda x: TAG_OPTIONS.index(x["type"]) if x["type"] in TAG_OPTIONS else 999):
                            s = self.transcript_text.index(tk.END)
                            self.transcript_text.insert(tk.END, f"#{t['type'].replace(' ', '-')} ")
                            e = self.transcript_text.index(tk.END)
                            self.transcript_text.tag_add("tag_badge", s, e)
                    if rels and self.relation_filter_var.get() in ("none", "all"):
                        emitted = []
                        for r in rels[:6]:
                            if r["source_ref"] == ref:
                                emitted.append(f"#{r['type']}{{{r['target_ref']}}}")
                            else:
                                emitted.append(f"#incoming-{r['type']}{{{r['source_ref']}}}")
                        if emitted:
                            s = self.transcript_text.index(tk.END)
                            self.transcript_text.insert(tk.END, " ".join(emitted) + " ")
                            e = self.transcript_text.index(tk.END)
                            self.transcript_text.tag_add("tag_badge", s, e)
                    if current_edge and self.relation_filter_var.get() not in ("none", "all"):
                        src_ref, tgt_ref = current_edge
                        marker_text = None
                        if ref == src_ref:
                            marker_text = f"<{self.relation_filter_var.get()}:src> "
                        elif ref == tgt_ref:
                            marker_text = f"<{self.relation_filter_var.get()}:tgt> "
                        if marker_text:
                            s = self.transcript_text.index(tk.END)
                            self.transcript_text.insert(tk.END, marker_text)
                            e = self.transcript_text.index(tk.END)
                            self.transcript_text.tag_add("tag_badge", s, e)
                            self.transcript_text.tag_add(f"rel_{self.relation_filter_var.get().replace('-', '_')}", s, e)
                    elif rels and self.relation_filter_var.get() == "all":
                        for r in rels[:4]:
                            role = "src" if r["source_ref"] == ref else "tgt"
                            s = self.transcript_text.index(tk.END)
                            self.transcript_text.insert(tk.END, f"<{r['type']}:{role}> ")
                            e = self.transcript_text.index(tk.END)
                            self.transcript_text.tag_add("tag_badge", s, e)
                            self.transcript_text.tag_add(f"rel_{r['type'].replace('-', '_')}", s, e)

                    speaker = self.detect_speaker(entry["text"])
                    speaker_prefix_tag = "speaker_you_prefix" if speaker == "You" else "speaker_ai_prefix"
                    self.transcript_text.tag_add(speaker_prefix_tag, ref_start, ref_end)

                    display_text = entry["text"]
                else:
                    # Transcript view: chat-style, speaker label then body
                    speaker = self.detect_speaker(entry["text"])
                    text = clean_tag_markers(entry["text"])
                    if text.startswith("You: "):
                        text = text[5:]
                    elif text.startswith("AI: "):
                        text = text[4:]
                    speaker_label = "You" if speaker == "You" else "AI"
                    # If body is empty after cleaning (line was pure tag markers), show a placeholder
                    body = text.strip() if text.strip() else "—"
                    display_text = f"{speaker_label}  {body}"

                self.transcript_text.insert(tk.END, display_text + "\n\n")

                self.row_to_ref[ref] = row
                self.line_ref_to_data[ref] = {"chunk_id": chunk["id"], "line": entry["line"], "text": entry["text"]}
                row += 2

            self.transcript_text.insert(tk.END, "\n")
            row += 1

        # CLEAR ALL HIGHLIGHT TAGS FIRST
        for tag in [
            "relationmatch",
            "relationmatch_prefix",
            "relation_source",
            "relation_source_prefix",
            "tagmatch",
            "tagmatch_prefix",
        ]:
            self.transcript_text.tag_remove(tag, "1.0", tk.END)

        # apply line-based styling after insertion
        for ref, r in self.row_to_ref.items():
            tag_match = self.ref_matches_tag_filter(ref)
            relation_source_match = False
            relation_target_match = False
            relation_match = False
            if self.relation_filter_var.get() not in ("none", "all") and current_edge:
                src_ref, tgt_ref = current_edge
                relation_source_match = (ref == src_ref)
                relation_target_match = (ref == tgt_ref)
                relation_match = relation_source_match or relation_target_match
            elif self.relation_filter_var.get() == "all":
                relation_match = self.ref_matches_relation_filter(ref)

            line_start = f"{r}.0"
            line_end = f"{r}.end"
            prefix_end = f"{r}.2"

            speaker = self.detect_speaker(self.line_ref_to_data[ref]["text"])
            is_you = speaker == "You"
            if view == "Transcript":
                bubble_tag = "speaker_you" if is_you else "speaker_ai"
                label_tag = "speaker_you_label" if is_you else "speaker_ai_label"
                # Apply bubble background first — tag colors will be layered on top
                self.transcript_text.tag_add(bubble_tag, line_start, line_end)
                label_len = 3 if is_you else 2
                label_start = f"{r}.2"
                label_end = f"{r}.{2 + label_len}"
                self.transcript_text.tag_add(label_tag, label_start, label_end)
            else:
                self.transcript_text.tag_add("speaker_you" if is_you else "speaker_ai", line_start, line_end)
                self.transcript_text.tag_add("speaker_you_prefix" if is_you else "speaker_ai_prefix", line_start, prefix_end)

            # Apply relation highlights — these override bubble backgrounds
            if relation_source_match:
                self.transcript_text.tag_add("relation_source", line_start, line_end)
                self.transcript_text.tag_add("relation_source_prefix", line_start, prefix_end)
            elif relation_target_match or (relation_match and self.relation_filter_var.get() == "all"):
                self.transcript_text.tag_add("relationmatch", line_start, line_end)
                self.transcript_text.tag_add("relationmatch_prefix", line_start, prefix_end)
            elif tag_match:
                # Apply tag color backgrounds after bubble so they win
                for name in TAG_COLORS.keys():
                    safe_name = name.replace(" ", "_")
                    self.transcript_text.tag_remove(f"tagmulti_{safe_name}", line_start, line_end)
                    self.transcript_text.tag_remove(f"tagmulti_prefix_{safe_name}", line_start, line_end)
                self.transcript_text.tag_remove("tagmatch", line_start, line_end)
                self.transcript_text.tag_remove("tagmatch_prefix", line_start, line_end)

                if self.tag_filter_var.get() == "custom":
                    chosen = set(self.custom_tag_selection)
                    line_tags = [t["type"] for t in self.tags_for_ref(ref) if t["type"] in chosen]
                    winner = self.winning_tag_type(line_tags)
                    if winner:
                        safe = winner.replace(" ", "_")
                        self.transcript_text.tag_add(f"tagmulti_{safe}", line_start, line_end)
                        self.transcript_text.tag_add(f"tagmulti_prefix_{safe}", line_start, prefix_end)
                elif self.tag_filter_var.get() == "all":
                    line_tags = [t["type"] for t in self.tags_for_ref(ref)]
                    winner = self.winning_tag_type(line_tags)
                    if winner:
                        safe = winner.replace(" ", "_")
                        self.transcript_text.tag_add(f"tagmulti_{safe}", line_start, line_end)
                        self.transcript_text.tag_add(f"tagmulti_prefix_{safe}", line_start, prefix_end)
                else:
                    self.transcript_text.tag_add("tagmatch", line_start, line_end)
                    self.transcript_text.tag_add("tagmatch_prefix", line_start, prefix_end)

        # FINAL RELATION STEP OVERRIDE
        if self.relation_filter_var.get() not in ("none", "all") and current_edge:
            src_ref, tgt_ref = current_edge

            def force_role(ref_value, role_name):
                if ref_value not in self.row_to_ref:
                    return
                rr = self.row_to_ref[ref_value]
                ls = f"{rr}.0"
                le = f"{rr}.end"
                pe = f"{rr}.2"
                # clear any conflicting highlight tags on just this line
                for tag in (
                    "relationmatch", "relationmatch_prefix",
                    "relation_source", "relation_source_prefix",
                    "tagmatch", "tagmatch_prefix"
                ):
                    self.transcript_text.tag_remove(tag, ls, le)
                if role_name == "source":
                    self.transcript_text.tag_add("relation_source", ls, le)
                    self.transcript_text.tag_add("relation_source_prefix", ls, pe)
                else:
                    self.transcript_text.tag_add("relationmatch", ls, le)
                    self.transcript_text.tag_add("relationmatch_prefix", ls, pe)

            force_role(src_ref, "source")
            force_role(tgt_ref, "target")

        # search
        self.apply_search_to_widget()
        self.transcript_text.tag_remove("highlight", "1.0", tk.END)

        self.transcript_text.tag_raise("speaker_ai")
        self.transcript_text.tag_raise("speaker_you")
        # Tag/relation colors raised above bubble backgrounds
        self.transcript_text.tag_raise("relationmatch")
        self.transcript_text.tag_raise("relation_source")
        self.transcript_text.tag_raise("relationmatch_prefix")
        self.transcript_text.tag_raise("relation_source_prefix")
        self.transcript_text.tag_raise("tagmatch")
        self.transcript_text.tag_raise("tagmatch_prefix")
        for name in TAG_COLORS.keys():
            safe_name = name.replace(" ", "_")
            self.transcript_text.tag_raise(f"tagmulti_{safe_name}")
            self.transcript_text.tag_raise(f"tagmulti_prefix_{safe_name}")
        # Speaker labels raised above tag backgrounds for readability
        self.transcript_text.tag_raise("speaker_you_label")
        self.transcript_text.tag_raise("speaker_ai_label")
        self.transcript_text.tag_raise("searchmatch")
        self.transcript_text.tag_raise("searchactive")
        self.transcript_text.tag_raise("selectedline")
        self.transcript_text.tag_raise("sourcesel")
        self.transcript_text.tag_raise("highlight")

        if self.selected_source_ref and self.selected_source_ref in self.row_to_ref:
            self.mark_source_line(self.selected_source_ref, False)
        if self.selected_line_ref and self.selected_line_ref in self.row_to_ref:
            self.mark_selected_line(self.selected_line_ref, False)

        # ABSOLUTE FINAL relation override for the current stepped edge
        if self.relation_filter_var.get() in ("none", "all") or not current_edge:
            self.transcript_text.tag_remove("relationmatch", "1.0", tk.END)
            self.transcript_text.tag_remove("relation_source", "1.0", tk.END)
            self.transcript_text.tag_remove("relationmatch_prefix", "1.0", tk.END)
            self.transcript_text.tag_remove("relation_source_prefix", "1.0", tk.END)
        else:
            src_ref, tgt_ref = current_edge

            def _force_final_role(ref_value, role_name):
                if ref_value not in self.row_to_ref:
                    return
                rr = self.row_to_ref[ref_value]
                ls = f"{rr}.0"
                le = f"{rr}.end"
                pe = f"{rr}.2"
                for tag in (
                    "relationmatch", "relationmatch_prefix",
                    "relation_source", "relation_source_prefix",
                    "tagmatch", "tagmatch_prefix",
                ):
                    self.transcript_text.tag_remove(tag, ls, le)
                if role_name == "source":
                    self.transcript_text.tag_add("relation_source", ls, le)
                    self.transcript_text.tag_add("relation_source_prefix", ls, pe)
                    self.transcript_text.tag_raise("relation_source")
                    self.transcript_text.tag_raise("relation_source_prefix")
                else:
                    self.transcript_text.tag_add("relationmatch", ls, le)
                    self.transcript_text.tag_add("relationmatch_prefix", ls, pe)
                    self.transcript_text.tag_raise("relationmatch")
                    self.transcript_text.tag_raise("relationmatch_prefix")

            _force_final_role(src_ref, "source")
            _force_final_role(tgt_ref, "target")

        self.transcript_text.configure(state="disabled")
        self.update_neighborhood()

        tag_sel = self.tag_filter_var.get()
        rel_sel = self.relation_filter_var.get()
        tag_desc = f"Tags: {tag_sel} ({tag_count} matches)" if tag_sel != "none" else "Tags: none"
        if rel_sel != "none":
            if rel_sel not in ("none", "all"):
                groups = self.build_relation_groups()
                rel_desc = f"Relations: {rel_sel} [{self.relation_group_index + 1}/{len(groups)}] ({relation_count} matches)" if groups else f"Relations: {rel_sel} (0 matches)"
            else:
                rel_desc = f"Relations: {rel_sel} ({relation_count} matches)"
        else:
            rel_desc = "Relations: none"
        mode_desc = "Raw view." if view == "Raw" else "Transcript view."
        self.status_var.set(f"{mode_desc} {tag_desc}. {rel_desc}.")


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
        if rel_type not in RELATION_OPTIONS:
            rel_type = "none"

        if rel_type in ("none", "all"):
            self.transcript_text.insert(tk.END, "Choose a specific relation type to view chains.")
            self.transcript_text.configure(state="disabled")
            if hasattr(self, "neighborhood_text"):
                self.neighborhood_text.configure(state="normal")
                self.neighborhood_text.delete("1.0", tk.END)
                self.neighborhood_text.insert(tk.END, "Chains view active. Choose a specific relation type.")
                self.neighborhood_text.configure(height=8)
                self.neighborhood_text.configure(state="disabled")
            self.status_var.set("Chains view. Choose a specific relation type.")
            return

        chains = self.maximal_chains_for_relation_type(rel_type)

        # Neighborhood becomes a chain summary in Chains view, not selected-line neighborhood.
        if hasattr(self, "neighborhood_text"):
            self.neighborhood_text.configure(state="normal")
            self.neighborhood_text.delete("1.0", tk.END)
            self.neighborhood_text.insert(tk.END, f"Chains view: maximal {rel_type} paths\n")
            self.neighborhood_text.insert(tk.END, f"Count: {len(chains)}\n\n")
            if chains:
                for idx, chain in enumerate(chains, 1):
                    self.neighborhood_text.insert(tk.END, f"{idx}. " + " → ".join(chain) + "\n")
            else:
                self.neighborhood_text.insert(tk.END, "No chains found.\n")
            self.neighborhood_text.configure(height=8)
            self.neighborhood_text.configure(state="disabled")

        if not chains:
            self.transcript_text.insert(tk.END, f"No maximal {rel_type} chains found.")
            self.transcript_text.configure(state="disabled")
            self.transcript_text.yview_moveto(0.0)
            self.status_var.set(f"Chains view: maximal {rel_type} paths (0 chains).")
            return

        # Render one block per chain.
        line_no = 1
        selected_chain_refs = set()
        if self.selected_line_ref:
            for chain in chains:
                if self.selected_line_ref in chain:
                    selected_chain_refs = set(chain)
                    break

        self.transcript_text.tag_configure("chain_header", font=("TkDefaultFont", 11, "bold"))
        self.transcript_text.tag_configure("chain_arrow", foreground="#666666")
        self.transcript_text.tag_configure("chain_member", background="#f5f5f5")
        self.transcript_text.tag_configure("chain_selected_member", background="#bbdefb")

        for idx, chain in enumerate(chains, 1):
            header = f"[{rel_type}] Chain {idx} ({len(chain)} nodes)"
            start = self.transcript_text.index(tk.END)
            self.transcript_text.insert(tk.END, header + "\n")
            end = self.transcript_text.index(tk.END)
            self.transcript_text.tag_add("chain_header", start, end)
            line_no += 1

            chain_line = " → ".join(chain)
            start = self.transcript_text.index(tk.END)
            self.transcript_text.insert(tk.END, chain_line + "\n")
            end = self.transcript_text.index(tk.END)
            self.transcript_text.tag_add("chain_arrow", start, end)
            line_no += 1

            for ref in chain:
                chunk_id, line_index = self.parse_ref(ref)
                text = self.lookup_line_text(chunk_id, line_index)
                rendered = f"{ref} {text}".rstrip()
                start = self.transcript_text.index(tk.END)
                self.transcript_text.insert(tk.END, rendered + "\n")
                end = self.transcript_text.index(tk.END)

                self.row_to_ref[line_no] = ref
                self.ref_to_row[ref] = line_no
                self.line_ref_to_data[ref] = (chunk_id, line_index, text)

                if ref in selected_chain_refs:
                    self.transcript_text.tag_add("chain_selected_member", start, end)
                else:
                    self.transcript_text.tag_add("chain_member", start, end)

                line_no += 1

            self.transcript_text.insert(tk.END, "\n")
            line_no += 1

        self.transcript_text.configure(state="disabled")
        self.transcript_text.yview_moveto(0.0)
        self.status_var.set(f"Chains view: maximal {rel_type} paths ({len(chains)} chains).")

    def render_tree(self):
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


    def graph_relation_filter(self):
        rel_type = self.graph_view_var.get().strip() or "all"
        return rel_type if rel_type in (["all"] + RELATION_OPTIONS) else "all"


    def relation_label_color(self, rel_type):
        return RELATION_COLORS.get(rel_type, "#666666")


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


    def graph_node_text(self, ref):
        body = choose_meaningful_label(self.line_text_from_ref(ref)) or clean_tag_markers(self.line_text_from_ref(ref)) or ref
        words = body.split()
        if len(words) > 12:
            body = " ".join(words[:12]) + " ..."
        return f"{ref}\n{body}"


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


    def spread_offsets(self, count, spacing):
        if count <= 0:
            return []
        if count == 1:
            return [0]
        start = -spacing * (count - 1) / 2
        return [start + i * spacing for i in range(count)]


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



    def current_thread_obj(self):
        if self.workspace_thread and self.workspace_thread in self.threads:
            return self.threads[self.workspace_thread]
        name = self.current_preview_name()
        return self.threads.get(name)

    def open_questions_panel(self):
        thread = self.current_thread_obj()
        if not thread:
            messagebox.showinfo("Open Questions", "No thread selected.")
            return
        if getattr(self, "questions_window", None) and self.questions_window.winfo_exists():
            self.questions_window.lift()
            try:
                self.questions_window.focus_force()
            except Exception:
                pass
            return
        win = tk.Toplevel(self.root)
        self.questions_window = win
        win.title(f"Open Questions — {thread['title']}")
        win.geometry("760x520")
        win.transient(self.root)
        win.lift()
        win.protocol("WM_DELETE_WINDOW", lambda: self._close_questions_window())

        container = ttk.Frame(win, padding=10)
        container.pack(fill="both", expand=True)

        left = ttk.Frame(container)
        left.pack(side="left", fill="y")
        right = ttk.Frame(container)
        right.pack(side="left", fill="both", expand=True, padx=(10,0))

        ttk.Label(left, text="Questions").pack(anchor="w")
        lb = tk.Listbox(left, width=34, height=20)
        lb.pack(fill="y", expand=True)

        form = ttk.Frame(right)
        form.pack(fill="x")
        ttk.Label(form, text="Question").pack(anchor="w")
        qtext = tk.Text(form, height=5, wrap="word")
        qtext.pack(fill="x", pady=(4,8))
        ref_var = tk.StringVar(value=self.selected_line_ref or "")
        ref_row = ttk.Frame(form)
        ref_row.pack(fill="x", pady=(0,8))
        ttk.Label(ref_row, text="Source line:").pack(side="left")
        ttk.Entry(ref_row, textvariable=ref_var, width=18).pack(side="left", padx=(6,6))
        def use_selected_ref():
            ref_var.set(self.selected_line_ref or "")
            self.status_var.set(f"Question source set to {ref_var.get() or '(none)'}." )

        ttk.Button(ref_row, text="Use selected", command=use_selected_ref).pack(side="left")

        details = tk.Text(right, height=10, wrap="word")
        details.pack(fill="both", expand=True)
        details.configure(state="disabled")

        self.questions_ref_var = ref_var
        self.questions_listbox = lb
        self.questions_qtext = qtext
        self.questions_details = details

        def refresh_list(select_index=None):
            lb.delete(0, tk.END)
            for item in thread.get("open_questions", []):
                ref = item.get("ref") or "no ref"
                title = item.get("text", "").strip().splitlines()[0][:55]
                lb.insert(tk.END, f"{ref} — {title}")
            if select_index is not None and 0 <= select_index < lb.size():
                lb.selection_clear(0, tk.END)
                lb.selection_set(select_index)
                lb.activate(select_index)
                on_select(None)

        def on_select(_event):
            sel = lb.curselection()
            details.configure(state="normal")
            details.delete("1.0", tk.END)
            if not sel:
                details.configure(state="disabled")
                return
            item = thread.get("open_questions", [])[sel[0]]
            body = item.get("text", "")
            ref = item.get("ref") or ""
            ref_var.set(ref)
            qtext.delete("1.0", tk.END)
            qtext.insert("1.0", body)
            if ref:
                details.insert("1.0", f"{ref}\n\n{body}")
            else:
                details.insert("1.0", body)
            details.configure(state="disabled")

        def add_question():
            body = qtext.get("1.0", tk.END).strip()
            if not body:
                messagebox.showinfo("Open Questions", "Type a question before adding it.", parent=win)
                qtext.focus_set()
                return
            ref = ref_var.get().strip() or ""
            sel = lb.curselection()
            if sel:
                thread.setdefault("open_questions", [])[sel[0]] = {"text": body, "ref": ref}
                idx = sel[0]
                self.status_var.set("Updated open question.")
            else:
                thread.setdefault("open_questions", []).append({"text": body, "ref": ref})
                idx = len(thread.get("open_questions", [])) - 1
                self.status_var.set("Added open question.")
            self.update_left_summary()
            refresh_list(idx)
            qtext.focus_set()

        def remove_question():
            sel = lb.curselection()
            if not sel:
                messagebox.showinfo("Open Questions", "Select a question to remove.", parent=win)
                return
            del thread.setdefault("open_questions", [])[sel[0]]
            qtext.delete("1.0", tk.END)
            self.update_left_summary()
            remaining = len(thread.get("open_questions", []))
            refresh_list(min(sel[0], remaining - 1) if remaining else None)
            self.status_var.set("Removed open question.")

        def jump_to_ref():
            sel = lb.curselection()
            if not sel:
                messagebox.showinfo("Open Questions", "Select a question to jump from.", parent=win)
                return
            ref = thread.get("open_questions", [])[sel[0]].get("ref")
            if not ref:
                messagebox.showinfo("Open Questions", "That question does not have a source line.", parent=win)
                return
            if ref and ref in self.line_ref_to_data:
                self.selected_line_ref = ref
                self.local_relation_jump_state = None
                self.set_active_view("Transcript", render=False)
                self.render_main()
                self.highlight_ref(ref, scroll=True)
                self.mark_selected_line(ref, False)
                self.update_neighborhood()
                self.status_var.set(f"Jumped to {ref} from questions.")
                try:
                    self.root.lift()
                except Exception:
                    pass
            else:
                messagebox.showinfo("Open Questions", f"Could not find source line {ref} in the current thread.", parent=win)

        btns = ttk.Frame(right)
        btns.pack(fill="x", pady=(8,0))
        ttk.Button(btns, text="Add / Update", command=add_question).pack(side="left")
        ttk.Button(btns, text="Remove", command=remove_question).pack(side="left", padx=(6,0))
        ttk.Button(btns, text="Jump to line", command=jump_to_ref).pack(side="left", padx=(6,0))

        lb.bind("<<ListboxSelect>>", on_select)
        refresh_list()
        qtext.focus_force()

    def _close_questions_window(self):
        win = getattr(self, "questions_window", None)
        if win and win.winfo_exists():
            win.destroy()
        self.questions_window = None
        self.questions_ref_var = None
        self.questions_listbox = None
        self.questions_qtext = None
        self.questions_details = None

    def _focus_allows_global_nav(self):

        widget = self.root.focus_get()
        if widget is None:
            return False
        cls = widget.winfo_class()
        return cls not in {"Entry", "TEntry", "Text", "TCombobox", "Listbox", "Spinbox"}

    def on_global_arrow_up(self, event):
        if self._focus_allows_global_nav():
            return self.navigate_selected_line(-1)

    def on_global_arrow_down(self, event):
        if self._focus_allows_global_nav():
            return self.navigate_selected_line(1)

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

    def update_questions_source_hint(self):
        if getattr(self, "questions_ref_var", None) is not None:
            try:
                if not self.questions_listbox or not self.questions_listbox.curselection():
                    self.questions_ref_var.set(self.selected_line_ref or "")
            except Exception:
                pass

    def open_protocol_commands(self):
        win = tk.Toplevel(self.root)
        win.title("Protocol / Commands")
        win.geometry("980x760")
        win.transient(self.root)

        top = ttk.Frame(win, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Copy commands for quick paste into ChatGPT.").pack(side="left")

        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tabs = [
            ("Protocol", PROTOCOL_SUMMARY),
            ("Consolidate", CONSOLIDATE_TEMPLATE),
            ("Final Consolidate", FINAL_CONSOLIDATE_TEMPLATE),
        ]
        for title, content in tabs:
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=title)
            btn_row = ttk.Frame(frame)
            btn_row.pack(fill="x", pady=(8, 4), padx=8)
            text_widget = tk.Text(frame, wrap="word")
            text_widget.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            text_widget.insert("1.0", content)
            def copy_text(widget=text_widget, label=title):
                data = widget.get("1.0", tk.END).rstrip()
                self.root.clipboard_clear()
                self.root.clipboard_append(data)
                self.status_var.set(f"Copied {label} command.")
            ttk.Button(btn_row, text="Copy", command=copy_text).pack(side="left")
            ttk.Button(btn_row, text="Select All", command=lambda w=text_widget: (w.focus_set(), w.tag_add("sel", "1.0", "end-1c"))).pack(side="left", padx=(6, 0))

    def set_graph_mode(self, mode):
        mode = (mode or "expanded").strip().lower()
        if mode not in ("expanded", "collapsed"):
            mode = "expanded"
        self.graph_mode = mode
        if self.active_view() == "Graph" and self.workspace_thread:
            self.render_graph()


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


    def graph_ref_from_event(self, event):
        cx = self.graph_canvas.canvasx(event.x)
        cy = self.graph_canvas.canvasy(event.y)
        items = self.graph_canvas.find_overlapping(cx, cy, cx, cy)
        for item in reversed(items):
            ref = self.graph_item_to_ref.get(item)
            if ref:
                return ref
        return None


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

