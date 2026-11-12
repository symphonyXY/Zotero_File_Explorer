"""Conservative suffix recognition, independently implemented from observed formats."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import SUPPORTED, AttachmentState, Record

# Exact terminal tokens only. Never match a title merely containing 'dual'.
PRODUCT = re.compile(
    r"^(?P<base>.+?)[.\-](?P<type>(?:LR_|TB_)?dual|mono|mono-cut|dual-cut|crop-compare|single-compare|compare|cut)\.pdf$",
    re.IGNORECASE,
)
PREFIX = re.compile(r"^[a-f0-9]{10}-", re.IGNORECASE)
TITLE_MARKER = re.compile(r"(?:pdf2zh|pdf2zh_next|babeldoc|双语对照|译文|翻译结果)", re.IGNORECASE)


@dataclass
class FilterRule:
    name: str
    pattern: str
    state: str = "translated"
    target: str = "filename"
    enabled: bool = True

    def validate(self) -> None:
        if self.state not in {"original", "translated", "review"}:
            raise ValueError("Invalid rule state")
        if self.target not in {"filename", "title"} or not 0 < len(self.pattern) <= 256:
            raise ValueError("Invalid rule target or pattern")

    def matches(self, item: Record) -> bool:
        self.validate()
        return self.enabled and fnmatch.fnmatchcase(
            getattr(item, self.target).casefold(), self.pattern.casefold()
        )


def default_rules() -> list[dict]:
    # Built-in source-verified detection is separate and cannot accidentally be deleted.
    return []


def classify(
    item: Record, siblings: list[Record], rules: list[dict] | None = None, manual: str = ""
) -> tuple[str, str]:
    filename = (
        Path(item.path).name
        if item.path and not item.path.startswith(("storage:", "attachments:"))
        else item.filename
    )
    filename = filename or item.filename
    if Path(filename).suffix.casefold() not in SUPPORTED or item.link_mode == "linked_url":
        return AttachmentState.EXCLUDED, "unsupported_type"
    if manual in {"original", "translated", "review"}:
        return manual, "manual"
    for raw in rules or []:
        rule = FilterRule(**raw)
        if rule.matches(item):
            return rule.state, "rule:" + rule.name
    match = PRODUCT.fullmatch(filename)
    title_evidence = bool(TITLE_MARKER.search(item.title))
    if match:
        base = match["base"]
        stripped = PREFIX.sub("", base)
        sibling_match = any(
            s.key != item.key and Path(s.filename).stem.casefold() in {base.casefold(), stripped.casefold()}
            for s in siblings
        )
        # Dot separators are the verified pdf2zh_next terminal format. Legacy hyphen
        # suffixes also occur in real paper names; require corroboration for those.
        token = match["type"]
        separator = filename[len(base)]
        if sibling_match or title_evidence or (separator == "." and token.casefold() != "cut"):
            return AttachmentState.TRANSLATED, "pdf2zh_suffix:" + token.lower()
        return AttachmentState.REVIEW, "ambiguous_suffix:" + token.lower()
    if title_evidence:
        return AttachmentState.REVIEW, "translation_title"
    return AttachmentState.ORIGINAL, "supported_no_product_marker"


def rule_to_dict(rule: FilterRule) -> dict:
    rule.validate()
    return asdict(rule)
