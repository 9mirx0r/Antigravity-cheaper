# Canonical Structure for Agent Skills (agentskills.io)

This document details the standard hierarchy and artifact distribution for AI agent skills across Antigravity, Claude Code, and Cursor.

## 1. Directory Structure

```text
<skill-name>/
├── SKILL.md                 # Root file with YAML frontmatter and executive guidelines (<150 lines)
├── scripts/                 # Deterministic tools in executable code (Python, Bash, etc.)
│   └── quick_validate.py    # Syntax and structural integrity validator
├── references/              # Extended documentation, specifications, and reference tables
│   ├── canonical-structure.md
│   ├── frontmatter-guide.md
│   └── edd-methodology.md
├── examples/                # Usage examples, templates, and before/after comparisons
│   └── sample-skill/
└── evals/                   # Test cases and evaluation benchmarks (EDD)
    └── eval-cases.json
```

## 2. Roles & Responsibilities by Component

### SKILL.md (Executive Body)
- **Purpose:** Provide immediate operational context and orchestrate workflow phases.
- **Line Budget:** Strictly keep below **150 lines**. Excessive prompt length degrades model reasoning and dilutes attention.
- **Progressive Disclosure:** Deep schemas, full API guides, and reference tables are delegated to `references/`.

### scripts/ (Determinism > Heuristics)
- **Purpose:** Automate mechanical, repetitive, or mathematical tasks that an LLM should not compute probabilistically.
- **Advantages:**
  - Zero hallucination in structural/syntax validation.
  - Significant token savings (local execution consumes zero context window).
  - Reproducible binary verification.

### references/ (On-Demand Loading)
- **Purpose:** House in-depth documentation, JSON/YAML schemas, formal specs, and best practice catalogs.
- **Access Pattern:** The agent reads these files via `view_file` **only** when the active task requires them.

### examples/ (Few-shot Grounding)
- **Purpose:** Demonstrate concrete inputs and outputs. Reduces generative entropy and aligns model heuristics.

### evals/ (Eval-Driven Development)
- **Purpose:** Empirically measure skill efficacy by benchmarking `with_skill` versus `without_skill` trajectories.
