# Code vs Spec Conformity Analysis — Prompts 01–40

## Summary Statistics

| Verdict | Count | Prompts |
|---|---|---|
| ✅ **full** | 4 | 01, 02, 03, 04 |
| 🔵 **over-engineered** | 9 | 05, 06, 07, 08, 10, 29, 32, 34, 35 |
| 🟠 **mixed** | 20 | 09, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 27, 28, 30 |
| 🔴 **partial** | 7 | 26, 31, 33, 36, 37, 38, 39, 40 |

> [!IMPORTANT]
> Only the **4 simplest prompts** (Hello World, calculator, basic todo) achieve full conformity. **All multi-entity or behaviorally complex prompts** suffer from either missing features, invented extras, or both.

---

## Global Patterns

### Pattern 1 — Systematic over-engineering in the repository layer
Almost every prompt (05–40) triggers generation of 5–15 extra methods per repository that the spec never requests: `export_*_to_csv`, `search_*`, `get_*_by_*_range`, `get_*_count`, `find_duplicate_*`, `get_total_*`. These are present even when the spec is a 1-line CRUD requirement.

### Pattern 2 — CLI/Service layer incompleteness for multi-entity prompts
Once a prompt introduces ≥2 entities or ≥1 business rule, the CLI and service layer systematically drop operations. The repositories are built (with extras), but the service/CLI only exposes a subset — often only the read/list path.

### Pattern 3 — Business logic silently skipped
Critical behavioral requirements are the most commonly missed:
- Unique constraints (prompts 11, 12, 13) declared in the spec are absent from the DB schema and service layer
- Soft-delete (14) implemented as hard delete
- Overlapping reservation rejection (27) not implemented
- Atomic cascade delete (37) not implemented
- Role-based access control (39) defined but never called
- Notification-on-confirm (40) disconnected

### Pattern 4 — Structural hallucinations in complex prompts
Several prompts (31, 33, 36, 38) produce duplicate class definitions across files (e.g., `CustomerService` defined in both `customer_service.py` and `audit_service.py`), creating silent conflicts.

---

## Per-Prompt Detail

### 01 ✅ full
**Spec:** Print "Hello, World!" as a small package with entry point.  
**Extra ops:** Click CLI setup (minor).  
**Notes:** Acceptable — click is a reasonable over-spec for a "package" framing.

---

### 02 ✅ full
**Spec:** CLI calculator with add/sub/mul/div and division-by-zero handling.  
**Notes:** `sqlite3` imported but unused (dead import).

---

### 03 ✅ full
**Spec:** CLI todo with in-memory storage — add, list, complete, delete.  
**Notes:** `sqlite3` imported but unused.

---

### 04 ✅ full
**Spec:** CLI todo with SQLite storage — add, list, complete, delete.  
**Notes:** Minimal extra (`init_db` helper, necessary).

---

### 05 🔵 over-engineered
**Spec:** Contact app with CRUD + SQLite.  
**Extra ops:** `search_contacts`, `get_contact_by_email`, `get_contact_by_phone`, `get_contacts_with_email_domain`, `get_contacts_by_name_prefix`, `get_contact_with_most_phones`, `get_contacts_with_no_email`, `get_contacts_with_no_phone` — 9 unrequested methods.

---

### 06 🔵 over-engineered
**Spec:** Product CRUD + SQLite.  
**Extra ops:** `get_by_name`, `get_count`, `get_highest_price`, `get_lowest_price`, `get_by_category`, `get_by_price_range`, `get_low_stock`, `get_total_value`, `search` — 9 unrequested methods.

---

### 07 🔵 over-engineered
**Spec:** Book CRUD + search by title + SQLite.  
**Extra ops:** `get_books_by_genre`, `get_books_by_author`, `get_books_by_publication_year_range`, `generate_genre_distribution_report`, `get_most_popular_author` — extensive unrequested reporting.

---

### 08 🔵 over-engineered
**Spec:** Product inventory with CRUD, filter by category, list low-stock.  
**Extra ops:** `get_product_count_by_category`, `get_products_with_price_range`.  
**Notes:** Core spec is met; modest bloat.

---

### 09 🟠 mixed
**Spec:** Employee CRUD + validation (email format, age 18–70, positive salary).  
**Missing:** All three validation rules are absent from the service.  
**Extra ops:** `export_employees_to_csv`, `get_average_salary`, `get_employees_with_higher_salary_than_average`, etc. (10 unrequested).

---

### 10 🔵 over-engineered
**Spec:** Notes CLI with CRUD in separate modules (model, persistence, logic, CLI).  
**Extra ops:** `search_notes`, `get_notes_by_month`.  
**Notes:** Structure is correct; modest extra features.

---

### 11 🟠 mixed
**Spec:** Library management — Book CRUD, unique ISBN, SQLite.  
**Missing:** CLI entirely absent; unique ISBN not enforced in DB schema.  
**Extra ops:** `get_books_by_author`, `get_books_by_publication_year_range`, `get_books_with_most_popular_authors`.

