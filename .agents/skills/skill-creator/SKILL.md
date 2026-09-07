---
name: skill-creator
description: Guides the creation, scaffolding, deterministic validation, and evaluation of new agent skills in Antigravity, Claude Code, or Cursor under the agentskills.io standard. Use when the user requests a new skill, wants to structure agentic runbooks, automate skill validations, or implement Eval-Driven Development (EDD).
---

# Skill Creator: Canonical Meta-Skill

Specialized meta-skill guiding the complete lifecycle of new AI agent skills following the `agentskills.io` standard and the principle of **Progressive Disclosure**.

For the full architectural specification, see [canonical-structure.md](./references/canonical-structure.md).

---

## Workflow Phases

### Phase 1: Requirements Discovery
Before writing code or instructions, clarify operational scope:
1. **Triggers and Activation:** Which keywords, user intents, or failure scenarios trigger this skill?
2. **Tooling Requirements:** Does it require local CLI scripts, external API calls, or helper tools?
3. **Determinism vs. Heuristics:**
   - Tasks that are mathematical, syntactic, or deterministically verifiable belong in executable scripts under `scripts/`.
   - Tasks requiring contextual reasoning or synthesis belong in prompt guidelines in `SKILL.md`.

### Phase 2: Canonical Scaffolding
Create the standard directory hierarchy:
```text
<skill-name>/
├── SKILL.md                 # Root file with YAML frontmatter and executive guidelines (<150 lines)
├── scripts/                 # Deterministic tools and verification scripts
│   └── quick_validate.py    # Structural and link validator
├── references/              # Detailed technical documentation and large reference tables
├── examples/                # Practical examples and few-shot templates
└── evals/                   # Benchmarks and quantitative evaluation suites
```

### Phase 3: Frontmatter & Progressive Disclosure
1. **Pushy Frontmatter:** Write the YAML frontmatter strictly in the third person, with actionable triggers and a kebab-case name matching the directory. See [frontmatter-guide.md](./references/frontmatter-guide.md).
2. **Line Budget (<150 lines):** Keep `SKILL.md` compact as an executive index.
3. **Progressive Disclosure:** Delegate deep schemas, reference tables, and extensive guides to modular files in `references/`.

### Phase 4: Automated Validation with `quick_validate.py`
Run the deterministic validator to verify YAML frontmatter, naming conventions, line limits, and physical link integrity:
```bash
python scripts/quick_validate.py --skill <path-to-skill>
# Or validate all skills in workspace:
python scripts/quick_validate.py --skills-dir .agents/skills/
```
Ensure the script returns exit code `0`. Tool reference: [quick_validate.py](./scripts/quick_validate.py).

### Phase 5: Eval-Driven Development (EDD)
Quantitatively verify performance improvement:
1. **Baseline (`without_skill`):** Test the agent on target tasks without the skill; record errors and token usage.
2. **Evaluation (`with_skill`):** Enable the skill and run identical test cases.
3. **Acceptance Criteria:**
   - Functional success rate >= 90%.
   - Measurable reduction in redundant tool calls and retries.
   - 100% pass rate on assertions in `evals/`.
   Detailed methodology: [edd-methodology.md](./references/edd-methodology.md).
