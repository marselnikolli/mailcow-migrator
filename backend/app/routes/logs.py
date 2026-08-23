import asyncio
import json

from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect, Depends
from app.core.queue import RedisQueue
from app.repositories.job_repo import JobRepository
from app.auth import AuthService
from app.deps.roles import get_current_user

router = APIRouter()
queue = RedisQueue()


@router.get("/{job_id}", dependencies=[Depends(get_current_user)])
async def get_logs(request: Request, job_id: int):
    """Get logs for a job."""
    tenant_id = request.state.tenant_id

    # Verify job belongs to tenant
    job = JobRepository.get_job_by_id(job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    logs = queue.get_job_log(job_id)
    return {
        "job_id": job_id,
        "logs": logs.split("\n") if logs else []
    }


@router.websocket("/ws/{job_id}")
async def websocket_logs(websocket: WebSocket, job_id: int):
    """WebSocket endpoint for real-time logs.

    Browsers can't set custom headers on a WebSocket handshake, so instead of
    putting the JWT in the URL (where it leaks into logs/history) the client
    sends it as the first text frame after the connection opens. Nothing is
    streamed back until that token is verified and the job's tenant checked.
    """
    await websocket.accept()

    try:
        auth_message = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        token = json.loads(auth_message).get("token", "")
    except WebSocketDisconnect:
        return
    except (asyncio.TimeoutError, json.JSONDecodeError, AttributeError):
        await websocket.close(code=4401, reason="Authentication required")
        return

    payload = AuthService.decode_token(token)
    if not payload:
        await websocket.close(code=4401, reason="Invalid or expired token")
        return

    tenant_id = payload.get("tenant_id")

    # Verify job belongs to tenant
    job = JobRepository.get_job_by_id(job_id, tenant_id)
    if not job:
        await websocket.close(code=4404, reason="Job not found")
        return

    try:
        # Send existing logs first
        existing_logs = queue.get_job_log(job_id)
        if existing_logs:
            await websocket.send_text(existing_logs)

        # Poll for new logs. Waiting on receive() instead of a plain sleep()
        # doubles as prompt disconnect detection: if the client goes away,
        # the ASGI server delivers a disconnect message immediately instead
        # of leaving this task parked until the next log line arrives.
        last_log_length = len(existing_logs)
        while True:
            current_logs = queue.get_job_log(job_id)
            if len(current_logs) > last_log_length:
                new_logs = current_logs[last_log_length:]
                await websocket.send_text(new_logs)
                last_log_length = len(current_logs)

            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=1)
                if message.get("type") == "websocket.disconnect":
                    break
            except asyncio.TimeoutError:
                continue

    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as e:
        await websocket.close(code=1000, reason=str(e))
