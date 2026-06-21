"""
management/commands/setup_demo.py

Creates (or repairs) the admin user required by the simulator and the Django
admin site.  Called from the web service entrypoint in docker-compose.yaml:

    python manage.py migrate && python manage.py setup_demo && daphne …

The command is fully idempotent — running it multiple times is safe.

Environment variables (set in docker-compose.yaml):
    DJANGO_ADMIN_USERNAME   default: admin
    DJANGO_ADMIN_PASSWORD   default: admin123
    DJANGO_ADMIN_EMAIL      default: admin@mine.test
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the demo admin user if they do not already exist."

    def handle(self, *args, **options):
        User = get_user_model()

        username = os.getenv("DJANGO_ADMIN_USERNAME", "admin")
        password = os.getenv("DJANGO_ADMIN_PASSWORD", "admin123")
        email    = os.getenv("DJANGO_ADMIN_EMAIL",    "admin@mine.test")

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email":        email,
                "role":         "admin",   # our custom field — must be 'admin'
                "is_staff":     True,
                "is_superuser": True,
            },
        )

        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created admin user '{username}' (role=admin, is_superuser=True)."
                )
            )
        else:
            updated = []
            if user.role != "admin":
                user.role = "admin"
                updated.append("role→admin")
            if not user.is_staff:
                user.is_staff = True
                updated.append("is_staff→True")
            if not user.is_superuser:
                user.is_superuser = True
                updated.append("is_superuser→True")
            if updated:
                user.save(update_fields=["role", "is_staff", "is_superuser"])
                self.stdout.write(
                    f"Updated existing user '{username}': {', '.join(updated)}."
                )
            else:
                self.stdout.write(f"Admin user '{username}' already configured correctly.")
