"""Pre-flight checks for Python files: would this fail the moment it runs?

Two checks today. The file parses, and the module-level names it reads actually
resolve. Both are runtime-fatal, and neither is a matter of taste.

That question is the charter, and it is what keeps this from drifting into a
second linter. A rule belongs here only if breaking it means the file cannot
run. Style, naming and house conventions belong in the PR review checks, which
can weigh context and explain themselves; this one only ever answers yes or no.

Runs on every .py, not only notebooks -- of 3,019 tracked files, 225 are
notebooks under src/ and the rest are shared library code, tooling and converter
artifacts. All of them can be broken the same way.

RUN THIS ON PYTHON 3.12 OR NEWER. The answer to "does this parse" depends on the
interpreter version, so the check has to match the runtime the code executes on:
DBR 18 LTS and serverless environment_version 5 are both 3.12. Python 3.11
rejects nested quotes inside an f-string, which PEP 701 made legal in 3.12:

    f"{context.processed_files_dir}/Keys {datetime.now().strftime("%Y%m%d")}.xls"

Eight production files use that form. Under 3.11 every one is reported as
`f-string: unmatched '('` -- working code called broken, which is how a checker
loses its audience.

`python -m py_compile` and `ast.parse` only prove a file is syntactically valid.
Neither says anything about whether the names a module-level statement refers to
actually exist there, so this slips through both:

    class Context:
        ENVIRONMENT = dbutils.widgets.get("ENV_NAME").lower()

    scope = getSecretScopeName(env=ENVIRONMENT.lower())   # NameError at runtime

A name bound in a class body is NOT in scope outside it -- it has to be reached
as `Context.ENVIRONMENT`. Valid syntax, guaranteed failure, and in a Databricks
notebook the failure arrives in production rather than in review.

That exact bug reached `develop` in 14 notebooks. It was introduced by an
automated edit that reused an existing local without checking which scope the
local lived in, which is a mistake an LLM makes far more readily than a human
reading one file at a time. As more changes here are machine-generated, the
check belongs in CI rather than in each session's scratch scripts.

Scope of the check, deliberately narrow so it can be trusted:

  - Only module-level reads. Function and method bodies resolve at call time
    against globals that may legitimately be defined later, or by a caller.
  - A name counts as bound if it is bound anywhere at module level, so ordering
    is not policed -- only existence.
  - Databricks injects spark, dbutils, display and friends; those are known.
  - A file that does not parse fails too. It cannot run at all, so a syntax
    error is strictly worse than an unresolved name. Pass --allow-syntax-errors
    to downgrade that to a report, which is only sensible for a repo-wide run:
    1,075 of the 1,102 currently-unparseable files are machine-generated Talend
    evidence under conversion_prep_artifacts that is never executed.

Usage:
    python .github/scripts/python_preflight.py                 # all tracked .py
    python .github/scripts/python_preflight.py a.py b.py       # specific files
    python .github/scripts/python_preflight.py --changed BASE  # changed vs BASE

Exit code is 1 when anything is found, 0 otherwise.
"""
import argparse
import ast
import builtins
import io
import subprocess
import sys

# Present in every module's globals, but not in builtins.
MODULE_GLOBALS = {
    "__file__",
    "__name__",
    "__doc__",
    "__package__",
    "__spec__",
    "__loader__",
    "__builtins__",
    "__dict__",
}

# Injected into every Databricks notebook's globals by the runtime.
DATABRICKS_GLOBALS = {
    "spark",
    "sc",
    "sqlContext",
    "dbutils",
    "display",
    "displayHTML",
    "getArgument",
    "udf",
    "table",
    "sql",
    "spark_partition_id",
}

# Nodes that open a new scope. Names bound inside one are not visible outside it.
SCOPED = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

MAGIC_PREFIXES = ("# MAGIC", "%pip", "%sh", "%sql", "%run", "%md", "%scala", "%r")


def strip_magics(text):
    """Blank Databricks magic lines, keeping line numbers intact.

    Deleting them would shift every subsequent line number and make the reported
    location wrong, which is worse than useless in a 900-line notebook.
    """
    out = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith(MAGIC_PREFIXES) or line.startswith("!"):
            out.append("")
        else:
            out.append(line)
    return "\n".join(out)


def walk_own_scope(node):
    """Like ast.walk, but never descends into a nested scope.

    ast.walk cannot express this. A `continue` inside its loop skips a single
    node, not its subtree, so class-body assignments still get collected as if
    they were module level -- which silently defeats the entire check. Child
    nodes are therefore pushed explicitly.
    """
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        for child in ast.iter_child_nodes(current):
            if isinstance(child, SCOPED):
                continue
            stack.append(child)


