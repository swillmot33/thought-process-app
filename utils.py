import re

from constants import TAG_PATTERNS, TAG_OPTIONS

def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")

def chunk_ref(chunk_id: str, line_no: int) -> str:
    return f"{chunk_id}:L{line_no}"

def parse_ref(ref: str):
    m = re.match(r"^(C\d+):L(\d+)$", ref)
    if not m:
        return ("", 0)
    return m.group(1), int(m.group(2))

def next_chunk_id(thread):
    return f"C{len(thread['chunks']) + 1}"

def clean_tag_markers(text: str) -> str:
    out = text
    for _, pattern in TAG_PATTERNS:
        out = pattern.sub("", out)
    out = re.sub(r"\s+", " ", out).strip(" -:\t")
    return out.strip()

def choose_meaningful_label(text: str):
    t = clean_tag_markers(text)
    t = re.sub(r"^(You|AI):\s*", "", t).strip()
    if ":" in t:
        _, after = t.split(":", 1)
        if len(after.strip()) >= 4:
            t = after.strip()
    t = re.sub(r"^\(([A-Za-z0-9]+)\)\s*", "", t)
    t = re.sub(r"^\d+\)\s*", "", t)
    t = t.strip(" .,:;!-")
    if not t:
        return ""
    words = t.split()
    if len(words) > 12:
        t = " ".join(words[:12])
    return t

def clean_split_label(text: str):
    t = choose_meaningful_label(text)
    t = re.sub(r"^(It's|It is)\s*:\s*", "", t, flags=re.I)
    t = re.sub(r"^(To start)\b", "start", t, flags=re.I)
    return t.strip() or clean_tag_markers(text)

def collect_section_lines(import_text: str, section_name: str):
    text = normalize_newlines(import_text)
    lines = text.split("\n")
    target = section_name.strip().upper()
    start_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().upper() == target:
            start_idx = i + 1
            break
    if start_idx is None:
        return []
    out = []
    section_header = re.compile(r"^[A-Z][A-Z0-9 /\-()]+$")
    for ln in lines[start_idx:]:
        stripped = ln.strip()
        if stripped.startswith("==="):
            break
        if stripped and stripped.upper() == stripped and section_header.match(stripped) and not re.match(r"^\[L\d+\]", stripped):
            break
        out.append(ln)
    return out

def split_pasted_transcript_lines(import_text: str):
    text = normalize_newlines(import_text).strip("\n")
    if not text:
        return []
    lines = text.split("\n")
    body = []
    current = None
    speaker_re = re.compile(r"^\s*(You|AI|Assistant|ChatGPT|User|System):\s*(.*)$", re.I)
    numbered_re = re.compile(r"^\s*\[L\d+\]\s*(.*)$")
    for ln in lines:
        raw = ln.rstrip()
        stripped = raw.strip()
        if not stripped:
            if current:
                body.append(current.strip())
                current = None
            continue
        m_num = numbered_re.match(raw)
        if m_num:
            content = m_num.group(1).strip()
            if current:
                body.append(current.strip())
            current = content
            continue
        m = speaker_re.match(raw)
        if m:
            if current:
                body.append(current.strip())
            current = f"{m.group(1).title()}: {m.group(2).strip()}".strip()
            continue
        if current is None:
            current = stripped
        else:
            current += (" " if not current.endswith(" ") else "") + stripped
    if current:
        body.append(current.strip())
    return body

def extract_transcript_body(import_text: str):
    transcript_lines = collect_section_lines(import_text, "TRANSCRIPT CHUNK")
    if transcript_lines:
        cleaned = []
        for ln in transcript_lines:
            m = re.match(r"^\[L\d+\]\s*(.*)$", ln)
            cleaned.append((m.group(1) if m else ln).rstrip())
        return [ln for ln in cleaned if ln.strip()]
    return split_pasted_transcript_lines(import_text)

def extract_thread_title(import_text: str):
    m = re.search(r"^THREAD:\s*(.+)$", normalize_newlines(import_text), re.M)
    if not m:
        return ""
    title = m.group(1).strip()
    title = re.sub(r"^<.*>$", "", title).strip()
    return title

def detect_tags_from_section(import_text: str, chunk_id: str, body_lines):
    section_lines = collect_section_lines(import_text, "TAGGED ITEMS")
    if not section_lines:
        return []
    tags = []
    seen = set()
    for ln in section_lines:
        m = re.search(r"\[(.*?)\]\s*C\d+:L(\d+)(?:-L(\d+))?", ln)
        if not m:
            continue
        tag_name = m.group(1).strip().lower()
        if tag_name not in TAG_OPTIONS:
            continue
        start = int(m.group(2))
        end = int(m.group(3) or start)
        for idx in range(start, end + 1):
            if 1 <= idx <= len(body_lines):
                key = (tag_name, idx)
                if key in seen:
                    continue
                seen.add(key)
                tags.append(make_tag_entry(tag_name, chunk_id, idx, body_lines[idx - 1], "imported"))
    return tags

def make_tag_entry(tag_name, chunk_id, idx, line, source):
    clean_text = clean_tag_markers(line)
    if tag_name in ("concept", "shift"):
        display_text = choose_meaningful_label(line)
    elif tag_name == "split":
        display_text = clean_split_label(line)
    else:
        display_text = clean_text
    return {
        "type": tag_name,
        "chunk_id": chunk_id,
        "line": idx,
        "ref": chunk_ref(chunk_id, idx),
        "text": line.rstrip(),
        "clean_text": clean_text,
        "display_text": display_text,
        "source": source,
    }

def detect_explicit_tags(lines, chunk_id):
    tags = []
    for idx, line in enumerate(lines, start=1):
        for tag_name, pattern in TAG_PATTERNS:
            if pattern.search(line):
                tags.append(make_tag_entry(tag_name, chunk_id, idx, line, "explicit"))
    return tags
