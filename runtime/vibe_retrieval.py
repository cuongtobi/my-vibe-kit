"""Unicode-aware bounded retrieval helpers for my-vibe-kit."""

import ast
import re
import unicodedata
from collections import Counter, deque
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

SEARCH_TEXT_LIMIT = 262144
SEARCH_TERM_LIMIT = 192
SEARCH_SYMBOL_LIMIT = 64

SEARCH_STOP_WORDS = {
    "and", "async", "await", "bool", "break", "case", "catch", "class", "const",
    "continue", "def", "default", "delete", "do", "else", "enum", "export", "extends",
    "false", "finally", "float", "for", "from", "func", "function", "if", "implements",
    "import", "in", "instanceof", "int", "interface", "let", "match", "module", "new",
    "none", "null", "package", "pass", "private", "protected", "public", "raise", "return",
    "self", "static", "str", "struct", "super", "switch", "this", "throw", "trait", "true",
    "try", "type", "use", "var", "void", "while", "with", "yield",
}

QUERY_STOP_WORDS = {
    "add", "build", "change", "create", "fix", "implement", "refactor", "the", "this", "that",
    "with", "from", "into", "for", "and", "use", "using", "feature", "bug", "project", "task",
    "new", "them", "sua", "tao", "cap", "nhat", "voi", "cho", "cua", "trong", "khi", "mot",
}

# Small deterministic bridge between common Vietnamese task wording and code identifiers.
# Projects can extend this through context.query_aliases in .vibe/config.json.
VIETNAMESE_QUERY_ALIASES = {
    "dang nhap": ["login", "auth", "authentication", "session"],
    "dang xuat": ["logout", "signout", "session"],
    "het han": ["expire", "expired", "expiry", "expiration"],
    "lam moi": ["refresh", "renew", "rotate"],
    "mat khau": ["password", "credential"],
    "nguoi dung": ["user", "account"],
    "phan quyen": ["permission", "authorization", "authorize", "role"],
    "xac thuc": ["auth", "authentication", "verify"],
    "phien": ["session"],
    "ma thong bao": ["token"],
    "don hang": ["order"],
    "gio hang": ["cart"],
    "thanh toan": ["payment", "checkout"],
    "co so du lieu": ["database", "db", "repository"],
    "bo nho dem": ["cache"],
    "hang doi": ["queue"],
    "kiem thu": ["test", "testing"],
    "kiem tra": ["check", "validate", "validation"],
    "loi": ["error", "failure", "bug"],
    "ngoai le": ["exception"],
    "tep": ["file"],
    "thu muc": ["directory", "folder"],
    "duong dan": ["path", "route"],
    "api": ["api", "endpoint", "route"],
}


def fold_text(value: str) -> str:
    """Case-fold Unicode and add an accent-insensitive comparison form."""
    value = unicodedata.normalize("NFKC", value or "").casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _append_token(out: List[str], seen: Set[str], value: str) -> None:
    value = value.strip("_$")
    if len(value) < 2 or value in seen:
        return
    seen.add(value)
    out.append(value)


def identifier_parts(value: str) -> List[str]:
    """Split ASCII/code and Unicode identifiers without dropping diacritics."""
    normalized = unicodedata.normalize("NFKC", value or "")
    out: List[str] = []
    seen: Set[str] = set()
    for raw in re.findall(r"[^\W\d_][\w$]*|\d+", normalized, flags=re.UNICODE):
        raw = raw.strip("$")
        if not raw:
            continue
        lowered = raw.casefold()
        _append_token(out, seen, lowered)
        folded = fold_text(lowered)
        _append_token(out, seen, folded)

        # Preserve camel/Pascal splitting used for code identifiers.
        for piece in re.findall(r"[A-Z]+(?=[A-Z][a-z]|\b)|[A-Z]?[a-z]+|[0-9]+", raw):
            lowered_piece = piece.casefold()
            _append_token(out, seen, lowered_piece)
            _append_token(out, seen, fold_text(lowered_piece))
    return out


