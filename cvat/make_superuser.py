#!/usr/bin/env python3
# Script to ensure user is a superuser
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cvat.settings.production')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

username = input("Enter username to make superuser: ").strip()
try:
    user = User.objects.get(username=username)
    user.is_superuser = True
    user.is_staff = True
    user.save()
    print(f"✓ User '{username}' is now a superuser with full permissions")
except User.DoesNotExist:
    print(f"✗ User '{username}' does not exist")
