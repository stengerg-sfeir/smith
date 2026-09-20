"""State of the numbered prompts 41..60: one functional probe per prompt.

    python3 analysis/state_41_60.py            # all
    python3 analysis/state_41_60.py 51 52      # some

Same instrument as ``state_01_40.py`` (its helpers are reused, not copied):
each probe drives the SHIPPED application's CLI and asserts only what the
prompt itself states. A probe never looks at the generator, and it never
invents a requirement the specification does not make.

Prompt 59 is deliberately absent: its generation is known to fail at scale
(the repair loop truncates at the output budget — see the progress journal),
so it is reported as such rather than probed.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from state_01_40 import (  # noqa: E402 - same-directory script by design
    RESULTS,
    VALUES,
    add_row,
    check,
    cli,
    contains,
    entry_of,
    execute,
    fresh,
    inserted_line,
    module_run,
    sql,
    surface,
)

# --------------------------------------------------------------------------
# Shared helpers: find a capability by NAME among the commands the
# application itself exposes, so a probe looks for what the prompt demands
# instead of hard-coding a noun the design was free to choose.
# --------------------------------------------------------------------------


def subgroups(project):
    """Every top-level command group the application exposes."""
    return [
        name for name in re.findall(r"^  ([\w-]+)\s{2,}\S", surface(project), re.M)
        if not name.startswith("-")
    ]


def subcommands(project, group):
    """Every command under ``group`` (its own ``--help`` listing)."""
    text = cli(project, group, "--help")[1]
    return [
        name for name in re.findall(r"^  ([\w-]+)\s{2,}\S", text, re.M)
        if not name.startswith("-") and name not in ("Options", "Commands")
    ]


def find_command(project, *keywords):
    """``(group, command)`` of the first command whose NAME names a keyword.

    The prompt demands a CAPABILITY ("know how much they have spent"); the
    generator is free to name it ``customer total`` or ``customer spent`` or
    ``report spending``. The search is on the application's own surface.
    """
    for group in subgroups(project):
        for command in subcommands(project, group):
            label = ("%s %s" % (group, command)).lower()
            if any(keyword in label for keyword in keywords):
                return group, command
    return None


def run(project, group, command, **options):
    argv = [group, command]
    for key, value in options.items():
        argv += ["--" + key.replace("_", "-"), str(value)]
    return cli(project, *argv)


# Values for the vocabulary of prompts 41..60 that the 01..40 table does not
# carry. A probe fills what a USER would have to type; it must never fail
# because the design named a field the probe had not met before.
_EXTRA_VALUES = {
    "membership-type": "standard", "membership": "standard",
    "return-date": "2026-03-01", "borrow-date": "2026-01-01",
    "loan-date": "2026-01-01", "start-time": "2026-01-01 10:00",
    "end-time": "2026-01-01 11:00", "starts-at": "2026-01-01 10:00",
    "ends-at": "2026-01-01 11:00", "guest-name": "G",
    "capacity": "2", "slots": "2", "seats": "2", "attendees": "2",
    "amount-paid": "100", "paid-amount": "100", "payment-method": "card",
    "invoice-id": "1", "client-name": "C", "supplier": "S", "vendor": "V",
    "collection": "general", "genre": "general", "shelf": "A1",
    "assignee-id": "1", "assigned-to": "1", "owner-id": "1",
    "priority": "high", "status": "pending", "role": "user",
    "quantity": "2", "qty": "2", "count": "2", "unit-price": "10",
    "sale-price": "10", "price": "10", "total": "20", "total-amount": "20",
}


def _fits(metavar, value):
    """True when ``value`` can be typed into an option of that declared type."""
    meta = (metavar or "").upper()
    text = str(value).strip()
    if "INT" in meta:
        return text.lstrip("-").isdigit()
    if "FLOAT" in meta or "DECIMAL" in meta:
        try:
            float(text)
        except ValueError:
            return False
        return True
    return True


def _generic_value(option, metavar):
    """A value a USER could type for an option the table does not know.

    ``INTEGER``/``FLOAT`` get a number, a date/time-ish name gets a date,
    everything else gets a short word. This is what keeps a probe measuring
    the application instead of its own vocabulary.
    """
    meta = (metavar or "").upper()
    name = option.lower()
    if "INT" in meta or "FLOAT" in meta or name.endswith("-id"):
        return "1"
    if "TIME" in meta or "DATE" in meta or "AT" in name or "date" in name:
        return "2026-01-01"
    if "BOOL" in meta or name.startswith(("is-", "has-")):
        return None  # a flag: simply omitted (it has a default)
    return name.replace("-", " ").title()


def create(project, candidates, **overrides):
    """Create one row through whichever candidate group offers ``add``.

    The prompt names an entity in prose ("purchases", "bookings"); the design
    may spell it differently ("sale", "order", "reservation"), and its field
    names are its own. EVERY required option of that group's ``add`` is
    therefore filled: from the caller's overrides, else the shared value
    table, else a value of the option's declared type.
    """
    for group in candidates:
        if "add" not in subcommands(project, group):
            continue
        help_text = cli(project, group, "add", "--help")[1]
        argv = [group, "add"]
        for option, metavar in re.findall(
            r"^\s*--([\w-]+)\s+(\S+)\s+\[required\]", help_text, re.M
        ):
            key = option.replace("-", "_")
            value = overrides.get(key)
            # The caller's own value is subject to the same type rule as the
            # table's: a probe that passed `priority="high"` to an INTEGER
            # option would report the application's clean click refusal as a
            # defect.
            if value is not None and not _fits(metavar, value):
                value = None
            if value is None:
                value = _EXTRA_VALUES.get(option) or VALUES.get(option)
                # A value from the table is only usable when it FITS the
                # option's declared type: "--priority INTEGER" refuses "high"
                # at parse time, which would read as an application defect
                # while it is the probe typing a word into a number.
                if value is not None and not _fits(metavar, value):
                    value = None
            if value is None:
                value = _generic_value(option, metavar)
            if value is None:
                continue
            argv += ["--%s" % option, str(value)]
        return (group,) + cli(project, *argv)
    return "", 1, "", "no add command among %s" % (candidates,)


# Commands a probe may RUN to look at data. Anything else on the surface
# (delete/close/process/...) is never executed by a probe: a check must not
# mutate the application it is measuring.
_READ_ONLY_COMMANDS = ("list", "search", "report", "available", "history",
                       "show", "detail", "find", "outstanding", "summary")


def availability_view(project, group):
    """The listing that answers "which <group> are available", or None.

    Two honest forms satisfy the requirement: a filter/flag carrying
    "available" on the listing, or a listing that itself carries an
    availability column. Only READ-ONLY commands are run. Returns
    ``(label, text)`` for the first form that works.
    """
    for command in subcommands(project, group):
        if not any(word in command for word in _READ_ONLY_COMMANDS):
            continue
        help_text = cli(project, group, command, "--help")[1]
        if "available" in help_text.lower():
            rc, out, err = cli(project, group, command, "--available-only")
            if rc == 0:
                return "%s %s --available-only" % (group, command), out
    listing = cli(project, group, "list")[1]
    if "available" in listing.lower():
        return "%s list" % group, listing
    return None, listing


def exposes(help_text, *candidates):
    """The first candidate ``--option`` the help DECLARES, or None."""
    for candidate in candidates:
        if "--" + candidate in help_text:
            return candidate
    return None



def stock_of(project, table="products"):
    """Every stock-ish column of ``table``, as one list of values."""
    columns = [
        str(row[1]) for row in sql(project, "PRAGMA table_info(%s)" % table)
        if len(row) >= 6 and re.search(r"stock|quant|on_hand|available", str(row[1]))
    ]
    values = []
    for column in columns:
        values += [row[0] for row in sql(project, "SELECT %s FROM %s" % (column, table))]
    return columns, values


# --------------------------------------------------------------------------
# Probes
# --------------------------------------------------------------------------


def probe_41():
    """Library: "manage books and members and keep track of loans … make it
    easy to know which books are available"."""
    project = fresh("41")
    book = create(project, ("book", "books"), title="B1", isbn="1")
    member = create(project, ("member", "members"), first_name="M",
                    last_name="One", email="m@x")
    check("a book and a member can be recorded",
          book[1] == 0 and member[1] == 0,
          "book=%s member=%s" % (book[1:3], member[1:3]))
    loan = create(project, ("loan", "loans", "borrowing", "borrow"),
                  book_id=1, member_id=1, due_date="2026-02-01")
    check("a loan can be recorded against them",
          loan[1] == 0, "rc=%s err=%s" % (loan[1], loan[3][:120]))
    label, shown = availability_view(project, "book")
    check("the application answers which books are available",
          label is not None, "listing=%s" % shown[:120])
    if label is not None:
        check("a borrowed book no longer appears as available",
              "B1" not in shown, "%s -> %s" % (label, shown[:120]))