def search_tokens_from_text(text: str, limit: int = SEARCH_TERM_LIMIT) -> List[str]:
    counts: Counter = Counter()
    for identifier in re.findall(r"[^\W\d_][\w$]{1,}", text or "", flags=re.UNICODE):
        for token in identifier_parts(identifier):
            if token not in SEARCH_STOP_WORDS:
                counts[token] += 1
    return [
        token
        for token, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def source_symbols(path: Path, text: str) -> List[str]:
    symbols: List[str] = []
    if path.suffix.lower() == ".py":
        try:
            tree = ast.parse(text, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols.append(node.name)
        except SyntaxError:
            pass
    else:
        ident = r"[^\W\d_][\w]*"
        patterns = [
            rf"\b(?:class|interface|trait|enum|struct|module|type)\s+({ident})",
            rf"\b(?:def|fn|func|function)\s+({ident}[!?=]?)",
            r"\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*(?:=|:)",
        ]
        for pattern in patterns:
            symbols.extend(re.findall(pattern, text or "", flags=re.UNICODE))

    unique: List[str] = []
    seen: Set[str] = set()
    for symbol in symbols:
        if symbol not in seen:
            seen.add(symbol)
            unique.append(symbol)
        if len(unique) >= SEARCH_SYMBOL_LIMIT:
            break
    return unique


def source_search_metadata(path: Path) -> Dict[str, object]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(SEARCH_TEXT_LIMIT)
    except OSError:
        return {"symbols": [], "search_terms": []}
    return {
        "symbols": source_symbols(path, text),
        "search_terms": search_tokens_from_text(text),
    }


def query_profile(value: str, custom_aliases: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    normalized = re.sub(r"\s+", " ", fold_text(value or "")).strip()
    tokens: List[str] = []
    seen: Set[str] = set()
    for token in identifier_parts(value or ""):
        folded = fold_text(token)
        if token not in QUERY_STOP_WORDS and folded not in QUERY_STOP_WORDS:
            _append_token(tokens, seen, token)
            _append_token(tokens, seen, folded)

    aliases: Dict[str, Sequence[str]] = dict(VIETNAMESE_QUERY_ALIASES)
    for key, raw_values in (custom_aliases or {}).items():
        if isinstance(raw_values, str):
            values = [raw_values]
        elif isinstance(raw_values, list):
            values = [str(item) for item in raw_values if isinstance(item, str)]
        else:
            continue
        aliases[fold_text(str(key))] = values

    expansions: Dict[str, List[str]] = {}
    padded = " " + normalized + " "
    for phrase, values in aliases.items():
        phrase_folded = re.sub(r"\s+", " ", fold_text(phrase)).strip()
        if not phrase_folded or (" " + phrase_folded + " ") not in padded:
            continue
        expanded: List[str] = []
        for value_item in values:
            for token in identifier_parts(value_item):
                folded = fold_text(token)
                if folded in QUERY_STOP_WORDS:
                    continue
                _append_token(tokens, seen, token)
                _append_token(tokens, seen, folded)
                if token not in expanded:
                    expanded.append(token)
        if expanded:
            expansions[phrase] = expanded

    return {
        "normalized": normalized,
        "tokens": tokens,
        "expansions": expansions,
    }


def path_score(path: str, tokens: Sequence[str]) -> int:
    lowered = fold_text(path)
    stem = fold_text(Path(path).stem)
    score = 0
    for token in tokens:
        folded = fold_text(token)
        if folded == stem:
            score += 6
        elif folded and folded in stem:
            score += 4
        elif folded and folded in lowered:
            score += 2
    return score


def indexed_relevance(path: str, record: object, tokens: Sequence[str]) -> Dict[str, object]:
    item = record if isinstance(record, dict) else {}
    symbols = [str(value) for value in (item.get("symbols") or [])]
    search_terms = {fold_text(str(value)) for value in (item.get("search_terms") or [])}
    symbol_parts: Set[str] = set()
    for symbol in symbols:
        symbol_parts.update(fold_text(value) for value in identifier_parts(symbol))

    folded_tokens = {fold_text(value) for value in tokens if value}
    symbol_matches = sorted(folded_tokens & symbol_parts)
    content_matches = sorted(folded_tokens & search_terms)
    pscore = path_score(path, tokens)
    score = pscore + (10 * len(symbol_matches)) + (3 * len(content_matches))
    return {
        "path": path,
        "score": score,
        "path_score": pscore,
        "symbol_matches": symbol_matches,
        "content_matches": content_matches,
    }


def bounded_reverse_dependencies(
    seeds: Sequence[str],
    reverse: Dict[str, Sequence[str]],
    depth: int,
) -> List[str]:
    queue = deque((seed, 0) for seed in seeds)
    seen = set(seeds)
    result: Set[str] = set()
    while queue:
        node, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for parent in reverse.get(node, []):
            if parent in seen:
                continue
            seen.add(parent)
            result.add(parent)
            queue.append((parent, current_depth + 1))
    return sorted(result)


def bounded_dependencies(
    seeds: Sequence[str],
    dependencies: Dict[str, Sequence[str]],
    depth: int,
) -> List[str]:
    queue = deque((seed, 0) for seed in seeds)
    seen = set(seeds)
    result: Set[str] = set()
    while queue:
        node, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for child in dependencies.get(node, []):
            if child in seen:
                continue
            seen.add(child)
            result.add(child)
            queue.append((child, current_depth + 1))
    return sorted(result)


def fallback_content_scan(
    root: Path,
    source_paths: Sequence[str],
    tokens: Sequence[str],
    *,
    max_scan_files: int,
    read_limit: int,
    max_results: int = 10,
) -> Dict[str, object]:
    folded_tokens = {fold_text(token) for token in tokens if len(fold_text(token)) >= 2}
    if not folded_tokens:
        return {"matches": [], "scanned_files": 0, "truncated": False}

    ordered = sorted(
        source_paths,
        key=lambda path: (-path_score(path, tokens), path),
    )
    limited = ordered[:max_scan_files]
    matches: List[Dict[str, object]] = []
    for relative in limited:
        path = root / relative
        try:
            with path.open("rb") as handle:
                text = handle.read(read_limit).decode("utf-8", errors="replace")
        except OSError:
            continue
        text_tokens = {
            fold_text(token)
            for identifier in re.findall(r"[^\W\d_][\w$]{1,}", text, flags=re.UNICODE)
            for token in identifier_parts(identifier)
        }
        hits = sorted(folded_tokens & text_tokens)
        if not hits:
            continue
        matches.append(
            {
                "path": relative,
                "score": (3 * len(hits)) + path_score(relative, tokens),
                "content_matches": hits,
                "reason": "fallback-content-scan",
            }
        )

    matches.sort(key=lambda item: (-int(item["score"]), str(item["path"])))
    return {
        "matches": matches[:max_results],
        "scanned_files": len(limited),
        "truncated": len(ordered) > len(limited),
    }


def build_relevant_payload(
    root: Path,
    *,
    graph: Dict[str, object],
    context: Dict[str, object],
    file_index: Dict[str, object],
    query: str,
    targets: Optional[Sequence[str]],
    changed_files: Sequence[str],
    depth: int,
    max_source: int,
    max_tests: int,
    max_modules: int,
    min_index_score: int,
    fallback_max_scan_files: int,
    fallback_read_bytes: int,
    custom_aliases: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    nodes = [str(item) for item in (graph.get("nodes") or [])]
    node_set = set(nodes)
    test_files = set(str(item) for item in (context.get("test_files") or []))
    selected = [
        Path(item).as_posix() for item in (targets or []) if Path(item).as_posix() in node_set
    ]
    explicit_target_valid = bool(targets) and bool(selected)

    profile = query_profile(query, custom_aliases)
    tokens = list(profile["tokens"])
    changed = set(changed_files)
    retrieval: List[Dict[str, object]] = []
    fallback = {
        "used": False,
        "reason": None,
        "scanned_files": 0,
        "truncated": False,
        "matches": [],
    }

    if not selected and tokens:
        ranked: List[Dict[str, object]] = []
        for path in nodes:
            if path in test_files:
                continue
            evidence = indexed_relevance(path, file_index.get(path), tokens)
            if path in changed:
                evidence["score"] = int(evidence["score"]) + 1
                evidence["changed_file_bonus"] = 1
            if int(evidence["score"]) > 0:
                ranked.append(evidence)
        ranked.sort(key=lambda item: (-int(item["score"]), str(item["path"])))
        retrieval = ranked[:10]
        top_score = int(ranked[0]["score"]) if ranked else 0

        if top_score >= min_index_score:
            selected = [str(item["path"]) for item in ranked[:3]]
        else:
            fallback_result = fallback_content_scan(
                root,
                [path for path in nodes if path not in test_files],
                tokens,
                max_scan_files=fallback_max_scan_files,
                read_limit=fallback_read_bytes,
            )
            fallback = {
                "used": True,
                "reason": "indexed-score-below-threshold",
                **fallback_result,
            }
            if fallback_result["matches"]:
                retrieval = list(fallback_result["matches"])
                selected = [str(item["path"]) for item in fallback_result["matches"][:3]]
            elif ranked:
                # Preserve weak evidence for inspection, but do not silently treat it as confident.
                selected = [str(ranked[0]["path"])]
    elif not selected:
        selected = [path for path in sorted(changed) if path in node_set]

    if explicit_target_valid:
        retrieval = [
            {
                "path": path,
                "score": None,
                "reason": "explicit-target",
                "symbol_matches": [],
                "content_matches": [],
            }
            for path in selected
        ]

    dependencies = graph.get("dependencies") or {}
    reverse = graph.get("reverse_dependencies") or {}
    forward = bounded_dependencies(selected, dependencies, depth)
    consumers = bounded_reverse_dependencies(selected, reverse, depth)
    ordered: List[str] = []
    for path in list(selected) + forward + consumers:
        if path not in ordered:
            ordered.append(path)

    source_files = [path for path in ordered if path not in test_files][:max_source]
    impacted = set(source_files) | set(selected)
    related_tests: List[str] = []
    for test in sorted(test_files):
        deps = set(dependencies.get(test, []))
        score = path_score(test, tokens)
        if test in impacted or deps & impacted or score > 0:
            related_tests.append(test)
    related_tests = related_tests[:max_tests]

    modules: List[str] = []
    for path in source_files:
        parts = Path(path).parts
        if not parts:
            continue
        if parts[0] in {"src", "app", "lib", "internal", "packages", "apps"} and len(parts) > 1:
            module = "/".join(parts[:2])
        else:
            module = parts[0]
        if module not in modules:
            modules.append(module)
        if len(modules) >= max_modules:
            break

    top_score = 0
    if retrieval and isinstance(retrieval[0].get("score"), int):
        top_score = int(retrieval[0]["score"])
    if explicit_target_valid:
        confidence = "explicit"
    elif fallback["used"] and fallback["matches"]:
        confidence = "medium"
    elif top_score >= max(min_index_score * 2, min_index_score + 6):
        confidence = "high"
    elif top_score >= min_index_score:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "query": query,
        "query_normalized": profile["normalized"],
        "query_tokens": tokens,
        "query_expansions": profile["expansions"],
        "targets": selected,
        "retrieval_mode": "explicit-target" if explicit_target_valid else (
            "fallback-content-scan" if fallback["used"] and fallback["matches"] else "indexed-symbol-content"
        ),
        "retrieval_confidence": confidence,
        "retrieval_evidence": retrieval,
        "fallback": fallback,
        "needs_scoped_search": confidence == "low" or bool(fallback.get("truncated")),
        "source_files": source_files,
        "test_files": related_tests,
        "related_modules": modules,
        "dependency_depth": depth,
        "dependency_authority": graph.get("authority"),
        "limits": {
            "max_source_files": max_source,
            "max_test_files": max_tests,
            "max_related_modules": max_modules,
            "fallback_max_scan_files": fallback_max_scan_files,
            "fallback_read_bytes": fallback_read_bytes,
        },
    }
