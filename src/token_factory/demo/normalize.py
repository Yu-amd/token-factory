"""Normalize Semantic Router labels ↔ Token Factory use-case ids."""

from __future__ import annotations

# Bidirectional aliases between SR domain/category labels and catalog use-case ids.
# Prefer soft eligibility: classification PASS when labels share an equivalence class.
SR_USE_CASE_ALIASES: dict[str, set[str]] = {
    "coding-assistant": {
        "coding-assistant",
        "coding",
        "code",
        "computer science",
        "computer_science",
        "computerscience",
        "coding_route",
        "code-completion",
        "code-generation",
        "code-review",
    },
    "code-completion": {
        "code-completion",
        "coding",
        "computer science",
        "coding-assistant",
        "coding_route",
    },
    "complex-reasoning": {
        "complex-reasoning",
        "general-reasoning",
        "reasoning",
        "math",
        "physics",
        "chemistry",
        "engineering",
        "mathematical-reasoning",
        "scientific-reasoning",
        "reasoning_route",
    },
    "general-reasoning": {
        "general-reasoning",
        "complex-reasoning",
        "reasoning",
        "math",
        "physics",
        "engineering",
        "reasoning_route",
    },
    "enterprise-chat": {
        "enterprise-chat",
        "simple-chat",
        "general",
        "business",
        "other",
        "general_route",
        "knowledge-assistant",
    },
    "simple-chat": {
        "simple-chat",
        "enterprise-chat",
        "general",
        "business",
        "other",
        "general_route",
    },
    "batch-summarization": {
        "batch-summarization",
        "summarization",
        "offline-document-batch",
        "document-analysis",
        "general",
        "business",
    },
    "summarization": {
        "summarization",
        "batch-summarization",
        "document-analysis",
        "general",
    },
    "rag-simple": {
        "rag-simple",
        "rag-complex",
        "long-context-rag",
        "document-analysis",
        "knowledge-assistant",
        "general",
    },
    "rag-complex": {
        "rag-complex",
        "rag-simple",
        "long-context-rag",
        "document-analysis",
        "knowledge-assistant",
    },
    "classification": {
        "classification",
        "extraction",
        "structured-generation",
        "general",
        "business",
    },
    "extraction": {
        "extraction",
        "classification",
        "structured-generation",
        "general",
    },
    "vlm": {
        "vlm",
        "image-understanding",
        "document-vision",
        "multimodal",
        "multimodal-agent",
        "vision",
    },
    "image-understanding": {
        "image-understanding",
        "vlm",
        "document-vision",
        "multimodal",
        "vision",
    },
    "multimodal-agent": {
        "multimodal-agent",
        "vlm",
        "image-understanding",
        "multimodal",
        "vision",
    },
    "tool-use-agent": {
        "tool-use-agent",
        "enterprise-agent",
        "multi-step-agent",
        "software-engineering-agent",
        "workflow-automation",
        "computer science",
        "general",
    },
    "domain-specific-assistant": {
        "domain-specific-assistant",
        "enterprise-chat",
        "simple-chat",
        "general",
        "business",
        "other",
        "general_route",
    },
}


def _canon(label: str | None) -> str:
    if not label:
        return ""
    return str(label).strip().lower().replace("_", "-").replace("  ", " ")


def normalize_label(label: str | None) -> str:
    """Normalize a classification or use-case label for comparison."""
    return _canon(label)


def equivalence_set(use_case_or_label: str | None) -> set[str]:
    """Return the set of labels considered equivalent for soft classification match."""
    key = _canon(use_case_or_label)
    if not key:
        return set()
    for canonical, aliases in SR_USE_CASE_ALIASES.items():
        if key == canonical or key in {_canon(a) for a in aliases}:
            return {_canon(a) for a in aliases} | {canonical}
    # Unknown label: match only itself (and spaced/underscored variants)
    return {key, key.replace("-", " "), key.replace(" ", "-")}


def classification_matches(expected: str | None, actual: str | None) -> bool:
    """Soft match: expected use-case vs SR category / routing decision / domain."""
    if not expected:
        return True
    if not actual:
        return False
    exp_set = equivalence_set(expected)
    act = _canon(actual)
    act_set = equivalence_set(actual)
    return bool(exp_set & act_set) or act in exp_set


def compute_family_of(compute_id: str | None, family: str | None = None) -> str | None:
    """Map compute id / family string to instinct|epyc|radeon."""
    if family:
        f = _canon(family)
        if f in ("instinct", "epyc", "radeon"):
            return f
    cid = (compute_id or "").upper()
    if cid.startswith("MI") or "INSTINCT" in cid:
        return "instinct"
    if cid.startswith("EPYC") or "CPU" in cid:
        return "epyc"
    if cid.startswith(("R", "W")) and any(x in cid for x in ("9700", "7900", "RADEON")):
        return "radeon"
    if cid.startswith("R") or cid.startswith("W"):
        return "radeon"
    return family


def normalize_compute_family(value: str | None) -> str | None:
    if not value:
        return None
    v = _canon(value)
    if v in ("instinct", "gpu", "mi300x", "mi325x", "mi350x", "mi355x", "mi350p", "mi250x"):
        return "instinct"
    if v in ("epyc", "cpu"):
        return "epyc"
    if v in ("radeon", "local", "workstation", "r9700", "w7900"):
        return "radeon"
    return v
