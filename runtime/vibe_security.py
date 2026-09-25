"""Runtime-assisted candidate classifier for security-sensitive task surfaces.

This module intentionally emits candidates, not a final security decision. The agent
must confirm or override the classification in structured security evidence.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from vibe_contracts import stamp_artifact

MAX_CLASSIFIER_FILES = 50
MAX_CLASSIFIER_BYTES = 65536

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


def _matches(text: str, patterns: Sequence[str]) -> List[str]:
    lowered = text.lower()
    return [pattern for pattern in patterns if re.search(pattern, lowered, flags=re.I)]


def classify_security_candidates(
    root: Path,
    *,
    request: str = "",
    files: Optional[Sequence[str]] = None,
    framework_routes: Optional[Sequence[Dict[str, object]]] = None,
) -> Dict[str, object]:
    normalized_files = []
    for value in files or []:
        relative = Path(str(value)).as_posix()
        if relative not in normalized_files:
            normalized_files.append(relative)
        if len(normalized_files) >= MAX_CLASSIFIER_FILES:
            break

    evidence: Dict[str, List[Dict[str, object]]] = {}
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
        path = root / relative
        try:
            text = path.read_bytes()[:MAX_CLASSIFIER_BYTES].decode("utf-8", errors="replace")
        except OSError:
            continue
        for surface, patterns in RULES.items():
            hits = _matches(text, patterns)
            if hits:
                evidence.setdefault(surface, []).append({
                    "source": "content",
                    "file": relative,
                    "matches": hits[:6],
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
        "limits": {
            "max_files": MAX_CLASSIFIER_FILES,
            "max_bytes_per_file": MAX_CLASSIFIER_BYTES,
        },
        "authority": {
            "level": "advisory",
            "note": "Runtime candidates assist review; the agent must make and record the final security classification.",
        },
    }
    return stamp_artifact("security-candidates", data)
