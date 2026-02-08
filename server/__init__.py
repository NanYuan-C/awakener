"""
Awakener - Server Package
=========================
The management console web server for the Awakener platform.

This package provides:
- FastAPI web application serving the management UI
- REST API endpoints for configuration, agent control, and data access
- WebSocket endpoint for real-time log streaming and status updates
- Authentication middleware with password protection and JWT tokens

Architecture:
    main.py      -> FastAPI app creation, middleware, static file serving
    auth.py      -> Password hashing, JWT tokens, route protection
    config.py    -> Read/write config.yaml and .env files
    routes.py    -> All REST API endpoint handlers
    websocket.py -> WebSocket connection manager and message broadcasting
    manager.py   -> Activator process lifecycle management (start/stop/status)
"""