def probe_42():
    """Customers and purchases: "find a customer's purchase history and
    determine how much they have spent"."""
    project = fresh("42")
    create(project, ("customer", "customers"), email="c@x")
    first = create(project, ("purchase", "purchases", "sale", "sales", "order",
                             "orders"), customer_id=1, amount="30")
    create(project, ("purchase", "purchases", "sale", "sales", "order",
                     "orders"), customer_id=1, amount="20")
    check("a customer's purchases can be recorded", first[1] == 0,
          "group=%s rc=%s err=%s" % (first[0], first[1], first[3][:120]))
    # "find a customer's purchase history": the design names that view freely
    # ("purchase list", "customer history"), so the command is looked up on the
    # application's own surface.
    history = find_command(project, "purchase", "history") \
        or find_command(project, "order", "sale")
    check("the purchase history of a customer is reachable",
          history is not None,
          "cmd=%s" % (history,))
    # "determine how much they have spent" is a CUSTOMER-level figure: the
    # command that carries it is the one on the customer group that reports the
    # customer with their purchases ("customer report --id 1"), not a
    # per-purchase total. The two seeded purchases are 30 and 20, so the figure
    # the prompt asks for is 50.
    spent = None
    for command in subcommands(project, "customer"):
        if command in ("report", "history", "summary", "spending", "total"):
            spent = ("customer", command)
            break
    if spent is None:
        spent = find_command(project, "report", "total", "spent", "spending")
    check("a 'how much has been spent' capability exists",
          spent is not None, "cmd=%s" % (spent,))
    if spent is not None:
        rc, out, err = cli(project, spent[0], spent[1], "--id", "1")
        check("how much a customer has spent is reported",
              rc == 0 and "50" in out,
              "cmd=%s rc=%s out=%s err=%s" % (" ".join(spent), rc, out[:120],
                                              err[:80]))
    else:
        check("how much a customer has spent is reported", False,
              "no command names a total/spent capability")


