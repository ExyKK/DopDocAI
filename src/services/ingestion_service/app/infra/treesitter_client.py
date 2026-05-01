import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import tree_sitter_go
from tree_sitter import Language, Node, Parser


@dataclass(frozen=True)
class GoImportSpec:
    path: str
    name: str | None
    is_dot: bool
    is_blank: bool


@dataclass(frozen=True)
class GoReceiver:
    text: str
    type_text: str
    base_type: str
    is_pointer: bool


@dataclass(frozen=True)
class GoSymbol:
    symbol_id: str
    kind: str
    name: str
    qualified_name: str
    package: str | None
    signature: str
    doc_comment: str | None
    type_parameters: str | None
    receiver: GoReceiver | None
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    exported: bool
    is_alias: bool
    source: str


@dataclass(frozen=True)
class GoFileAnalysis:
    path: str
    package: str | None
    imports: tuple[GoImportSpec, ...]
    symbols: tuple[GoSymbol, ...]
    parse_error: bool
    is_generated: bool
    is_test: bool
    is_vendor: bool


class TreeSitterManager:
    def __init__(self) -> None:
        self._go_language = Language(tree_sitter_go.language())
        self._go_parser = Parser(self._go_language)

    def extract_go_file(self, text: str, path: str | Path) -> GoFileAnalysis:
        normalized_path = self._normalize_path(path)
        source_bytes = text.encode("utf-8")
        tree = self._go_parser.parse(source_bytes)
        if tree is None:
            raise RuntimeError("tree-sitter did not return a parse tree for Go source.")

        root = tree.root_node
        lines = text.splitlines()
        package_name: str | None = None
        imports: list[GoImportSpec] = []
        symbols: list[GoSymbol] = []

        for node in root.named_children:
            if node.type == "package_clause":
                package_name = _node_text(source_bytes, _first_named_child(node)) or None
            elif node.type == "import_declaration":
                imports.extend(_extract_import_specs(node, source_bytes))
            elif node.type == "function_declaration":
                symbol = _extract_function_symbol(node, source_bytes, lines, normalized_path, package_name)
                if symbol is not None:
                    symbols.append(symbol)
            elif node.type == "method_declaration":
                symbol = _extract_method_symbol(node, source_bytes, lines, normalized_path, package_name)
                if symbol is not None:
                    symbols.append(symbol)
            elif node.type == "type_declaration":
                symbols.extend(_extract_type_symbols(node, source_bytes, lines, normalized_path, package_name))

        symbols.sort(key=lambda item: (item.start_line, item.end_line, item.kind, item.qualified_name))
        return GoFileAnalysis(
            path=normalized_path,
            package=package_name,
            imports=tuple(imports),
            symbols=tuple(symbols),
            parse_error=root.has_error,
            is_generated=_is_generated(normalized_path, source_bytes),
            is_test=_is_test(normalized_path),
            is_vendor=_is_vendor(normalized_path),
        )

    def extract_go_entities(self, text: str, path: Path) -> dict[str, object]:
        parsed = self.extract_go_file(text, path)
        return {
            "package": parsed.package,
            "imports": [spec.path for spec in parsed.imports],
            "entities": [
                {
                    "kind": symbol.kind,
                    "name": symbol.name,
                    "start": symbol.start_line,
                    "end": symbol.end_line,
                    "src": symbol.source,
                }
                for symbol in parsed.symbols
            ],
        }

    def extract_functions_or_blocks(self, text: str, path: Path) -> list[tuple[int, int, str | None, str]]:
        if path.suffix.lower() != ".go":
            return []

        parsed = self.extract_go_file(text, path)
        return [
            (symbol.start_byte, symbol.end_byte, symbol.name, symbol.source)
            for symbol in parsed.symbols
            if symbol.kind in {"function", "method"}
        ]

    def extract_by_extension(self, text: str, extension: str) -> list[tuple[int, int, str | None, str]]:
        fake_path = Path(f"/tmp/file{extension}")
        return self.extract_functions_or_blocks(text, fake_path)

    @staticmethod
    def _normalize_path(path: str | Path) -> str:
        if isinstance(path, Path):
            return str(PurePosixPath(path.as_posix()))

        return str(PurePosixPath(path))


def _extract_import_specs(node: Node, source_bytes: bytes) -> list[GoImportSpec]:
    imports: list[GoImportSpec] = []

    def visit(candidate: Node) -> None:
        if candidate.type == "import_spec":
            name_node = candidate.child_by_field_name("name")
            path_node = candidate.child_by_field_name("path")
            import_path = _unquote_go_string(_node_text(source_bytes, path_node))
            import_name = _node_text(source_bytes, name_node) or None
            imports.append(
                GoImportSpec(
                    path=import_path,
                    name=import_name,
                    is_dot=import_name == ".",
                    is_blank=import_name == "_",
                )
            )
            return

        for child in candidate.named_children:
            visit(child)

    visit(node)
    return imports


