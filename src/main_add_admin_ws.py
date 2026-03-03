# This shows the code to add to main.py

# Add this import at the top with other admin imports:
from .admin import (
    router as admin_ui_router,
    api_router as admin_api_router,
    fragments_router as admin_fragments_router,
    admin_ws_manager,  # <-- ADD THIS
)

# Add this function before the ws_events endpoint (around line 270):

async def get_admin_session_from_cookie(request: Request) -> Optional[str]:
    """Extract and validate admin session from cookie"""
    from .admin.auth import AdminSession
    
    session_id = request.cookies.get("admin_session")
    if not session_id:
        return None
    
    db = tenant_manager._db
    if not db:
        return None
    
    admin_session = AdminSession(db)
    session_data = await admin_session.get_session(session_id)
    
    if not session_data:
        return None
    
    return session_id


@app.websocket("/admin/ws")
async def admin_ws_events(websocket: WebSocket):
    """WebSocket endpoint for admin dashboard real-time updates"""
    logger.debug("Admin WebSocket connection attempt")
    
    # Get session from cookie (WebSocket doesn't support Query params for auth in browsers well)
    session_id = websocket.cookies.get("admin_session") if hasattr(websocket, 'cookies') else None
    
    # Alternative: extract from query param if cookie not available
    if not session_id:
        from fastapi import Query
        # Note: We'll need to pass session as query param for WebSocket connections
        # because cookies aren't always available in WebSocket handshake
        return
    
    # Validate session
    db = tenant_manager._db
    if not db:
        logger.warning("Admin WebSocket rejected: database not available")
        await websocket.close(code=1011, reason="Database not available")
        return
    
    from .admin.auth import AdminSession
    admin_session = AdminSession(db)
    session_data = await admin_session.get_session(session_id)
    
    if not session_data:
        logger.warning("Admin WebSocket rejected: invalid session")
        await websocket.close(code=1008, reason="Invalid session")
        return
    
    logger.info(f"Admin WebSocket connected: session={session_id[:16]}...")
    await admin_ws_manager.connect(websocket, session_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        logger.info(f"Admin WebSocket disconnected: session={session_id[:16]}...")
        await admin_ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"Admin WebSocket error: {e}")
        await admin_ws_manager.disconnect(websocket)
