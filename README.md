# cc-slim

**Scan your Claude Code prefix. See what's costing you tokens.**

## The Problem

Claude Code loads your skills, MEMORY.md, CLAUDE.md, and rules into every request as part of the system prompt prefix. This prefix is cached and re-read on every single turn.

Every extra 1K tokens in your prefix gets re-read every turn. At 30 turns/session and 26 sessions/month, that's 780 extra reads per month — per 1K tokens. It adds up fast.

Nobody measures this. This tool does.

We built this tool in a single session. That session itself proved why you need it.

## Real Numbers

One user's before/after:

| | Prefix | Controllable | Monthly cache reads (30t x 26s) |
|---|---|---|---|
| Before | ~29.8K tokens | ~15.3K tokens | ~11.9M tokens |
| After | ~22.4K tokens | ~7.9K tokens | ~6.2M tokens |
| **Saved** | **~7.4K tokens/turn** | | **~5.8M tokens/month** |

The savings came from archiving unused skill descriptions and splitting operational content out of MEMORY.md.

## Install

```bash
git clone https://github.com/cyberxuan-XBX/cc-slim.git
cd cc-slim
python3 cc_slim.py scan
```

No dependencies. No pip install. Just Python 3.6+.

## Usage

### `cc-slim scan`

Scans your `~/.claude/` directory and reports what's in your prefix:

```
$ python3 cc_slim.py scan

  cc-slim scan results

╭─────────────────────────┬──────────────┬───────────────╮
│ Source                  │         Size │ Tokens (est.) │
├─────────────────────────┼──────────────┼───────────────┤
│ Skills (12 active)      │  5,230 chars │        ~1,420 │
│ MEMORY.md (1 found)     │  3,800 chars │        ~1,200 │
│ CLAUDE.md (1 found)     │  2,100 chars │          ~525 │
│ Rules (3 files)         │  1,500 chars │          ~420 │
├─────────────────────────┼──────────────┼───────────────┤
│ Your controllable total │              │        ~3,565 │
│ Estimated total prefix  │              │       ~18,065 │
╰─────────────────────────┴──────────────┴───────────────╯

  Top 5 largest skill descriptions (prefix cost):
    1. my-big-skill           892 chars  (~223 tokens)  "Use when..."
    2. another-skill           456 chars  (~114 tokens)  "Handles..."
    ...
```

**What it measures:**
- **Skills**: Only the `description` field from each SKILL.md frontmatter (that's what Claude Code injects into the prefix listing — not the full file)
- **MEMORY.md**: Your auto-memory files in `~/.claude/projects/*/memory/`
- **CLAUDE.md**: Project instruction files from your working directory up to `~`
- **Rules**: Files in `~/.claude/rules/`
- **Uncontrollable**: System prompt (~11K) + tool definitions (~3.5K) are estimated as fixed constants

### JSON output

```bash
python3 cc_slim.py scan --json
```

Machine-readable output for scripting or dashboards.

## How Token Estimation Works

cc-slim uses character-based heuristics (no external tokenizer needed):
- English text: ~4 chars per token
- CJK text: ~1.5 chars per token
- Mixed content uses a weighted average

These are rough estimates. For exact counts, use a tokenizer like `tiktoken`. But for comparison and optimization purposes, the estimates are consistent and useful.

## What Can You Do With the Results?

1. **Archive unused skills**: Move skill folders from `~/.claude/skills/` to `~/.claude/skills-archive/`. Claude Code only loads active skills.
2. **Trim skill descriptions**: Long descriptions cost tokens every turn. Keep them concise.
3. **Split MEMORY.md**: Move operational details (port lists, curl templates, project details) to reference files. Keep MEMORY.md under 200 lines with only what you need every turn.
4. **Slim CLAUDE.md**: Move manuals and guides to separate files. Keep CLAUDE.md focused on identity and critical rules.

## Roadmap

- [x] `scan` — Diagnose your prefix
- [ ] `suggest` — Automated recommendations
- [ ] `slim` — Execute cleanup with backup/restore

## See Also

- [prompt-slim](https://github.com/cyberxuan-XBX/prompt-slim) — Same idea, for any LLM. Supports Ollama, any system prompt file.
- [skill-sanitizer](https://github.com/cyberxuan-XBX/skill-sanitizer) — Scan your Claude Code skills for security threats
- Security, performance, and measurement. The toolkit.

## License

MIT
