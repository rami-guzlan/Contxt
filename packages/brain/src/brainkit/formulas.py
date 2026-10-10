"""Column formulas for State sheets (brain-logic plan 8.2): one formula per column, applied to
every row, written with column names and computed at read time by this small evaluator. Never a
model, never arbitrary code: a formula is parsed into a short list of allowed shapes, and
anything else is refused when the column is made.

Written the way a person would: `[Renewal date] - TODAY()`, `IF([Health] = "Red", "At risk",
"")`, `COUNT("issues")`, `LOOKUP([Owner], "Email")`, `AGE("Health")`.

- Inputs: the row's other columns (`[Name]`), `TODAY()`, the row's own dates (`CREATED()`,
  `UPDATED()`), a cell's age in days (`AGE("Column")`, from the cell log), and linked rows: rows
  of another sheet whose reference column points at this row (`COUNT("sheet")`,
  `SUM("sheet", "Column")`, `AVERAGE`, `MIN`, `MAX`), or one field looked up through this row's
  reference column (`LOOKUP([Owner], "Email")`).
- Functions: arithmetic (+ - * /), comparisons (= <> < <= > >=), AND, OR, NOT, IF, JOIN (text),
  DAYS(a, b) (a minus b in days), ADD_DAYS(date, n), ROUND(x, places).
- Dates: a date minus a date is a number of days; a date plus a number is a date.
- Left out on purpose: cell-by-cell references, arrays, pivots, macros and scripts.
"""
from __future__ import annotations

import ast
import datetime as dt
import re
from typing import Any, Callable

FUNCTIONS = ("TODAY", "CREATED", "UPDATED", "AGE", "COUNT", "SUM", "AVERAGE", "MIN", "MAX",
             "LOOKUP", "IF", "AND", "OR", "NOT", "JOIN", "DAYS", "ADD_DAYS", "ROUND")
COLUMN = re.compile(r"\[([^\[\]]{1,80})\]")
MAX_FORMULA = 300


class FormulaError(ValueError):
    pass


def _date(value: Any) -> dt.date | None:
    if isinstance(value, dt.date):
        return value
    text = str(value or "").strip()[:10]
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None


def parse(formula: str, columns: list[str]) -> tuple[ast.Expression, dict[str, str]]:
    """The formula as a checked expression, and its placeholders for column names. A formula
    that names an unknown column or uses anything outside the allowed shapes is refused."""
    text = str(formula or "").strip()
    if text.startswith("="):
        text = text[1:].strip()
    if not text:
        raise FormulaError("A formula needs something to compute.")
    if len(text) > MAX_FORMULA:
        raise FormulaError(f"Keep a formula under {MAX_FORMULA} characters.")
    names: dict[str, str] = {}
    known = {c.lower(): c for c in columns}

    def place(match: re.Match) -> str:
        name = match.group(1).strip()
        if name.lower() not in known:
            raise FormulaError(f"There is no column {name!r}.")
        slot = f"c{len(names)}"
        names[slot] = known[name.lower()]
        return slot

    python = COLUMN.sub(place, text)
    # A person writes = and <> ; Python reads == and !=.
    python = re.sub(r"(?<![<>=!])=(?!=)", "==", python).replace("<>", "!=")
    try:
        tree = ast.parse(python, mode="eval")
    except SyntaxError as exc:
        raise FormulaError("The formula could not be read: check its brackets and quotes.") \
            from exc
    _check(tree.body, set(names))
    return tree, names


ALLOWED_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
ALLOWED_CMP = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def _check(node: ast.AST, slots: set[str]) -> None:
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float, str)) or isinstance(node.value, bool):
            raise FormulaError("Only numbers and quoted text can be written as values.")
        return
    if isinstance(node, ast.Name):
        if node.id not in slots:
            raise FormulaError(f"{node.id!r} is not a column: put column names in brackets, "
                               "like [Renewal date].")
        return
    if isinstance(node, ast.BinOp) and isinstance(node.op, ALLOWED_OPS):
        _check(node.left, slots)
        _check(node.right, slots)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        _check(node.operand, slots)
        return
    if isinstance(node, ast.Compare) and len(node.ops) == 1 \
            and isinstance(node.ops[0], ALLOWED_CMP):
        _check(node.left, slots)
        _check(node.comparators[0], slots)
        return
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id.upper() in FUNCTIONS and not node.keywords:
        for arg in node.args:
            _check(arg, slots)
        return
    raise FormulaError("That formula uses something formulas cannot do here; see the "
                       "functions listed beside the formula box.")


class Row:
    """What a formula can read about one row."""

    def __init__(self, values: dict[str, Any], *, created: str = "", updated: str = "",
                 ages: dict[str, int] | None = None,
                 linked: Callable[[str], list[dict[str, Any]]] | None = None,
                 lookup: Callable[[str, str], Any] | None = None):
        self.values = values
        self.created = created
        self.updated = updated
        self.ages = ages or {}
        self.linked = linked or (lambda sheet: [])
        self.lookup = lookup or (lambda ref, column: None)


