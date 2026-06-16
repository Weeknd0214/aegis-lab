# CVAT server + aegis-lab patches (no_auth + iframe for platform embed)
# Base: official CVAT server image; customizations in vendor/cvat/patches/
FROM cvat/server:dev

COPY vendor/cvat/patches/base.py /home/django/cvat/settings/base.py
COPY vendor/cvat/patches/no_auth.py /home/django/cvat/apps/iam/no_auth.py
COPY vendor/cvat/patches/no_auth_middleware.py /home/django/cvat/apps/iam/no_auth_middleware.py
