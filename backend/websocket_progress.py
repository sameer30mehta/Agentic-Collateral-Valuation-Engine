"""
WebSocket Server for Real-Time Pipeline Progress Updates
Enables live progress tracking during property valuation
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from sqlalchemy.orm import Session
import asyncio
import json
from typing import Dict, List
import uuid
from datetime import datetime
from database import get_db
from config import settings

router = APIRouter()

# Store active WebSocket connections
# Format: {valuation_id: [websocket1, websocket2, ...]}
active_connections: Dict[str, List[WebSocket]] = {}
progress_cache: Dict[str, dict] = {}  # Cache latest progress for each valuation


class ConnectionManager:
    """Manage WebSocket connections for progress updates"""
    
    def __init__(self):
        self.active_connections = {}
    
    async def connect(self, valuation_id: str, websocket: WebSocket):
        """Accept and register a new WebSocket connection"""
        await websocket.accept()
        if valuation_id not in self.active_connections:
            self.active_connections[valuation_id] = []
        self.active_connections[valuation_id].append(websocket)
        print(f"[WebSocket] Client connected to valuation {valuation_id}")
    
    async def disconnect(self, valuation_id: str, websocket: WebSocket):
        """Remove disconnected WebSocket"""
        if valuation_id in self.active_connections:
            self.active_connections[valuation_id].remove(websocket)
            if not self.active_connections[valuation_id]:
                del self.active_connections[valuation_id]
            print(f"[WebSocket] Client disconnected from valuation {valuation_id}")
    
    async def broadcast_progress(self, valuation_id: str, progress_data: dict):
        """Send progress update to all clients watching this valuation"""
        if valuation_id not in self.active_connections:
            return
        
        # Cache the latest progress
        progress_cache[valuation_id] = progress_data
        
        # Send to all connected clients
        disconnected = []
        for websocket in self.active_connections[valuation_id]:
            try:
                await websocket.send_json(progress_data)
            except Exception as e:
                print(f"[WebSocket] Error sending to client: {e}")
                disconnected.append(websocket)
        
        # Remove dead connections
        for ws in disconnected:
            await self.disconnect(valuation_id, ws)


manager = ConnectionManager()


class ProgressTracker:
    """Track and emit pipeline progress updates"""
    
    def __init__(self, valuation_id: str):
        self.valuation_id = valuation_id
        self.start_time = datetime.now()
        self.task_progress = {}
    
    async def update_task(self, task_name: str, status: str, details: dict = None):
        """Update status of a task and broadcast to clients"""
        self.task_progress[task_name] = {
            'status': status,  # running, completed, failed
            'details': details or {},
            'timestamp': datetime.now().isoformat(),
        }
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        progress_data = {
            'valuation_id': self.valuation_id,
            'type': 'task_update',
            'task': task_name,
            'status': status,
            'elapsed_seconds': elapsed,
            'task_progress': self.task_progress,
            'details': details or {},
            'timestamp': datetime.now().isoformat(),
        }
        
        await manager.broadcast_progress(self.valuation_id, progress_data)
    
    async def update_stage(self, stage_name: str, description: str, progress_pct: int):
        """Update overall pipeline stage (50% complete, etc)"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        progress_data = {
            'valuation_id': self.valuation_id,
            'type': 'stage_update',
            'stage': stage_name,
            'description': description,
            'progress_percent': progress_pct,
            'elapsed_seconds': elapsed,
            'timestamp': datetime.now().isoformat(),
        }
        
        await manager.broadcast_progress(self.valuation_id, progress_data)
    
    async def complete(self, results: dict):
        """Mark valuation as complete"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        progress_data = {
            'valuation_id': self.valuation_id,
            'type': 'complete',
            'status': 'completed',
            'total_time_seconds': elapsed,
            'results': results,
            'timestamp': datetime.now().isoformat(),
        }
        
        await manager.broadcast_progress(self.valuation_id, progress_data)
    
    async def error(self, error_message: str, task_name: str = None):
        """Report an error"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        progress_data = {
            'valuation_id': self.valuation_id,
            'type': 'error',
            'status': 'failed',
            'error': error_message,
            'task': task_name,
            'elapsed_seconds': elapsed,
            'timestamp': datetime.now().isoformat(),
        }
        
        await manager.broadcast_progress(self.valuation_id, progress_data)


# ============================================================================
# WebSocket Routes
# ============================================================================

@router.websocket("/ws/progress/{valuation_id}")
async def websocket_progress(valuation_id: str, websocket: WebSocket):
    """
    WebSocket endpoint for real-time valuation progress
    
    Usage (Frontend):
    const ws = new WebSocket(`ws://localhost:8000/ws/progress/${valuationId}`);
    ws.onmessage = (event) => {
        const progress = JSON.parse(event.data);
        console.log(`${progress.task}: ${progress.status}`);
        updateProgressBar(progress.progress_percent);
    };
    """
    await manager.connect(valuation_id, websocket)
    
    try:
        # Send cached progress if available
        if valuation_id in progress_cache:
            await websocket.send_json(progress_cache[valuation_id])
        
        # Keep connection open
        while True:
            data = await websocket.receive_text()
            # Echo heartbeat or handle commands
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        await manager.disconnect(valuation_id, websocket)
    except Exception as e:
        print(f"[WebSocket] Error: {e}")
        await manager.disconnect(valuation_id, websocket)


@router.get("/progress/{valuation_id}")
async def get_progress(valuation_id: str, db: Session = Depends(get_db)):
    """
    HTTP endpoint to get current progress (fallback if WebSocket unavailable)
    """
    if valuation_id not in progress_cache:
        raise HTTPException(status_code=404, detail="No progress found for this valuation")
    
    return progress_cache[valuation_id]


@router.get("/progress-history/{valuation_id}")
async def get_progress_history(valuation_id: str, db: Session = Depends(get_db)):
    """
    Get progress history for a completed valuation
    Useful for debugging and audit trails
    """
    # This would retrieve from database if persisted
    # For now, return cached version
    if valuation_id not in progress_cache:
        raise HTTPException(status_code=404, detail="Valuation not found")
    
    return {
        'valuation_id': valuation_id,
        'final_progress': progress_cache[valuation_id],
    }
