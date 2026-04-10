from fastapi import APIRouter, Request, HTTPException, WebSocket
from app.core.queue import RedisQueue
from app.repositories.job_repo import JobRepository
import asyncio

router = APIRouter()
queue = RedisQueue()

@router.get("/{job_id}")
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
async def websocket_logs(websocket: WebSocket, job_id: int, request: Request):
    """WebSocket endpoint for real-time logs."""
    tenant_id = request.state.tenant_id
    
    # Verify job belongs to tenant
    job = JobRepository.get_job_by_id(job_id, tenant_id)
    if not job:
        await websocket.close(code=404, reason="Job not found")
        return
    
    await websocket.accept()
    
    try:
        # Send existing logs first
        existing_logs = queue.get_job_log(job_id)
        if existing_logs:
            await websocket.send_text(existing_logs)
        
        # Poll for new logs
        last_log_length = len(existing_logs)
        while True:
            current_logs = queue.get_job_log(job_id)
            if len(current_logs) > last_log_length:
                new_logs = current_logs[last_log_length:]
                await websocket.send_text(new_logs)
                last_log_length = len(current_logs)
            
            await asyncio.sleep(1)
    
    except Exception as e:
        await websocket.close(code=1000, reason=str(e))
