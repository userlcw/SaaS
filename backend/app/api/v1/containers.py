"""Docker 容器与镜像管理 API。"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from sqlalchemy.orm import Session

from backend.app.api.v1.auth import _get_current_user
from backend.app.core.security import decode_token
from backend.app.db.session import SessionLocal, get_db
from backend.app.models.docker import AuditLog
from backend.app.models.user import User
from backend.app.schemas.auth import ApiResponse
from backend.app.schemas.docker import ContainerCreateRequest
from backend.app.services.docker_service import DockerListFilters, DockerService

router = APIRouter()


def get_docker_service() -> DockerService:
    return DockerService()


def get_current_user_for_docker(current_user: User = Depends(_get_current_user)) -> User:
    return current_user


def _is_admin(user: Any) -> bool:
    if isinstance(user, dict):
        return bool(user.get("is_admin"))
    return bool(getattr(user, "is_admin", False))


def _require_admin(user: Any) -> None:
    if not _is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 40301, "message": "无权限执行该操作"},
        )


def _docker_error(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"code": 50001, "message": f"Docker 引擎异常：{exc}"},
    )


def _user_id(user: Any) -> int | None:
    raw = user.get("id") if isinstance(user, dict) else getattr(user, "id", None)
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else ""


def _safe_container_summary(docker_service: DockerService, container_id: str) -> dict[str, Any] | None:
    try:
        return docker_service.container_summary(container_id)
    except Exception:
        return None


def _record_audit(
    db: Session,
    request: Request,
    user: Any,
    action: str,
    result: str,
    params: dict[str, Any],
    error_message: str = "",
    started_at: float | None = None,
) -> None:
    summary = dict(params)
    summary["device"] = request.headers.get("user-agent", "")
    log = AuditLog(
        user_id=_user_id(user),
        request_id=str(getattr(request.state, "request_id", "")),
        ip=_client_ip(request),
        action=action,
        result=result,
        params_summary=json.dumps(summary, ensure_ascii=False, default=str),
        error_message=error_message,
        duration_ms=int((time.perf_counter() - started_at) * 1000) if started_at else 0,
    )
    db.add(log)
    db.commit()


def _socket_recv(sock: Any, size: int) -> bytes:
    target = getattr(sock, "_sock", sock)
    return target.recv(size)


def _socket_send(sock: Any, data: bytes) -> int:
    target = getattr(sock, "_sock", sock)
    return target.send(data)


def _user_from_access_token(token: str, db: Session) -> User:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise JWTError("wrong token type")
        user_id = int(payload.get("sub", "0"))
    except (JWTError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40102, "message": "凭据无效或已过期"},
        ) from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40103, "message": "用户不存在或已停用"},
        )
    return user


@router.get("/containers", response_model=ApiResponse, summary="容器列表")
def list_containers(
    keyword: str = "",
    query_field: str = Query("all", alias="queryField"),
    server: str = "",
    status_value: str = Query("", alias="status"),
    channel: str = "",
    image: str = "",
    container_type: str = Query("", alias="containerType"),
    page: int = 1,
    page_size: int = Query(20, alias="page_size"),
    sort: str = "name",
    current_user: User = Depends(get_current_user_for_docker),  # noqa: ARG001
    docker_service: DockerService = Depends(get_docker_service),
) -> ApiResponse:
    filters = DockerListFilters(
        keyword=keyword,
        query_field=query_field,
        server=server,
        status=status_value,
        channel=channel,
        image=image,
        container_type=container_type,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    try:
        data = docker_service.list_containers(filters)
    except Exception as exc:
        raise _docker_error(exc) from exc
    return ApiResponse(code=0, message="ok", data=data)


@router.get("/images", response_model=ApiResponse, summary="镜像列表")
def list_images(
    server: str = "local",
    current_user: User = Depends(get_current_user_for_docker),  # noqa: ARG001
    docker_service: DockerService = Depends(get_docker_service),
) -> ApiResponse:
    try:
        items = docker_service.list_images(server=server)
    except Exception as exc:
        raise _docker_error(exc) from exc
    return ApiResponse(code=0, message="ok", data={"items": items, "total": len(items)})


@router.get("/containers/{container_id}/logs", response_model=ApiResponse, summary="查看容器日志")
def container_logs(
    container_id: str,
    tail: int = Query(200, ge=1, le=2000),
    current_user: User = Depends(get_current_user_for_docker),  # noqa: ARG001
    docker_service: DockerService = Depends(get_docker_service),
) -> ApiResponse:
    try:
        logs = docker_service.container_logs(container_id, tail=tail)
    except Exception as exc:
        raise _docker_error(exc) from exc
    return ApiResponse(code=0, message="ok", data={"container_id": container_id, "tail": tail, "logs": logs})


@router.websocket("/containers/{container_id}/terminal")
async def container_terminal(websocket: WebSocket, container_id: str) -> None:
    await websocket.accept()
    db = SessionLocal()
    sock = None
    try:
        auth_raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        try:
            auth_data = json.loads(auth_raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": 40106, "message": "终端认证数据不合法"},
            ) from exc
        token = str(auth_data.get("token") or "")
        user = _user_from_access_token(token, db)
        _require_admin(user)
        sock = DockerService().open_terminal_socket(container_id)
        await websocket.send_text("Connected to container. Press Ctrl+D or close the page to exit.\r\n")
        stop_event = asyncio.Event()

        async def docker_to_browser() -> None:
            while not stop_event.is_set():
                try:
                    chunk = await asyncio.to_thread(_socket_recv, sock, 4096)
                except Exception:
                    break
                if not chunk:
                    break
                if isinstance(chunk, bytes):
                    text = chunk.decode("utf-8", errors="replace")
                else:
                    text = str(chunk)
                await websocket.send_text(text)
            stop_event.set()

        async def browser_to_docker() -> None:
            while not stop_event.is_set():
                try:
                    message = await websocket.receive_text()
                except WebSocketDisconnect:
                    break
                except Exception:
                    break
                if message == "\x04":
                    break
                try:
                    await asyncio.to_thread(_socket_send, sock, message.encode("utf-8"))
                except Exception:
                    break
            stop_event.set()

        await asyncio.gather(docker_to_browser(), browser_to_docker())
    except HTTPException as exc:
        await websocket.send_text(f"\r\n连接被拒绝：{exc.detail}\r\n")
    except Exception as exc:
        await websocket.send_text(f"\r\n终端连接失败：{exc}\r\n")
    finally:
        db.close()
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass


@router.post("/containers", response_model=ApiResponse, summary="创建容器")
def create_container(
    payload: ContainerCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user_for_docker),
    docker_service: DockerService = Depends(get_docker_service),
    db: Session = Depends(get_db),
) -> ApiResponse:
    _require_admin(current_user)
    started_at = time.perf_counter()
    try:
        data = docker_service.create_container(payload)
    except Exception as exc:
        _record_audit(
            db,
            request,
            current_user,
            "container:create",
            "failed",
            {"payload": payload.model_dump(mode="json")},
            str(exc),
            started_at,
        )
        raise _docker_error(exc) from exc
    _record_audit(
        db,
        request,
        current_user,
        "container:create",
        "success",
        {"container_id": data.get("docker_id") or data.get("id"), "container_name": data.get("name"), "before": None, "after": data},
        started_at=started_at,
    )
    return ApiResponse(code=0, message="容器创建成功", data=data)


@router.post("/containers/{container_id}/actions/start", response_model=ApiResponse, summary="启动容器")
def start_container(
    container_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_for_docker),
    docker_service: DockerService = Depends(get_docker_service),
    db: Session = Depends(get_db),
) -> ApiResponse:
    _require_admin(current_user)
    started_at = time.perf_counter()
    before = _safe_container_summary(docker_service, container_id)
    try:
        data = docker_service.start_container(container_id)
    except Exception as exc:
        _record_audit(
            db,
            request,
            current_user,
            "container:start",
            "failed",
            {"container_id": container_id, "before": before, "after": None},
            str(exc),
            started_at,
        )
        raise _docker_error(exc) from exc
    _record_audit(
        db,
        request,
        current_user,
        "container:start",
        "success",
        {"container_id": container_id, "container_name": data.get("name"), "before": before, "after": data},
        started_at=started_at,
    )
    return ApiResponse(code=0, message="容器启动成功", data=data)


@router.post("/containers/{container_id}/actions/stop", response_model=ApiResponse, summary="停止容器")
def stop_container(
    container_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_for_docker),
    docker_service: DockerService = Depends(get_docker_service),
    db: Session = Depends(get_db),
) -> ApiResponse:
    _require_admin(current_user)
    started_at = time.perf_counter()
    before = _safe_container_summary(docker_service, container_id)
    try:
        data = docker_service.stop_container(container_id)
    except Exception as exc:
        _record_audit(
            db,
            request,
            current_user,
            "container:stop",
            "failed",
            {"container_id": container_id, "before": before, "after": None},
            str(exc),
            started_at,
        )
        raise _docker_error(exc) from exc
    _record_audit(
        db,
        request,
        current_user,
        "container:stop",
        "success",
        {"container_id": container_id, "container_name": data.get("name"), "before": before, "after": data},
        started_at=started_at,
    )
    return ApiResponse(code=0, message="容器停止成功", data=data)


@router.post("/containers/{container_id}/actions/restart", response_model=ApiResponse, summary="重启容器")
def restart_container(
    container_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_for_docker),
    docker_service: DockerService = Depends(get_docker_service),
    db: Session = Depends(get_db),
) -> ApiResponse:
    _require_admin(current_user)
    started_at = time.perf_counter()
    before = _safe_container_summary(docker_service, container_id)
    try:
        data = docker_service.restart_container(container_id)
    except Exception as exc:
        _record_audit(
            db,
            request,
            current_user,
            "container:restart",
            "failed",
            {"container_id": container_id, "before": before, "after": None},
            str(exc),
            started_at,
        )
        raise _docker_error(exc) from exc
    _record_audit(
        db,
        request,
        current_user,
        "container:restart",
        "success",
        {"container_id": container_id, "container_name": data.get("name"), "before": before, "after": data},
        started_at=started_at,
    )
    return ApiResponse(code=0, message="容器重启成功", data=data)


@router.delete("/containers/{container_id}", response_model=ApiResponse, summary="删除容器")
def delete_container(
    container_id: str,
    request: Request,
    force: bool = False,
    current_user: User = Depends(get_current_user_for_docker),
    docker_service: DockerService = Depends(get_docker_service),
    db: Session = Depends(get_db),
) -> ApiResponse:
    _require_admin(current_user)
    started_at = time.perf_counter()
    before = _safe_container_summary(docker_service, container_id)
    try:
        data = docker_service.delete_container(container_id, force=force)
    except Exception as exc:
        _record_audit(
            db,
            request,
            current_user,
            "container:delete",
            "failed",
            {"container_id": container_id, "force": force, "before": before, "after": None},
            str(exc),
            started_at,
        )
        raise _docker_error(exc) from exc
    _record_audit(
        db,
        request,
        current_user,
        "container:delete",
        "success",
        {"container_id": container_id, "container_name": data.get("name"), "force": force, "before": before, "after": data},
        started_at=started_at,
    )
    return ApiResponse(code=0, message="容器删除成功", data=data)
