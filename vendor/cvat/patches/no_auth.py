"""
Auto-authentication class that logs in every request as a default admin user.
"""
from django.contrib.auth import get_user_model
from rest_framework import authentication

User = get_user_model()


class NoAuthAuthentication(authentication.BaseAuthentication):
    """Authenticate every request as the first superuser found in the DB."""

    def authenticate(self, request):
        try:
            user = User.objects.filter(is_superuser=True).first()
            if not user:
                user = User.objects.create_superuser(
                    username="auto",
                    email="auto@local.dev",
                    password="auto",
                )
            return (user, None)
        except Exception:
            pass
        return None
