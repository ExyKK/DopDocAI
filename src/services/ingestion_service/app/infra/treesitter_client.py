from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import deque

from tree_sitter import Language, Parser

# import grammars you need here
import tree_sitter_go
# import tree_sitter_html
# import tree_sitter_json
# import tree_sitter_typescript
# import tree_sitter_toml
# import tree_sitter_yaml

# import tree_sitter_dockerfile
# import tree_sitter_markdown
# import tree_sitter_css


class TreeSitterManager:
    """Manager for tree-sitter languages and parsing.

    Responsibilities:
    - Build a language registry mapping canonical keys to Language objects.
    - Maintain a Parser cache (one Parser per language key).
    - Provide extraction helpers like extract_functions_or_blocks(text, file_path).

    The manager is conservative: for languages that don't have "function" nodes it
    returns an empty list so callers can fall back to file-level chunking.
    """

    def __init__(self):
        # build the language registry (key -> Language)
        self._language_registry: Dict[str, Language] = {
            "go": Language(tree_sitter_go.language()),
            # "html": Language(tree_sitter_html.language()),
            # "json": Language(tree_sitter_json.language()),
            # "typescript": Language(tree_sitter_typescript.language()), # fix no language() in ts library
            # "toml": Language(tree_sitter_toml.language()),
            # "yaml": Language(tree_sitter_yaml.language()),
            # "dockerfile": Language(tree_sitter_dockerfile.language()),
            # "markdown": Language(tree_sitter_markdown.language()),
            # "css": Language(tree_sitter_css.language()),
        }

        # extension -> key mapping
        self._ext_to_key: Dict[str, str] = {
            ".go": "go",
            ".html": "html",
            ".htm": "html",
            ".json": "json",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".toml": "toml",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".markdown": "markdown",
            ".css": "css",
        }

        # node types to search by language key
        # Extend this dictionary if you want to support more node names
        self._node_selection: Dict[str, Tuple[str, ...]] = {
            "go": ("function_declaration", "method_declaration"),
            "ts": ("function_declaration", "method_definition", "method_signature"),
            "tsx": ("function_declaration", "method_definition", "method_signature"),
            # others intentionally empty -> fallback to chunking
            "html": tuple(),
            "json": tuple(),
            "toml": tuple(),
            "yaml": tuple(),
            "md": tuple(),
            "css": tuple(),
            "dockerfile": tuple(),
        }

        # parser cache
        self._parsers: Dict[str, Parser] = {}

    def _key_for_path(self, path: Path) -> Optional[str]:
        """Return registry key for given path (handles special names like Dockerfile)."""
        # exact name matches
        name = path.name
        if name == "Dockerfile":
            return "dockerfile"
        ext = path.suffix.lower()
        return self._ext_to_key.get(ext)

    def get_parser_for_path(self, path: Path) -> Optional[Parser]:
        key = self._key_for_path(path)
        if not key:
            return None
        lang = self._language_registry.get(key)
        if not lang:
            return None
        parser = self._parsers.get(key)
        if parser is None:
            parser = Parser(lang)
            self._parsers[key] = parser
        return parser

    # ------------------ Go-specific extractor ------------------
    def extract_go_entities(self, text: str, path: Path) -> Dict[str, Any]:
        """
        Parse Go source and return a dict with keys:
          - 'package': package_name or None
          - 'imports': list of import paths
          - 'entities': list of dicts {kind, name, start, end, src}
        """
        parser = self.get_parser_for_path(path)
        if not parser:
            return {"package": None, "imports": [], "entities": []}

        btext = text.encode("utf8")
        try:
            tree = parser.parse(btext)
        except Exception:
            return {"package": None, "imports": [], "entities": []}
        root = tree.root_node

        package_name = None
        imports: List[str] = []
        entities: List[Dict[str, Any]] = []

        # helper to decode bytes slice
        def decode_slice(s: int, e: int) -> str:
            try:
                return btext[s:e].decode("utf8", errors="replace")
            except Exception:
                return ""

        # 1) extract package and imports (top-level)
        for child in root.children:
            # package_clause -> contains identifier node with package name
            if child.type == "package_clause":
                for gc in child.children:
                    if gc.type == "package_identifier":
                        package_name = decode_slice(gc.start_byte, gc.end_byte)
                        break
            # import_declaration -> collect import_spec(s)
            elif child.type == "import_declaration":
                for gc in child.children:
                    if gc.type in ("import_spec_list", "import_spec"):
                        for spec in gc.children:
                            if spec.type == "import_spec":
                                # import_spec may have string_literal or interpreted_string_literal
                                for s_ch in spec.children:
                                    if s_ch.type in ("interpreted_string_literal", "string_literal"):
                                        # remove quotes
                                        val = decode_slice(s_ch.start_byte, s_ch.end_byte)
                                        val = val.strip('`"')
                                        imports.append(val)
                            elif spec.type in ("string_literal", "interpreted_string_literal"):
                                val = decode_slice(spec.start_byte, spec.end_byte).strip('`"')
                                imports.append(val)

        # 2) traverse AST for entities (functions, methods, types)
        dq = deque([root])
        while dq:
            n = dq.popleft()

            # functions / methods
            if n.type in ("function_declaration", "method_declaration"):
                start, end = n.start_point.row + 1, n.end_point.row + 1
                name = None
                # find identifier for name
                for c in n.children:
                    if c.type in ("field_identifier", "identifier"):
                        name = decode_slice(c.start_byte, c.end_byte)
                        break

                src = decode_slice(n.start_byte, n.end_byte)
                entities.append({
                    "kind": "method" if n.type == "method_declaration" else "function",
                    "name": name,
                    "start": start,
                    "end": end,
                    "src": src,
                })

            # type declarations (structs, interfaces, aliases)
            elif n.type == "type_declaration":
                # iterate children to find type_spec nodes
                for ts in n.children:
                    if ts.type == "type_spec":
                        # type_spec children include 'type' and name identifier
                        type_name = None
                        type_kind = "type"
                        for c in ts.children:
                            if c.type in ("type_identifier", "type_name", "identifier"):
                                # name of the type (varies by grammar)
                                type_name = decode_slice(c.start_byte, c.end_byte)
                                # continue searching for the actual type node
                            if c.type in ("struct_type", "interface_type"):
                                if c.type == "struct_type":
                                    type_kind = "struct"
                                elif c.type == "interface_type":
                                    type_kind = "interface"
                                # src for the whole type_spec:
                                start, end = ts.start_point.row + 1, ts.end_point.row + 1
                                src = decode_slice(ts.start_byte, ts.end_byte)
                                entities.append({
                                    "kind": type_kind,
                                    "name": type_name,
                                    "start": start,
                                    "end": end,
                                    "src": src,
                                })
                                break
                        # if no struct/interface matched, still record the type_spec as generic
                        else:
                            start, end = ts.start_point.row + 1, ts.end_point.row + 1
                            src = decode_slice(ts.start_byte, ts.end_byte)
                            entities.append({
                                "kind": "type",
                                "name": type_name,
                                "start": start,
                                "end": end,
                                "src": src,
                            })

            else:
                # continue traversal
                dq.extend(n.children)

        return {"package": package_name, "imports": imports, "entities": entities}

    def extract_functions_or_blocks(self, text: str, path: Path) -> List[Tuple[int, int, Optional[str], str]]:
        """Return list of (start_byte, end_byte, name_or_None, source_text).

        For languages with function-like nodes, returns those nodes. For others returns []
        (caller should fall back to file-level chunking).
        """
        parser = self.get_parser_for_path(path)
        if not parser:
            return []
        try:
            # keep the bytes we pass to parser so byte offsets align
            btext = text.encode("utf8")
            tree = parser.parse(bytes(text, "utf8"))
        except Exception:
            return []
        root = tree.root_node

        key = self._key_for_path(path)
        node_types = self._node_selection.get(key, tuple())
        if not node_types:
            return []

        results: List[Tuple[int, int, Optional[str], str]] = []
        dq = deque([root])
        # common child node types that can hold names in various grammars:
        name_node_types = ("identifier", "name", "property_identifier", "field_identifier", "field_name")

        while dq:
            n = dq.popleft()
            if n.type in node_types:
                start, end = n.start_byte, n.end_byte
                # look for a name-ish child (search deeper if needed)
                name = None

                # first try direct children
                for c in n.children:
                    if c.type in name_node_types:
                        try:
                            # slice from the bytes, then decode to str
                            name = btext[c.start_byte:c.end_byte].decode("utf8", errors="replace")
                        except Exception:
                            name = None
                        break

                # as fallback, search grandchildren (some grammars nest the identifier)
                if name is None:
                    # shallow BFS limited depth 2
                    for c in n.children:
                        for gc in c.children:
                            if gc.type in name_node_types:
                                try:
                                    name = btext[gc.start_byte:gc.end_byte].decode("utf8", errors="replace")
                                except Exception:
                                    name = None
                                break
                        if name:
                            break

                try:
                    src = btext[start:end].decode("utf8", errors="replace")
                except Exception:
                    src = ""
                results.append((start, end, name, src))
            else:
                dq.extend(n.children)
        return results

    # convenience helper for callers that only have extension string
    def extract_by_extension(self, text: str, extension: str) -> List[Tuple[int, int, Optional[str], str]]:
        fake_path = Path(f"/tmp/file{extension}")
        return self.extract_functions_or_blocks(text, fake_path)

