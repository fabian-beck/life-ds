#!/usr/bin/env python3
"""Static extraction of pipeline facts from the generation scripts.

Everything in here is derived from the source with `ast`—no imports of the
generators, so it runs without an API key and without triggering module-level
side effects. That matters because the whole point of this layer is to be the
thing that *cannot* drift from the code: if a phase changes its model, its
reasoning effort, its output schema, or its prompt wording, the chart changes
with it on the next run.

What is extracted per script:

- **AI call sites**—`client.responses.parse/create`, `chat.completions.create`
  and image generation calls, with the model expression, reasoning effort and
  structured-output schema resolved through module-level constants.
- **Prompt sources**—functions whose name looks like a prompt builder, plus
  module-level `*_PROMPT` constants, reduced to a template: the literal text the
  model sees, with `{expr}` placeholders where data is injected and the
  surrounding conditions recorded.
- **Schemas**—Pydantic model classes with their fields, annotations and
  `Field(description=...)` text.
- **CLI flags**—`parser.add_argument` calls with help text and defaults.
"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parents[1]

# Methods that put a prompt on the wire. Keyed by the trailing attribute path so
# `client.responses.parse` and `self.client.responses.parse` both match.
#
# `parse_structured` is the pipeline's own wrapper (`utils/model_calls.py`), and
# it is listed here for the same reason the SDK methods are: it is where a step
# names its model, its reasoning effort and its output schema, which is what the
# report reads. It is labeled by the API it makes, since that is what the step
# actually does, and the wrapper's own call to the SDK is skipped — see
# TRANSPORT_MODULE.
AI_CALL_SUFFIXES: Dict[Tuple[str, ...], str] = {
    ("responses", "parse"): "responses.parse",
    ("responses", "create"): "responses.create",
    ("chat", "completions", "parse"): "chat.completions.parse",
    ("chat", "completions", "create"): "chat.completions.create",
    ("images", "generate"): "images.generate",
    ("images", "edit"): "images.edit",
    ("parse_structured",): "responses.parse",
    ("parse_structured_or_raise",): "responses.parse",
}

TRANSPORT_MODULE = "model_calls.py"
"""The module whose whole job is making the call, rather than being a step.