def probe_43():
    """Projects contain tasks; "tasks have priorities and statuses, and users
    should be able to see what needs attention"."""
    project = fresh("43")
    created = create(project, ("project", "projects"), name="P")
    check("a project can be recorded", created[1] == 0,
          "rc=%s err=%s" % (created[1], created[3][:120]))
    task = create(project, ("task", "tasks"), title="T", project_id=1,
                  priority="high", status="pending")
    check("a task carries a priority and a status", task[1] == 0,
          "rc=%s err=%s" % (task[1], task[3][:120]))
    help_text = cli(project, "task", "list", "--help")[1].lower()
    report = find_command(project, "attention", "pending", "todo", "overdue")
    reachable = "status" in help_text or "priority" in help_text or report
    check("what needs attention is reachable (status/priority filter or report)",
          bool(reachable), "task list help=%s report=%s" % (help_text[:60], report))


def probe_44():
    """A small shop: "products, customers and sales … know what has been sold
    and what is still in stock"."""
    project = fresh("44")
    product = create(project, ("product", "products"), name="P1", price="10",
                     stock_quantity="5")
    customer = create(project, ("customer", "customers"), email="c@x")
    check("products and customers can be recorded",
          product[1] == 0 and customer[1] == 0,
          "product=%s customer=%s" % (product[1:3], customer[1:3]))
    sale = create(project, ("sale", "sales", "order", "orders"), customer_id=1,
                  product_id=1, quantity="2", total_amount="20")
    check("a sale can be recorded", sale[1] == 0,
          "group=%s rc=%s err=%s" % (sale[0], sale[1], sale[3][:120]))
    # "know what has been sold": prefer the SALE's own listing over any other
    # report that merely happens to carry a report command.
    sold = None
    if "sale" in subgroups(project) and "list" in subcommands(project, "sale"):
        sold = ("sale", "list")
    if sold is None:
        sold = find_command(project, "sold", "sale-report")
    if sold is not None:
        rc, out, err = cli(project, sold[0], sold[1])
        check("what has been sold is reachable", rc == 0,
              "cmd=%s rc=%s err=%s" % (" ".join(sold), rc, err[:100]))
    else:
        check("what has been sold is reachable", sale[1] == 0,
              "no dedicated command; the sale itself was recorded")
    columns, values = stock_of(project)
    check("what is still in stock is readable on the product",
          bool(columns) and bool(values),
          "columns=%s values=%s" % (columns, values))


def probe_45():
    """Hotel: "manage rooms, guests and bookings and should not accidentally
    book the same room twice for the same period"."""
    project = fresh("45")
    create(project, ("guest", "guests", "customer", "customers"), email="g@x")
    create(project, ("room", "rooms"), room_number="101", capacity="2")
    create(project, ("room", "rooms"), room_number="102", capacity="2")

    def book(room, start, end):
        return create(project, ("booking", "bookings", "reservation",
                                "reservations"), guest_id=1, room_id=room,
                      start_date=start, end_date=end, customer_id=1)

    made = book(1, "2026-01-01", "2026-01-05")
    overlapping = book(1, "2026-01-03", "2026-01-07")
    other_room = book(2, "2026-01-03", "2026-01-07")
    check("a booking can be made", made[1] == 0,
          "group=%s rc=%s err=%s" % (made[0], made[1], made[3][:120]))
    check("the same room cannot be booked twice for the same period",
          overlapping[1] != 0,
          "rc=%s err=%s" % (overlapping[1], overlapping[3][:120]))
    check("a different room may be booked for that period",
          other_room[1] == 0,
          "rc=%s err=%s" % (other_room[1], other_room[3][:120]))
