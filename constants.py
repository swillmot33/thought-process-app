import re

TAG_OPTIONS = ["flag", "key phrasing", "trigger", "interesting", "not relevant", "split", "concept", "shift"]
RELATION_OPTIONS = ["rephrase", "example", "subconcept", "continue", "supports", "split-from", "refers-back"]
TAG_HIGHLIGHT_OPTIONS = ["none", "all", "custom"] + TAG_OPTIONS
RELATION_HIGHLIGHT_OPTIONS = ["none", "all"] + RELATION_OPTIONS

TAG_PATTERNS = [
    ("flag", re.compile(r"#flag\b|\[flag\]|tag:\s*flag\b", re.I)),
    ("key phrasing", re.compile(r"#key phrasing\b|\[key phrasing\]|tag:\s*key phrasing\b", re.I)),
    ("trigger", re.compile(r"#trigger\b|\[trigger\]|tag:\s*trigger\b", re.I)),
    ("interesting", re.compile(r"#interesting\b|\[interesting\]|tag:\s*interesting\b", re.I)),
    ("not relevant", re.compile(r"#not relevant\b|\[not relevant\]|tag:\s*not relevant\b", re.I)),
    ("split", re.compile(r"#split\b|\[split\]|tag:\s*split\b", re.I)),
    ("concept", re.compile(r"#concept\b|\[concept\]|tag:\s*concept\b", re.I)),
    ("shift", re.compile(r"#shift\b|\[shift\]|tag:\s*shift\b", re.I)),
]

TAG_COLORS = {
    "flag": "#ffe082",
    "key phrasing": "#cfe8ff",
    "trigger": "#ead8ff",
    "interesting": "#d6f5d1",
    "not relevant": "#efefef",
    "split": "#ffd6ef",
    "concept": "#d7f4ff",
    "shift": "#ffd6d6",
}

TAG_PRIORITY = {
    "flag": 1,
    "key phrasing": 2,
    "concept": 3,
    "split": 4,
    "interesting": 5,
    "trigger": 6,
    "shift": 7,
    "not relevant": 8,
}
RELATION_COLORS = {
    "rephrase": "#0b6aa2",
    "example": "#2c8c2c",
    "subconcept": "#5a49b6",
    "continue": "#a36a00",
    "supports": "#1d7d59",
    "split-from": "#b54c87",
    "refers-back": "#7a46b5",
}

PROTOCOL_SUMMARY = """Protocol (v160)

Tags
- flag
- key phrasing
- trigger
- interesting
- not relevant
- split
- concept
- shift

Tag modes
- live    (inline during conversation: #tag added in the message itself)
- review  (added manually in the app after import)
- ai      (proposed by AI in consolidate output, applied in app)

Tagging layers
- Most tagging comes from AI (layer: ai) in the consolidate output
- Some inline tagging happens live during conversation (layer: live)
- Light manual cleanup happens in the app (layer: review)
- Goal: eventually every line has a tag or is part of a relation

Commands
- consolidate
- final consolidate

Line Numbering + References
- Every transcript chunk must be line-numbered
- Every consolidate and final consolidate must include a chunk id
- References are always chunk-local

Reference format
- Single line: C#:L#
- Line range: C#:L#-L#

Design Rules
- The verbatim transcript is the primary output — reproduce as close to word-for-word as possible
- Summaries and interpretations are derived from the transcript, not a replacement for it
- Chunk transcripts as finely as practical
- Keep ideas modular
- Make relations between ideas explicit
- Notes are organized by tags/context, not rigid thought-process reconstruction
- Search and referencing happen in the app
- The app is for external storage + structure
- Live conversation happens here
- Prioritize capturing triggers and flow over completeness
- If uncertain, mark uncertainty rather than invent structure
"""

