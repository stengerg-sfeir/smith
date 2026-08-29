# Ground Truth Target: Code Intent Conformance (Prompts 01–40)

This reference document defines the **ground truth verdict** on whether the generated code matches the prompt intent for Prompts 01 to 40. 

Use this target to verify whether your behavioral test oracle generates tests that detect these exact behaviors and failures.

---

## 1. Quick Reference: Target Verdicts Matrix

| Prompt | Domain | Core Invariant / Intent | Does Code Satisfy Intent? | What Tester Should Report |
|---|---|---|---|---|
| **01** | Hello World | Print "Hello, World!" as package entry point | **YES** | PASS |
| **02** | CLI Calculator | Add, sub, mul, div; handle div-by-zero | **YES** | PASS |
| **03** | Todo (Memory) | CRUD tasks in memory | **YES** | PASS |
| **04** | Todo (SQLite) | CRUD tasks with SQLite persistence | **YES** | PASS |
| **05** | Contacts | CRUD contacts (name, email, phone) | **YES** (over-engineered) | PASS |
| **06** | Products | CRUD products in SQLite | **YES** (over-engineered) | PASS |
| **07** | Books | CRUD books + search by title | **YES** (over-engineered) | PASS |
| **08** | Inventory | CRUD products + filter category & low stock | **YES** (over-engineered) | PASS |
| **09** | Employees | Validate email format, age 18-70, salary > 0 | **NO** (validations omitted) | **FAIL** (missing validation) |
| **10** | Notes | Multi-module architecture (model/repo/service/cli) | **YES** | PASS |
| **11** | Library | Book CRUD + unique ISBN in SQLite | **NO** (unique constraint missing) | **FAIL** (missing unique constraint) |
| **12** | Customers | Customer CRUD + unique email + domain filter | **NO** (unique email missing) | **FAIL** (missing unique constraint) |
| **13** | Inventory | Unique SKU + low stock report + search/filter | **NO** (unique SKU missing from DB) | **FAIL** (missing unique constraint) |
| **14** | Projects | Soft-delete: project remains in DB but hidden from list | **NO** (hard DELETE FROM executed) | **FAIL** (soft delete violated) |
| **15** | Products | CRUD + sorting by name, price, qty (asc/desc) | **NO** (service/CLI missing CRUD) | **FAIL** (missing core CRUD) |
| **16** | Customers | Paginated list returning page data & total pages | **NO** (total count missing in pagination) | **FAIL** (pagination incomplete) |
| **17** | Inventory | Combinable multi-filters (name, category, price, qty) | **NO** (cannot combine >2 filters) | **FAIL** (combinable filter bug) |
| **18** | Contacts | CSV Import rejecting invalid rows without corruption | **YES** (importer validates/skips bad rows) | PASS |
| **19** | Tasks | JSON Import with input validation | **YES** | PASS |
| **20** | Sales | Sales report (total amount & count per product) | **NO** (Product/Sale write CRUD missing) | **FAIL** (missing CRUD) |
| **21** | Orders | Customer & Order CRUD + list orders by customer | **NO** (service/CLI drops CRUD) | **FAIL** (missing CRUD in service) |
| **22** | Order Items | Calculate total order amount from order items | **NO** (unimplemented stubs in service) | **FAIL** (stub methods) |
| **23** | Blog | Author, Post, Tag CRUD + search post by tag | **NO** (author/tag CRUD missing in service) | **FAIL** (missing author/tag CRUD) |
| **24** | Projects | Project & Task CRUD | **NO** (task CRUD missing in CLI) | **FAIL** (missing CLI task ops) |
| **25** | Employees | Employee & Department CRUD + list by dept | **NO** (dept CRUD & emp update/del missing) | **FAIL** (incomplete CRUD) |
| **26** | Library | Create/close loans + check book availability | **YES** (logic in service; CLI absent) | PASS (or FAIL if CLI required) |
| **27** | Reservations | Reject overlapping reservations for same room | **NO** (overlap guard never checked) | **FAIL** (overlap allowed) |
| **28** | Invoicing | Invoice total calculated from its invoice lines | **NO** (total not calculated on save) | **FAIL** (sum invariant violated) |
| **29** | Architecture | Explicit layering: models, repo, service, CLI | **YES** (clean layered design) | PASS |
| **30** | Repo Pattern | Abstract Repo Interface (ABC/Protocol) + SQLite impl | **NO** (no abstract interface/ABC created) | **FAIL** (pattern requirement ignored) |
| **31** | Banking | Reject withdrawal if balance becomes negative | **YES** (guard exists; create methods dropped) | PASS (or partial) |
| **32** | State Machine | Allowed state transitions enforced explicitly | **YES** (state machine strict & correct) | PASS |
| **33** | Audit Log | Every create/update/delete writes an audit record | **NO** (audit service unwired in CRUD) | **FAIL** (audit records not written) |
| **34** | Transactions | Atomic order + lines creation (rollback on failure) | **YES** (atomic insert implemented in repo) | PASS |
| **35** | Bulk Update | Atomic bulk stock update in single transaction | **YES** (executed as single atomic SQL query) | PASS |
| **36** | Foreign Keys | Prevent deleting category if products belong to it | **NO** (delete category method absent from service) | **FAIL** (missing delete logic) |
| **37** | Cascades | Deleting project atomically removes associated tasks | **NO** (cascade delete omitted; orphaned tasks) | **FAIL** (orphaned tasks on delete) |
| **38** | Auth/Ownership | Users only read/modify/delete own documents | **NO** (service missing write ops & ownership logic) | **FAIL** (ownership check missing) |
| **39** | RBAC | Admin vs user permissions (user views own orders only) | **NO** (permission helper defined but never called) | **FAIL** (unwired RBAC) |
| **40** | Notification | Send notification when order is confirmed | **NO** (notification service not invoked on confirm) | **FAIL** (unwired notification) |