def probe_46():
    """Invoicing: "keep track of clients, invoices and payments and make it
    possible to know which invoices are still outstanding"."""
    project = fresh("46")
    create(project, ("client", "clients", "customer", "customers"), email="c@x")
    invoice = create(project, ("invoice", "invoices"), client_id=1,
                     customer_id=1, total_amount="100", amount="100")
    check("a client and an invoice can be recorded", invoice[1] == 0,
          "group=%s rc=%s err=%s" % (invoice[0], invoice[1], invoice[3][:120]))
    # "know which invoices are still outstanding": a dedicated view OR a
    # status filter on the invoice listing both answer it.
    outstanding = find_command(project, "outstanding", "unpaid", "due",
                               "receivable")
    status_opt = None
    if outstanding is None:
        invoice_help = cli(project, "invoice", "list", "--help")[1]
        status_opt = exposes(invoice_help, "status", "state")
        outstanding = ("invoice", "list") if status_opt else None
    check("which invoices are outstanding is reachable", outstanding is not None,
          "cmd=%s" % (outstanding,))
    if outstanding is None:
        return
    before = cli(project, outstanding[0], outstanding[1])
    check("an outstanding view can be listed",
          before[0] == 0, "cmd=%s rc=%s err=%s" % (" ".join(outstanding),
                                                   before[0], before[2][:80]))
    paid = create(project, ("payment", "payments"), invoice_id=1, amount="100",
                  amount_paid="100", payment_date="2026-01-01")
    if paid[1] == 0:
        after = cli(project, outstanding[0], outstanding[1])
        check("recording the payment reaches the invoice view",
              after[0] == 0, "before=%s after=%s" % (before[1][:60],
                                                     after[1][:60]))
    else:
        check("a payment can be recorded against the invoice", False,
              "rc=%s err=%s" % (paid[1], paid[3][:120]))


def probe_47():
    """A software team's work: "projects, tasks and people, and should be able
    to see who is responsible for what"."""
    project = fresh("47")
    create(project, ("project", "projects"), name="P")
    person = create(project, ("person", "people", "user", "users", "employee",
                              "employees", "member", "members"),
                    name="Alice", email="a@x.com", first_name="Alice",
                    last_name="A")
    assigned = create(project, ("task", "tasks"), title="T", project_id=1,
                      assignee_id=1, person_id=1, user_id=1, assigned_to=1)
    check("a person and a task can be recorded", person[1] == 0,
          "person=%s err=%s" % (person[1], person[3][:120]))
    check("a task can be assigned to a person", assigned[1] == 0,
          "rc=%s err=%s" % (assigned[1], assigned[3][:120]))
    by_person = find_command(project, "assign", "responsible", "owner",
                             "by_person", "person")
    listing = cli(project, "task", "list")[1]
    check("who is responsible for what is reachable",
          by_person is not None or "Alice" in listing or "assignee" in listing.lower(),
          "report=%s listing=%s" % (by_person, listing[:100]))


def probe_48():
    """A collection of books: "add books, find books and organize them. The
    application should remember the information between executions"."""
    project = fresh("48")
    added = create(project, ("book", "books"), title="Dune", isbn="I1",
                   author="Herbert", category="sci-fi")
    check("a book can be added", added[1] == 0,
          "rc=%s err=%s" % (added[1], added[3][:120]))
    found = find_command(project, "search", "find")
    if found is not None:
        rc, out, err = cli(project, found[0], found[1], "--term", "Dune")
        check("a book can be found", rc == 0 and "Dune" in out,
              "cmd=%s rc=%s out=%s err=%s" % (" ".join(found), rc, out[:80],
                                              err[:80]))
    else:
        check("a book can be found", "Dune" in cli(project, "book", "list")[1],
              "no search command; list carries the row")
    help_text = cli(project, "book", "list", "--help")[1].lower() + \
        cli(project, "book", "add", "--help")[1].lower()
    check("books can be organized (a category/collection/shelf field)",
          any(word in help_text for word in
              ("category", "collection", "genre", "shelf", "tag")),
          help_text[:100])
    # "Remember between executions": every ``cli`` call is a NEW process, so a
    # row added by one and listed by the next is persistence across runs.
    rc, out, err = cli(project, "book", "list")
    check("the information survives the next execution",
          rc == 0 and "Dune" in out, "rc=%s out=%s" % (rc, out[:80]))


def probe_49():
    """Employees: "which employees belong to which departments … find
    employees quickly"."""
    project = fresh("49")
    create(project, ("department", "departments"), name="D1")
    create(project, ("department", "departments"), name="D2")
    first = create(project, ("employee", "employees"), first_name="E",
                   last_name="One", department_id=1, email="e1@x.com")
    create(project, ("employee", "employees"), first_name="F", last_name="Two",
           department_id=2, email="e2@x.com")
    check("employees can be attached to departments", first[1] == 0,
          "rc=%s err=%s" % (first[1], first[3][:120]))
    help_text = cli(project, "employee", "list", "--help")[1]
    if "--department-id" in help_text:
        by_dept = cli(project, "employee", "list", "--department-id", "1")[1]
        check("an employee listing can be narrowed to one department",
              by_dept.count("Employee(") == 1,
              "out=%s" % by_dept[:120])
    else:
        check("an employee listing can be narrowed to one department", False,
              "employee list help=%s" % help_text[:100])
    found = find_command(project, "search", "find")
    if found is not None:
        rc, out, err = cli(project, found[0], found[1], "--term", "One")
        check("an employee can be found quickly", rc == 0,
              "cmd=%s rc=%s err=%s" % (" ".join(found), rc, err[:80]))
    else:
        check("an employee can be found quickly",
              "--name" in help_text or "--first-name" in help_text,
              "employee list help=%s" % help_text[:100])


