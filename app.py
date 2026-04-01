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

from search_manager import SearchMixin
from tag_manager import TagMixin
from relation_manager import RelationMixin
from thread_manager import ThreadMixin
from keyboard_handler import KeyboardMixin
from transcript_interactions import TranscriptInteractionMixin
from graph_interactions import GraphInteractionMixin
from view_renderer import ViewRendererMixin
from transcript_renderer import TranscriptRendererMixin
from graph_renderer import GraphRendererMixin
from ui_builder import UiBuilderMixin

class App(
    UiBuilderMixin,
    ThreadMixin,
    TagMixin,
    RelationMixin,
    SearchMixin,
    TranscriptRendererMixin,
    ViewRendererMixin,
    GraphRendererMixin,
    GraphInteractionMixin,
    TranscriptInteractionMixin,
    KeyboardMixin,
):
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

    def current_preview_name(self):
        return self.workspace_thread if self.mode == "workspace" and self.workspace_thread else self.preview_thread

    def current_thread(self):
        return self.threads[self.current_preview_name()]

    def current_thread_obj(self):
        if self.workspace_thread and self.workspace_thread in self.threads:
            return self.threads[self.workspace_thread]
        name = self.current_preview_name()
        return self.threads.get(name)

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

    def recompute_search_matches(self):
        self.search_matches = []
        self.search_index = -1
        self.search_status_var.set("")

    def goto_search_match(self):
        self.update_active_search_match()

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
