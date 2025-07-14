from fastapi import APIRouter

from . import users, search, payments

api_router = APIRouter()
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(payments.router, prefix="/payments", tags=["payments"]) 