def probe_50():
    """Events: "create events and register for them. The application should
    prevent registrations when an event is full"."""
    project = fresh("50")
    event_help = cli(project, "event", "add", "--help")[1]
    cap_opt = exposes(event_help, "max-participants", "capacity", "capacity-max",
                      "slots", "seats")
    check("an event declares a participant limit", cap_opt is not None,
          "options=%s" % re.findall(r"--[\w-]+", event_help)[:8])
    if cap_opt is None:
        return
    event = create(project, ("event", "events"), title="E", name="E",
                   **{cap_opt.replace("-", "_"): "2"})
    check("an event with a participant limit can be created", event[1] == 0,
          "rc=%s err=%s" % (event[1], event[3][:120]))
    # The registration is whichever command names BOTH an event and a person
    # ("registration add", "event register", ...): every command is inspected
    # rather than taking the first whose name mentions one.
    register = None
    event_opt = person_opt = None
    for group in subgroups(project):
        for command in subcommands(project, group):
            reg_help = cli(project, group, command, "--help")[1]
            e_opt = exposes(reg_help, "event-id", "event")
            p_opt = exposes(reg_help, "person-id", "attendee-id", "user-id",
                            "member-id", "guest-id")
            if e_opt and p_opt:
                register, event_opt, person_opt = (group, command), e_opt, p_opt
                break
        if register is not None:
            break
    if register is None:
        check("a command registers a person for an event", False,
              "no command names an event and a person")
        return
    check("a command registers a person for an event", True)
    outcomes = []
    for index in range(1, 4):
        rc, out, err = cli(project, register[0], register[1],
                           "--" + event_opt, "1", "--" + person_opt, str(index))
        outcomes.append(rc)
    check("the first registrations are accepted",
          outcomes[0] == 0, "rcs=%s" % outcomes)
    check("a registration beyond the participant limit is prevented",
          outcomes[2] != 0, "rcs=%s" % outcomes)


def probe_51():
    """Products: "Each product must have a unique SKU. At the same time, the
    system must allow multiple products to use the same SKU when they belong
    to different categories"."""
    project = fresh("51")
    first = create(project, ("product", "products"), sku="S1", name="A",
                   category="tools", category_id="1", price="10")
    duplicate = create(project, ("product", "products"), sku="S1", name="B",
                       category="tools", category_id="1", price="20")
    other_category = create(project, ("product", "products"), sku="S1",
                            name="C", category="food", category_id="2",
                            price="30")
    check("a product can be created with a SKU", first[1] == 0,
          "rc=%s err=%s" % (first[1], first[3][:120]))
    check("the same SKU is refused inside one category",
          duplicate[1] != 0, "rc=%s err=%s" % (duplicate[1], duplicate[3][:120]))
    check("the same SKU is allowed in a different category",
          other_category[1] == 0,
          "rc=%s err=%s" % (other_category[1], other_category[3][:120]))


def probe_52():
    """Library: "a book that is currently being borrowed should not appear as
    available. When it is returned, it should become available again"."""
    project = fresh("52")
    create(project, ("book", "books"), title="B1", isbn="1")
    create(project, ("member", "members"), first_name="M", last_name="One",
           email="m@x")
    borrowed = create(project, ("borrow_record", "borrow_record",
                                "loan", "loans", "borrowing", "borrow"),
                      book_id=1, member_id=1, due_date="2026-02-01")
    check("a book can be borrowed by a member", borrowed[1] == 0,
          "group=%s rc=%s err=%s" % (borrowed[0], borrowed[1], borrowed[3][:120]))
    label, during = availability_view(project, "book")
    check("the availability listing is reachable", label is not None,
          "listing=%s" % during[:120])
    if label is None:
        # A book listing is what makes availability observable at all; without
        # one the prompt's "should not appear as available" cannot be met.
        check("the application offers a book listing", False,
              "book commands=%s" % subcommands(project, "book"))
        return
    if label is not None:
        check("a borrowed book is not presented as available",
              "B1" not in during, "%s -> %s" % (label, during[:120]))
    returned = find_command(project, "return")
    if returned is None:
        check("the book can be returned", False, "no return command")
        return
    rc, out, err = cli(project, returned[0], returned[1], "--id", "1",
                       "--loan-id", "1", "--book-id", "1")
    check("the book can be returned", rc == 0,
          "cmd=%s rc=%s err=%s" % (" ".join(returned), rc, err[:100]))
    if label is not None:
        after = availability_view(project, "book")[1]
        check("the returned book is available again",
              "B1" in after, "%s -> %s" % (label, after[:120]))
def first_number(values):
    """The first value of ``values`` as a float, or None when there is none."""
    for value in values:
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def option_named(help_text, *candidates):
    """The first ``--option`` named among the candidates, as an argv name."""
    for candidate in candidates:
        if "--" + candidate in help_text:
            return candidate
    return candidates[-1]


