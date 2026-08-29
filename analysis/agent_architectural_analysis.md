# Architectural Analysis: The Neurosymbolic Coding Agent (`agentlib`)

## Executive Summary

The agent uses a **manifest-first neurosymbolic architecture**:
1. An LLM emits schema-constrained JSON declarations (Manifest, Models, Repositories, Services, CLI).
2. Deterministic generators synthesize boilerplate files (`models.py`, `database.py`, standard CRUD repository methods, CLI wiring).
3. The LLM is only invoked to "fill" custom method bodies inside locked skeletons.
4. AST and structural checks run repair loops.

While this architecture guarantees **zero syntax errors and perfect import resolution**, it is the direct cause of why **only ~15–17 out of 40 prompts satisfy their behavioral intent**.

---

## The 5 Root-Cause Bottlenecks in the Agent

### 1. Invariant Blindness in the Service Generator (`_service_method_body`)
* **What happens:** In `agentlib/generation/service_render.py`, service methods follow a fixed dispatch waterfall:
  1. `dispatch_impl_body` (only handles 7 hardcoded recipe kinds like `export_csv` or `sum_by_group`).
  2. Single-shape repository delegation.
  3. `_generic_service_delegation` (generic `repo.create(inst)` or `repo.list()`).
  4. Locked stub for LLM fill (`raise NotImplementedError`).
* **The Failure:** If a prompt requires a business rule (e.g. Prompt 09: *validate email & age 18–70*, Prompt 27: *reject overlapping reservations*, Prompt 33: *write audit log*, Prompt 39: *check user role*), the generator matches the method name to generic CRUD (`add_<entity>` / `create_<entity>`) and automatically outputs a **direct repository pass-through**:
  ```python
  def create_employee(self, name: str, email: str, age: int, salary: float) -> bool:
      employee = Employee(name=name, email=email, age=age, salary=salary)
      return self.employee_repo.create(employee)  # ZERO validation logic!
  ```
  Because the generator considered this a "known generic CRUD method", it **never asked the LLM to write the validation or invariant check**.

---

### 2. The Fixed "Recipe Kernel" Causes Repository Over-Engineering
* **What happens:** The agent has a fixed set of kernel recipes (`_IMPL_KINDS` in `agentlib/design.py`):
  * `total_in_period`, `total_filtered`, `export_csv`, `duplicate_groups`, `sum_by_group`, `below_foreign_threshold`.
* **The Failure:** During the LLM design phase (`_design_module`), the schema guides the LLM to design extra analytical methods matching these kernel recipes (e.g., `export_contacts_to_csv`, `get_contacts_with_no_phone`, `get_average_salary`). The agent injects 5–10 of these into **every** repository, regardless of whether the prompt was a simple 1-line CRUD task.

---

### 3. DDL Generator Ignores Relational Cascades and Modifiers
* **What happens:** `_generate_ddl_from_models()` in `agentlib/naming.py` builds SQLite `CREATE TABLE` statements by inspecting dataclass field annotations extracted from the AST.
* **The Failure:** 
  * Foreign keys are inferred solely by regex: `if field_name.endswith("_id")`.
  * Generated SQL: `FOREIGN KEY (project_id) REFERENCES projects (id)`.
  * It **never emits `ON DELETE CASCADE`**. Therefore, prompts requiring cascade deletes (Prompt 37: *deleting a project removes its tasks*) will always leave orphaned records in SQLite unless manual multi-table delete code is written.

---

### 4. Structural Validator (`_check_structural`) Only Checks "Presence", Not "Wiring"
* **What happens:** In `agentlib/checks/ast_utils.py`, `_check_structural()` verifies that:
  1. Exception classes exist in code (`"class %s" % exc in all_code`).
  2. Model classes & fields exist in `models.py`.
  3. Service methods exist in `service.py`.
* **The Failure:** It performs **zero behavioral/data-flow checks**:
  * In Prompt 33 (Audit logging), `AuditService` exists and `CustomerService` exists, so `_check_structural` returns `0 errors`. It never checks whether `CustomerService.create_customer` actually calls `AuditService`.
  * In Prompt 40 (Notifications), `NotificationService` exists and `confirm_order` exists, so it passes, even though `confirm_order` never calls `NotificationService`.

---

### 5. Architectural Canonicalization Collapses Custom Multi-Class Patterns
* **What happens:** In `agentlib/pipeline/manifest.py`, the agent forces all files into a rigid 1-entity-to-1-repo/service naming scheme:
  * `<entity>_repository.py`, `<entity>_service.py`.
* **The Failure:** When a prompt specifies an explicit software design pattern:
  * **Prompt 30:** Requires an abstract repository interface (`ABC`/`Protocol`) and a separate SQLite implementation. The agent's canonicalizer strips the interface and only outputs a single concrete `TaskRepository`.
  * **Prompt 38 & 39:** When multiple services share domain access (e.g. `AuthService` + `DocumentService`), the agent either overwrites one with the other or duplicates class definitions across files.

---

## Summary Matrix: Why Prompts Failed

| Failure Category | Affected Prompts | Responsible Agent Subsystem |
|---|---|---|
| **Silent CRUD Passthrough (Skipped Invariants)** | 09, 27, 28, 31, 32 | `agentlib/generation/service_render.py` (`_generic_service_delegation`) |
| **Unwired Cross-Cutting Concerns** | 33, 38, 39, 40 | `agentlib/checks/ast_utils.py` (AST check only verifies definition, not calls) |
| **Missing DDL Options (`ON DELETE CASCADE`)** | 37 | `agentlib/naming.py` (`_generate_ddl_from_models`) |
| **Rigid Pattern Flattening (Dropped Interfaces)** | 30 | `agentlib/pipeline/manifest.py` (file canonicalization) |
| **CLI / Service Surface Mismatch** | 15, 16, 20, 21, 23, 24, 25 | `agentlib/pipeline/cli_propagate.py` & `service_render.py` |
