# Eval-Driven Development (EDD) for Agent Skills

Eval-Driven Development (EDD) adapts Test-Driven Development (TDD) principles to AI agent skills and runbooks. No skill is considered production-ready until it demonstrates a measurable quantitative advantage over the model's unassisted baseline.

## 1. The EDD Cycle

```
1. Define Test Cases (evals/eval-cases.json)
               │
               ▼
2. Baseline Execution (WITHOUT_SKILL)
               │
               ▼
3. Skill Implementation (SKILL.md + scripts/ + references/)
               │
               ▼
4. Guided Execution (WITH_SKILL)
               │
               ▼
5. Comparative Analysis & Refactoring
```

## 2. Evaluation Metrics

To rigorously benchmark `with_skill` vs `without_skill`, track these core metrics:

1. **Functional Pass Rate (%):** Did the agent complete the task without errors and satisfy all requirements?
2. **Tool Call Count:** Did the skill eliminate redundant exploratory tool calls via deterministic scripts and precise guidelines?
3. **Context & Token Usage:** Did Progressive Disclosure prevent full-file dumps into prompt context?
4. **Hallucination Resistance:** Did the model adhere strictly to canonical signatures without inventing flags?
5. **Autonomy (Turn Count):** How many interactions or user clarifications were needed to complete the task?

## 3. Test Case Schema (`evals/eval-cases.json`)

```json
[
  {
    "id": "eval-001",
    "description": "Scaffolding of a new database migration skill",
    "prompt": "Create a skill named 'db-migrator' to automate migrations with Alembic.",
    "assertions": [
      "Target directory contains SKILL.md and scripts/quick_validate.py",
      "Frontmatter specifies name: db-migrator and description with actionable triggers",
      "quick_validate.py returns exit code 0"
    ]
  }
]
```

## 4. Acceptance Criteria
A skill is ready for production when:
- Success rate `with_skill` >= 90% (vs baseline).
- Reduction in turns or failed steps of at least 30%.
- Zero broken relative links and 100% pass rate in deterministic validation.