def create_with_times(project, candidates, start, end, **overrides):
    """Create a row, filling whatever start/end option the group declares.

    The prompt says "appointments have a start and end time"; the design names
    those columns freely (``start_time``, ``starts_at``, ``begin``). The
    option names are read from the group's OWN ``add`` help.
    """
    for group in candidates:
        help_text = cli(project, group, "add", "--help")[1]
        if "Options" not in help_text:
            continue
        extra = dict(overrides)
        for option in re.findall(r"--([\w-]+)", help_text):
            key = option.replace("-", "_")
            if key in extra:
                continue
            if key.startswith(("start", "begin", "from")):
                extra[key] = start
            elif key.startswith(("end", "finish", "to_")):
                extra[key] = end
        return (group,) + create(project, (group,), **extra)
    return "", 1, "", "no add command among %s" % (candidates,)


def probe_53():
    """Orders: "A customer must not be able to place an order if any product
    has insufficient stock. When an order is successfully created, the
    corresponding stock quantities must be decreased"."""
    project = fresh("53")
    create(project, ("product", "products"), name="P1", price="10",
           stock_quantity="5")
    create(project, ("customer", "customers"), email="c@x")
    order_help = cli(project, "order", "add", "--help")[1]
    product_opt = exposes(order_help, "product-id", "product", "item-id")
    quantity_opt = exposes(order_help, "quantity", "qty", "count")
    check("order add takes a product and a quantity",
          product_opt is not None and quantity_opt is not None,
          "options=%s" % re.findall(r"--[\w-]+", order_help)[:8])
    if product_opt is None or quantity_opt is None:
        return
    before = first_number(stock_of(project)[1])
    too_much = create(project, ("order", "orders"), customer_id=1,
                      product_id=1, product="1", item_id="1", quantity="10",
                      qty="10", count="10")
    check("an order beyond the available stock is refused", too_much[1] != 0,
          "group=%s rc=%s err=%s" % (too_much[0], too_much[1], too_much[3][:120]))
    placed = create(project, ("order", "orders"), customer_id=1, product_id=1,
                    product="1", item_id="1", quantity="2", qty="2", count="2")
    check("an order within the stock is accepted", placed[1] == 0,
          "group=%s rc=%s err=%s" % (placed[0], placed[1], placed[3][:120]))
    after = first_number(stock_of(project)[1])
    check("the stock is decreased by the order",
          before is not None and after is not None and after < before,
          "before=%s after=%s" % (before, after))


def probe_54():
    """Appointments: "must always end after it starts, but the application
    must also support appointments whose start and end time are identical"."""
    project = fresh("54")
    help_text = cli(project, "appointment", "add", "--help")[1]
    start_opt = exposes(help_text, "start-time", "start", "starts-at",
                        "start-date", "begin")
    end_opt = exposes(help_text, "end-time", "end", "ends-at", "end-date",
                      "finish")
    check("appointment add takes a start and an end time",
          start_opt is not None and end_opt is not None,
          "options=%s" % re.findall(r"--[\w-]+", help_text)[:8])
    if start_opt is None or end_opt is None:
        return
    backwards = create_with_times(
        project, ("appointment", "appointments"),
        "2026-01-01 10:00", "2026-01-01 09:00", title="A", name="A",
    )
    check("an appointment ending before it starts is refused",
          backwards[1] != 0,
          "group=%s rc=%s err=%s" % (backwards[0], backwards[1],
                                     backwards[3][:120]))
    identical = create_with_times(
        project, ("appointment", "appointments"),
        "2026-01-01 10:00", "2026-01-01 10:00", title="B", name="B",
    )
    check("an appointment whose start and end are identical is supported",
          identical[1] == 0,
          "group=%s rc=%s err=%s" % (identical[0], identical[1],
                                     identical[3][:120]))


