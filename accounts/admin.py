from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from config.utils import PrivateLookups

from .models import User


@admin.register(User)
class UserAdmin(PrivateLookups, BaseUserAdmin):
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
        # Kuruluştan sonra B statüsü yalnızca oylamayla değişir (kural 2, ExpertProposal); yönetici ataması da
        # kapanır (yöntemi açık nokta). Yöneticiler moderasyon kaydı sayfasında herkese açık listelenir. Kayıt
        # tarihi de: geri alınırsa yeni hesap kural 1'deki hesap yaşını beklemeden oy verir (sunumda kuruluş sürer).
        founding = settings.FORUM['FOUNDING']
        return self.readonly_fields + (() if founding else ('role', 'is_moderator', 'date_joined'))

    def has_add_permission(self, request):
        # Kuruluştan sonra hesap yalnızca kayıt formundan (e-posta doğrulaması + CAPTCHA, kural 1) açılır.
        return settings.FORUM['FOUNDING'] and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        # Gerçek silme yok: karar oylarını CASCADE'le silip bitmiş sonuçları değiştirirdi, onay sayfası da üyenin
        # oylarını ve şikayetlerini listelerdi (kural 6). Hesap silme üyenin kendisinde: User.anonymize().
        return False
