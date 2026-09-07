# Frontmatter Specification & "Pushy Descriptions"

Under the `agentskills.io` standard and Antigravity / Claude Code discovery systems, agents read YAML frontmatter during startup indexing without loading full file bodies into memory.

## 1. Mandatory YAML Schema

```yaml
---
name: <kebab-case-name>
description: <third-person-description-with-clear-triggers>
---
```

### Naming Invariants (`name`)
1. **Directory Match:** The `name` value must strictly match the enclosing directory name.
2. **Strict Kebab-Case:** Lowercase letters (`a-z`), digits (`0-9`), and single hyphens (`-`) only. No underscores or uppercase characters.
3. **Max Length:** 64 characters.

## 2. Pushy Descriptions: Actionable Triggering

The `description` field is the **only** text the model inspects when deciding whether to activate a skill. A passive description leads to agent under-activation or omission.

### Anatomy of a Pushy Description
1. **Active Third-Person Action Verbs:** Start with direct action verbs: `Designs...`, `Guides...`, `Optimizes...`, `Builds...`, `Validates...`.
2. **Concrete Capabilities:** List 2 to 4 specific technical problems solved.
3. **Explicit Triggers ("Use when..."):** Define exact keywords, error scenarios, or user requests that mandate activation.

### Antipatterns vs Best Practices

| Antipattern (Avoid) | Best Practice (Adopt) |
| :--- | :--- |
| `name: my_skill` (underscores) | `name: my-skill` (kebab-case) |
| `description: I can help you format code` (first-person) | `description: Formats and refactors Python code according to PEP 8...` (third-person) |
| `description: Helps with databases` (vague, no triggers) | `description: Diagnoses PostgreSQL bottlenecks. Use when queries are slow, connection pool errors occur, or EXPLAIN ANALYZE is requested.` |
| Descriptions > 1024 characters | Concise descriptions between 80 and 500 characters, dense in technical keywords. |
