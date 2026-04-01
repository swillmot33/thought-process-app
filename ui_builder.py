import tkinter as tk
from tkinter import ttk

from constants import TAG_OPTIONS, RELATION_OPTIONS, TAG_HIGHLIGHT_OPTIONS, RELATION_HIGHLIGHT_OPTIONS


class UiBuilderMixin:
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
