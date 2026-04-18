"""Interactive Tk GUI for the Mercari agent.

Flow:
    1. Enter keyword -> click Search (or press Enter)
    2. See top-N titles + prices in a listbox
    3. Double-click a row, or multi-select + "Show details"
    4. Details (title, price, URL, description) appear in the right pane

Search is capped at SEARCH_TIMEOUT seconds; the progress bar + coloured
status bar make "waiting" vs "results shown" unambiguous.
"""

import sys
import threading
import tkinter as tk
import traceback
from tkinter import messagebox, ttk
from typing import Dict, List

from mercari_api_client import MercariApiClient

SEARCH_TIMEOUT = 4.0       # seconds
DETAIL_TIMEOUT = 8.0       # seconds (higher because of concurrent detail fetches)


def _format_price(value) -> str:
    """Render Mercari's price (int or numeric string) as '¥1,200'. '¥?' on unknown."""
    if value in (None, "", 0, "0"):
        return "¥?"
    try:
        return f"¥{int(value):,}"
    except (TypeError, ValueError):
        try:
            return f"¥{int(str(value).replace(',', '').strip()):,}"
        except (TypeError, ValueError):
            return f"¥{value}"

# Status bar colour scheme
COLOR_IDLE = "#e8e8e8"
COLOR_BUSY = "#ffe8a8"
COLOR_OK = "#c8f0c8"
COLOR_ERROR = "#f6c8c8"


class MercariGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Mercari Agent")
        self.root.geometry("1100x680")

        self.search_client = MercariApiClient(timeout=SEARCH_TIMEOUT)
        self.detail_client = MercariApiClient(timeout=DETAIL_TIMEOUT)
        self.search_results: List[Dict[str, str]] = []

        self._build_widgets()
        self._set_status("Ready", COLOR_IDLE)

    # ── UI layout ──────────────────────────────────────────────────────────

    def _build_widgets(self) -> None:
        # Top: keyword input + buttons
        top = ttk.Frame(self.root, padding=(10, 8))
        top.pack(fill=tk.X)

        ttk.Label(top, text="Keyword:").pack(side=tk.LEFT)
        self.keyword_var = tk.StringVar()
        self.keyword_entry = ttk.Entry(top, textvariable=self.keyword_var, width=60)
        self.keyword_entry.pack(side=tk.LEFT, padx=(6, 6), fill=tk.X, expand=True)
        self.keyword_entry.bind("<Return>", lambda _e: self._on_search())
        self.keyword_entry.focus_set()

        ttk.Label(top, text="Top-N:").pack(side=tk.LEFT)
        self.topn_var = tk.IntVar(value=10)
        ttk.Spinbox(top, from_=1, to=50, textvariable=self.topn_var, width=5).pack(
            side=tk.LEFT, padx=(2, 6)
        )

        self.search_btn = ttk.Button(top, text="Search", command=self._on_search)
        self.search_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.details_btn = ttk.Button(
            top, text="Show details", command=self._on_show_details, state=tk.DISABLED
        )
        self.details_btn.pack(side=tk.LEFT)

        # Progress bar (shown only while a request is in flight)
        progress_row = ttk.Frame(self.root, padding=(10, 0))
        progress_row.pack(fill=tk.X)
        self.progress = ttk.Progressbar(progress_row, mode="indeterminate")
        self.progress.pack(fill=tk.X)
        self.progress.pack_forget()  # hidden until needed

        # Middle: two panes
        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=(6, 6))

        # Left: titles list
        left = ttk.Frame(main)
        ttk.Label(
            left,
            text="Results  —  double-click = quick details,  "
            "Ctrl/Shift-click = multi-select",
        ).pack(anchor=tk.W)
        list_frame = ttk.Frame(left)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.titles_list = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            font=("Meiryo UI", 10),
            activestyle="none",
        )
        self.titles_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.titles_list.bind("<Double-Button-1>", self._on_double_click)
        scroll = ttk.Scrollbar(list_frame, command=self.titles_list.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.titles_list.config(yscrollcommand=scroll.set)
        main.add(left, weight=1)

        # Right: details view
        right = ttk.Frame(main)
        ttk.Label(right, text="Details").pack(anchor=tk.W)
        self.details_text = tk.Text(
            right, wrap=tk.WORD, font=("Meiryo UI", 10), state=tk.DISABLED
        )
        self.details_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        dscroll = ttk.Scrollbar(right, command=self.details_text.yview)
        dscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.details_text.config(yscrollcommand=dscroll.set)
        main.add(right, weight=2)

        # Bottom: coloured status bar
        self.status_var = tk.StringVar(value="")
        self.status_label = tk.Label(
            self.root,
            textvariable=self.status_var,
            anchor=tk.W,
            padx=10,
            pady=5,
            font=("Meiryo UI", 10, "bold"),
        )
        self.status_label.pack(fill=tk.X)

    # ── Async helpers ──────────────────────────────────────────────────────

    def _run_bg(self, worker, on_done) -> None:
        """Run `worker()` on a thread, then hand (result, err) to `on_done`
        on the Tk thread."""

        def target():
            try:
                result = worker()
                err = None
            except Exception as exc:
                print(f"[bg-thread] {type(exc).__name__}: {exc}", file=sys.stderr)
                traceback.print_exc()
                result = None
                err = exc
            self.root.after(0, on_done, result, err)

        threading.Thread(target=target, daemon=True).start()

    # ── Actions ────────────────────────────────────────────────────────────

    def _on_search(self) -> None:
        keyword = self.keyword_var.get().strip()
        if not keyword:
            messagebox.showwarning("Input needed", "Please enter a keyword.")
            return
        top_n = max(1, int(self.topn_var.get()))

        self.titles_list.delete(0, tk.END)
        self._set_details("")
        self.search_results = []

        self._start_busy(f"⏳ Searching for '{keyword}' (timeout {SEARCH_TIMEOUT:.0f}s)...")
        self._run_bg(
            lambda: self.search_client.search_titles(keyword, top_n=top_n),
            self._on_search_done,
        )

    def _on_search_done(self, results, err) -> None:
        self._stop_busy()
        if err:
            self._set_status(f"✖ Search failed: {err}", COLOR_ERROR)
            messagebox.showerror("Search failed", f"{type(err).__name__}: {err}")
            return
        if not results:
            self._set_status("✖ No items found.", COLOR_ERROR)
            return
        self.search_results = results
        for i, item in enumerate(results, start=1):
            title = item.get("title") or f"(no title) {item['id']}"
            price_str = _format_price(item.get("price"))
            self.titles_list.insert(tk.END, f"{i:02d}.  [{price_str}]  {title}")
        self.details_btn.config(state=tk.NORMAL)
        self._set_status(
            f"✓ {len(results)} items loaded — double-click a row for quick details",
            COLOR_OK,
        )

    def _on_show_details(self) -> None:
        selected = self.titles_list.curselection()
        if not selected:
            messagebox.showinfo("Select items", "Please select at least one item.")
            return
        self._fetch_details_for_indices(selected)

    def _on_double_click(self, event) -> None:
        idx = self.titles_list.nearest(event.y)
        if idx < 0 or idx >= len(self.search_results):
            return
        self._fetch_details_for_indices([idx])

    def _fetch_details_for_indices(self, indices) -> None:
        ids = [self.search_results[i]["id"] for i in indices]
        if not ids:
            return
        self._set_details("")
        self._start_busy(f"⏳ Fetching details for {len(ids)} item(s)...")
        self._run_bg(
            lambda: self.detail_client.fetch_details_for_ids(ids),
            self._on_details_done,
        )

    def _on_details_done(self, items, err) -> None:
        self._stop_busy()
        if err:
            self._set_status(f"✖ Fetch failed: {err}", COLOR_ERROR)
            messagebox.showerror("Fetch failed", f"{type(err).__name__}: {err}")
            return
        if not items:
            self._set_status("✖ No details returned.", COLOR_ERROR)
            return

        blocks = []
        for idx, item in enumerate(items, start=1):
            price_str = _format_price(item.get("price"))
            blocks.append(
                f"[{idx}] {item.get('title', '').strip()}\n"
                f"Price: {price_str}\n"
                f"URL: {item.get('url', '')}\n\n"
                f"{item.get('description', '').strip() or '(empty description)'}\n"
            )
        self._set_details(("\n" + "─" * 80 + "\n\n").join(blocks))
        self._set_status(f"✓ Loaded details for {len(items)} item(s)", COLOR_OK)

    # ── UI state helpers ───────────────────────────────────────────────────

    def _start_busy(self, msg: str) -> None:
        self.search_btn.config(state=tk.DISABLED)
        self.details_btn.config(state=tk.DISABLED)
        self.root.config(cursor="watch")
        self.progress.pack(fill=tk.X, padx=10, pady=(0, 2))
        self.progress.start(12)  # animation interval in ms
        self._set_status(msg, COLOR_BUSY)

    def _stop_busy(self) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        self.search_btn.config(state=tk.NORMAL)
        if self.search_results:
            self.details_btn.config(state=tk.NORMAL)
        self.root.config(cursor="")

    def _set_status(self, msg: str, color: str) -> None:
        self.status_var.set(msg)
        self.status_label.config(background=color)

    def _set_details(self, text: str) -> None:
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete("1.0", tk.END)
        if text:
            self.details_text.insert("1.0", text)
        self.details_text.config(state=tk.DISABLED)


def setup_console_encoding() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    setup_console_encoding()
    root = tk.Tk()
    MercariGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
