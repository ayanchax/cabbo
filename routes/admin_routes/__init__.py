from .driver import router as driver_admin_router
from .user import router as user_admin_router
from .auth import router as admin_auth_router

routers = [driver_admin_router, user_admin_router, admin_auth_router]