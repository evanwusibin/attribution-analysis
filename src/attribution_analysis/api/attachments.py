"""Case 附件摄取边界：隔离存储、元数据审计与解析快照。"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status

from attribution_analysis.api.authentication import SubjectContext, current_subject
from attribution_analysis.api.cases import service
from attribution_analysis.application.core import CaseNotFoundError
from attribution_analysis.domain.core import Evidence, EvidenceClass, new_id, utc_now
from attribution_analysis.config.settings import PROJECT_ROOT

router = APIRouter(prefix="/api/v1/attachments", tags=["attachments"])

UPLOAD_DIR = PROJECT_ROOT / "uploads"
MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".csv", ".docx", ".jpg", ".jpeg", ".md", ".pdf", ".png", ".pptx", ".txt", ".xlsx"}
CONTENT_TYPES = {
    ".csv": {"text/csv", "application/vnd.ms-excel"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
    ".md": {"text/markdown", "text/plain"}, ".txt": {"text/plain"},
    ".pdf": {"application/pdf"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
}


def _now() -> str:
    """当前 UTC 时间的 ISO 字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _case_dir(subject_id: str, case_id: str) -> Path:
    """按主体+Case 生成隔离存储目录，校验路径穿越。"""
    if not case_id or Path(case_id).name != case_id:
        raise HTTPException(status_code=400, detail="invalid case id")
    directory = (UPLOAD_DIR / subject_id / case_id).resolve()
    root = UPLOAD_DIR.resolve()
    if root not in directory.parents:
        raise HTTPException(status_code=400, detail="invalid attachment path")
    return directory


def _manifest_path(directory: Path) -> Path:
    """返回附件清单 JSON 路径。"""
    return directory / "attachments.json"


def _read_manifest(directory: Path) -> list[dict[str, object]]:
    """读取附件清单；不存在时返回空列表。"""
    path = _manifest_path(directory)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def _write_manifest(directory: Path, entries: list[dict[str, object]]) -> None:
    """持久化附件清单 JSON。"""
    directory.mkdir(parents=True, exist_ok=True)
    _manifest_path(directory).write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_snapshot(filename: str, content: bytes) -> dict[str, object]:
    """生成摄取时的解析快照（文本预览/行数或二进制说明）。"""
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".csv"}:
        text = content.decode("utf-8", errors="replace")
        snapshot: dict[str, object] = {"kind": "text", "characters": len(text), "preview": text[:1000]}
        if suffix == ".csv":
            try:
                snapshot["rows"] = sum(1 for _ in csv.reader(text.splitlines()))
            except csv.Error:
                snapshot["rows"] = None
        return snapshot
    return {"kind": "binary", "bytes": len(content), "preview": "二进制文件已隔离保存，待专用解析器处理。"}


def _require_case(case_id: str, subject: SubjectContext):
    """校验 Case 存在且归属当前主体，否则抛 404。"""
    try:
        return service.get_case(case_id, subject.subject_id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc


@router.post("/cases/{case_id}", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    case_id: str,
    file: UploadFile = File(...),
    subject: SubjectContext = Depends(current_subject),
) -> dict[str, object]:
    """Store an allowed file under an owned Case and retain its immutable intake snapshot."""
    case = _require_case(case_id, subject)
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="unsupported attachment type")
    if file.content_type and file.content_type not in CONTENT_TYPES[suffix]:
        raise HTTPException(status_code=415, detail="attachment media type does not match its extension")
    content = await file.read(MAX_FILE_SIZE + 1)
    if not content:
        raise HTTPException(status_code=422, detail="attachment is empty")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="attachment exceeds 20MB limit")

    directory = _case_dir(subject.subject_id, case_id)
    digest = hashlib.sha256(content).hexdigest()
    safe_name = f"{digest[:16]}_{filename}"
    target = directory / safe_name
    directory.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(content)
    entries = _read_manifest(directory)
    entry = next((item for item in entries if item["sha256"] == digest), None)
    if entry is None:
        entry = {"attachment_id": f"att_{digest[:24]}", "filename": filename, "stored_name": safe_name,
                 "sha256": digest, "size": len(content), "content_type": file.content_type or "application/octet-stream",
                 "uploaded_at": _now(), "parse_snapshot": _parse_snapshot(filename, content)}
        entries.append(entry)
        _write_manifest(directory, entries)
        service.append_evidence(
            case_id,
            subject.subject_id,
            Evidence(
                evidence_id=new_id("evidence"), case_id=case.case_id, execution_id="attachment_intake",
                source_class=EvidenceClass.FACT, source_ref=f"attachment:{entry['attachment_id']}",
                rule_version="attachment-intake.v1",
                content_summary=f"附件 {filename} 已完成隔离保存与解析快照。",
                recorded_at=utc_now(),
            ),
        )
    return {"data": entry}


@router.get("/cases/{case_id}")
def list_attachments(case_id: str, subject: SubjectContext = Depends(current_subject)) -> dict[str, object]:
    """列出 Case 下已摄取的全部附件清单。"""
    _require_case(case_id, subject)
    return {"data": _read_manifest(_case_dir(subject.subject_id, case_id))}