def _extract_function_symbol(
    node: Node,
    source_bytes: bytes,
    lines: list[str],
    file_path: str,
    package_name: str | None,
) -> GoSymbol | None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None

    name = _node_text(source_bytes, name_node)
    type_params = _node_text(source_bytes, node.child_by_field_name("type_parameters")) or None
    parameters = _node_text(source_bytes, node.child_by_field_name("parameters"))
    result = _node_text(source_bytes, node.child_by_field_name("result"))
    signature = _collapse_whitespace(
        f"func {name}{type_params or ''}{parameters}{(' ' + result) if result else ''}"
    )

    return _build_symbol(
        source_bytes=source_bytes,
        lines=lines,
        file_path=file_path,
        package_name=package_name,
        kind="function",
        name=name,
        qualified_name=_qualified_name(package_name, name),
        signature=signature,
        type_parameters=type_params,
        receiver=None,
        declaration_node=node,
        is_alias=False,
    )


def _extract_method_symbol(
    node: Node,
    source_bytes: bytes,
    lines: list[str],
    file_path: str,
    package_name: str | None,
) -> GoSymbol | None:
    name_node = node.child_by_field_name("name")
    receiver_node = node.child_by_field_name("receiver")
    if name_node is None or receiver_node is None:
        return None

    receiver = _extract_receiver(receiver_node, source_bytes)
    if receiver is None:
        return None

    name = _node_text(source_bytes, name_node)
    parameters = _node_text(source_bytes, node.child_by_field_name("parameters"))
    result = _node_text(source_bytes, node.child_by_field_name("result"))
    signature = _collapse_whitespace(
        f"func {receiver.text} {name}{parameters}{(' ' + result) if result else ''}"
    )

    return _build_symbol(
        source_bytes=source_bytes,
        lines=lines,
        file_path=file_path,
        package_name=package_name,
        kind="method",
        name=name,
        qualified_name=_qualified_name(package_name, f"{receiver.base_type}.{name}"),
        signature=signature,
        type_parameters=None,
        receiver=receiver,
        declaration_node=node,
        is_alias=False,
    )


def _extract_type_symbols(
    node: Node,
    source_bytes: bytes,
    lines: list[str],
    file_path: str,
    package_name: str | None,
) -> list[GoSymbol]:
    symbols: list[GoSymbol] = []

    for child in node.named_children:
        if child.type not in {"type_spec", "type_alias"}:
            continue

        name_node = child.child_by_field_name("name")
        type_node = child.child_by_field_name("type")
        if name_node is None or type_node is None:
            continue

        name = _node_text(source_bytes, name_node)
        type_params = _node_text(source_bytes, child.child_by_field_name("type_parameters")) or None
        is_alias = child.type == "type_alias"
        kind = _go_type_kind(type_node)
        signature = _build_type_signature(name, type_params, type_node, source_bytes, is_alias)

        symbol = _build_symbol(
            source_bytes=source_bytes,
            lines=lines,
            file_path=file_path,
            package_name=package_name,
            kind=kind,
            name=name,
            qualified_name=_qualified_name(package_name, name),
            signature=signature,
            type_parameters=type_params,
            receiver=None,
            declaration_node=child,
            is_alias=is_alias,
        )
        symbols.append(symbol)

    return symbols


def _build_symbol(
    *,
    source_bytes: bytes,
    lines: list[str],
    file_path: str,
    package_name: str | None,
    kind: str,
    name: str,
    qualified_name: str,
    signature: str,
    type_parameters: str | None,
    receiver: GoReceiver | None,
    declaration_node: Node,
    is_alias: bool,
) -> GoSymbol:
    start_line = declaration_node.start_point.row + 1
    end_line = declaration_node.end_point.row + 1
    doc_comment = _extract_doc_comment(lines, start_line)
    source = _node_text(source_bytes, declaration_node)
    symbol_id = _build_symbol_id(
        file_path=file_path,
        package_name=package_name,
        kind=kind,
        qualified_name=qualified_name,
        signature=signature,
    )

    return GoSymbol(
        symbol_id=symbol_id,
        kind=kind,
        name=name,
        qualified_name=qualified_name,
        package=package_name,
        signature=signature,
        doc_comment=doc_comment,
        type_parameters=type_parameters,
        receiver=receiver,
        start_line=start_line,
        end_line=end_line,
        start_byte=declaration_node.start_byte,
        end_byte=declaration_node.end_byte,
        exported=bool(name) and name[0].isupper(),
        is_alias=is_alias,
        source=source,
    )


