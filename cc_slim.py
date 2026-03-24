#!/usr/bin/env python3
"""
cc-slim: Scan your Claude Code prefix and find what's costing you tokens.

Zero dependencies. Python 3.6+.
"""

import argparse
import os
import sys
import re
import json
from pathlib import Path


__version__ = "0.1.0"

# ── Constants ────────────────────────────────────────────────────────────────

# These are rough estimates for the parts of the prefix users cannot control.
# They will vary across Claude Code versions; treat them as ballpark figures.
SYSTEM_PROMPT_TOKENS_EST = 11000
TOOL_DEFS_TOKENS_EST = 3500
UNCONTROLLABLE_EST = SYSTEM_PROMPT_TOKENS_EST + TOOL_DEFS_TOKENS_EST

# Token estimation ratios (chars → tokens)
RATIO_EN = 4.0     # ~4 English chars per token
RATIO_CJK = 1.5    # ~1.5 CJK chars per token

# CJK Unicode ranges
CJK_RE = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff00-\uffef"
    r"\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]"
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Estimate token count from text using char-based heuristics."""
    if not text:
        return 0
    cjk_chars = len(CJK_RE.findall(text))
    other_chars = len(text) - cjk_chars
    tokens = cjk_chars / RATIO_CJK + other_chars / RATIO_EN
    return max(1, int(round(tokens)))


def read_file_safe(path: str) -> str:
    """Read a file, return empty string on failure."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, IOError):
        return ""


def extract_skill_info(skill_md_path: str) -> dict:
    """Extract name and description from a SKILL.md file."""
    content = read_file_safe(skill_md_path)
    if not content:
        return {"name": "unknown", "description": "", "chars": 0}

    name = "unknown"
    description = ""

    # Parse YAML frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            for line in frontmatter.strip().split("\n"):
                line = line.strip()
                if line.startswith("name:"):
                    name = line[5:].strip().strip('"').strip("'")
                elif line.startswith("description:"):
                    description = line[12:].strip().strip('"').strip("'")

    # Claude Code injects only the description into the prefix (system-reminder).
    # The full SKILL.md body is loaded only when the skill is invoked.
    # Prefix cost = "- name: description\n" per skill in the listing.
    listing = f"- {name}: {description}\n"

    return {
        "name": name,
        "description": description,
        "prefix_chars": len(listing),
        "total_chars": len(content),
    }


def format_number(n: int) -> str:
    """Format number with comma separators."""
    return f"{n:,}"


# ── Box drawing ──────────────────────────────────────────────────────────────

def print_table(rows, headers, col_aligns=None):
    """Print a table with box-drawing characters.

    rows: list of tuples
    headers: list of strings
    col_aligns: list of 'l' or 'r' per column (default: first col 'l', rest 'r')
    """
    num_cols = len(headers)
    if col_aligns is None:
        col_aligns = ["l"] + ["r"] * (num_cols - 1)

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    # Add padding
    widths = [w + 2 for w in widths]

    def hline(left, mid, right, fill="─"):
        parts = [fill * w for w in widths]
        return left + mid.join(parts) + right

    def data_line(cells, is_header=False):
        parts = []
        for i, cell in enumerate(cells):
            s = str(cell)
            if col_aligns[i] == "r":
                parts.append(s.rjust(widths[i] - 1) + " ")
            else:
                parts.append(" " + s.ljust(widths[i] - 1))
        return "│" + "│".join(parts) + "│"

    print(hline("╭", "┬", "╮"))
    print(data_line(headers, is_header=True))
    print(hline("├", "┼", "┤"))

    for idx, row in enumerate(rows):
        print(data_line(row))
        # Print separator before the last 2 rows (totals section)
        if idx == len(rows) - 3:
            print(hline("├", "┼", "┤"))

    print(hline("╰", "┴", "╯"))


# ── Scan ─────────────────────────────────────────────────────────────────────

def find_claude_dir() -> str:
    """Find the ~/.claude directory."""
    claude_dir = os.path.expanduser("~/.claude")
    if not os.path.isdir(claude_dir):
        print("Error: ~/.claude directory not found.", file=sys.stderr)
        print("Are you running this on a machine with Claude Code installed?",
              file=sys.stderr)
        sys.exit(1)
    return claude_dir