---

## 2. Detailed Per-Prompt Evaluation

### Prompts 01–10: Single-Entity / Core Basics
* **Prompt 01 (Hello World):** Satisfies prompt. Entry point in `hello/cli.py` works.
* **Prompt 02 (Calculator):** Satisfies prompt. CLI supports 4 operations; division by zero produces clear error message.
* **Prompt 03 (Todo in Memory):** Satisfies prompt. In-memory dict storage with add/list/complete/delete.
* **Prompt 04 (Todo SQLite):** Satisfies prompt. SQLite table created and CRUD operations persist.
* **Prompt 05 (Contacts):** Satisfies prompt. Contacts CRUD in SQLite present. (Contains 8 extra unrequested search methods).
* **Prompt 06 (Products):** Satisfies prompt. Product CRUD in SQLite present. (Contains extra analytical queries).
* **Prompt 07 (Books):** Satisfies prompt. Book CRUD + title search present. (Contains extra genre/author analytics).
* **Prompt 08 (Inventory):** Satisfies prompt. CRUD + category filter + low stock check present.
* **Prompt 09 (Employees with Validations):** **FAILS INTENT.**
  * *Prompt requires:* Email validation, age between 18 and 70, salary > 0.
  * *Code reality:* `EmployeeService.create_employee` passes raw values directly to the repository with zero validation checks.
* **Prompt 10 (Notes Architecture):** Satisfies prompt. Code cleanly separated into models, repository, service, and CLI modules.

---

### Prompts 11–20: Constraints, Filters, and Serialization
* **Prompt 11 (Library ISBN Unique):** **FAILS INTENT.**
  * *Prompt requires:* ISBN must be unique.
  * *Code reality:* SQLite table has `isbn TEXT NOT NULL` without `UNIQUE` constraint; no check before insert in service.
* **Prompt 12 (Customer Email Unique):** **FAILS INTENT.**
  * *Prompt requires:* Email must be unique.
  * *Code reality:* SQLite schema and service lack unique enforcement.
* **Prompt 13 (Product SKU Unique):** **FAILS INTENT.**
  * *Prompt requires:* SKU must be unique.
  * *Code reality:* SQLite schema lacks unique constraint on `sku`.
* **Prompt 14 (Soft Delete):** **FAILS INTENT.**
  * *Prompt requires:* Deleting a project must be a soft delete (remain in DB, hidden from normal listing).
  * *Code reality:* `ProjectRepository.delete` runs `DELETE FROM projects WHERE id = ?` (hard delete). Normal `list()` runs `SELECT * FROM projects` without filtering deleted items.
* **Prompt 15 (Sorted Listings):** **FAILS INTENT.**
  * *Prompt requires:* CRUD operations + sorted listing by name/price/qty.
  * *Code reality:* `ProductService` only implements query/sort methods; create/update/delete are absent.
* **Prompt 16 (Pagination):** **FAILS INTENT.**
  * *Prompt requires:* Return requested page items + information to determine total pages.
  * *Code reality:* Repo slices with `LIMIT/OFFSET` but does not return total count or total pages. Service lacks create/update/delete.
* **Prompt 17 (Combinable Filters):** **FAILS INTENT.**
  * *Prompt requires:* All 4 filters (name, category, max price, min qty) must be combinable.
  * *Code reality:* Code hardcodes individual pairwise `if/elif` branches rather than building dynamic SQL predicates; cannot combine 3 or 4 filters simultaneously.
* **Prompt 18 (CSV Import/Export):** Satisfies prompt. Export creates CSV; Import validates headers & rows, skipping malformed rows without crashing.
* **Prompt 19 (JSON Import/Export):** Satisfies prompt. JSON import validates schema before persistence.
* **Prompt 20 (Sales Reporting):** **FAILS INTENT.**
  * *Prompt requires:* CRUD for products and sales + sales report.
  * *Code reality:* Product and Sale update/delete operations are missing; CLI routes incorrectly.

---

