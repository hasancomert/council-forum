from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (('Forum', {'fields': ('role',)}),)
    # Zorunlu alanlar "kullanıcı ekle" sayfasında da sorulmalı
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'first_name', 'last_name', 'email',
                       'usable_password', 'password1', 'password2'),
        }),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_active', 'is_staff')
    list_filter = BaseUserAdmin.list_filter + ('role',)