def _extract_receiver(node: Node, source_bytes: bytes) -> GoReceiver | None:
    parameter_node = None
    for child in node.named_children:
        if child.type in {"parameter_declaration", "variadic_parameter_declaration"}:
            parameter_node = child
            break

    if parameter_node is None:
        return None

    type_node = parameter_node.child_by_field_name("type")
    if type_node is None:
        return None

    type_text = _collapse_whitespace(_node_text(source_bytes, type_node))
    base_type = _receiver_base_type(type_text)

    return GoReceiver(
        text=_collapse_whitespace(_node_text(source_bytes, node)),
        type_text=type_text,
        base_type=base_type,
        is_pointer=type_text.startswith("*"),
    )


def _build_type_signature(name: str, type_params: str | None, type_node: Node, source_bytes: bytes, is_alias: bool) -> str:
    type_text = _collapse_whitespace(_node_text(source_bytes, type_node))
    params = type_params or ""

    if is_alias:
        return _collapse_whitespace(f"type {name}{params} = {type_text}")
    if type_node.type == "struct_type":
        return _collapse_whitespace(f"type {name}{params} struct")
    if type_node.type == "interface_type":
        return _collapse_whitespace(f"type {name}{params} interface")

    return _collapse_whitespace(f"type {name}{params} {type_text}")


def _build_symbol_id(
    *,
    file_path: str,
    package_name: str | None,
    kind: str,
    qualified_name: str,
    signature: str,
) -> str:
    payload = json.dumps(
        {
            "file_path": file_path,
            "package": package_name,
            "kind": kind,
            "qualified_name": qualified_name,
            "signature": signature,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _qualified_name(package_name: str | None, local_name: str) -> str:
    if package_name:
        return f"{package_name}.{local_name}"

    return local_name


def _go_type_kind(type_node: Node) -> str:
    if type_node.type == "struct_type":
        return "struct"
    if type_node.type == "interface_type":
        return "interface"
    return "type"


def _extract_doc_comment(lines: list[str], start_line: int) -> str | None:
    if start_line <= 1:
        return None

    previous_index = start_line - 2
    if previous_index < 0:
        return None

    previous_line = lines[previous_index].strip()
    if not previous_line:
        return None

    if previous_line.startswith("//"):
        collected: list[str] = []
        cursor = previous_index
        while cursor >= 0:
            candidate = lines[cursor].strip()
            if not candidate.startswith("//"):
                break
            collected.append(candidate[2:].lstrip())
            cursor -= 1
        collected.reverse()
        return "\n".join(collected).strip() or None

    if previous_line.endswith("*/"):
        collected: list[str] = []
        cursor = previous_index
        while cursor >= 0:
            candidate = lines[cursor]
            collected.append(candidate)
            if "/*" in candidate:
                collected.reverse()
                return _normalize_block_comment(collected)
            cursor -= 1

    return None


def _normalize_block_comment(lines: list[str]) -> str | None:
    text = "\n".join(lines).strip()
    if text.startswith("/*"):
        text = text[2:]
    if text.endswith("*/"):
        text = text[:-2]

    normalized_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].lstrip()
        normalized_lines.append(stripped)

    normalized = "\n".join(normalized_lines).strip()
    return normalized or None


def _receiver_base_type(type_text: str) -> str:
    normalized = type_text.lstrip("*").strip()
    bracket_index = normalized.find("[")
    if bracket_index >= 0:
        normalized = normalized[:bracket_index]
    if "." in normalized:
        normalized = normalized.rsplit(".", 1)[-1]
    return normalized


def _unquote_go_string(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "`"}:
        return value[1:-1]
    return value


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def _node_text(source_bytes: bytes, node: Node | None) -> str:
    if node is None:
        return ""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _first_named_child(node: Node) -> Node | None:
    return node.named_children[0] if node.named_children else None


def _is_generated(path: str, raw: bytes) -> bool:
    name = PurePosixPath(path).name.lower()
    if name.endswith(".pb.go") or ".generated." in name or name.endswith("_generated.go") or name.endswith(".gen.go"):
        return True

    sample = raw[:4096].lower()
    return b"code generated" in sample or b"do not edit" in sample


def _is_test(path: str) -> bool:
    pure_path = PurePosixPath(path)
    name = pure_path.name.lower()
    parts = {part.lower() for part in pure_path.parts}
    if name.endswith("_test.go") or name.startswith("test_") or ".spec." in name or ".test." in name:
        return True

    return "test" in parts or "tests" in parts


def _is_vendor(path: str) -> bool:
    pure_path = PurePosixPath(path)
    parts = {part.lower() for part in pure_path.parts}
    return "vendor" in parts
