"""Read-only audit of the explicit whitepaper migration manifest; no tree walk."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "项目记忆/仓库文件白名单.json"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
FORBIDDEN_NAMES = {"场景SVG生成进度.md", "等距轴测场景说明图制作方法流程和计划_20261020.md"}


def forbidden(path: str) -> bool:
    item = PurePosixPath(path)
    return (
        item.suffix.lower() in {".svg", ".mjs", ".ps1", ".3dm", ".step", ".xlsx"}
        or any(part.startswith("_qa") or part in {".git", "node_modules", "tmp", "_handover_work", "skills", "__pycache__"} for part in item.parts)
        or item.name in FORBIDDEN_NAMES
        or item.name.startswith("~$")
        or item.name.startswith(".env")
        or item.name.startswith("workflow_")
        or (item.suffix == ".py" and path not in {"tools/project_audit.py", "tools/extract_docx_snapshot.py"})
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    errors = []
    seen = set()
    byte_count = 0
    for record in manifest["files"]:
        value = record["path"]
        posix = PurePosixPath(value)
        if value in seen or posix.is_absolute() or ".." in posix.parts or "\\" in value or ":" in value:
            errors.append("Invalid or duplicate path: " + value)
            continue
        seen.add(value)
        path = (ROOT / value).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            errors.append("Path outside repository: " + value)
            continue
        if forbidden(value):
            errors.append("Excluded file in allowlist: " + value)
        if not path.is_file():
            errors.append("Missing: " + value)
            continue
        data = path.read_bytes()
        byte_count += len(data)
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            errors.append("Hash changed, review and refresh manifest: " + value)

    for value in manifest.get("strict_link_files", []):
        path = ROOT / value
        if not path.is_file():
            errors.append("Missing link source: " + value)
            continue
        content = path.read_text(encoding="utf-8-sig")
        if re.search(r"(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|/Users/)", content):
            errors.append("Machine absolute path in portable entry: " + value)
        for target in re.findall(r"\]\(([^)]+)\)", content):
            target = target.strip("<>").split("#", 1)[0]
            if not target or re.match(r"^[a-z]+://", target, flags=re.I):
                continue
            destination = (path.parent / unquote(target)).resolve()
            if not destination.is_relative_to(ROOT.resolve()) or not destination.exists():
                errors.append("Broken or external local link: " + value + " -> " + target)

    word = ROOT / manifest["authoritative_historical_word"]
    word_info = {}
    if word.is_file():
        with zipfile.ZipFile(word) as archive:
            xml = ET.fromstring(archive.read("word/document.xml"))
            body = xml.find(W + "body")
            styles = ET.fromstring(archive.read("word/styles.xml"))
            names = {}
            for style in styles.findall(W + "style"):
                name = style.find(W + "name")
                names[style.get(W + "styleId", "")] = name.get(W + "val", "").lower() if name is not None else ""
            scene_paragraphs = []
            for paragraph in body.findall(W + "p"):
                text = "".join(n.text or "" for n in paragraph.iter(W + "t"))
                style = paragraph.find(W + "pPr/" + W + "pStyle")
                name = names.get(style.get(W + "val", ""), "") if style is not None else ""
                if ("heading" in name or "标题" in name) and re.match(r"^(?:0[1-9]|[1-4][0-9])\s+", text):
                    scene_paragraphs.append(text)
            word_info = {
                "paragraph_scene_titles": len(scene_paragraphs),
                "drawing_instances": len(xml.findall(".//" + W + "drawing")),
                "media_files": len([n for n in archive.namelist() if n.startswith("word/media/")]),
                "note": "Text/OOXML check only; not a new layout render or engineering validation",
            }
    else:
        errors.append("Authoritative historical Word missing")

    print(json.dumps({"ok": not errors, "file_count": len(seen), "bytes": byte_count,
                      "svg_generation_included": False, "word_structure": word_info,
                      "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