### Prompts 21–30: Relational Domains & Business Rules
* **Prompt 21 (Customer / Orders):** **FAILS INTENT.**
  * *Prompt requires:* CRUD for customers and orders + list orders by customer.
  * *Code reality:* Service and CLI layers drop write operations for customers and orders.
* **Prompt 22 (Order Items Total):** **FAILS INTENT.**
  * *Prompt requires:* Calculate total order amount from order items.
  * *Code reality:* Multiple service methods are empty stubs (`pass`); no CLI provided.
* **Prompt 23 (Blog / Tags):** **FAILS INTENT.**
  * *Prompt requires:* CRUD for authors, posts, tags + search by tag.
  * *Code reality:* Author CRUD and Tag CRUD are completely omitted from the Service layer.
* **Prompt 24 (Project / Tasks):** **FAILS INTENT.**
  * *Prompt requires:* CRUD for projects and tasks.
  * *Code reality:* CLI only exposes project operations; task create/update/delete are absent from CLI.
* **Prompt 25 (Employee / Department):** **FAILS INTENT.**
  * *Prompt requires:* CRUD for employees and departments.
  * *Code reality:* Department CRUD and Employee update/delete are missing in the CLI.
* **Prompt 26 (Library Loans):** Satisfies prompt at the service layer.
  * *Code reality:* Loan creation verifies book availability; closing loan marks it available. CLI is absent, but domain intent is implemented.
* **Prompt 27 (Reservations Overlap):** **FAILS INTENT.**
  * *Prompt requires:* A room cannot have two overlapping reservations. Reject reservations that overlap.
  * *Code reality:* `ReservationService.create_reservation` inserts directly into repository without checking date overlap.
* **Prompt 28 (Invoice Line Total):** **FAILS INTENT.**
  * *Prompt requires:* Invoice total must be calculated from its lines.
  * *Code reality:* `InvoiceRepository.create` accepts a raw `total_amount` float without computing `quantity * unit_price` across lines.
* **Prompt 29 (Layered Architecture):** Satisfies prompt. Clean physical separation of models, repository, service, and CLI.
* **Prompt 30 (Repository Interface):** **FAILS INTENT.**
  * *Prompt requires:* Explicit repository interface (ABC/Protocol) separate from SQLite implementation.
  * *Code reality:* Only concrete `TaskRepository` class created; no `AbstractRepository` or `Protocol` exists.

---

### Prompts 31–40: Advanced Invariants & Cross-Cutting Logic
* **Prompt 31 (Bank Withdrawal Guard):** Satisfies core invariant.
  * *Code reality:* `AccountService.withdraw` checks `account.balance - amount < 0` and raises `InsufficientFundsError`.
* **Prompt 32 (State Machine Transitions):** Satisfies prompt.
  * *Code reality:* `OrderService.update_order_status` explicitly checks dictionary of valid transitions; raises `OrderAlreadyShippedError` / `OrderAlreadyCancelledError`.
* **Prompt 33 (Audit Logging):** **FAILS INTENT.**
  * *Prompt requires:* Every creation, update, and deletion must produce an audit record.
  * *Code reality:* `CustomerService.create_customer`, `update_customer`, and `delete_customer` never invoke `AuditService` or insert into `audit_records`.
* **Prompt 34 (Atomic Order Lines):** Satisfies prompt.
  * *Code reality:* Repository creates order and lines within a single connection transaction, rolling back if any line insert fails.
* **Prompt 35 (Bulk Stock Update):** Satisfies prompt.
  * *Code reality:* Executes batch update within a single SQLite transaction block.
* **Prompt 36 (Foreign Key Cascade Guard):** **FAILS INTENT.**
  * *Prompt requires:* A category cannot be deleted while products still belong to it.
  * *Code reality:* `CategoryService` lacks a `delete_category` method entirely.
* **Prompt 37 (Cascade Delete on Project):** **FAILS INTENT.**
  * *Prompt requires:* Deleting a project must atomically remove its tasks.
  * *Code reality:* `ProjectRepository.delete` only runs `DELETE FROM projects WHERE id = ?`. Foreign keys are not configured with `ON DELETE CASCADE`, leaving orphaned tasks.
* **Prompt 38 (Document Ownership):** **FAILS INTENT.**
  * *Prompt requires:* Authenticated users can only read, modify, or delete their own documents.
  * *Code reality:* `DocumentOperationsService` only provides search/query helpers; document modification/deletion operations and ownership assertions are missing.
* **Prompt 39 (Role-Based Access):** **FAILS INTENT.**
  * *Prompt requires:* Admin vs normal user access rules (users only see own orders; admins manage products).
  * *Code reality:* Role checking functions exist as orphan helpers but are never called inside CRUD methods.
* **Prompt 40 (Notification on Confirm):** **FAILS INTENT.**
  * *Prompt requires:* Sending a notification when an order is confirmed.
  * *Code reality:* `OrderService.confirm_order` updates order status in DB but never calls `NotificationService.send_notification`.
