# Companion Research Console

A desktop app for capturing, tagging, and navigating complex thought processes — built for structured AI-assisted research sessions.

## What it does

The app lets you import conversation transcripts, break them into numbered chunks, tag individual lines with semantic labels, and draw explicit relations between ideas. It provides multiple views (list, tree, graph) to navigate the structure of a conversation over time.

## Features

- **Threads** — organize conversations into named threads; each thread holds a sequence of chunks
- **Chunked transcripts** — conversations are split into line-numbered chunks (`C1:L3`, `C2:L1-L4`) for stable cross-references
- **Tags** — annotate lines with: `flag`, `key phrasing`, `trigger`, `interesting`, `not relevant`, `split`, `concept`, `shift`
- **Relations** — link chunks with typed edges: `rephrase`, `example`, `subconcept`, `continue`, `supports`, `split-from`, `refers-back`
- **Graph view** — visualize the relation graph rooted at any chunk, with zoom and collapse
- **Tree view** — navigate the relation tree forward/backward with keyboard shortcuts
- **Search** — full-text search across all threads
- **Consolidate / Final Consolidate** — structured templates for summarizing a discussion span into key ideas, triggers, open questions, and notes
- **Import** — load conversation transcripts directly into a thread

## Running

Requires Python 3 with tkinter (included in most standard Python distributions).

```bash
python new_mixed_chains.py
```

To open a project file directly:

```bash
python new_mixed_chains.py path/to/project.crc.json
```

If a `Test.crc.json` file exists in the same directory, it loads automatically on startup.

## Project files

Projects are saved as `.crc.json` files. Each file contains all threads, chunks, tags, and relations.

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `s` | Set selected chunk as source |
| `a` | Add relation from source to selection |
| `d` | Clear source |
| `↑` / `↓` | Navigate list / tree |

## File structure

| File | Purpose |
|------|---------|
| `app.py` | Main application class and UI |
| `new_mixed_chains.py` | Entry point |
| `constants.py` | Tag/relation definitions, colors, protocol templates |
| `utils.py` | Parsing and reference utilities |
| `dialogs.py` | Import and relation-edit dialog windows |


Josslyn is super awesome
