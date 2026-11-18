import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.database import db_session
from backend.app.models import DetectionStatus
from backend.app.schemas import DetectionLogView, SecurityEventView
from backend.app.schemas import DeleteLogResponse
from backend.app.schemas import DeleteLogsResponse
from backend.services.log_service import LogService

router = APIRouter(prefix="/logs", tags=["logs"])


def get_log_service(
    connection: sqlite3.Connection = Depends(db_session),
) -> LogService:
    return LogService(connection)


@router.get("", response_model=list[DetectionLogView])
def list_logs(
    status: DetectionStatus | None = None,
    camera_id: int | None = Query(default=None, gt=0),
    session_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=50, ge=1, le=200),
    service: LogService = Depends(get_log_service),
):
    return service.list_logs(
        status=status,
        camera_id=camera_id,
        session_id=session_id,
        limit=limit,
    )


@router.get("/latest", response_model=DetectionLogView)
def get_latest_log(service: LogService = Depends(get_log_service)):
    log = service.latest_log()
    if log is None:
        raise HTTPException(status_code=404, detail="No detection logs found")
    return log


@router.get("/security-events", response_model=list[SecurityEventView])
def list_security_events(
    event_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    service: LogService = Depends(get_log_service),
):
    return service.list_security_events(event_type=event_type, limit=limit)


@router.delete("/all", response_model=DeleteLogsResponse)
def delete_all_logs(service: LogService = Depends(get_log_service)):
    return service.delete_all_logs()


@router.delete("/{log_id}", response_model=DeleteLogResponse)
def delete_log(
    log_id: int,
    service: LogService = Depends(get_log_service),
):
    deleted = service.delete_log(log_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Detection log not found")
    return deleted