CONSOLIDATE_TEMPLATE = """=== CONSOLIDATE START ===
THREAD: <thread name or working title>
SPAN: since last consolidate
CHUNK ID: C<next_chunk_number>

VERBATIM TRANSCRIPT
(reproduce as close to word-for-word as possible — this is the primary record)
[L1] You: ...
[L2] AI: ...
[L3] You: ...
[L4] AI: ...
(continue for all lines in this span)

KEY TERMS / DEFINITIONS
- term: concise definition

PROPOSED TAGS  (layer: ai — to be applied in app)
- [flag]        C#:L# — reason
- [key phrasing] C#:L# — exact phrase
- [trigger]     C#:L# -> C#:L# — what triggered what
- [interesting] C#:L# — reason
- [not relevant] C#:L# — reason
- [split]       C#:L# — branch description
- [concept]     C#:L# — concept name
- [shift]       C#:L# — description of shift

PROPOSED RELATIONS  (layer: ai — to be applied in app)
- C#:L# --rephrase--> C#:L#
- C#:L# --example--> C#:L#
- C#:L# --subconcept--> C#:L#
- C#:L# --continues--> C#:L#
- C#:L# --supports--> C#:L#
- C#:L# --split-from--> C#:L#
- C#:L# --refers-back--> C#:L#

TRIGGERS
- C#:L# — source phrase / idea
  -> what it triggered (C#:L# if known)

SPLITS
- C#:L# — split point
  - likely branch direction
  - stay in thread / new thread

RESUME POINTS
- C#:L# — good re-entry point into the thought process

OPEN QUESTIONS
- ...

FACTS
- term: definition / theorem / reference

AI INTERPRETATION
- (high confidence) ...
- (medium confidence) ...
- (speculative) ...

UNCERTAINTIES
- ...

NOTES MARKDOWN
# Section
## Subsection
- note bullets suitable for app notes layer

=== CONSOLIDATE END ===
"""

FINAL_CONSOLIDATE_TEMPLATE = """=== FINAL CONSOLIDATE START ===
THREAD: <thread name>
SPAN: since last final consolidate
CHUNK ID: C<next_chunk_number>

VERBATIM TRANSCRIPT
(reproduce the full span as close to word-for-word as possible — primary record)
[L1] You: ...
[L2] AI: ...
[L3] You: ...
[L4] AI: ...
(continue for all lines in this span)

TRUNCATED DISCUSSION OUTPUT
(compressed readable version for reference — comes after verbatim, not instead of it)
- ...

KEY TERMS / DEFINITIONS
- term: definition

PROPOSED TAGS  (layer: ai — to be applied in app)
- [flag]         C#:L# — reason
- [key phrasing] C#:L# — exact phrase
- [trigger]      C#:L# -> C#:L# — what triggered what
- [interesting]  C#:L# — reason
- [not relevant] C#:L# — reason
- [split]        C#:L# — branch description
- [concept]      C#:L# — concept name
- [shift]        C#:L# — description of shift

PROPOSED RELATIONS  (layer: ai — to be applied in app)
- C#:L# --rephrase--> C#:L#
- C#:L# --example--> C#:L#
- C#:L# --subconcept--> C#:L#
- C#:L# --continues--> C#:L#
- C#:L# --supports--> C#:L#
- C#:L# --split-from--> C#:L#
- C#:L# --refers-back--> C#:L#

TRIGGERS
- C#:L# — source
  -> resulting shift (C#:L# if known)

SPLITS / THREADING SUGGESTIONS
- C#:L# — split point
  - continuation suggestion
  - new-thread suggestion if appropriate

RESUME POINTS
- C#:L# — strong re-entry into discussion

OPEN QUESTIONS
- ...

BEST WRITE-UP OF KEY IDEAS
- Idea A
  - supporting lines: C#:L#-L#
  - explanation
  - relation to other ideas

FACTS
- term: definition / theorem / reference

AI INTERPRETATION
- (high confidence) ...
- (medium confidence) ...
- (speculative) ...
- strongest structural reading
- most important shifts in thinking
- likely next directions

UNCERTAINTIES
- ...

NOTES MARKDOWN
# Title
## Section
### Subsection
- polished, app-ready note content
- organized by tags/context

INDEX TERMS
- ...

=== FINAL CONSOLIDATE END ===
"""
