"""Runtime-assisted candidate classifier for security-sensitive task surfaces.

This module intentionally emits candidates, not a final security decision. The agent
must confirm or override the classification in structured security evidence.
"""

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from vibe_contracts import stamp_artifact

MAX_CLASSIFIER_FILES = 50
MAX_CLASSIFIER_BYTES = 65536
MAX_CLASSIFIER_DIFF_BYTES = 65536

RULES = {
    "authentication-authorization": [
        r"\bauth(?:entication|orization)?\b", r"\blogin\b", r"\blogout\b",
        r"\bpermission\b", r"\brole\b", r"\baccess[_ -]?control\b", r"\boauth\b",
    ],
    "session-token": [
        r"\bsession\b", r"\btoken\b", r"\bjwt\b", r"\brefresh[_ -]?token\b",
        r"\bcookie\b", r"\brevocation\b",
    ],
    "password-credential": [
        r"\bpassword\b", r"\bcredential\b", r"\bapi[_ -]?key\b", r"\bprivate[_ -]?key\b",
    ],
    "file-upload-filesystem": [
        r"\bupload\b", r"\bfilesystem\b", r"\bpath[_ -]?traversal\b",
        r"\bfilename\b", r"\bfile[_ -]?storage\b", r"\bsymlink\b",
    ],
    "database-query": [
        r"\bsql\b", r"\bdatabase\b", r"\bquery\b", r"\bexecute\s*\(",
        r"\braw[_ -]?query\b", r"\bmass[_ -]?assignment\b",
    ],
    "user-controlled-url": [
        r"\bssrf\b", r"\buser[_ -]?controlled[_ -]?url\b", r"\bredirect\b",
        r"\bfetch[_ -]?url\b", r"\bcallback[_ -]?url\b",
    ],
    "html-rendering": [
        r"dangerouslysetinnerhtml", r"\binnerhtml\b", r"\bmarkup\b",
        r"\btemplate[_ -]?injection\b", r"\bhtml[_ -]?render",
        r"\brender_template\s*\(", r"\bmark_safe\s*\(", r"\bhtml_safe\b",
        r"\bv-html\b", r"\{@html\b",
    ],
    "command-process": [
        r"\bsubprocess\b", r"\bos\.system\b", r"\bchild_process\b",
        r"\bshell\s*=\s*true\b", r"\bcommand[_ -]?execution\b",
    ],
    "payment": [
        r"\bpayment\b", r"\bcheckout\b", r"\bstripe\b", r"\bwebhook\b",
    ],
    "secrets": [
        r"\bsecret\b", r"\bcredentials?\b", r"\baccess[_ -]?key\b",
        r"\bclient[_ -]?secret\b",
    ],
}

PATH_HINTS = {
    "authentication-authorization": ("auth", "login", "permission", "policy"),
    "session-token": ("session", "token", "jwt", "cookie"),
    "password-credential": ("password", "credential"),
    "file-upload-filesystem": ("upload", "storage", "filesystem"),
    "database-query": ("repository", "database", "query", "sql"),
    "payment": ("payment", "checkout", "billing", "stripe"),
    "secrets": ("secret", "credential"),
}


def _safe_repo_relative(root: Path, value: object) -> Optional[str]:
    if not isinstance(value, str) or not value:
        return None
    base = root.resolve()
    candidate = (root / value).resolve()
    try:
        return candidate.relative_to(base).as_posix()
    except ValueError:
        return None


def _matches(text: str, patterns: Sequence[str]) -> List[str]:
    lowered = text.lower()
    return [pattern for pattern in patterns if re.search(pattern, lowered, flags=re.I)]


