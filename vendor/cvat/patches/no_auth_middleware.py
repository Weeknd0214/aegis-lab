"""
Auto-authenticate all requests as a default admin user.
This removes the need for login in local/test environments.
"""
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()


class NoAuthMiddleware:
    """Middleware that auto-authenticates every request as the first superuser."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only set user if not already authenticated
        if not request.user.is_authenticated:
            try:
                user = User.objects.filter(is_superuser=True).first()
                if not user:
                    user = User.objects.create_superuser(
                        username="auto",
                        email="auto@local.dev",
                        password="auto",
                    )
                request.user = user
            except Exception:
                pass

        return self.get_response(request)
