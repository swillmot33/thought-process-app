import tkinter as tk

from constants import TAG_COLORS, TAG_OPTIONS, RELATION_COLORS
from utils import chunk_ref, clean_tag_markers


class TranscriptRendererMixin:
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
