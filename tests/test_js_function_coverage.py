"""Static analysis: verify all onclick/hx-on JS functions are defined in the correct page scripts."""

import ast
import os
import re
import pytest


def _extract_routes_file():
    routes_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "admin", "routes.py"
    )
    with open(routes_path) as f:
        return f.read(), routes_path


def _extract_websocket_js():
    js_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "admin", "static", "websocket.js"
    )
    with open(js_path) as f:
        return f.read()


def _find_all_js_functions(script_text: str) -> set[str]:
    pattern = r"(?:function\s+(\w+)\s*\(|window\.(\w+)\s*=\s*(?:function|async))"
    return {m.group(1) or m.group(2) for m in re.finditer(pattern, script_text)}


def _find_all_js_arrow_functions(script_text: str) -> set[str]:
    pattern = r"(?:(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>|window\.(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>)"
    return {m.group(1) or m.group(2) for m in re.finditer(pattern, script_text)}


def _find_onclick_handlers(html_text: str) -> list[str]:
    pattern = r'onclick="([^"]*)"'
    results = []
    for m in re.finditer(pattern, html_text):
        for call in re.findall(r"(\w+)\s*\(", m.group(1)):
            if call not in ("if", "event", "confirm", "alert", "setTimeout"):
                results.append(call)
    return results


def _find_hxon_handlers(html_text: str) -> list[str]:
    pattern = r'hx-on:\w+="([^"]*)"'
    results = []
    for m in re.finditer(pattern, html_text):
        snippet = m.group(1)
        for call in re.findall(r"(\w+)\s*\(", snippet):
            if call not in ("if", "event", "confirm", "alert"):
                results.append(call)
    return results


def _find_inline_js_calls(html_text: str) -> list[str]:
    pattern = r'on(?:keypress|keyup|keydown|change|click|submit|focus|blur)="([^"]*)"'
    results = []
    for m in re.finditer(pattern, html_text):
        for call in re.findall(r"(\w+)\s*\(", m.group(1)):
            if call not in (
                "if",
                "event",
                "confirm",
                "alert",
                "setTimeout",
                "parseInt",
            ):
                results.append(call)
    return results


def _extract_functions_from_text(text: str) -> set[str]:
    """Extract JS function names from a text block."""
    funcs = set()
    if "function " in text:
        funcs |= _find_all_js_functions(text)
        funcs |= _find_all_js_arrow_functions(text)
    return funcs


def _get_all_script_content(routes_source: str) -> set[str]:
    """Extract JS function names from all script= assignments (triple-quoted strings)."""
    functions = set()
    for sm in re.finditer(r'(\w+)\s*=\s*f?"""', routes_source):
        var_name = sm.group(1)
        if var_name not in ("script", "js"):
            continue
        open_quote = sm.end()
        rest = routes_source[open_quote:]
        close_quote = rest.find('"""')
        if close_quote == -1:
            continue
        var_content = rest[:close_quote]
        functions |= _extract_functions_from_text(var_content)
    return functions


