"""Read one DOCX and emit an ordered text/table snapshot; never write files."""

from __future__ import annotations

import argparse
import hashlib
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{" + NS["w"] + "}"


def text_of(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t"))


def extract(path: Path, root: Path) -> str:
    resolved = path.resolve(strict=True)
    relative = resolved.relative_to(root.resolve(strict=True)).as_posix()
    data = resolved.read_bytes()
    with zipfile.ZipFile(resolved) as archive:
        body = ET.fromstring(archive.read("word/document.xml")).find("w:body", NS)
        if body is None:
            raise ValueError("DOCX body is missing")
        style_names = {}
        if "word/styles.xml" in archive.namelist():
            for style in ET.fromstring(archive.read("word/styles.xml")).findall("w:style", NS):
                name = style.find("w:name", NS)
                style_names[style.get(W + "styleId", "")] = name.get(W + "val", "") if name is not None else ""
        lines = [
            "# V2现存Word文字快照",
            "",
            "提取日期：2026-10-26。只读提取，不修改原Word。",
            "",
            f"源文件：[V2 Word](../{relative})。",
            "",
            f"源文件SHA256：`{hashlib.sha256(data).hexdigest()}`。",
            "",
            "本快照按正文顺序保留段落与表格供检索；不复现页面、浮动图、全部样式、页眉页脚或批注。",
            "它是历史正文提取，不是获批V3正文，也不是可运行旧构建器的输入。图文权威仍为源Word；表中的旧参数和能力受当前配置基线与用户要求约束。",
            "",
            "## 原Word正文",
            "",
        ]
        for block in body:
            if block.tag == W + "p":
                value = text_of(block).strip()
                if value:
                    prop = block.find("w:pPr/w:pStyle", NS)
                    style_id = prop.get(W + "val", "") if prop is not None else ""
                    name = style_names.get(style_id, "").lower()
                    prefix = ""
                    if "heading" in name or "标题" in name:
                        prefix = "### "
                    lines.extend([prefix + value, ""])
                if block.findall(".//w:drawing", NS):
                    lines.extend(["[本处有原Word内嵌图，图片与版面请查源文件。]", ""])
            elif block.tag == W + "tbl":
                rows = []
                for row in block.findall("w:tr", NS):
                    cells = []
                    for cell in row.findall("w:tc", NS):
                        values = [text_of(p).strip() for p in cell.findall("w:p", NS)]
                        cells.append("<br>".join(v for v in values if v).replace("|", "\\|"))
                    rows.append(cells)
                if rows:
                    width = max(len(row) for row in rows)
                    for index, row in enumerate(rows):
                        row += [""] * (width - len(row))
                        lines.append("| " + " | ".join(row) + " |")
                        if index == 0:
                            lines.append("| " + " | ".join(["---"] * width) + " |")
                    lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(extract(args.input, args.root))


if __name__ == "__main__":
    main()