---

### 12 🟠 mixed
**Spec:** Customer CRUD, search by name, filter by email domain, unique email.  
**Missing:** Unique email constraint (DB + service); CLI missing update and delete.  
**Extra ops:** `get_customers_with_phone_prefix`, `get_customer_count_by_domain`.

---

### 13 🟠 mixed
**Spec:** Inventory — Product CRUD, search, category filter, low-stock report, unique SKU.  
**Missing:** Unique SKU constraint in DB; CLI only updates stock qty (not general update).  
**Extra ops:** `export_products_to_csv`, `get_total_stock_value`, `get_products_with_price_range`.

---

### 14 🟠 mixed
**Spec:** Project CRUD with soft delete (hide deleted from listings).  
**Missing:** Soft delete uses `DELETE FROM` (hard delete); listings don't filter soft-deleted.  
**Extra ops:** `list_projects_with_pagination`, `get_project_stats`, `export_projects_to_csv`.

---

### 15 🟠 mixed
**Spec:** Product management with CRUD and sorted listings (name/price/qty, ASC/DESC).  
**Missing:** Create, Update, Delete are entirely absent from Service and CLI.  
**Extra ops:** `get_product_count`, `get_product_report_by_category`, `list_products_with_pagination`.

---

### 16 🟠 mixed
**Spec:** Customer CRUD with paginated listing returning total item count.  
**Missing:** Create, Update, Delete missing from Service/CLI; pagination returns no total count.  
**Extra ops:** `get_customers_by_last_name_prefix`, `get_customers_with_recent_activity`, etc.

---

### 17 🟠 mixed
**Spec:** Product search with combinable filters (name, category, max price, min qty).  
**Missing:** Filter combination is hardcoded for pairs — can't combine 3+ filters.  
**Extra ops:** `get_product_count`, `export_products_to_csv`, `find_duplicate_products`.

---

### 18 🟠 mixed
**Spec:** Contact CRUD, CSV export, CSV import with row validation (no corruption).  
**Missing:** Update, Delete, List missing from CLI.  
**Extra ops:** `get_contact_count_by_last_name`, `get_contacts_with_invalid_email_format`.

---

### 19 🟠 mixed
**Spec:** Task CRUD, JSON export, JSON import with validation.  
**Missing:** Read/List operation missing from CLI.  
**Extra ops:** `get_task_count_by_status`, `get_overdue_tasks`, `get_tasks_with_pagination`.

---

### 20 🟠 mixed
**Spec:** Sales app — Product and Sale CRUD, report total sales and per-product sales.  
**Missing:** Update/Delete for Product and Sale absent; CLI commands map to wrong methods.  
**Extra ops:** `get_sales_with_low_quantity_threshold`, `export_sales_report_to_csv`.

---

### 21 🟠 mixed
**Spec:** Order management — Customer and Order CRUD + list orders by customer.  
**Missing:** Full CRUD not exposed through Service/CLI.  
**Extra ops:** `export_orders_to_csv`, `get_customer_total_orders_and_revenue`.

---

### 22 🟠 mixed
**Spec:** Order/Product/OrderItem with CRUD and calculated order total.  
**Missing:** CLI entirely absent; many service methods are stubs.  
**Extra ops:** `get_product_usage_count`, `export_order_items_to_csv`.

---

### 23 🟠 mixed
**Spec:** Blog — Author, Post, Tag CRUD + search posts by tag.  
**Missing:** Author CRUD and Tag CRUD absent from Service/CLI.  
**Extra entities:** `PostTag` (junction — reasonable but not named in spec).  
**Extra ops:** `get_tag_usage_stats`, `get_posts_with_author_and_tag_info`.

---

### 24 🟠 mixed
**Spec:** Project management — Project + Task CRUD.  
**Missing:** Task create/update/delete absent from CLI.  
**Extra ops:** `project_completion_rate`, `project_task_distribution`, `get_task_stats_by_project`.

---

### 25 🟠 mixed
**Spec:** Employee + Department CRUD + list employees by department.  
**Missing:** Department CRUD and Employee update/delete absent from CLI.  
**Extra ops:** `find_duplicate_employees_by_department`, `export_employees_to_csv`.

---

### 26 🔴 partial
**Spec:** Library — Book, Member, Loan: create loan, close loan, check book availability.  
**Missing:** CLI entirely absent.  
**Extra ops:** `get_overdue_loans_summary`, `export_loans_to_csv`, `get_members_with_most_loans`.

---

### 27 🟠 mixed
**Spec:** Reservation — Customer, Room, Reservation CRUD + reject overlapping reservations.  
**Missing:** Overlap-conflict validation not implemented; CLI absent.  
**Extra ops:** `get_reservation_count_by_room`, `get_overlapping_reservations_report`.

