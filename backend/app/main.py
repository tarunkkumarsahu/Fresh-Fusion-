import os
import socket
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .api import datasets, external, images, investigation, samples, sensors
from .config import CORS_ORIGINS, UPLOAD_DIR
from .database import Base, engine
from .realtime import manager

Base.metadata.create_all(bind=engine)
app = FastAPI(
    title="FreshFusion API",
    version="2.3.0",
    description="Multimodal fruit intelligence backend with automatic Apple/Banana identity, ESP32 telemetry, continuous phone vision, public dataset references, computer vision and fusion scoring.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=CORS_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
app.include_router(samples.router, prefix="/api/v1")
app.include_router(sensors.router, prefix="/api/v1")
app.include_router(images.router, prefix="/api/v1")
app.include_router(external.router, prefix="/api/v1")
app.include_router(datasets.router, prefix="/api/v1")
app.include_router(investigation.router, prefix="/api/v1")


def _lan_ip() -> str:
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        value = probe.getsockname()[0]
        probe.close()
        return value
    except Exception:
        return "127.0.0.1"


def _public_origin(request: Request) -> str:
    forwarded_host = request.headers.get("x-forwarded-host", "").strip()
    host = forwarded_host or request.headers.get("host", "").strip()
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    proto = forwarded_proto or request.url.scheme or "https"
    if not host:
        return ""
    return f"{proto}://{host}".rstrip("/")


@app.get("/api/v1/health")
def health(request: Request):
    lan_ip = _lan_ip()
    backend_port = int(os.getenv("FRESHFUSION_BACKEND_PORT", "8000"))
    frontend_port = int(os.getenv("FRESHFUSION_FRONTEND_PORT", "5173"))
    public_phone_url = os.getenv("PHONE_DASHBOARD_URL", "").strip()
    is_cloud = bool(os.getenv("VERCEL"))

    if public_phone_url:
        phone_dashboard = public_phone_url
        phone_mode = (
            "trusted-https-tunnel"
            if public_phone_url.startswith("https://")
            else "configured"
        )
        camera_secure = public_phone_url.startswith("https://")
    elif is_cloud:
        # The dashboard and phone page are deployed under the same Vercel origin.
        # Build the URL from forwarded request headers so QR pairing survives
        # preview/production domains without hardcoding a deployment hostname.
        origin = _public_origin(request)
        phone_dashboard = f"{origin}/phone.html" if origin else "/phone.html"
        phone_mode = "cloud-same-origin"
        camera_secure = phone_dashboard.startswith("https://") or not origin
    else:
        phone_dashboard = f"http://{lan_ip}:{frontend_port}/phone.html"
        phone_mode = "lan-fallback"
        camera_secure = False

    return {
        "status": "online",
        "service": "FreshFusion",
        "version": "2.3.0",
        "lan_ip": lan_ip,
        "phone_dashboard": phone_dashboard,
        "phone_mode": phone_mode,
        "camera_secure": camera_secure,
        "backend_port": backend_port,
        "frontend_port": frontend_port,
        "esp32_endpoint": f"http://{lan_ip}:{backend_port}/api/v1/sensors/readings",
        "fruit_identity": {
            "mode": "auto",
            "supported_now": ["Apple", "Banana"],
            "broader_identity_dataset": "Fruits-360",
        },
    }


@app.websocket("/ws/live/{sample_id}")
async def live(websocket: WebSocket, sample_id: str):
    await manager.connect(sample_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(sample_id, websocket)
