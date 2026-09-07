# Governance Rule: Context Discipline & Token Efficiency

This rule is strictly enforced across all operations in this Antigravity (AGY) workspace. Its objective is to preserve context window capacity, maximize Gemini Context Caching hit rate (>85%), eliminate attention degradation, and optimize execution accuracy.

---

## 1. Output Discipline & Anti-Overengineering

### A. Ladder of Laziness (YAGNI Hierarchy)
Before writing any code, evaluate the task against this hierarchy and stop at the first rung that satisfies the requirement:
1. **Does this need to exist? (YAGNI):** If speculative ("just in case"), discard immediately.
2. **Already in this codebase?:** Search before writing (`grep_search`). Reuse existing helpers, patterns, or utilities.
3. **Does standard library do it?:** Prioritize built-in modules (`itertools`, `pathlib`, `json`, `dataclasses`, etc.) over custom code.
4. **Native platform feature?:** Use native browser/OS capabilities (e.g., `<input type="date">`, `<dialog>`, SQL constraints) instead of third-party libraries.
5. **Installed dependency?:** Reuse what is already in `package.json`/`pyproject.toml`. Do not install new packages for tasks solvable in a few lines.
6. **Can it be a one-liner?:** If it fits cleanly and legibly in one line, keep it to one line.
7. **Only then: Minimum working code:** Write the smallest valid diff that satisfies acceptance criteria.

### B. Zero Tool Narration (No Conversational Filler)
- **Never narrate tool calls before executing them.**
  - *Wrong:* "I will now search the `src/` directory for the `validateToken` function to see error handling. Let me run grep..."
  - *Right:* Invoke `grep_search` directly.
- Provide explanations or summaries only **after** receiving tool output, never before.

### C. Code-First Response Structure
- Deliver code modifications or diffs first.
- Follow with at most **3 concise lines**: what changed, what was deliberately omitted, and how to verify.

### D. BPE Tokenizer Rule (No Invented Abbreviations)
- **Do not invent abbreviations** such as `cfg`, `impl`, `req`, `fn`, `authz`. The BPE tokenizer fragments them into 2 to 3 sub-tokens, increasing token cost and degrading readability. Always use complete standard English words (`config`, `request`, `implementation`).

### E. Verify and Stop
- Once acceptance tests or verification checks pass, **stop immediately**.
- Do not perform unrequested cosmetic cleanup, speculative refactors, or extra styling once the goal is achieved.

---

## 2. Symbol Navigation Before File Dumping

- **Never read entire files by default**: Do not call `view_file` on large files (>150 lines) without locating the target region first.
- **Pre-flight localization**:
  - Use `grep_search` to locate class, function, variable, or error definitions.
  - Use AST tools (`agy_ast.py skeleton` / `symbols`) to view signatures without function bodies.
  - Use `find_by_name` to locate file paths before guessing.
- **Bounded windows**: When reading with `view_file`, always supply `StartLine` and `EndLine` for the specific region of interest.

---

## 3. Evidence Routing & Circuit Breaker

- **Local Threshold Routing (`agy_handoff.py`)**:
  - If serialized evidence fits within base budget (≤ 24 KB / ~6,000 tokens), deliver full content in a single turn to eliminate multi-turn expansion overhead (+97% tokens).
  - If content exceeds the threshold, pack with `agy_pack.py` using `--contains` and `--context` for targeted slicing.
- **2-Recovery Circuit Breaker:**
  - If 2 consecutive recovery attempts occur on the same unchanged source hash (`recovery_attempts >= 2`), **halt packing immediately**. Switch to direct focused reading (`view_file` on specific line ranges) to prevent token exhaustion loops.

---

## 4. Shell Dump Prohibition (`cat`, `type`, `Get-Content`)

- **Strict prohibition**: Do not invoke `cat`, `type`, or `Get-Content` on source, log, or data files via `run_command`.
- **Mandatory alternative**: Use `view_file` with line slices or bounded shell filters (`head`, `tail`).

---

## 5. Bounded Test & Build Outputs

- **Noise suppression**: Test runners (`pytest`, `npm test`, `cargo test`, etc.) are intercepted by `noise_sanitizer.py`.
- **Tee recovery hint**: Full logs are saved to `.gemini/scratch/test_output.log` while only the final ~35 lines and the log path are surfaced.
- **Pipeline contract preservation**: Commands piped into machine utilities (`| xargs`, `| wc`, `| awk`, `| jq`) remain unformatted to protect shell pipelines.

---

## 6. Clean Slate Subagent Delegation

- Delegate deep multi-file exploration or research to isolated subagents (`research` or specialized).
- Subagents must return only an executive summary, verified facts, and clickable file links (`file:///...`), never raw terminal dumps or intermediate logs.