def scan_skills(claude_dir: str) -> list:
    """Scan all active skills."""
    skills_dir = os.path.join(claude_dir, "skills")
    skills = []
    if not os.path.isdir(skills_dir):
        return skills

    for entry in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, entry, "SKILL.md")
        if os.path.isfile(skill_path):
            info = extract_skill_info(skill_path)
            info["dir_name"] = entry
            skills.append(info)

    return skills


def scan_memory(project_dirs: list) -> list:
    """Find MEMORY.md files in project directories."""
    results = []
    for pdir in project_dirs:
        mem_path = os.path.join(pdir, "memory", "MEMORY.md")
        if os.path.isfile(mem_path):
            content = read_file_safe(mem_path)
            # Claude Code truncates MEMORY.md at 200 lines but still loads them
            lines = content.split("\n")
            results.append({
                "path": mem_path,
                "chars": len(content),
                "lines": len(lines),
                "project": os.path.basename(pdir),
            })
    return results


def scan_rules(claude_dir: str) -> list:
    """Scan rules files."""
    rules_dir = os.path.join(claude_dir, "rules")
    rules = []
    if not os.path.isdir(rules_dir):
        return rules

    for entry in sorted(os.listdir(rules_dir)):
        if entry.endswith(".md"):
            path = os.path.join(rules_dir, entry)
            content = read_file_safe(path)
            rules.append({
                "name": entry,
                "chars": len(content),
            })
    return rules


def scan_claude_md() -> list:
    """Find CLAUDE.md files (project root and parents)."""
    results = []
    # Check current directory and parents up to home
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    check_dirs = set()

    path = cwd
    while True:
        check_dirs.add(path)
        parent = os.path.dirname(path)
        if parent == path or not path.startswith(home):
            break
        path = parent

    for d in sorted(check_dirs):
        claude_md = os.path.join(d, "CLAUDE.md")
        if os.path.isfile(claude_md):
            content = read_file_safe(claude_md)
            results.append({
                "path": claude_md,
                "chars": len(content),
                "dir": d,
            })

    return results


def find_project_dirs(claude_dir: str) -> list:
    """Find project memory directories."""
    projects_dir = os.path.join(claude_dir, "projects")
    dirs = []
    if not os.path.isdir(projects_dir):
        return dirs

    for entry in os.listdir(projects_dir):
        full = os.path.join(projects_dir, entry)
        if os.path.isdir(full):
            dirs.append(full)

    return dirs


