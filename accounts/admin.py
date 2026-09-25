from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Forum', {'fields': ('role', 'is_moderator', 'banned_until', 'terms_accepted_at', 'deleted_at')}),
    )
    # Zorunlu alanlar "kullanıcı ekle" sayfasında da sorulmalı
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'first_name', 'last_name', 'email',
                       'usable_password', 'password1', 'password2'),
        }),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_moderator', 'is_active', 'is_staff')
    list_filter = BaseUserAdmin.list_filter + ('role', 'is_moderator')
    # Engel ve hesap kapatma yalnızca moderasyon sayfalarından (kayda düşsün diye).
    readonly_fields = ('is_active', 'banned_until', 'terms_accepted_at', 'deleted_at')

    def get_readonly_fields(self, request, obj=None):
        # Kuruluştan sonra B statüsü yalnızca oylamayla değişir (kural 2, ExpertProposal).
        return self.readonly_fields + (() if settings.FORUM['FOUNDING'] else ('role',))