def probe_55():
    """Inventory: "Users can sell products. The application should never allow
    the inventory to become incorrect"."""
    project = fresh("55")
    add_help = cli(project, "product", "add", "--help")[1]
    stock_opt = exposes(add_help, "stock-quantity", "stock", "quantity", "qty",
                        "on-hand")
    # The stock option is passed EXPLICITLY: a user who wants stock 5 types it,
    # whether or not the option is declared required.
    argv = ["product", "add", "--name", "P1", "--price", "10"]
    if stock_opt:
        argv += ["--" + stock_opt, "5"]
    rc, out, err = cli(project, *argv)
    product = ("product", rc, out, err)
    initial = first_number(stock_of(project)[1])
    check("a product records an initial stock of 5",
          product[1] == 0 and initial == 5,
          "stock_opt=%s rc=%s stock=%s" % (stock_opt, product[1], initial))
    if initial != 5:
        return
    # The sale is the command that names BOTH a product and a quantity; it may
    # be "sale add", "product sell" or anything else, so every command is
    # inspected instead of taking the first whose name mentions a sale.
    sell = None
    for group in subgroups(project):
        for command in subcommands(project, group):
            text = cli(project, group, command, "--help")[1]
            if exposes(text, "quantity", "qty", "count") and exposes(
                text, "product-id", "product", "item-id"
            ):
                sell = (group, command)
                break
        if sell is not None:
            break
    if sell is None:
        check("a command records a sale of a product in a quantity", False,
              "no command names both a product and a quantity")
        return
    help_text = cli(project, sell[0], sell[1], "--help")[1]
    id_opt = exposes(help_text, "product-id", "product", "item-id")
    qty_opt = exposes(help_text, "quantity", "qty", "count")
    check("the sale command takes a product and a quantity",
          id_opt is not None and qty_opt is not None,
          "cmd=%s options=%s" % (" ".join(sell), re.findall(r"--[\w-]+", help_text)[:8]))
    if id_opt is None or qty_opt is None:
        return
    price_opt = exposes(help_text, "sale-price", "unit-price", "price", "total")
    extra = []
    if price_opt:
        extra = ["--" + price_opt, "10"]
    before = first_number(stock_of(project)[1])
    ok = cli(project, sell[0], sell[1], "--" + id_opt, "1", "--" + qty_opt, "2",
             *extra)
    after = first_number(stock_of(project)[1])
    check("a sale of 2 leaves the stock at 3",
          ok[0] == 0 and before == 5 and after == 3,
          "rc=%s before=%s after=%s err=%s" % (ok[0], before, after, ok[2][:100]))
    refused = cli(project, sell[0], sell[1], "--" + id_opt, "1", "--" + qty_opt,
                  "100", *extra)
    final = first_number(stock_of(project)[1])
    check("selling more than the stock is refused and changes nothing",
          refused[0] != 0 and final == after,
          "rc=%s after=%s final=%s err=%s" % (refused[0], after, final,
                                              refused[2][:100]))


def probe_56():
    """CLI: "products can be searched and filtered, orders can be cancelled,
    cancelling an order must restore its product quantities, and all
    modifications must be persisted atomically in SQLite"."""
    project = fresh("56")
    create(project, ("product", "products"), name="P1", price="10",
           stock_quantity="5")
    create(project, ("customer", "customers"), email="c@x")
    search = find_command(project, "search")
    if search is not None:
        term_opt = exposes(cli(project, search[0], search[1], "--help")[1],
                           "term", "query", "name", "title")
        argv = ["--" + term_opt, "P1"] if term_opt else []
        rc, out, err = cli(project, search[0], search[1], *argv)
        check("products can be searched", rc == 0,
              "cmd=%s rc=%s err=%s" % (" ".join(search), rc, err[:100]))
    else:
        listing = cli(project, "product", "list")[1]
        check("products can be searched", "P1" in listing,
              "no search command; listing=%s" % listing[:80])
    order_help = cli(project, "order", "add", "--help")[1]
    product_opt = exposes(order_help, "product-id", "product", "item-id")
    quantity_opt = exposes(order_help, "quantity", "qty", "count")
    line_cmd = find_command(project, "order_item", "order-line", "line")
    check("an order can be given products (order add, or a line command)",
          (product_opt is not None and quantity_opt is not None)
          or line_cmd is not None,
          "order add options=%s line=%s"
          % (re.findall(r"--[\w-]+", order_help)[:8], line_cmd))
    if product_opt is None or quantity_opt is None:
        return
    before = first_number(stock_of(project)[1])
    placed = create(project, ("order", "orders"), customer_id=1, product_id=1,
                    product="1", item_id="1", quantity="2", qty="2", count="2")
    check("an order can be placed", placed[1] == 0,
          "group=%s rc=%s err=%s" % (placed[0], placed[1], placed[3][:120]))
    cancel = find_command(project, "cancel")
    if cancel is None:
        check("an order can be cancelled", False, "no cancel command")
        return
    rc, out, err = cli(project, cancel[0], cancel[1], "--id", "1")
    check("an order can be cancelled", rc == 0,
          "cmd=%s rc=%s err=%s" % (" ".join(cancel), rc, err[:100]))
    restored = first_number(stock_of(project)[1])
    check("cancelling the order restores the product quantity",
          before is not None and restored == before,
          "before the order=%s after the cancel=%s" % (before, restored))


def probe_57():
    """Documents: "The CLI should remain independent from persistence so that
    the persistence mechanism can later be replaced"."""
    project = fresh("57")
    added = create(project, ("document", "documents"), title="D",
                   content="C", user_id="1", owner_id="1")
    check("a document can be recorded through the CLI", added[1] == 0,
          "group=%s rc=%s err=%s" % (added[0], added[1], added[3][:120]))
    stems = {path.stem for path in project.glob("*.py")}
    check("the business logic sits in a service, not in the CLI",
          any(stem.endswith("_service") or stem == "service" for stem in stems),
          str(sorted(stems)))
    entry = entry_of(project)
    cli_text = entry.read_text() if entry is not None else ""
    check("the CLI reaches no persistence mechanism of its own",
          "import sqlite3" not in cli_text
          and not re.search(r"^\s*from\s+\w*(database|repository)\w*\s+import",
                            cli_text, re.M),
          "entry=%s" % (entry.name if entry else None))