Its `responses.parse` belongs to no phase — every phase's call reaches the wire
through it — so counting it would leave the coverage check demanding a step in
`spec.py` for the transport layer, and the figures drawing a node for it.
"""

# String literals in these calls are plumbing (dict lookups, separators), not
# prompt text, so they are dropped when a prompt template is reconstructed.
NON_PROMPT_CALLS = {
    "get",
    "join",
    "strip",
    "rstrip",
    "lstrip",
    "replace",
    "split",
    "startswith",
    "endswith",
    "encode",
    "decode",
    "setdefault",
    "pop",
    "getenv",
    "format",
    "lower",
    "upper",
    "title",
}

# Calls whose string arguments are console output or separators, never prompt.
CONSOLE_CALLS = {"print", "warn", "ValueError", "RuntimeError", "TypeError", "KeyError"}
SEPARATOR_CALLS = {"join"}
CONSOLE_ATTRS = {"info", "debug", "warning", "error", "exception", "write"}

PROMPT_FUNCTION_RE = re.compile(r"(^|_)prompt(s)?($|_)", re.IGNORECASE)
PROMPT_CONSTANT_RE = re.compile(r"(PROMPT|INSTRUCTIONS|SYSTEM)$")


@dataclass
class AiCall:
    """One outbound model call found in the source."""

    script: str
    function: str
    lineno: int
    method: str
    model_expr: Optional[str] = None
    model_value: Optional[str] = None
    reasoning_expr: Optional[str] = None
    reasoning_value: Optional[str] = None
    schema: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    model_source: str = "call site"

    def to_json(self) -> Dict[str, Any]:
        return {
            "script": self.script,
            "function": self.function,
            "lineno": self.lineno,
            "method": self.method,
            "model_expr": self.model_expr,
            "model_value": self.model_value,
            "model_source": self.model_source,
            "reasoning_expr": self.reasoning_expr,
            "reasoning_value": self.reasoning_value,
            "schema": self.schema,
            "roles": self.roles,
        }


@dataclass
class PromptSegment:
    """A run of literal prompt text plus the branches that guard it."""

    text: str
    conditions: List[str]
    lineno: int

    def to_json(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "conditions": self.conditions,
            "lineno": self.lineno,
        }


@dataclass
class PromptSource:
    """A prompt builder function or module-level prompt constant."""

    script: str
    symbol: str
    lineno: int
    kind: str
    docstring: Optional[str]
    segments: List[PromptSegment]
    signature: Optional[str] = None

    @property
    def text(self) -> str:
        return "\n".join(segment.text for segment in self.segments)

    def to_json(self) -> Dict[str, Any]:
        return {
            "script": self.script,
            "symbol": self.symbol,
            "lineno": self.lineno,
            "kind": self.kind,
            "docstring": self.docstring,
            "signature": self.signature,
            "segments": [segment.to_json() for segment in self.segments],
        }


@dataclass
class SchemaField:
    name: str
    annotation: str
    default: Optional[str]
    description: Optional[str]

    def to_json(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "annotation": self.annotation,
            "default": self.default,
            "description": self.description,
        }


@dataclass
class Schema:
    """A structured-output model a phase asks the API to fill in."""

    name: str
    script: str
    lineno: int
    bases: List[str]
    docstring: Optional[str]
    fields: List[SchemaField]

    def to_json(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "script": self.script,
            "lineno": self.lineno,
            "bases": self.bases,
            "docstring": self.docstring,
            "fields": [item.to_json() for item in self.fields],
        }


@dataclass
class CliFlag:
    script: str
    flags: List[str]
    help: Optional[str]
    default: Optional[str]
    action: Optional[str]

    def to_json(self) -> Dict[str, Any]:
        return {
            "script": self.script,
            "flags": self.flags,
            "help": self.help,
            "default": self.default,
            "action": self.action,
        }


@dataclass
class FunctionFacts:
    name: str
    lineno: int
    end_lineno: int
    docstring: Optional[str]
    signature: str


@dataclass
class ScriptFacts:
    """Everything statically known about a single generation script."""

    name: str
    path: Path
    docstring: Optional[str]
    fingerprint: str
    line_count: int
    constants: Dict[str, str]
    functions: Dict[str, FunctionFacts]
    ai_calls: List[AiCall]
    prompts: Dict[str, PromptSource]
    schemas: Dict[str, Schema]
    cli_flags: List[CliFlag]


@dataclass
class Codebase:
    """The union of all scanned scripts, with cross-script lookups."""

    scripts: Dict[str, ScriptFacts]

    def schema(self, name: str) -> Optional[Schema]:
        for facts in self.scripts.values():
            if name in facts.schemas:
                return facts.schemas[name]
        return None

    def prompt(self, script: str, symbol: str) -> Optional[PromptSource]:
        facts = self.scripts.get(script)
        if facts is None:
            return None
        return facts.prompts.get(symbol)

    def all_ai_calls(self) -> List[AiCall]:
        calls: List[AiCall] = []
        for facts in self.scripts.values():
            calls.extend(facts.ai_calls)
        return calls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unparse(node: Optional[ast.AST]) -> Optional[str]:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive, unparse is total in 3.10+
        return None


def _attribute_path(node: ast.AST) -> Tuple[str, ...]:
    """Return the dotted path of an attribute chain, outermost last."""
    parts: List[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    parts.reverse()
    return tuple(parts)


def _keyword(call: ast.Call, name: str) -> Optional[ast.AST]:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _string_value(node: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _module_constants(tree: ast.Module) -> Dict[str, str]:
    """Collect module-level `NAME = <expr>` assignments as source text."""
    constants: Dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets: Sequence[ast.expr]
        if isinstance(node, ast.Assign):
            targets = node.targets
        else:
            targets = [node.target]
        value = node.value
        if value is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                rendered = _unparse(value)
                if rendered is not None:
                    constants[target.id] = rendered
    return constants


def _resolve_constant(
    expr: Optional[str],
    constants: Dict[str, str],
    shared: Dict[str, str],
    depth: int = 0,
) -> Optional[str]:
    """Follow `A = B = os.getenv("X", "default")` chains down to a literal.

    The generators layer their model configuration—`PHASE1_REASONING_EFFORT =
    DEFAULT_REASONING_EFFORT` in the script, `DEFAULT_REASONING_EFFORT =
    os.getenv(...)` in `config.py`—so a single hop is never enough.
    """
    if expr is None or depth > 6:
        return None
    expr = expr.strip()
    if expr.startswith(("'", '"')) and expr.endswith(("'", '"')) and len(expr) >= 2:
        return expr[1:-1]
    getenv = re.match(r"os\.getenv\(\s*['\"]([^'\"]+)['\"]\s*,\s*(.+)\)\s*$", expr)
    if getenv:
        fallback = _resolve_constant(getenv.group(2), constants, shared, depth + 1)
        if fallback is not None:
            return f"{fallback} (env {getenv.group(1)})"
        return None
    if expr in constants:
        return _resolve_constant(constants[expr], constants, shared, depth + 1)
    if expr in shared:
        return _resolve_constant(shared[expr], constants, shared, depth + 1)
    return None


def _parameter_defaults(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Dict[str, str]:
    """Map parameter name -> default expression source.

    Every phase takes its model and reasoning effort as a parameter defaulting
    to the module constant, so without this hop the extracted model for each
    call site is the useless string "model".
    """
    defaults: Dict[str, str] = {}
    args = node.args
    positional = args.posonlyargs + args.args
    for parameter, default in zip(
        positional[len(positional) - len(args.defaults) :], args.defaults
    ):
        rendered = _unparse(default)
        if rendered is not None:
            defaults[parameter.arg] = rendered
    for parameter, kw_default in zip(args.kwonlyargs, args.kw_defaults):
        if kw_default is None:
            continue
        rendered = _unparse(kw_default)
        if rendered is not None:
            defaults[parameter.arg] = rendered
    return defaults


def _reasoning_effort_expr(node: Optional[ast.AST]) -> Optional[str]:
    """Pull the effort out of `reasoning={"effort": X}` or `reasoning_effort=X`.

    The two API surfaces spell the same setting differently — the responses API
    nests it in a dict, chat completions takes it flat — and a step documented
    as having no effort when it has one is the kind of drift this module exists
    to prevent, so the caller passes whichever keyword the call site used and
    both arrive here.

    Call sites that pass a typed `OpenAI` client wrap the dict in
    `cast(Any, ...)`, because the effort constants are plain strings read from
    the environment while the SDK expects a literal. Look through that wrapper
    so the report shows the effort rather than the cast.
    """
    if isinstance(node, ast.Call) and _unparse(node.func) == "cast" and node.args:
        node = node.args[-1]
    if not isinstance(node, ast.Dict):
        return _unparse(node)
    for key, value in zip(node.keys, node.values):
        if _string_value(key) == "effort":
            return _unparse(value)
    return _unparse(node)


def _input_roles(node: Optional[ast.AST]) -> List[str]:
    """List the message roles of an `input=[{"role": ...}]` argument."""
    roles: List[str] = []
    if not isinstance(node, ast.List):
        return roles
    for element in node.elts:
        if not isinstance(element, ast.Dict):
            continue
        for key, value in zip(element.keys, element.values):
            if _string_value(key) == "role":
                role = _string_value(value)
                if role:
                    roles.append(role)
    return roles


# ---------------------------------------------------------------------------
# Prompt template reconstruction
# ---------------------------------------------------------------------------


def _literal_strings(node: ast.AST) -> List[Tuple[int, int, str]]:
    """Collect prompt-ish string literals from an expression, in source order.

    f-strings keep their shape: `{expr}` marks where runtime data lands, which
    is exactly the distinction that makes a static template readable—the
    instructions are ours, the placeholders are the biography.
    """
    found: List[Tuple[int, int, str]] = []

    def add(node: ast.AST, text: str) -> None:
        if text:
            found.append(
                (getattr(node, "lineno", 0), getattr(node, "col_offset", 0), text)
            )

    def visit(current: ast.AST) -> None:
        if isinstance(current, ast.Call):
            func = current.func
            name = func.id if isinstance(func, ast.Name) else None
            if name in CONSOLE_CALLS:
                return  # progress output, not prompt text
            if isinstance(func, ast.Attribute):
                if func.attr in SEPARATOR_CALLS or func.attr in CONSOLE_ATTRS:
                    return  # `", ".join(...)`—the receiver is a separator
                if func.attr in NON_PROMPT_CALLS:
                    # Still descend into the receiver: `("a" + x).strip()` keeps "a".
                    visit(func.value)
                    return
        if isinstance(current, ast.Dict):
            # Message dicts are the one place a dict carries prompt text. Render
            # them with their role so a multi-message call reads in order
            # instead of collapsing to "rolesystemcontentYou are...".
            entries = {
                _string_value(key): value
                for key, value in zip(current.keys, current.values)
                if _string_value(key) is not None
            }
            if "content" in entries:
                role = _string_value(entries.get("role")) or "message"
                buffer: List[Tuple[int, int, str]] = []
                nested = _literal_strings(entries["content"])
                buffer.extend(nested)
                body = "".join(item[2] for item in buffer)
                add(current, f"\n<<{role}>>\n{body}")
                return
            for value in current.values:
                visit(value)
            return
        if isinstance(current, ast.JoinedStr):
            parts: List[str] = []
            for value in current.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                elif isinstance(value, ast.FormattedValue):
                    parts.append("{" + (_unparse(value.value) or "...") + "}")
            add(current, "".join(parts))
            return
        if isinstance(current, ast.Constant) and isinstance(current.value, str):
            add(current, current.value)
            return
        for child in ast.iter_child_nodes(current):
            visit(child)

    visit(node)
    found.sort(key=lambda item: (item[0], item[1]))
    return found


def _statement_text(stmt: ast.stmt) -> Optional[str]:
    """Render the prompt text a single statement contributes, if any."""
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
        return None  # bare docstring / stray literal
    pieces = _literal_strings(stmt)
    if not pieces:
        return None
    text = "".join(piece[2] for piece in pieces)
    # Separator-only fragments ("\n", "=" * 60 operands) add noise, not meaning.
    if not text.strip(" \n\t=-*_"):
        return None
    return text


def _walk_prompt_body(
    body: Iterable[ast.stmt], conditions: List[str], out: List[PromptSegment]
) -> None:
    for stmt in body:
        if isinstance(stmt, (ast.Raise, ast.Assert, ast.Import, ast.ImportFrom)):
            continue  # error text and imports are never prompt content
        if isinstance(stmt, ast.If):
            test = _unparse(stmt.test) or "?"
            _walk_prompt_body(stmt.body, conditions + [f"if {test}"], out)
            if stmt.orelse:
                _walk_prompt_body(stmt.orelse, conditions + [f"if not ({test})"], out)
            continue
        if isinstance(stmt, (ast.For, ast.AsyncFor)):
            target = _unparse(stmt.target) or "item"
            iterable = _unparse(stmt.iter) or "..."
            _walk_prompt_body(
                stmt.body, conditions + [f"for {target} in {iterable}"], out
            )
            _walk_prompt_body(stmt.orelse, conditions, out)
            continue
        if isinstance(stmt, ast.While):
            _walk_prompt_body(
                stmt.body, conditions + [f"while {_unparse(stmt.test)}"], out
            )
            continue
        if isinstance(stmt, (ast.Try, ast.With, ast.AsyncWith)):
            _walk_prompt_body(stmt.body, conditions, out)
            for handler in getattr(stmt, "handlers", []):
                _walk_prompt_body(handler.body, conditions, out)
            _walk_prompt_body(getattr(stmt, "orelse", []), conditions, out)
            _walk_prompt_body(getattr(stmt, "finalbody", []), conditions, out)
            continue
        text = _statement_text(stmt)
        if text is not None:
            out.append(
                PromptSegment(
                    text=text, conditions=list(conditions), lineno=stmt.lineno
                )
            )


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = _unparse(node.args) or ""
    returns = _unparse(node.returns)
    suffix = f" -> {returns}" if returns else ""
    return f"{node.name}({args}){suffix}"


def _is_prompt_function(name: str) -> bool:
    return bool(PROMPT_FUNCTION_RE.search(name))


def _extract_prompt_function(
    script: str, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> PromptSource:
    body = list(node.body)
    docstring = ast.get_docstring(node)
    if docstring and body and isinstance(body[0], ast.Expr):
        body = body[1:]
    segments: List[PromptSegment] = []
    _walk_prompt_body(body, [], segments)
    return PromptSource(
        script=script,
        symbol=node.name,
        lineno=node.lineno,
        kind="function",
        docstring=docstring,
        segments=segments,
        signature=_function_signature(node),
    )


# ---------------------------------------------------------------------------
# Schema and CLI extraction
# ---------------------------------------------------------------------------


def _field_description(value: Optional[ast.AST]) -> Tuple[Optional[str], Optional[str]]:
    """Return (default, description) for a Pydantic field assignment."""
    if value is None:
        return None, None
    if isinstance(value, ast.Call):
        func_name = value.func.id if isinstance(value.func, ast.Name) else None
        if func_name == "Field":
            default = _unparse(value.args[0]) if value.args else None
            description = None
            for keyword in value.keywords:
                if keyword.arg == "description":
                    description = _string_value(keyword.value) or _unparse(
                        keyword.value
                    )
                elif keyword.arg == "default" and default is None:
                    default = _unparse(keyword.value)
            return default, description
    return _unparse(value), None


def _extract_schema(script: str, node: ast.ClassDef) -> Schema:
    fields: List[SchemaField] = []
    for stmt in node.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue
        default, description = _field_description(stmt.value)
        fields.append(
            SchemaField(
                name=stmt.target.id,
                annotation=_unparse(stmt.annotation) or "Any",
                default=default,
                description=description,
            )
        )
    return Schema(
        name=node.name,
        script=script,
        lineno=node.lineno,
        bases=[_unparse(base) or "?" for base in node.bases],
        docstring=ast.get_docstring(node),
        fields=fields,
    )


def _extract_cli_flag(script: str, call: ast.Call) -> Optional[CliFlag]:
    flags = [_string_value(arg) for arg in call.args]
    named = [flag for flag in flags if flag and flag.startswith("-")]
    positional = [flag for flag in flags if flag and not flag.startswith("-")]
    if not named and not positional:
        return None
    help_node = _keyword(call, "help")
    default_node = _keyword(call, "default")
    action_node = _keyword(call, "action")
    return CliFlag(
        script=script,
        flags=named or positional,
        help=_string_value(help_node) or _unparse(help_node),
        default=_unparse(default_node),
        action=_string_value(action_node),
    )


# ---------------------------------------------------------------------------
# Per-script scan
# ---------------------------------------------------------------------------


def scan_script(path: Path, shared_constants: Dict[str, str]) -> ScriptFacts:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    name = path.name
    constants = _module_constants(tree)

    functions: Dict[str, FunctionFacts] = {}
    prompts: Dict[str, PromptSource] = {}
    schemas: Dict[str, Schema] = {}
    ai_calls: List[AiCall] = []
    cli_flags: List[CliFlag] = []

    # Module-level prompt constants (e.g. STYLE_TRANSFER_PROMPT).
    for constant_name, expr in constants.items():
        if not PROMPT_CONSTANT_RE.search(constant_name):
            continue
        literal = expr.strip()
        if literal.startswith(("'", '"')):
            prompts[constant_name] = PromptSource(
                script=name,
                symbol=constant_name,
                lineno=0,
                kind="constant",
                docstring=None,
                segments=[
                    PromptSegment(
                        text=ast.literal_eval(literal), conditions=[], lineno=0
                    )
                ],
            )

    class Visitor(ast.NodeVisitor):
        """Single pass that records which function each construct sits in."""

        def __init__(self) -> None:
            self.stack: List[str] = []
            self.defaults: List[Dict[str, str]] = []

        @property
        def scope(self) -> str:
            return ".".join(self.stack) if self.stack else "<module>"

        def resolve(self, expr: Optional[str]) -> Optional[str]:
            """Resolve through enclosing parameter defaults, then constants."""
            if expr is None:
                return None
            seen = 0
            current = expr
            while seen < 4:
                direct = _resolve_constant(current, constants, shared_constants)
                if direct is not None:
                    return direct
                replacement = None
                for scope_defaults in reversed(self.defaults):
                    if current in scope_defaults:
                        replacement = scope_defaults[current]
                        break
                if replacement is None or replacement == current:
                    return None
                current = replacement
                seen += 1
            return None

        def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            qualified = ".".join(self.stack + [node.name])
            functions[qualified] = FunctionFacts(
                name=qualified,
                lineno=node.lineno,
                end_lineno=node.end_lineno or node.lineno,
                docstring=ast.get_docstring(node),
                signature=_function_signature(node),
            )
            before = len(ai_calls)
            self.stack.append(node.name)
            self.defaults.append(_parameter_defaults(node))
            self.generic_visit(node)
            self.defaults.pop()
            self.stack.pop()
            # Named builders are prompts by convention; so is any function that
            # calls the API directly, because several phases assemble their
            # instructions inline at the call site instead of in a builder.
            calls_api_here = any(
                call.function == qualified for call in ai_calls[before:]
            )
            if _is_prompt_function(node.name) or calls_api_here:
                prompts[node.name] = _extract_prompt_function(name, node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_function(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            bases = {_unparse(base) for base in node.bases}
            if bases & {"BaseModel"} or any(
                base and base.endswith("BaseModel") for base in bases if base
            ):
                schemas[node.name] = _extract_schema(name, node)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node: ast.Call) -> None:
            path_parts = _attribute_path(node.func)
            for suffix, label in AI_CALL_SUFFIXES.items():
                if (
                    len(path_parts) >= len(suffix)
                    and tuple(path_parts[-len(suffix) :]) == suffix
                ):
                    model_expr = _unparse(_keyword(node, "model"))
                    reasoning_expr = _reasoning_effort_expr(
                        _keyword(node, "reasoning")
                        or _keyword(node, "reasoning_effort")
                    )
                    schema_node = _keyword(node, "text_format") or _keyword(
                        node, "response_format"
                    )
                    ai_calls.append(
                        AiCall(
                            script=name,
                            function=self.scope,
                            lineno=node.lineno,
                            method=label,
                            model_expr=model_expr,
                            model_value=self.resolve(model_expr),
                            reasoning_expr=reasoning_expr,
                            reasoning_value=self.resolve(reasoning_expr),
                            schema=_unparse(schema_node),
                            roles=_input_roles(_keyword(node, "input")),
                        )
                    )
                    break
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
            ):
                flag = _extract_cli_flag(name, node)
                if flag is not None:
                    cli_flags.append(flag)
            self.generic_visit(node)

    Visitor().visit(tree)

    # Phases take `model` as a plain parameter with no default—the value is
    # whatever the entry point passed. Falling back to the script's own
    # `--model` default is what makes the chart show a real model name instead
    # of the word "model", and the source is labeled so the distinction stays
    # visible.
    cli_model_default = None
    for flag in cli_flags:
        if "--model" in flag.flags:
            cli_model_default = _resolve_constant(
                flag.default, constants, shared_constants
            )
            break
    if cli_model_default:
        for call in ai_calls:
            if call.model_value is None:
                call.model_value = cli_model_default
                call.model_source = "--model default"

    return ScriptFacts(
        name=name,
        path=path,
        docstring=ast.get_docstring(tree),
        fingerprint=hashlib.sha256(source.encode("utf-8")).hexdigest()[:16],
        line_count=source.count("\n") + 1,
        constants=constants,
        functions=functions,
        ai_calls=ai_calls,
        prompts=prompts,
        schemas=schemas,
        cli_flags=cli_flags,
    )


def scan_codebase(scripts_dir: Path = SCRIPTS_DIR) -> Codebase:
    """Scan every generation script plus `scripts/utils`."""
    shared: Dict[str, str] = {}
    config_path = scripts_dir / "config.py"
    if config_path.exists():
        shared = _module_constants(ast.parse(config_path.read_text(encoding="utf-8")))

    paths = sorted(scripts_dir.glob("*.py")) + sorted(
        (scripts_dir / "utils").glob("*.py")
    )
    scripts: Dict[str, ScriptFacts] = {}
    for path in paths:
        if path.name == "__init__.py" or "pipeline_docs" in path.parts:
            continue
        facts = scan_script(path, shared)
        if path.name == TRANSPORT_MODULE:
            facts.ai_calls.clear()
        scripts[path.name] = facts
    return Codebase(scripts=scripts)