def module_level_bindings(tree):
    """Every name bound at module scope, anywhere in the file."""
    bound = set()
    for node in tree.body:
        if isinstance(node, SCOPED):
            name = getattr(node, "name", None)
            if name:
                bound.add(name)
            continue
        for sub in walk_own_scope(node):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                bound.add(sub.id)
            elif isinstance(sub, (ast.Import, ast.ImportFrom)):
                for alias in sub.names:
                    bound.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(sub, ast.ExceptHandler) and sub.name:
                bound.add(sub.name)
            elif isinstance(sub, (ast.Global, ast.Nonlocal)):
                bound.update(sub.names)
            # A def or class nested in an `if` or `try` still binds its name at
            # module scope. walk_own_scope stops at the boundary, so the name is
            # collected here without descending into the body.
            for child in ast.iter_child_nodes(sub):
                if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    bound.add(child.name)
    return bound


def class_body_bindings(tree):
    """-> {name: ClassName} for names bound directly in a class body.

    Used only to make the message actionable: knowing a name came from a class
    body turns "undefined" into "write Context.REGION".
    """
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if isinstance(stmt, SCOPED):
                continue
            for sub in walk_own_scope(stmt):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    found.setdefault(sub.id, node.name)
    return found


def module_level_loads(tree):
    """Names read by module-level statements, as (name, lineno)."""
    reads = []
    for node in tree.body:
        if isinstance(node, SCOPED):
            continue
        # Comprehensions bind their own targets; those are not free variables.
        comprehension_targets = set()
        for sub in walk_own_scope(node):
            if isinstance(sub, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                for generator in sub.generators:
                    for name_node in ast.walk(generator.target):
                        if isinstance(name_node, ast.Name):
                            comprehension_targets.add(name_node.id)
        for sub in walk_own_scope(node):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                if sub.id not in comprehension_targets:
                    reads.append((sub.id, sub.lineno))
    return reads


def has_star_import(tree):
    """`from x import *` puts unknown names in scope, so the check cannot be sure.

    Reporting a name that a star import provides is a false positive, and a check
    that cries wolf gets switched off. Files using one are skipped.
    """
    return any(
        isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names)
        for node in ast.walk(tree)
    )


def check_file(path):
    """-> (problems, parse_error). problems is [(name, lineno, class_or_None)]."""
    try:
        text = io.open(path, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return [], f"unreadable: {exc}"
    try:
        tree = ast.parse(strip_magics(text))
    except SyntaxError as exc:
        return [], f"line {exc.lineno}: {exc.msg}"

    if has_star_import(tree):
        return [], None

    known = (
        module_level_bindings(tree)
        | MODULE_GLOBALS
        | DATABRICKS_GLOBALS
        | set(dir(builtins))
    )
    from_class = class_body_bindings(tree)

    seen = set()
    problems = []
    for name, lineno in module_level_loads(tree):
        if name in known or (name, lineno) in seen:
            continue
        seen.add((name, lineno))
        problems.append((name, lineno, from_class.get(name)))
    return problems, None


def tracked_python_files():
    return subprocess.run(
        ["git", "ls-files", "--", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()


def changed_python_files(base):
    out = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=d", base],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [f for f in out if f.endswith(".py")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="files to check; default is all tracked .py")
    parser.add_argument("--changed", metavar="BASE", help="only files changed against BASE")
    parser.add_argument(
        "--allow-syntax-errors",
        action="store_true",
        help="report files that do not parse without failing (for repo-wide runs)",
    )
    args = parser.parse_args()

    if args.paths:
        paths = args.paths
    elif args.changed:
        paths = changed_python_files(args.changed)
    else:
        paths = tracked_python_files()

    if not paths:
        print("No Python files to check.")
        return 0

    total = 0
    unparseable = []
    for path in sorted(paths):
        problems, parse_error = check_file(path)
        if parse_error:
            unparseable.append((path, parse_error))
            continue
        if not problems:
            continue
        total += len(problems)
        print(f"{path}")
        for name, lineno, cls in problems:
            if cls:
                hint = f" -- bound in class {cls}; write {cls}.{name}"
            else:
                hint = " -- not defined at module level"
            print(f"  line {lineno}: {name}{hint}")
        print()

    if unparseable:
        label = "reported, not failed" if args.allow_syntax_errors else "FAILED"
        print(f"Files that do not parse ({label}):")
        for path, why in unparseable:
            print(f"  {path}")
            print(f"    {why}")
        print()

    print(
        f"Checked {len(paths)} file(s). "
        f"Syntax errors: {len(unparseable)}. "
        f"Unresolved module-level names: {total}."
    )

    if total:
        print(
            "\nEach unresolved name raises NameError when the module runs. A name "
            "bound in a\nclass body is not in scope outside it -- qualify it, or "
            "bind it at module level."
        )
    if unparseable and not args.allow_syntax_errors:
        print(
            "\nA file that does not parse cannot run at all. If it was already "
            "broken before\nyour change, say so in the pull request; do not leave "
            "it unexplained."
        )

    failed = total or (unparseable and not args.allow_syntax_errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
