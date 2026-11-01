"""
Analysis sessions and their query history: /api/v1/sessions (API_CONTRACT.md §5).

Every lookup is filtered by the caller's user id; another user's session is a 404.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Response
from sqlalchemy import delete, func, select

from app.config import DATA_DIR
from app.errors import ApiError
from app.models.api import (
    ExecutionSummary,
    HistoryEntry,
    QueryResponse,
    SessionCreate,
    SessionOut,
    SessionUpdate,
    VisualEvidence,
)
from app.models.db import AnalysisSession, QueryRecord, utc_now
from app.security import CurrentUser, DbSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


async def _owned_session(db: DbSession, user_id: str, session_id: str) -> AnalysisSession:
    session = await db.get(AnalysisSession, session_id)
    if session is None or session.user_id != user_id:
        raise ApiError(404, "NOT_FOUND", "Analysis session not found.")
    return session


async def _count(db: DbSession, session_id: str) -> int:
    return (await db.execute(
        select(func.count()).select_from(QueryRecord).where(QueryRecord.session_id == session_id)
    )).scalar_one()


def _out(s: AnalysisSession, n: int) -> SessionOut:
    return SessionOut(id=s.id, title=s.title, created_at=s.created_at, updated_at=s.updated_at, query_count=n)


def _evidence_path(ref: str | None):
    if not ref:
        return None
    path = (DATA_DIR / ref).resolve()
    return path if DATA_DIR.resolve() in path.parents else None


def _history_entry(q: QueryRecord) -> HistoryEntry:
    response = None
    if q.status == "success":
        evidence = VisualEvidence(type=q.visual_evidence_type)
        path = _evidence_path(q.visual_evidence_ref)
        if path and path.is_file():
            try:
                evidence = VisualEvidence.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("Unreadable evidence file for query %s", q.id)
        response = QueryResponse(
            answer=q.answer or "",
            confidence=q.confidence,
            task=q.selected_task,
            visual_evidence=evidence,
            execution_summary=ExecutionSummary(
                selected_task=q.selected_task, tool_used=q.tool_used,
                parameters=json.loads(q.parameters) if q.parameters else {},
                inputs_validated=bool(q.inputs_validated), latency_ms=q.latency_ms,
            ),
        )
    return HistoryEntry(id=q.id, query_text=q.query_text, created_at=q.created_at, status=q.status,
                        error_code=q.error_code, image_asset_ids=json.loads(q.image_ids or "[]"),
                        response=response)


@router.get("", response_model=list[SessionOut])
async def list_sessions(user: CurrentUser, db: DbSession) -> list[SessionOut]:
    counts = (select(QueryRecord.session_id, func.count().label("n"))
              .where(QueryRecord.user_id == user.id).group_by(QueryRecord.session_id).subquery())
    rows = (await db.execute(
        select(AnalysisSession, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.session_id == AnalysisSession.id)
        .where(AnalysisSession.user_id == user.id)
        .order_by(AnalysisSession.updated_at.desc())
    )).all()
    return [_out(s, n) for s, n in rows]


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(user: CurrentUser, db: DbSession, body: SessionCreate | None = None) -> SessionOut:
    body = body or SessionCreate()
    session = AnalysisSession(user_id=user.id, title=body.title.strip() or "New analysis")
    db.add(session)
    await db.commit()
    return _out(session, 0)


@router.get("/{session_id}", response_model=SessionOut)
async def get_session_(session_id: str, user: CurrentUser, db: DbSession) -> SessionOut:
    session = await _owned_session(db, user.id, session_id)
    return _out(session, await _count(db, session.id))


@router.patch("/{session_id}", response_model=SessionOut)
async def rename_session(session_id: str, body: SessionUpdate, user: CurrentUser, db: DbSession) -> SessionOut:
    session = await _owned_session(db, user.id, session_id)
    session.title = body.title.strip()
    session.updated_at = utc_now()
    await db.commit()
    return _out(session, await _count(db, session.id))


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str, user: CurrentUser, db: DbSession) -> Response:
    session = await _owned_session(db, user.id, session_id)
    refs = (await db.execute(
        select(QueryRecord.visual_evidence_ref).where(QueryRecord.session_id == session.id)
    )).scalars().all()
    await db.execute(delete(QueryRecord).where(QueryRecord.session_id == session.id))
    await db.delete(session)
    await db.commit()
    for ref in refs:  # evidence files belong to the deleted queries; images stay as the user's assets
        path = _evidence_path(ref)
        if path:
            path.unlink(missing_ok=True)
    return Response(status_code=204)


@router.get("/{session_id}/queries", response_model=list[HistoryEntry])
async def session_history(session_id: str, user: CurrentUser, db: DbSession) -> list[HistoryEntry]:
    session = await _owned_session(db, user.id, session_id)
    rows = (await db.execute(
        select(QueryRecord)
        .where(QueryRecord.session_id == session.id, QueryRecord.user_id == user.id)
        .order_by(QueryRecord.created_at.asc())
    )).scalars().all()
    return [_history_entry(q) for q in rows]