---

### 28 🟠 mixed
**Spec:** Invoice — Invoice belongs to customer, has InvoiceLines; total computed from lines.  
**Missing:** Invoice total calculation on creation/update; CLI absent.  
**Extra ops:** `export_invoice_lines_to_csv`, `find_invoices_with_low_total_vs_product_price`.

---

### 29 🔵 over-engineered
**Spec:** Customer/Order with layered architecture (models, repos, services, CLI).  
**Notes:** Structure is correct; all required layers present.  
**Extra ops:** `get_customer_total_spent`, `get_orders_in_month`, `get_orders_below_customer_threshold`.

---

### 30 🟠 mixed
**Spec:** Task app using a repository interface, SQLite impl, service, CLI.  
**Missing:** No abstract repository interface (ABC/Protocol) — only concrete SQLite class.  
**Extra ops:** `find_duplicate_tasks_by_title`, `sum_task_priority_by_status`, `export_tasks_to_csv`.

---

### 31 🔴 partial
**Spec:** Banking — Customer + Account, deposit/withdraw, reject negative balance.  
**Missing:** `create_customer` and `create_account` absent from service layer.  
**Structural:** `AccountService` defined twice across files.  
**Extra ops:** `get_total_balance_by_customer`, `export_account_transactions_to_csv`.

---

### 32 🔵 over-engineered
**Spec:** Order with explicit state transitions (pending→confirmed/cancelled, confirmed→shipped/cancelled, shipped→cannot cancel).  
**Notes:** State machine correctly implemented.  
**Extra ops:** `get_orders_with_customer_count`, `get_orders_by_status_and_date_range`.

---

### 33 🔴 partial
**Spec:** Customer CRUD with automatic audit record on every create/update/delete.  
**Missing:** Audit logging not called from CRUD operations.  
**Structural:** `CustomerService` defined in both `audit_service.py` and `customer_service.py` — conflict.

---

### 34 🔵 over-engineered
**Spec:** Order with lines created atomically; rollback if any line invalid.  
**Notes:** Manual rollback via delete rather than proper DB transaction, but a separate atomic repo method also exists.  
**Extra ops:** `generate_order_report_by_product`, `get_order_line_total_by_product`.

---

### 35 🔵 over-engineered
**Spec:** Inventory CRUD + atomic bulk stock update.  
**Notes:** Bulk update correctly executed as single query.  
**Extra ops:** `get_product_sales_trend`, `get_products_with_low_stock_alert`, `get_total_stock_by_category`.

---

### 36 🔴 partial
**Spec:** Product + Category; products belong to categories; prevent category deletion if products exist.  
**Missing:** Category delete operation missing from service (only a validation method exists); `create_product` and `create_category` absent from CLI.  
**Structural:** `ProductService` redefined in `category_service.py`.

---

### 37 🔴 partial
**Spec:** Project + Task; deleting a project atomically removes its tasks.  
**Missing:** No cascade delete logic — project repo delete doesn't remove tasks, no DB CASCADE.  
**Extra ops:** `get_project_completion_rate`, `search_tasks_by_title`.

---

### 38 🔴 partial
**Spec:** User + Document; authenticated users can only read/modify/delete their own documents.  
**Missing:** `create_document`, `modify_document`, `delete_document`, ownership enforcement.  
**Structural:** `AuthService` redefined in `document_operations_service.py`.

---

### 39 🔴 partial
**Spec:** User/Product/Order with role-based access (admins manage products/users; users manage own orders).  
**Missing:** Permission enforcement never called inside CRUD operations; admin product management absent.  
**Structural:** `UserService` used inconsistently across files.

---

### 40 🔴 partial
**Spec:** Order confirmation triggers notification via notification service (logs).  
**Missing:** `confirm_order` does not call `NotificationService`.  
**Structural:** Notification logic split disconnectedly across `order_service.py` and `notification_service.py`.

---

## Comparison with Behavioral Tester

| Dimension | Manual Code Review (this report) | Behavioral Tester (oracle) |
|---|---|---|
| **Scope** | Structural & semantic gap analysis | Runtime execution tests |
| **Coverage** | All 40 prompts | Only prompts with `test_spec.json` |
| **Detects missing business logic** | ✅ Yes (static read) | ✅ Yes (runtime assertion) |
| **Detects extra/invented code** | ✅ Yes | ❌ No (doesn't penalize extra) |
| **Detects structural hallucinations** | ✅ Yes (duplicate class defs) | ❌ No |
| **Detects missing CLI ops** | ✅ Yes | ⚠️ Partially (if tested via service) |
| **Detects DB schema issues** | ✅ Yes (missing UNIQUE, CASCADE) | ✅ Yes (runtime integrity check) |
| **False positives** | Low (human-level read) | Medium (oracle over-generates tests) |
| **Reproducible** | ❌ Manual | ✅ Deterministic |
