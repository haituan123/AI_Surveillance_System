import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from backend.app.config import (
    ALLOWED_VIDEO_EXTENSIONS,
    SNAPSHOTS_DIR,
    TEMP_UPLOADS_DIR,
    VIDEO_UPLOAD_MAX_BYTES,
    resolve_storage_path,
)
from backend.app.database import db_session
from backend.app.schemas import (
    QAAskRequest,
    QAConversation,
    QAConversationCreate,
    QAConversationDetail,
    QAMessage,
    QAUploadedVideo,
)
from backend.services.qa_service import QAService

router = APIRouter(prefix="/qa", tags=["Question Answering"])


def get_qa_service(connection: sqlite3.Connection = Depends(db_session)) -> QAService:
    return QAService(connection)


@router.post(
    "/conversations",
    response_model=QAConversation,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new QA conversation",
)
def create_conversation(
    payload: QAConversationCreate,
    service: QAService = Depends(get_qa_service),
) -> QAConversation:
    return service.create_conversation(title=payload.title)


@router.get(
    "/conversations",
    response_model=list[QAConversation],
    summary="List all QA conversations",
)
def list_conversations(
    service: QAService = Depends(get_qa_service),
) -> list[QAConversation]:
    return service.list_conversations()


@router.get(
    "/conversations/{conversation_id}",
    response_model=QAConversationDetail,
    summary="Get conversation detail with messages and evidences",
)
def get_conversation_detail(
    conversation_id: int,
    service: QAService = Depends(get_qa_service),
) -> QAConversationDetail:
    try:
        return service.get_conversation_detail(conversation_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a QA conversation",
)
def delete_conversation(
    conversation_id: int,
    service: QAService = Depends(get_qa_service),
) -> None:
    service.delete_conversation(conversation_id)


# ==================== VIDEO UPLOAD ENDPOINTS ====================


@router.post(
    "/conversations/{conversation_id}/videos",
    response_model=QAUploadedVideo,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a video to analyze and index for QA in a conversation",
)
async def upload_conversation_video(
    conversation_id: int,
    file: UploadFile = File(...),
    service: QAService = Depends(get_qa_service),
) -> QAUploadedVideo:
    # 1. Validate conversation exists
    try:
        service.get_conversation(conversation_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # 2. Validate file extension
    filename = file.filename or "uploaded_video.mp4"
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported video format: {extension}. Allowed formats: {', '.join(sorted(ALLOWED_VIDEO_EXTENSIONS))}",
        )

    # 3. Save uploaded file to TEMP_UPLOADS_DIR
    TEMP_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    temp_filename = f"qa_{conversation_id}_{uuid4().hex[:8]}_{filename}"
    target_path = TEMP_UPLOADS_DIR / temp_filename

    try:
        with open(target_path, "wb") as buffer:
            size = 0
            while content := await file.read(1024 * 1024):  # 1MB chunks
                size += len(content)
                if size > VIDEO_UPLOAD_MAX_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Video size exceeds limit ({VIDEO_UPLOAD_MAX_BYTES // (1024 * 1024)}MB)",
                    )
                buffer.write(content)
    except Exception as exc:
        if target_path.exists():
            target_path.unlink()
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save video: {exc}",
        ) from exc

    # 4. Register video & start background indexing
    try:
        return service.upload_video(
            conversation_id=conversation_id,
            file_path=target_path,
            filename=filename,
        )
    except Exception as exc:
        if target_path.exists():
            target_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize video processing: {exc}",
        ) from exc


@router.get(
    "/conversations/{conversation_id}/videos",
    response_model=list[QAUploadedVideo],
    summary="List uploaded videos for a conversation",
)
def list_conversation_videos(
    conversation_id: int,
    service: QAService = Depends(get_qa_service),
) -> list[QAUploadedVideo]:
    try:
        return service.list_uploaded_videos(conversation_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/videos/{video_id}/status",
    response_model=QAUploadedVideo,
    summary="Get processing status of an uploaded video",
)
def get_video_status(
    video_id: str,
    service: QAService = Depends(get_qa_service),
) -> QAUploadedVideo:
    try:
        return service.get_uploaded_video_status(video_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/videos/{video_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an uploaded video and its indexed frames/entities/threats",
)
def delete_uploaded_video(
    video_id: str,
    service: QAService = Depends(get_qa_service),
) -> None:
    try:
        service.delete_uploaded_video(video_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/videos/{video_id}/retry",
    response_model=QAUploadedVideo,
    summary="Retry indexing an uploaded video that previously failed",
)
def retry_uploaded_video(
    video_id: str,
    service: QAService = Depends(get_qa_service),
) -> QAUploadedVideo:
    try:
        return service.retry_uploaded_video(video_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==================== ASK & EVIDENCE ENDPOINTS ====================


@router.post(
    "/ask",
    response_model=QAMessage,
    summary="Ask a surveillance question in Vietnamese",
)
def ask_question(
    payload: QAAskRequest,
    service: QAService = Depends(get_qa_service),
) -> QAMessage:
    try:
        return service.ask(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"QA inference error: {exc}",
        ) from exc


@router.get("/evidences/{evidence_id}/snapshot")
def get_evidence_snapshot(
    evidence_id: int,
    service: QAService = Depends(get_qa_service),
):
    evidence = service.connection.execute(
        "SELECT snapshot_path FROM qa_evidences WHERE id = ?",
        (evidence_id,),
    ).fetchone()
    if evidence is None or not evidence["snapshot_path"]:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    path = resolve_storage_path(evidence["snapshot_path"])
    if not path.is_relative_to(SNAPSHOTS_DIR.resolve()):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot file not found on disk")
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )

