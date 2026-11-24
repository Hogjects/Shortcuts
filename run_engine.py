"""Executes a Shortcut by walking its steps and resolving params and control flow"""

import action_library as lib


class RunContext:
    def __init__(self, ask_text=None):
        self.variables = {}
        self.previous_result = None
        self.ask_text = ask_text  # callable taking prompt and default or None
        self.log = []
        self.call_stack = []  # uids currently running to guard against cycles

    def note(self, message):
        self.log.append(message)


def resolve_params(action_instance, action_type):
    resolved = {}
    for spec in action_type.params:
        pv = action_instance.params.get(spec.key)
        resolved[spec.key] = spec.default if pv is None else pv
    return resolved


def _resolve_values(resolved_params, ctx):
    return {k: (v.resolve(ctx) if hasattr(v, "resolve") else v) for k, v in resolved_params.items()}


def _compare(left, operator, right):
    def as_number(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    if operator == "is":
        return str(left) == str(right)
    if operator == "is not":
        return str(left) != str(right)
    if operator == "contains":
        return str(right) in str(left)
    if operator in ("is greater than", "is less than"):
        ln, rn = as_number(left), as_number(right)
        if ln is None or rn is None:
            ln, rn = str(left), str(right)
        return ln > rn if operator == "is greater than" else ln < rn
    return False


def run_steps(steps, ctx):
    for step in steps:
        run_step(step, ctx)


def run_step(step, ctx):
    action_type = lib.get_action_type(step.action_id)
    if action_type is None:
        ctx.note(f"Unknown action: {step.action_id}")
        return

    resolved = _resolve_values(resolve_params(step, action_type), ctx)

    if action_type.control == "if":
        cond = _compare(resolved.get("left", ""), resolved.get("operator", "is"), resolved.get("right", ""))
        ctx.note(f"If {resolved.get('left')!r} {resolved.get('operator')} {resolved.get('right')!r} \u2192 {cond}")
        run_steps(step.then_steps if cond else step.else_steps, ctx)
        return

    if action_type.control == "repeat":
        try:
            count = int(float(resolved.get("count", 0) or 0))
        except (TypeError, ValueError):
            count = 0
        for i in range(max(0, count)):
            ctx.note(f"Repeat {i + 1}/{count}")
            run_steps(step.body_steps, ctx)
        return

    ctx.note(f"Running {action_type.name}\u2026")
    result = action_type.run(resolved, ctx)
    ctx.previous_result = result
    if result is not None:
        ctx.note(f"\u2192 {result}")


def run_shortcut(shortcut, ctx):
    uid = getattr(shortcut, "uid", None)
    if uid is not None:
        ctx.call_stack.append(uid)
    try:
        run_steps(shortcut.steps, ctx)
    finally:
        if uid is not None:
            ctx.call_stack.pop()