def cmd_scan(args):
    """Execute the scan command."""
    claude_dir = find_claude_dir()
    output_json = getattr(args, "json", False)

    # ── Collect data ──
    skills = scan_skills(claude_dir)
    project_dirs = find_project_dirs(claude_dir)
    memories = scan_memory(project_dirs)
    rules = scan_rules(claude_dir)
    claude_mds = scan_claude_md()

    # ── Calculate tokens ──
    # Skills: only description is injected into prefix (system-reminder listing)
    skill_prefix_chars = sum(s["prefix_chars"] for s in skills)
    skill_prefix_tokens = sum(estimate_tokens(
        f"- {s['name']}: {s['description']}\n"
    ) for s in skills)

    memory_total_chars = sum(m["chars"] for m in memories)
    memory_total_tokens = sum(estimate_tokens(read_file_safe(m["path"])) for m in memories)

    rules_total_chars = sum(r["chars"] for r in rules)
    rules_total_tokens = sum(estimate_tokens(read_file_safe(
        os.path.join(claude_dir, "rules", r["name"])
    )) for r in rules)

    claude_md_total_chars = sum(c["chars"] for c in claude_mds)
    claude_md_total_tokens = sum(estimate_tokens(read_file_safe(c["path"])) for c in claude_mds)

    controllable = skill_prefix_tokens + memory_total_tokens + rules_total_tokens + claude_md_total_tokens
    total_est = controllable + UNCONTROLLABLE_EST

    # ── JSON output ──
    if output_json:
        data = {
            "version": __version__,
            "skills": {
                "count": len(skills),
                "prefix_chars": skill_prefix_chars,
                "prefix_tokens_est": skill_prefix_tokens,
                "items": [{"name": s["name"], "dir": s["dir_name"],
                           "prefix_chars": s["prefix_chars"],
                           "total_chars": s["total_chars"],
                           "prefix_tokens_est": estimate_tokens(
                               f"- {s['name']}: {s['description']}\n"
                           )} for s in skills],
            },
            "memory": {
                "count": len(memories),
                "chars": memory_total_chars,
                "tokens_est": memory_total_tokens,
                "items": [{"path": m["path"], "chars": m["chars"], "lines": m["lines"]}
                          for m in memories],
            },
            "rules": {
                "count": len(rules),
                "chars": rules_total_chars,
                "tokens_est": rules_total_tokens,
                "items": [{"name": r["name"], "chars": r["chars"]} for r in rules],
            },
            "claude_md": {
                "count": len(claude_mds),
                "chars": claude_md_total_chars,
                "tokens_est": claude_md_total_tokens,
                "items": [{"path": c["path"], "chars": c["chars"]} for c in claude_mds],
            },
            "controllable_tokens_est": controllable,
            "uncontrollable_tokens_est": UNCONTROLLABLE_EST,
            "total_prefix_tokens_est": total_est,
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    # ── Table output ──
    print()
    print("  cc-slim scan results")
    print()

    table_rows = [
        (f"Skills ({len(skills)} active)", format_number(skill_prefix_chars) + " chars",
         "~" + format_number(skill_prefix_tokens)),
        (f"MEMORY.md ({len(memories)} found)", format_number(memory_total_chars) + " chars",
         "~" + format_number(memory_total_tokens)),
        (f"CLAUDE.md ({len(claude_mds)} found)", format_number(claude_md_total_chars) + " chars",
         "~" + format_number(claude_md_total_tokens)),
        (f"Rules ({len(rules)} files)", format_number(rules_total_chars) + " chars",
         "~" + format_number(rules_total_tokens)),
        ("Your controllable total", "", "~" + format_number(controllable)),
        ("Estimated total prefix", "", "~" + format_number(total_est)),
    ]

    print_table(
        table_rows,
        ["Source", "Size", "Tokens (est.)"],
        ["l", "r", "r"],
    )

    # ── Top skills by prefix cost ──
    if skills:
        print()
        sorted_skills = sorted(skills, key=lambda s: s["prefix_chars"], reverse=True)
        top_n = min(5, len(sorted_skills))
        print(f"  Top {top_n} largest skill descriptions (prefix cost):")
        for i, s in enumerate(sorted_skills[:top_n]):
            tokens = estimate_tokens(f"- {s['name']}: {s['description']}\n")
            desc_preview = s["description"][:50] + "..." if len(s["description"]) > 50 else s["description"]
            print(f"    {i+1}. {s['dir_name']:<20} {s['prefix_chars']:>5} chars  (~{tokens:>3} tokens)  \"{desc_preview}\"")

    # ── Memory details ──
    if memories:
        print()
        for m in memories:
            note = ""
            if m["lines"] > 200:
                note = f"  (⚠ {m['lines']} lines — only first 200 loaded, but all count toward cache)"
            elif m["lines"] > 150:
                note = f"  (⚠ {m['lines']} lines — approaching 200-line truncation limit)"
            print(f"  MEMORY.md: {m['lines']} lines, {format_number(m['chars'])} chars{note}")

    # ── Cost projection ──
    print()
    print("  Cost projection:")
    print(f"    Every extra 1K tokens in your prefix is re-read on every turn.")
    print(f"    At 30 turns/session × 26 sessions/month:")
    monthly_reads = 30 * 26
    monthly_controllable = controllable * monthly_reads
    print(f"    Your controllable prefix alone: ~{format_number(monthly_controllable)} tokens read/month")
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="cc-slim",
        description="Scan your Claude Code prefix and find what's costing you tokens.",
    )
    parser.add_argument("--version", action="version", version=f"cc-slim {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scan
    scan_parser = subparsers.add_parser("scan", help="Scan your Claude Code configuration")
    scan_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.command is None:
        # Default to scan
        args.command = "scan"
        args.json = False

    if args.command == "scan":
        cmd_scan(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
