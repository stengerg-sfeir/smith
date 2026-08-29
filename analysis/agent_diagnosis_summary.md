# Executive Summary: Coding Agent & Behavioral Testing Diagnosis

## 1. Core Summary: The Agent's Two Main Deficiencies

The coding agent (`agentlib`) struggles with complex prompts due to two fundamental architectural issues:

### A. It is "Too Rigid in Checking" (Static Form over Behavioral Substance)
* **Symbol-Presence Blindness:** The AST validation (`agentlib/checks/ast_utils.py`) only asserts that classes and functions exist syntactically (`"class %s" in all_code`), never checking whether they are wired or invoked in data flow. As a result, unwired audit logs (Prompt 33), notifications (Prompt 40), and RBAC checks (Prompt 39) pass validation with zero errors.
* **Over-Constrained Canonicalization:** The manifest pipeline (`agentlib/pipeline/manifest.py`) forces all code into a flat `1-entity = 1-repository = 1-service` scheme. It strips abstract interface patterns (such as `ABC`/`Protocol` in Prompt 30) and duplicates or overwrites cross-cutting domain services.

### B. "Some Patterns are Missing" (Gaps in the Deterministic Machinery)
* **Missing Invariant/Validation Tier in Service Rendering:** `_service_method_body()` in `agentlib/generation/service_render.py` assumes any method matching standard CRUD names (`create_<entity>`, `add_<entity>`) is purely mechanical boilerplate. It generates a direct 1-line pass-through (`repo.create(...)`), bypassing the LLM completely and silently dropping all prompt-specified validations (e.g., age 18–70 in Prompt 09, reservation overlap checks in Prompt 27, calculated invoice line totals in Prompt 28).
* **Missing Relational DDL Modifiers:** The DDL generator in `agentlib/naming.py` lacks support for relational lifecycle modifiers such as `ON DELETE CASCADE` (causing orphaned tasks in Prompt 37).
* **Narrow Recipe Vocabulary:** The kernel only contains ~7 hardcoded recipe patterns (`export_csv`, `sum_by_group`, etc.), which prompts the LLM to over-generate analytical bloat while omitting core behavioral patterns like soft-delete, audit trails, and multi-filter compositions.

---

## 2. Benchmark Baseline: Prompts 01–40 Ground Truth

Out of 40 generated codebases, **only ~15–17 satisfy their prompt intent**, while **~23–25 exhibit legitimate behavioral failures**:

```
Total Prompts: 40
├── ✅ ~15–17 Fulfill Intent (Clean Passes)
│     ├── 01–04: Simple standalone scripts (Hello World, Calculator, Todo)
│     ├── 05–08, 10: Basic Single-Entity CRUD (Over-engineered with extra queries, but functional)
│     ├── 18–19: File import/export with data validation
│     ├── 29: Multi-module layered architecture
│     └── 31, 32, 34, 35: Invariants handled properly (Banking guard, State transitions, Atomic transactions)
│
└── ❌ ~23–25 Fail Intent (Legitimate Failures to Detect)
      ├── Schema & Constraints: Missing UNIQUE on ISBN/SKU/Email (11, 12, 13), missing CASCADE (37)
      ├── Unwired/Skipped Invariants: Overlap checks skipped (27), Audit unwired (33), Notifications unwired (40), RBAC unwired (39), Soft-delete done as hard delete (14)
      └── Incomplete Surfaces: Core CRUD write operations dropped in Service/CLI (15, 16, 20, 21, 22, 23, 24, 25)
```

---

## 3. Related Artifacts & Detailed Reports

All comprehensive breakdowns are saved in the project artifact directory:

1. [**Ground Truth Target Matrix**](file:///home/gstenger/.gemini/antigravity-cli/brain/31153097-4395-4f98-b0b9-92666b8e482f/ground_truth_target.md): Exact prompt-by-prompt expected behavioral verdicts for debugging the test oracle.
2. [**Agent Architectural Analysis**](file:///home/gstenger/.gemini/antigravity-cli/brain/31153097-4395-4f98-b0b9-92666b8e482f/agent_architectural_analysis.md): Detailed subsystem-by-subsystem breakdown of `agentlib` bottlenecks.
3. [**Oracle Test Bloat Analysis**](file:///home/gstenger/.gemini/antigravity-cli/brain/31153097-4395-4f98-b0b9-92666b8e482f/oracle_test_bloat_analysis.md): Investigation into why the behavioral test generator creates redundant/misfired tests (e.g. inventory prompt).
4. [**Code vs. Spec Conformity Report**](file:///home/gstenger/.gemini/antigravity-cli/brain/31153097-4395-4f98-b0b9-92666b8e482f/code_spec_analysis.md): Initial 40-prompt code review summary.