def evaluate(tree: ast.Expression, names: dict[str, str], row: Row,
             today: dt.date | None = None) -> Any:
    """The formula's value for one row; None when an input is missing or does not fit (a blank
    cell shows blank, never an error)."""
    today = today or dt.date.today()
    try:
        return _value(_eval(tree.body, names, row, today))
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None


def _value(found: Any) -> Any:
    if isinstance(found, float) and found.is_integer():
        return int(found)
    if isinstance(found, float):
        return round(found, 4)
    if isinstance(found, dt.date):
        return found.isoformat()
    return found


def _eval(node: ast.AST, names: dict[str, str], row: Row, today: dt.date) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        raw = row.values.get(names[node.id])
        if raw in (None, ""):
            return None
        return _date(raw) if _date(raw) and re.match(r"^\d{4}-\d{2}-\d{2}", str(raw)) \
            else (_number(raw) if _number(raw) is not None else raw)
    if isinstance(node, ast.UnaryOp):
        found = _eval(node.operand, names, row, today)
        return None if found is None else -found
    if isinstance(node, ast.BinOp):
        left = _eval(node.left, names, row, today)
        right = _eval(node.right, names, row, today)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Sub) and isinstance(left, dt.date) \
                and isinstance(right, dt.date):
            return (left - right).days
        if isinstance(node.op, (ast.Add, ast.Sub)) and isinstance(left, dt.date):
            days = dt.timedelta(days=float(right))
            return left + days if isinstance(node.op, ast.Add) else left - days
        ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
               ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}
        return ops[type(node.op)](left, right)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, names, row, today)
        right = _eval(node.comparators[0], names, row, today)
        if isinstance(left, str) and isinstance(right, str):
            left, right = left.lower(), right.lower()
        op = node.ops[0]
        if left is None or right is None:
            return isinstance(op, ast.NotEq) and left != right
        cmp = {ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b,
               ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b,
               ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b}
        return cmp[type(op)](left, right)
    assert isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    name = node.func.id.upper()
    args = node.args
    if name == "IF":
        if len(args) not in (2, 3):
            raise TypeError("IF takes a test, a value, and an optional other value")
        test = _eval(args[0], names, row, today)
        if test:
            return _eval(args[1], names, row, today)
        return _eval(args[2], names, row, today) if len(args) == 3 else ""
    values = [_eval(a, names, row, today) for a in args]
    if name == "TODAY":
        return today
    if name == "CREATED":
        return _date(row.created)
    if name == "UPDATED":
        return _date(row.updated)
    if name == "AGE":
        return row.ages.get(str(values[0])) if values else None
    if name == "AND":
        return all(bool(v) for v in values)
    if name == "OR":
        return any(bool(v) for v in values)
    if name == "NOT":
        return not bool(values[0]) if values else None
    if name == "JOIN":
        return " ".join(str(v) for v in values if v not in (None, ""))
    if name == "DAYS":
        a, b = (_date(v) for v in values[:2])
        return None if a is None or b is None else (a - b).days
    if name == "ADD_DAYS":
        start = _date(values[0])
        return None if start is None or values[1] is None else start + dt.timedelta(
            days=float(values[1]))
    if name == "ROUND":
        number = _number(values[0])
        return None if number is None else round(number, int(values[1]) if len(values) > 1
                                                 else 0)
    if name == "LOOKUP":
        return row.lookup(str(values[0] or ""), str(values[1] if len(values) > 1 else ""))
    if name in ("COUNT", "SUM", "AVERAGE", "MIN", "MAX"):
        linked = row.linked(str(values[0] or ""))
        if name == "COUNT":
            return len(linked)
        column = str(values[1] if len(values) > 1 else "")
        numbers = [n for n in (_number(r.get(column)) for r in linked) if n is not None]
        if name == "SUM":
            return sum(numbers)
        if not numbers:
            return None
        return {"AVERAGE": sum(numbers) / len(numbers), "MIN": min(numbers),
                "MAX": max(numbers)}[name]
    raise TypeError(name)


def describe(formula: str) -> str:
    """The formula in plain words for the column header."""
    text = str(formula or "").strip().lstrip("=").strip()
    words = [(r"\bTODAY\(\)", "today"), (r"\bCREATED\(\)", "when the row was added"),
             (r"\bUPDATED\(\)", "when the row last changed"),
             (r'\bAGE\("([^"]+)"\)', r"days since \1 last changed"),
             (r'\bCOUNT\("([^"]+)"\)', r"how many linked \1 rows"),
             (r'\bSUM\("([^"]+)",\s*"([^"]+)"\)', r"the sum of \2 over linked \1 rows"),
             (r'\bLOOKUP\(\[([^\]]+)\],\s*"([^"]+)"\)', r"\2 of the row in \1"),
             (r"\s-\s", " minus "), (r"\s\+\s", " plus "), (r"<>", " is not "),
             (r"\[([^\]]+)\]", r"\1")]
    for pattern, replacement in words:
        text = re.sub(pattern, replacement, text)
    return " ".join(text.split())