def _get_all_paren_script_content(routes_source: str) -> set[str]:
    """Extract JS function names from script = (\"\"\"...\"\"\" + ... + \"\"\"...\"\"\") patterns."""
    functions = set()
    for sm in re.finditer(r"script\s*=\s*\(", routes_source):
        start = sm.end()
        depth = 1
        i = start
        while i < len(routes_source) and depth > 0:
            c = routes_source[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            i += 1
        block = routes_source[start : i - 1]
        for qm in re.finditer(r'"""(.*?)"""', block, re.DOTALL):
            functions |= _extract_functions_from_text(qm.group(1))
    return functions


def _get_all_script_tag_content(routes_source: str) -> set[str]:
    """Extract JS function names from <script> tags embedded in HTML templates."""
    functions = set()
    for sm in re.finditer(r"<script[^>]*>(.*?)</script>", routes_source, re.DOTALL):
        content = sm.group(1).strip()
        functions |= _extract_functions_from_text(content)
    return functions


JS_BUILTIN = {
    "if",
    "event",
    "confirm",
    "alert",
    "setTimeout",
    "parseInt",
    "parseFloat",
    "Number",
    "String",
    "Boolean",
    "isNaN",
    "encodeURIComponent",
    "decodeURIComponent",
    "JSON",
    "htmx",
    "stopPropagation",
    "str",
    "lower",
    "remove",
    "document",
    "window",
    "console",
    "Math",
    "Date",
    "Array",
    "Object",
    "RegExp",
    "Error",
    "setTimeout",
    "setInterval",
    "clearInterval",
    "clearTimeout",
    "fetch",
    "navigator",
    "localStorage",
    "sessionStorage",
    "toLowerCase",
    "toUpperCase",
    "trim",
    "includes",
    "indexOf",
    "charAt",
    "substring",
    "slice",
    "split",
    "join",
    "replace",
    "forEach",
    "map",
    "filter",
    "find",
    "findIndex",
    "reduce",
    "push",
    "pop",
    "shift",
    "length",
    "querySelectorAll",
    "querySelector",
    "getElementById",
    "classList",
    "getAttribute",
    "setAttribute",
    "addEventListener",
    "removeEventListener",
    "preventDefault",
    "appendChild",
    "innerHTML",
    "textContent",
    "value",
    "style",
    "display",
    "focus",
    "blur",
    "createElement",
    "log",
    "warn",
    "error",
    "stringify",
    "parse",
    "keys",
    "entries",
    "assign",
    "headers",
    "status",
    "json",
    "then",
    "catch",
    "finally",
    "async",
    "await",
    "return",
    "true",
    "false",
    "null",
    "undefined",
    "this",
    "self",
    "parent",
    "top",
    "frames",
    "history",
    "location",
    "open",
    "close",
    "setTimeout",
    "prompt",
    "type",
    "target",
    "currentTarget",
    "checked",
    "disabled",
    "options",
    "selectedIndex",
    "href",
    "src",
    "alt",
    "title",
    "id",
    "name",
    "className",
    "children",
    "parentNode",
    "nextSibling",
    "previousSibling",
    "firstChild",
    "lastChild",
    "nodeType",
    "nodeName",
    "nodeValue",
    "hasOwnProperty",
    "toString",
    "valueOf",
    "prototype",
    "constructor",
    "call",
    "apply",
    "bind",
    "arguments",
    "callee",
    "caller",
    "new",
    "delete",
    "void",
    "typeof",
    "instanceof",
    "in",
    "of",
    "for",
    "while",
    "do",
    "switch",
    "case",
    "break",
    "continue",
    "default",
    "else",
    "try",
    "catch",
    "throw",
    "class",
    "extends",
    "super",
    "import",
    "export",
    "from",
    "as",
    "with",
    "yield",
    "const",
    "let",
    "var",
    "function",
    "Arrow",
    "arrow",
}


def _get_all_defined_functions(routes_source: str) -> set[str]:
    """Get ALL JS function names from every source: script= blocks, script=(...), script tags, websocket.js."""
    ws_js = _extract_websocket_js()
    ws_functions = _find_all_js_functions(ws_js) | _find_all_js_arrow_functions(ws_js)
    return (
        ws_functions
        | _get_all_script_content(routes_source)
        | _get_all_paren_script_content(routes_source)
        | _get_all_script_tag_content(routes_source)
    )


def test_websocket_js_loads():
    """websocket.js must define error reporting functions."""
    js = _extract_websocket_js()
    assert len(js) > 100, "websocket.js appears empty"
    functions = _find_all_js_functions(js)
    assert "reportFrontendError" in functions, (
        "websocket.js missing reportFrontendError function"
    )
    assert "reportFetchError" in functions, (
        "websocket.js missing reportFetchError function"
    )


def test_no_missing_onclick_functions():
    """Every onclick/hx-on handler in routes.py must be defined in a script block or websocket.js."""
    routes_source, _ = _extract_routes_file()
    all_defined = _get_all_defined_functions(routes_source)

    onclick_calls = _find_onclick_handlers(routes_source)
    hxon_calls = _find_hxon_handlers(routes_source)
    inline_calls = _find_inline_js_calls(routes_source)
    all_calls = set(onclick_calls + hxon_calls + inline_calls)

    missing = sorted(all_calls - all_defined - JS_BUILTIN)

    assert not missing, (
        f"JS functions called in routes.py but not defined in any script block or websocket.js: {missing}"
    )


def test_dashboard_and_tenants_have_all_tenant_functions():
    """Dashboard and Tenants page scripts must define functions needed by their fragments."""
    routes_source, _ = _extract_routes_file()
    all_defined = _get_all_defined_functions(routes_source)

    required = {
        "hideTenantActionsModal",
        "showTenantActions",
        "handleAction",
        "handleDelete",
        "addWebhook",
        "toggleTenantPanel",
        "toggleEnabled",
        "syncContacts",
        "syncMessages",
        "sendMsgAsTenant",
        "selectContact",
    }
    missing = sorted(required - all_defined)
    assert not missing, (
        f"Functions needed by Dashboard/Tenants fragments but not defined in any script: {missing}"
    )


def test_tenant_details_has_selectContact():
    """Tenant Details page must define selectContact for the contacts fragment."""
    routes_source, _ = _extract_routes_file()
    all_defined = _get_all_defined_functions(routes_source)
    assert "selectContact" in all_defined, (
        "selectContact not defined in any script block or <script> tag"
    )


def test_no_dynamic_tailwind_classes_in_routes():
    """Catch f-string interpolated Tailwind classes that won't work with CDN JIT."""
    routes_source, _ = _extract_routes_file()
    dynamic_class_pattern = r"text-\{[^}]+\}-\d+|bg-\{[^}]+\}-\d+|border-\{[^}]+\}-\d+"
    matches = list(re.finditer(dynamic_class_pattern, routes_source))

    if matches:
        lines = [
            f"  line {m.start()}: ...{routes_source[max(0, m.start() - 20) : m.end() + 20]}..."
            for m in matches
        ]
        pytest.fail(
            f"Found {len(matches)} dynamic Tailwind class(es) that won't work with CDN:\n"
            + "\n".join(lines)
        )
