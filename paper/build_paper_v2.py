# -*- coding: utf-8 -*-
"""Assemble paper/paper_zh_draft_v2.md from the v1 draft plus the W21-W24 sections."""
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def read(p):
    return io.open(p, encoding="utf-8").read()


def strip_rules(text):
    lines = text.strip("\n").split("\n")
    while lines and lines[-1].strip() in ("", "---"):
        lines.pop()
    return "\n".join(lines).strip("\n")


def slice_between(text, start, stop):
    i = text.index(start)
    j = text.index(stop, i)
    return text[i:j].strip("\n")


old = read(REPO / "paper" / "paper_zh_draft.md")
head = strip_rules(read(ROOT / "_v2_head.md"))
front = strip_rules(read(ROOT / "_v2_front.md"))
sec29 = strip_rules(read(ROOT / "_v2_sec29.md"))
body_a = strip_rules(read(ROOT / "_v2_body_a.md"))
body_b = strip_rules(read(ROOT / "_v2_body_b.md"))
disc_extra = strip_rules(read(ROOT / "_v2_disc_extra.md"))
concl = strip_rules(read(ROOT / "_v2_concl.md"))
appendix = strip_rules(read(ROOT / "_v2_appendix.md"))

sec2 = slice_between(old, "## 2 \u6570\u636e\u4e0e\u65b9\u6cd5", "## 3 \u7ed3\u679c")
sec3 = slice_between(old, "## 3 \u7ed3\u679c", "## 4 \u8ba8\u8bba")
sec4 = slice_between(old, "## 4 \u8ba8\u8bba", "## 5 \u7ed3\u8bba")

sec2 = sec2.replace("### 2.9 \u591a\u667a\u80fd\u4f53", "### 2.10 \u591a\u667a\u80fd\u4f53")
sec2 = sec2.replace("### 2.10 \u7b5b\u9009\u7ba1\u7ebf", "### 2.11 \u7b5b\u9009\u7ba1\u7ebf")
sec2 = sec2.replace("\u00a72.1\u2013\u00a72.9", "\u00a72.1\u2013\u00a72.10")
sec2 = sec2.replace("\u8868 2.10", "\u8868 2.11")
marker = "### 2.10 \u591a\u667a\u80fd\u4f53"
assert marker in sec2, "section 2.10 marker missing"
sec2 = sec2.replace(marker, sec29 + "\n\n" + marker, 1)

sec4 = sec4.replace("\uff08\u00a72.9\uff09", "\uff08\u00a72.10\uff09")

parts = [head, front, sec2, sec3, body_a, body_b, sec4, disc_extra, concl, appendix]
out = ("\n\n---\n\n").join(strip_rules(p) for p in parts) + "\n"
def validate_tables(text):
    """Fail loudly when a markdown table block has ragged column counts.

    A literal pipe inside a cell (for example a Spearman rank written with
    vertical bars) silently splits that cell and pushes the table one column
    wider.  Catching it at assembly time keeps the rendered docx honest.
    """
    lines = text.split("\n")
    problems = []
    tables = 0
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            tables += 1
            widths = set()
            for row in block:
                stripped = row.strip().strip("|")
                widths.add(len(stripped.split("|")))
            if len(widths) > 1:
                problems.append((block[0].strip()[:60], sorted(widths)))
        else:
            i += 1
    if problems:
        raise SystemExit("ragged markdown tables: " + repr(problems))
    return tables

n_tables = validate_tables(out)

target = ROOT / "paper_zh_draft_v2.md"
io.open(target, "w", encoding="utf-8", newline="\n").write(out)

print("wrote", target)
print("chars", len(out), "lines", out.count(chr(10)) + 1, "figures", out.count("!["), "tables", n_tables)
for h in ["## 1 ", "## 2 ", "## 3 ", "## 4 ", "## 5 ", "## \u6570\u636e\u4e0e\u4ee3\u7801", "## \u9644\u5f55 A", "## \u9644\u5f55 B", "## \u9644\u5f55 C", "## \u53c2\u8003\u6587\u732e", "### 2.9 ", "### 2.10 ", "### 2.11 ", "### 3.17 ", "### 3.18 ", "### 3.19 ", "### 3.20 ", "### 4.6 ", "### 4.7 "]:
    print(h.strip(), "->", out.count(h))
