import tkinter as tk


class SearchMixin:
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

    def clear_search_tags(self):
        self.transcript_text.tag_remove("searchmatch", "1.0", tk.END)
        self.transcript_text.tag_remove("searchactive", "1.0", tk.END)