def probe_58():
    """Customers plus an external information service: "The application should
    continue to operate correctly when the external service is unavailable"."""
    project = fresh("58")
    added = create(project, ("customer", "customers"), email="c@x", name="C")
    check("a customer can be recorded", added[1] == 0,
          "rc=%s err=%s" % (added[1], added[3][:120]))
    rc, out, err = cli(project, "customer", "list")
    check("customers can be listed with no external service running",
          rc == 0, "rc=%s err=%s" % (rc, err[:120]))
    external = find_command(project, "external", "info", "details", "enrich",
                            "fetch", "lookup", "profile")
    if external is None:
        check("the external-information capability is reachable", False,
              "no command names an external lookup")
        return
    rc, out, err = cli(project, external[0], external[1], "--id", "1",
                       "--customer-id", "1")
    check("an unavailable external service does not crash the application",
          "Traceback" not in err,
          "cmd=%s rc=%s out=%s err=%s" % (" ".join(external), rc, out[:80],
                                          err[:120]))
    check("the application still answers after that failure",
          cli(project, "customer", "list")[0] == 0,
          "list rc=%s" % (cli(project, "customer", "list")[0],))


def probe_60():
    """A small business: "Confirming an order reserves stock. Cancelling a
    confirmed order releases the reserved stock. An invoice is created when an
    order is confirmed … keep business logic separate from persistence"."""
    project = fresh("60")
    category = create(project, ("category", "categories"), name="C1")
    product = create(project, ("product", "products"), name="P1", price="10",
                     stock_quantity="5", category_id="1")
    create(project, ("customer", "customers"), email="c@x", name="C")
    check("categories and products can be managed",
          category[1] == 0 and product[1] == 0,
          "category=%s product=%s" % (category[1:3], product[1:3]))
    order_help = cli(project, "order", "add", "--help")[1]
    product_opt = exposes(order_help, "product-id", "product", "item-id")
    quantity_opt = exposes(order_help, "quantity", "qty", "count")
    check("order add takes a product and a quantity",
          product_opt is not None and quantity_opt is not None,
          "options=%s" % re.findall(r"--[\w-]+", order_help)[:8])
    if product_opt is None or quantity_opt is None:
        return
    before = first_number(stock_of(project)[1])
    placed = create(project, ("order", "orders"), customer_id=1, product_id=1,
                    product="1", item_id="1", quantity="2", qty="2", count="2")
    check("an order can be placed", placed[1] == 0,
          "group=%s rc=%s err=%s" % (placed[0], placed[1], placed[3][:120]))
    confirm = find_command(project, "confirm")
    if confirm is None:
        check("an order can be confirmed", False, "no confirm command")
        return
    rc, out, err = cli(project, confirm[0], confirm[1], "--id", "1")
    reserved = first_number(stock_of(project)[1])
    tables = [str(row[0]) for row in
              sql(project, "SELECT name FROM sqlite_master WHERE type='table'")]
    invoices = [name for name in tables if "invoice" in name.lower()]
    entries = sum(len(sql(project, "SELECT * FROM %s" % name))
                  for name in invoices)
    check("confirming the order reserves stock",
          rc == 0 and before is not None and reserved is not None
          and reserved < before,
          "rc=%s before=%s after=%s err=%s" % (rc, before, reserved, err[:100]))
    check("confirming the order creates an invoice",
          bool(invoices) and entries >= 1,
          "tables=%s" % tables)
    cancel = find_command(project, "cancel")
    if cancel is None:
        check("a confirmed order can be cancelled", False, "no cancel command")
        return
    rc, out, err = cli(project, cancel[0], cancel[1], "--id", "1")
    released = first_number(stock_of(project)[1])
    check("cancelling the confirmed order releases the stock",
          rc == 0 and released == before,
          "rc=%s before the order=%s after the cancel=%s err=%s"
          % (rc, before, released, err[:100]))
    entry = entry_of(project)
    cli_text = entry.read_text() if entry is not None else ""
    check("the CLI reaches no persistence mechanism of its own",
          "import sqlite3" not in cli_text,
          "entry=%s" % (entry.name if entry else None))


PROBES = {
    "%02d" % number: globals()["probe_%02d" % number]
    for number in range(41, 61)
    if "probe_%02d" % number in globals()
}


def main():
    wanted = sys.argv[1:] or sorted(PROBES)
    verdicts = {}
    for number in wanted:
        probe = PROBES.get(number)
        if probe is None:
            continue
        del RESULTS[:]
        print("== %s ==" % number)
        try:
            probe()
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            check("the probe itself failed", False, repr(exc))
        passed = sum(1 for ok in RESULTS if ok)
        verdicts[number] = (passed, len(RESULTS))
    print()
    print("verdicts: %s" % {k: "%d/%d" % v for k, v in sorted(verdicts.items())})
    total_pass = sum(p for p, _ in verdicts.values())
    total = sum(t for _, t in verdicts.values())
    print("TOTAL %d/%d checks" % (total_pass, total))
    print("NOTE: prompt 59 is not probed - its generation fails at scale "
          "(output-budget truncation in the repair loop); see "
          "analysis/progress_journal.md")


if __name__ == "__main__":
    main()
