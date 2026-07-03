"""API v1 路由汇总。"""
from fastapi import APIRouter

from backend.app.api.v1 import admin as admin_v1
from backend.app.api.v1 import auth as auth_v1
from backend.app.api.v1 import containers as containers_v1

api_router = APIRouter()
api_router.include_router(auth_v1.router, prefix="/auth", tags=["auth"])
api_router.include_router(containers_v1.router, tags=["docker"])
api_router.include_router(admin_v1.router, tags=["admin"])
