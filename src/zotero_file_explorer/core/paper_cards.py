from dataclasses import dataclass
from pathlib import Path

from .models import Record

CARD_TAG = "zfe-paper-card"
CARD_FILENAME = "PaperCard.md"


def is_paper_card(record: Record) -> bool:
    return (
        record.kind == "attachment"
        and bool(record.parent)
        and record.link_mode == "imported_file"
        and Path(record.filename).suffix.casefold() == ".md"
        and (record.card_marker or bool({CARD_TAG, "zfe-paper-card-phase1"}.intersection(record.tags)))
    )


def may_have_card_marker(record: Record) -> bool:
    return (
        record.kind == "attachment"
        and bool(record.parent)
        and record.link_mode == "imported_file"
        and record.filename.casefold() == CARD_FILENAME.casefold()
    )


def has_card_marker(header: bytes) -> bool:
    lines = header.decode("utf-8-sig", errors="replace").splitlines()
    if lines[:1] != ["---"] or "---" not in lines[1:]:
        return False
    fields = lines[1 : lines.index("---", 1)]
    return "card_type: explorer-paper-card" in fields and "schema_version: 1" in fields


@dataclass(frozen=True)
class CardTarget:
    instance: str
    library: str
    parent: str


@dataclass(frozen=True)
class CardDraft:
    attachment: str
    base_md5: str
    text: str
    creating: bool = False


def card_template(english=False):
    header = "---\ncard_type: explorer-paper-card\nschema_version: 1\n---\n\n"
    sections = (
        [
            ("In one sentence", "What is the main contribution?"),
            ("Research question", ""),
            ("Core method", "- Method\n- Innovation\n- Approach"),
            ("Main findings", "- "),
            ("Key details", "- Dataset or participants\n- Conditions and parameters\n- Figures and pages"),
            ("Compared with other papers", ""),
            ("Limitations", ""),
            ("My reflections", ""),
            ("Recall cues", ""),
        ]
        if english
        else [
            ("一句话概括", "这篇论文研究了什么问题？最重要的贡献是什么？"),
            ("研究问题", "作者试图解决什么问题？"),
            ("核心方法", "- 主要方法：\n- 核心创新：\n- 技术路线："),
            ("主要发现", "- 发现 1：\n- 发现 2：\n- 发现 3："),
            ("关键细节", "- 研究对象 / 数据集：\n- 重要实验条件：\n- 核心参数：\n- 关键图表与页码："),
            ("与其他论文的区别", "这篇论文最独特的地方是什么？"),
            ("局限性", "方法在哪些条件下存在限制？"),
            ("我的思考", "这篇论文与我的研究有什么关系？"),
            ("记忆线索", "最能帮助我迅速想起这篇论文的关键词、图片或概念。"),
        ]
    )
    return header + "\n\n".join(f"# {title}\n\n{body}" for title, body in sections).rstrip() + "\n"
