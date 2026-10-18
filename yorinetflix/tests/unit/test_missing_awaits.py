"""
YoriNetflix — "forgot to await" static regression test.

The ``/referral`` production crash was an un-awaited coroutine::

    aiogram.exceptions.TelegramBadRequest: Telegram server says - Bad Request:
    can't parse entities: Unsupported start tag "coroutine" at byte offset 28

``get_referral_link()`` is ``async def`` but was called without ``await``, so
its repr (``<coroutine object …>``) was formatted straight into the HTML
message.  Python only reports this as a ``RuntimeWarning`` when the coroutine
is garbage collected, which is easy to miss in a busy log.

This test resolves every import in the application, then walks the AST and
fails on any call to a coroutine function that is not awaited (and is not
handed to ``asyncio.gather``/``create_task``/…, which legitimately take the
coroutine object itself).  Resolution is import-aware so that unrelated
methods that merely share a name — ``dict.get()``, ``set.add()`` — are not
reported.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # yorinetflix/
APP_ROOT = PACKAGE_ROOT / "app"

# Calls that take a coroutine *object* rather than its result.
_ASYNC_WRAPPERS = {
    "gather",
    "create_task",
    "ensure_future",
    "wait_for",
    "shield",
    "as_completed",
    "wait",
    "run_coroutine_threadsafe",
    "iscoroutine",
    "iscoroutinefunction",
    "Task",
    "run",
}


# ── Module model ──────────────────────────────────────────────


class Module:
    """One application module: its AST, coroutine names and import bindings."""

    def __init__(self, path: Path):
        self.path = path
        self.name = path.relative_to(PACKAGE_ROOT).with_suffix("").as_posix().replace("/", ".")
        self.tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(self.tree):
            for child in ast.iter_child_nodes(node):
                child._parent = node  # type: ignore[attr-defined]

        #: coroutine functions defined in this module
        self.coroutines = {
            node.name
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        #: local name -> coroutine function (defined here or imported)
        self.coroutine_bindings: dict[str, str] = {}
        #: local name -> module dotted name (``from app.x import y`` submodules)
        self.module_bindings: dict[str, str] = {}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Module {self.name}>"


def _load_modules() -> dict[str, Module]:
    modules = {p: Module(p) for p in sorted(APP_ROOT.rglob("*.py"))}
    return {m.name: m for m in modules.values()}


def _resolve_import(modules: dict[str, Module], module_name: str, alias: str) -> str | None:
    """Resolve an imported alias to a known application *module* name.

    ``from app.database.repositories import user_repo`` binds a submodule,
    while ``from app.services.referrals import get_referral_link`` binds a
    function — only the former resolves here.
    """
    submodule = f"{module_name}.{alias}"
    return submodule if submodule in modules else None


def _bind_imports(modules: dict[str, Module]) -> None:
    """Populate every module's coroutine/module bindings from its imports."""
    for module in modules.values():
        for node in ast.walk(module.tree):
            if isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if not base.startswith("app"):
                    continue
                for alias in node.names:
                    local = alias.asname or alias.name
                    target = _resolve_import(modules, base, alias.name)
                    if target is not None:
                        module.module_bindings[local] = target
                        continue
                    if base in modules and alias.name in modules[base].coroutines:
                        module.coroutine_bindings[local] = base
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app"):
                        local = alias.asname or alias.name
                        if alias.name in modules:
                            module.module_bindings[local] = alias.name

        for name in module.coroutines:
            module.coroutine_bindings.setdefault(name, module.name)


# ── Call analysis ─────────────────────────────────────────────


def _callee_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _consumed_as_awaitable(node: ast.AST) -> bool:
    """True when the call is awaited or handed to an asyncio helper."""
    current = node
    for _ in range(4):
        parent = getattr(current, "_parent", None)
        if parent is None:
            return False
        if isinstance(parent, ast.Await):
            return True
        if isinstance(parent, ast.Call):
            return _callee_name(parent) in _ASYNC_WRAPPERS
        if isinstance(parent, (ast.List, ast.Tuple, ast.Set, ast.Starred, ast.keyword)):
            current = parent
            continue
        return False
    return False


def _unawaited_call(
    modules: dict[str, Module], module: Module, call: ast.Call
) -> str | None:
    """Return a description if this call needs ``await`` but does not have it."""
    func = call.func
    target_module: str | None = None

    if isinstance(func, ast.Name):
        if func.id in module.coroutine_bindings:
            target_module = module.coroutine_bindings[func.id]
    elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        owner = module.module_bindings.get(func.value.id)
        if owner is not None and func.attr in modules[owner].coroutines:
            target_module = owner

    if target_module is None or _consumed_as_awaitable(call):
        return None

    relative = module.path.relative_to(PACKAGE_ROOT)
    return (
        f"{relative}:{call.lineno} — '{_callee_name(call)}()' is a coroutine "
        f"(defined in {target_module}) and is never awaited"
    )


def find_unawaited_coroutine_calls() -> list[str]:
    modules = _load_modules()
    _bind_imports(modules)

    problems: list[str] = []
    for module in modules.values():
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Call):
                problem = _unawaited_call(modules, module, node)
                if problem:
                    problems.append(problem)
    return sorted(problems)


# ── Tests ─────────────────────────────────────────────────────


class TestNoMissingAwaits:
    def test_app_tree_is_scanned(self):
        modules = _load_modules()
        assert modules, f"no python modules found under {APP_ROOT}"
        assert any(m.coroutines for m in modules.values()), (
            "expected to find coroutine functions in the app"
        )

    def test_imports_resolve(self):
        modules = _load_modules()
        _bind_imports(modules)
        rewards = modules["app.handlers.rewards"]
        assert rewards.coroutine_bindings.get("get_referral_link") == "app.services.referrals"
        assert rewards.module_bindings.get("user_repo") == "app.database.repositories.user_repo"

    def test_dict_methods_are_not_flagged(self):
        """Guard against the obvious false positive (``dict.get`` vs an
        ``async def get`` somewhere in the repositories)."""
        modules = _load_modules()
        _bind_imports(modules)
        throttle = modules["app.middleware.throttle"]
        assert "get" not in throttle.coroutine_bindings

    def test_every_coroutine_call_is_awaited(self):
        problems = find_unawaited_coroutine_calls()
        assert not problems, (
            "Un-awaited coroutines render as '<coroutine object …>' in message "
            "text, which Telegram rejects with \"can't parse entities\":\n"
            + "\n".join(problems)
        )

    def test_referral_link_helper_is_awaited_in_handler(self):
        """Explicit guard for the exact regression that hit production."""
        source = (APP_ROOT / "handlers" / "rewards.py").read_text(encoding="utf-8")
        assert "await get_referral_link(" in source
        assert "link = get_referral_link(" not in source