def _matched_symbols(text: str, patterns: Sequence[str]) -> List[str]:
    identifiers = sorted(set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", text)))
    return [value for value in identifiers if _matches(value, patterns)][:12]


def _git_diff_text(root: Path, relative: str) -> str:
    chunks = []
    for cached in (False, True):
        command = ["git", "diff", "--no-ext-diff", "--unified=0"]
        if cached:
            command.append("--cached")
        command.extend(["--", relative])
        try:
            proc = subprocess.run(
                command,
                cwd=str(root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0 and proc.stdout:
            chunks.append(proc.stdout)
    if not chunks:
        return ""
    raw = b"\n".join(chunks)[:MAX_CLASSIFIER_DIFF_BYTES]
    return raw.decode("utf-8", errors="replace")


def classify_security_candidates(
    root: Path,
    *,
    request: str = "",
    files: Optional[Sequence[str]] = None,
    framework_routes: Optional[Sequence[Dict[str, object]]] = None,
) -> Dict[str, object]:
    normalized_files = []
    for value in files or []:
        relative = _safe_repo_relative(root, value)
        if relative is None:
            continue
        if relative not in normalized_files:
            normalized_files.append(relative)
        if len(normalized_files) >= MAX_CLASSIFIER_FILES:
            break

    evidence: Dict[str, List[Dict[str, object]]] = {}
    truncated_files: List[str] = []
    for surface, patterns in RULES.items():
        request_hits = _matches(request, patterns)
        if request_hits:
            evidence.setdefault(surface, []).append({
                "source": "task-request",
                "matches": request_hits[:6],
            })

    for relative in normalized_files:
        path_text = relative.lower()
        for surface, hints in PATH_HINTS.items():
            hits = [hint for hint in hints if hint in path_text]
            if hits:
                evidence.setdefault(surface, []).append({
                    "source": "path",
                    "file": relative,
                    "matches": hits[:6],
                })
        diff_text = _git_diff_text(root, relative)
        if diff_text:
            for surface, patterns in RULES.items():
                diff_hits = _matches(diff_text, patterns)
                if diff_hits:
                    evidence.setdefault(surface, []).append({
                        "source": "diff",
                        "file": relative,
                        "matches": diff_hits[:6],
                    })

        path = root / relative
        try:
            raw = path.read_bytes()
            truncated = len(raw) > MAX_CLASSIFIER_BYTES
            if truncated:
                truncated_files.append(relative)
            text = raw[:MAX_CLASSIFIER_BYTES].decode("utf-8", errors="replace")
        except OSError:
            continue
        for surface, patterns in RULES.items():
            hits = _matches(text, patterns)
            if hits:
                evidence.setdefault(surface, []).append({
                    "source": "content",
                    "file": relative,
                    "matches": hits[:6],
                    "truncated": truncated,
                })
            symbols = _matched_symbols(text, patterns)
            if symbols:
                evidence.setdefault(surface, []).append({
                    "source": "symbol",
                    "file": relative,
                    "matches": symbols[:6],
                })

    file_set = set(normalized_files)
    for route in framework_routes or []:
        if not isinstance(route, dict):
            continue
        route_file = str(route.get("file") or "")
        if file_set and route_file not in file_set:
            continue
        route_text = "{} {}".format(route.get("method") or "", route.get("path") or "")
        for surface, patterns in RULES.items():
            hits = _matches(route_text, patterns)
            if hits:
                evidence.setdefault(surface, []).append({
                    "source": "framework-route",
                    "file": route_file,
                    "route": route.get("path"),
                    "matches": hits[:6],
                })

    surfaces = sorted(evidence)
    data = {
        "classification": "candidate-security-sensitive" if surfaces else "no-candidate",
        "surfaces": surfaces,
        "evidence": {key: value[:12] for key, value in sorted(evidence.items())},
        "files_considered": normalized_files,
        "files_truncated": sorted(set(truncated_files)),
        "limits": {
            "max_files": MAX_CLASSIFIER_FILES,
            "max_bytes_per_file": MAX_CLASSIFIER_BYTES,
            "max_diff_bytes_per_file": MAX_CLASSIFIER_DIFF_BYTES,
        },
        "authority": {
            "level": "advisory",
            "note": "Runtime candidates assist review; the agent must make and record the final security classification.",
        },
    }
    return stamp_artifact("security-candidates", data)
