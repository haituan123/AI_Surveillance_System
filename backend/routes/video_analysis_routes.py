from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from backend.app.config import (
    ALLOWED_VIDEO_EXTENSIONS,
    TEMP_UPLOADS_DIR,
    VIDEO_UPLOAD_MAX_BYTES,
)
from backend.app.schemas import (
    VideoAnalysisDeleteResponse,
    VideoAnalysisResults,
    VideoAnalysisStatus,
)
from backend.routes.surveillance_routes import get_surveillance_manager
from backend.services.surveillance_manager import LiveSurveillanceManager
from backend.services.video_analysis_manager import (
    VideoAnalysisBusyError,
    VideoAnalysisManager,
    VideoAnalysisNotFoundError,
    VideoAnalysisStopTimeoutError,
    video_analysis_manager,
)

router = APIRouter(prefix="/video-analysis", tags=["video-analysis"])


def get_video_analysis_manager() -> VideoAnalysisManager:
    return video_analysis_manager


async def _save_temporary_upload(upload: UploadFile) -> Path:
    filename = upload.filename or ""
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported video type. Allowed extensions: "
                + ", ".join(sorted(ALLOWED_VIDEO_EXTENSIONS))
            ),
        )

    TEMP_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    target = TEMP_UPLOADS_DIR / f"{uuid4().hex}{extension}"
    total_bytes = 0
    try:
        with target.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > VIDEO_UPLOAD_MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Uploaded video is too large",
                    )
                output.write(chunk)
        if total_bytes == 0:
            raise HTTPException(
                status_code=400,
                detail="Uploaded video is empty",
            )
        return target
    except Exception:
        if target.exists():
            target.unlink()
        raise
    finally:
        await upload.close()


@router.post("", response_model=VideoAnalysisStatus, status_code=202)
async def submit_video_analysis(
    file: UploadFile = File(...),
    manager: VideoAnalysisManager = Depends(get_video_analysis_manager),
    surveillance: LiveSurveillanceManager = Depends(
        get_surveillance_manager
    ),
):
    if surveillance.status().running:
        raise HTTPException(
            status_code=409,
            detail="Stop live surveillance before analyzing an uploaded video",
        )

    path = await _save_temporary_upload(file)
    try:
        return manager.submit(path, file.filename or path.name)
    except VideoAnalysisBusyError as exc:
        if path.exists():
            path.unlink()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        if path.exists():
            path.unlink()
        raise


@router.get("/{job_id}/status", response_model=VideoAnalysisStatus)
def get_video_analysis_status(
    job_id: str,
    manager: VideoAnalysisManager = Depends(get_video_analysis_manager),
):
    try:
        return manager.status(job_id)
    except VideoAnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/results", response_model=VideoAnalysisResults)
def get_video_analysis_results(
    job_id: str,
    manager: VideoAnalysisManager = Depends(get_video_analysis_manager),
):
    try:
        return manager.results(job_id)
    except VideoAnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/frame")
def get_video_analysis_frame(
    job_id: str,
    manager: VideoAnalysisManager = Depends(get_video_analysis_manager),
):
    try:
        frame = manager.latest_frame(job_id)
    except VideoAnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if frame is None:
        raise HTTPException(
            status_code=404,
            detail="No analyzed video frame is available",
        )
    return Response(
        content=frame,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{job_id}/events/{event_id}/snapshot")
def get_video_analysis_event_snapshot(
    job_id: str,
    event_id: str,
    manager: VideoAnalysisManager = Depends(get_video_analysis_manager),
):
    try:
        frame = manager.event_snapshot(job_id, event_id)
    except VideoAnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if frame is None:
        raise HTTPException(status_code=404, detail="Event snapshot not found")
    return Response(
        content=frame,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.delete(
    "/{job_id}",
    response_model=VideoAnalysisDeleteResponse,
)
def delete_video_analysis(
    job_id: str,
    manager: VideoAnalysisManager = Depends(get_video_analysis_manager),
):
    try:
        manager.delete(job_id)
    except VideoAnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VideoAnalysisStopTimeoutError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "message": "Temporary video-analysis job deleted",
        "job_id": job_id,
    }
