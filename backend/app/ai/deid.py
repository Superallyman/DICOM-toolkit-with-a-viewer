# app/ai/deid.py
from __future__ import annotations
import os, re, json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_session
from app.db.models import EventLog, DICOMMetadataLog
from loguru import logger

router = APIRouter(prefix="/v1/ai/deid", tags=["AI-DeID"])

# Tags we scan (free-text leaning)
TAG_LABELS = {
    "00081030": "StudyDescription",
    "0008103E": "SeriesDescription",
    "00181030": "ProtocolName",
    "001021B0": "AdditionalPatientHistory",
    "00104000": "PatientComments",
    "00321060": "RequestedProcedureDescription",
    "00400007": "ScheduledProcedureStepDescription",
}
SCAN_TAGS = set(TAG_LABELS.keys())

# --------- regex rules (tuned for low false positives) ---------
RE_PATTERNS: List[Tuple[str, re.Pattern, str]] = [
    # Person names (JOHN DOE, Doe^John, Doe, John)
    ("NAME_LIKE", re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b"), "Looks like a person name"),
    ("NAME_CARET", re.compile(r"\b[A-Z][A-Za-z]+(?:\^[A-Z][A-Za-z]+)+\b"), "Looks like DICOM caret-delimited name"),
    # Emails
    ("EMAIL", re.compile(r"\b[a-zA-Z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "Looks like an email"),
    # Phone numbers
    ("PHONE", re.compile(r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b"), "Looks like a phone number"),
    # Dates (YYYYMMDD, YYYY-MM-DD, DD/MM/YYYY, etc.)
    ("DATE", re.compile(
        r"\b(?:(?:19|20)\d{2}[-/.]?(?:0[1-9]|1[0-2])[-/.]?(?:0[1-9]|[12]\d|3[01])|"
        r"(?:0[1-9]|[12]\d|3[01])[-/.](?:0[1-9]|1[0-2])[-/.](?:19|20)\d{2})\b"
    ), "Looks like a full date"),
    # IDs (MRN/Accession-ish) – alnum 6–14 w/ at least 2 digits (avoid generic words)
    ("ID_CODE", re.compile(r"\b(?=[A-Za-z0-9]{6,14}\b)(?:[A-Za-z]*\d[A-Za-z\d]*\d[A-Za-z\d]*)\b"),
     "Looks like an ID code"),
    # Address-ish
    ("ADDRESS", re.compile(
        r"\b\d{1,5}\s+[A-Za-z0-9.\-]+\s+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b",
        re.IGNORECASE
    ), "Looks like a street address"),
]

CRITICAL_CODES = {"NAME_LIKE", "NAME_CARET", "EMAIL", "PHONE", "ADDRESS", "ID_CODE"}
WARNING_CODES  = {"DATE"}  # dates can be allowed if shifted; treat as review unless policy says fail

def _apply_rules(text: str) -> List[Dict[str, Any]]:
    """Return list of issue dicts with spans for the given text."""
    findings: List[Dict[str, Any]] = []
    if not isinstance(text, str):
        return findings
    for code, pat, desc in RE_PATTERNS:
        for m in pat.finditer(text):
            findings.append({
                "code": code,
                "detail": desc,
                "span": [m.start(), m.end()],
                "match": m.group(0)
            })
    return findings

def _status_from_findings(all_findings: List[Dict[str, Any]]) -> str:
    has_critical = any(f["code"] in CRITICAL_CODES for f in all_findings)
    has_warning  = any(f["code"] in WARNING_CODES  for f in all_findings)
    if has_critical:
        return "fail"
    if has_warning:
        return "review"
    return "pass"

def _suggest_fix(value: str, issues: List[Dict[str, Any]]) -> str:
    """Very simple masker: replace matched spans with bracketed tokens."""
    if not isinstance(value, str) or not issues:
        return value if isinstance(value, str) else ""
    s = value
    # Work from end to not shift indices
    for f in sorted(issues, key=lambda x: x["span"][0], reverse=True):
        a, b = f["span"]
        token = {
            "NAME_LIKE": "[NAME]",
            "NAME_CARET": "[NAME]",
            "EMAIL": "[EMAIL]",
            "PHONE": "[PHONE]",
            "DATE": "[DATE]",
            "ID_CODE": "[ID]",
            "ADDRESS": "[ADDRESS]",
        }.get(f["code"], "[REDACTED]")
        s = s[:a] + token + s[b:]
    return s

def _is_sanitized(value: Optional[str]) -> bool:
    """Treat empty/None or bracket tokens as sanitized."""
    if value is None:
        return True
    v = str(value).strip()
    if not v:
        return True
    # Heuristically consider masked tokens as sanitized
    return bool(re.fullmatch(r"\[([A-Z]+|REDACTED)\]", v))

async def _escalate_llm(text_fields: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Optional LLM red-team step if env vars are configured."""
    if not os.getenv("AI_DEID_ENABLE_LLM", "").lower() in {"1", "true", "yes"}:
        return None
    llm_url = os.getenv("LLM_URL")
    llm_key = os.getenv("LLM_API_KEY")
    if not llm_url or not llm_key:
        return None

    prompt = (
        "You are auditing de-identified DICOM header text for possible PHI leakage. "
        "Flag only content that is likely PHI (names, contact info, specific dates, IDs, addresses). "
        "Be conservative and avoid false positives. Return JSON with an array 'flags', "
        "each item: {tag, snippet, reason}. Here is the input JSON array of {tag, label, value}:\n\n"
        + json.dumps(text_fields, ensure_ascii=False)
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                llm_url,
                headers={"Authorization": f"Bearer {llm_key}"},
                json={
                    "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1
                },
            )
        data = r.json()
        # Extract content from typical providers; fallback to full JSON
        content = None
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            content = json.dumps(data)
        return {"raw": data, "content": content}
    except Exception as e:
        logger.warning(f"[AI-DEID] LLM escalation failed: {e}")
        return {"error": str(e)}

def _read_metadata_json(row: DICOMMetadataLog) -> Dict[str, Any]:
    """Safely load JSON from row.metadata_json (JSON/JSONB or string)."""
    raw = getattr(row, "metadata_json", None) or getattr(row, "tags", None)
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}

def _row_phase(row: DICOMMetadataLog, tags: Dict[str, Any]) -> Optional[str]:
    """Get phase from column if present, else from JSON['__phase']."""
    ph = getattr(row, "phase", None)
    if ph:
        return ph
    return tags.get("__phase")

def _collect_text_fields_from_tags(tags: Dict[str, Any]) -> Dict[str, str]:
    """Return tag->text value for SCAN_TAGS from a tags dict."""
    out: Dict[str, str] = {}
    for tag, val in tags.items():
        if tag not in SCAN_TAGS:
            continue
        if val is None:
            continue
        value = " ".join(str(v) for v in val) if isinstance(val, list) else str(val)
        value = value.strip()
        if value:
            out[tag] = value
    return out

def _merge_latest_per_tag(rows: List[DICOMMetadataLog], want_phase: Optional[str]) -> Dict[str, str]:
    """
    From a list of rows, pick the most recent non-empty value for each tag for a given phase.
    If want_phase is None, match rows without an explicit phase.
    """
    merged: Dict[str, Tuple[datetime, str]] = {}
    for row in rows:
        tags = _read_metadata_json(row)
        phase = _row_phase(row, tags)
        if (want_phase is None and phase is not None) or (want_phase is not None and phase != want_phase):
            continue
        text_map = _collect_text_fields_from_tags(tags)
        created = getattr(row, "created_at", None) or datetime.min
        for tag, value in text_map.items():
            prev = merged.get(tag)
            if prev is None or created >= prev[0]:
                merged[tag] = (created, value)
    # unwrap
    return {tag: v for tag, (_ts, v) in merged.items()}

@router.get("/audit")
async def audit_study(
    study_uid: str = Query(..., min_length=3),
    session: AsyncSession = Depends(get_session)
):
    # 1) fetch metadata logs for this study
    res = await session.execute(
        select(DICOMMetadataLog).where(DICOMMetadataLog.study_uid == study_uid)
    )
    rows: List[DICOMMetadataLog] = res.scalars().all()

    # If no rows, return a harmless 200 so the UI can show a friendly message
    if not rows:
        return {
            "study_uid": study_uid,
            "status": "pass",
            "summary": "No metadata logs found for this StudyInstanceUID.",
            "issues": [],
            "scannedCount": 0,
        }

    # 2) Build per-phase views
    pre_map  = _merge_latest_per_tag(rows, want_phase="pre")
    post_map = _merge_latest_per_tag(rows, want_phase="post")

    # Back-compat: if neither explicit phase is present, merge unphased as PRE
    if not pre_map and not post_map:
        pre_map = _merge_latest_per_tag(rows, want_phase=None)

    # Compose list we’ll actually scan and compare
    all_tags = sorted(set(pre_map.keys()) | set(post_map.keys()))
    scanned_fields_for_count = post_map if post_map else pre_map

    ui_issues: List[Dict[str, Any]] = []
    all_post_findings: List[Dict[str, Any]] = []
    pre_only_findings: List[Dict[str, Any]] = []

    changed_cnt = 0
    unchanged_cnt = 0

    for tag in all_tags:
        label = TAG_LABELS.get(tag, tag)
        pre_val  = pre_map.get(tag)
        post_val = post_map.get(tag)

        pre_findings  = _apply_rules(pre_val)  if pre_val  else []
        post_findings = _apply_rules(post_val) if post_val else []

        # Track changes summary
        if post_map:
            if pre_val is not None and post_val is not None:
                if pre_val != post_val:
                    changed_cnt += 1
                else:
                    unchanged_cnt += 1

        # If POST exists, it's the source of truth for status
        if post_map:
            if post_val is None or _is_sanitized(post_val):
                # Looks sanitized/cleared; no issue
                continue
            if post_findings:
                reasons = "; ".join(sorted({i["detail"] for i in post_findings}))
                suggested = _suggest_fix(post_val, post_findings)
                # Provide a succinct pre→post context in the reason
                if pre_val is not None and pre_val != post_val:
                    reasons = f"{reasons} | changed pre→post"
                ui_issues.append({
                    "field": label,
                    "tag": tag,
                    "reason": reasons,
                    "suggested": suggested,
                })
                all_post_findings.extend(post_findings)
        else:
            # No POST: fall back to PRE; flag as review if PRE had possible PHI
            if pre_findings:
                reasons = "; ".join(sorted({i["detail"] for i in pre_findings}))
                suggested = _suggest_fix(pre_val, pre_findings)
                ui_issues.append({
                    "field": label,
                    "tag": tag,
                    "reason": f"{reasons} | no post-phase log yet",
                    "suggested": suggested,
                })
                pre_only_findings.extend(pre_findings)

    # Decide status
    if post_map:
        status = _status_from_findings(all_post_findings)
    else:
        # no post: be conservative
        status = _status_from_findings(pre_only_findings)
        if status == "pass" and pre_only_findings:
            # Shouldn't happen, but guard
            status = "review"

    # Optional LLM escalation (best-effort) — run against POST if present, else PRE
    try:
        if os.getenv("AI_DEID_ENABLE_LLM", "").lower() in {"1", "true", "yes"}:
            chosen_map = post_map if post_map else pre_map
            text_fields_for_llm = [
                {"tag": t, "label": TAG_LABELS.get(t, t), "value": v}
                for t, v in chosen_map.items()
                if v and v.strip()
            ]
            llm_report = await _escalate_llm(text_fields_for_llm)
            if llm_report and "content" in llm_report and isinstance(llm_report["content"], str):
                # Non-invasive: include one synthetic issue line if model flags anything textual
                # You can extend this to parse JSON from llm_report["content"] if your gateway returns structured data.
                pass  # Keep logic intact; not altering ui_issues list format here.
    except Exception as e:
        logger.warning(f"[AI-DEID] LLM step skipped: {e}")

    # Human summary
    if post_map and (changed_cnt or unchanged_cnt):
        summary = (
            f"Compared PRE vs POST across {len(all_tags)} fields: "
            f"{changed_cnt} changed, {unchanged_cnt} unchanged."
        )
        if status == "pass":
            summary += " No PHI-like content detected in POST."
        elif status == "review":
            summary += " Possible date-like content remains in POST; please review."
        else:
            summary += " Potential PHI remains in POST."
    elif post_map:
        summary = "POST-phase metadata present; no free-text fields to audit."
    elif pre_map:
        summary = (
            "Only PRE-phase metadata found. "
            "If anonymization was performed, ensure POST-phase logs are written."
        )
        if status == "pass":
            summary += " No PHI-like content detected in PRE."
        elif status == "review":
            summary += " Possible date-like content detected in PRE."
        else:
            summary += " Potential PHI detected in PRE."
    else:
        summary = "No free-text DICOM header fields found to audit."

    result = {
        "study_uid": study_uid,
        "status": status,
        "summary": summary,
        "issues": ui_issues,
        "scannedCount": len(scanned_fields_for_count),
    }

    # 4) log an EventLog (best-effort)
    try:
        evt = EventLog(
            event_type="DEID_AUDIT",
            success=(status == "pass"),
            message=json.dumps({
                "study_uid": study_uid,
                "status": status,
                "issues": len(ui_issues),
                "has_post": bool(post_map),
                "has_pre": bool(pre_map),
            }),
            timestamp=datetime.utcnow(),
        )
        session.add(evt)
        await session.commit()
    except Exception as e:
        logger.warning(f"[AI-DEID] Failed to write EventLog: {e}")
        await session.rollback()

    return result
