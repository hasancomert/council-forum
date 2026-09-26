from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme


def get_target(ct, pk, base):
    """URL'deki (içerik tipi, pk) çiftinin nesnesi. Beyaz liste: yalnızca `base`'ten türeyen modeller
    (ör. bir User'a yorum yazılamaz, bir oy gizlenemez); yoksa 404.
    """
    try:
        target = get_object_or_404(ContentType, pk=ct).get_object_for_this_type(pk=pk)
    except ObjectDoesNotExist:
        raise Http404
    if not isinstance(target, base):
        raise Http404
    return target


def back(request, default):
    """Formdaki gizli `next` alanının (ya da ?next=) adresi, yoksa default. Yalnızca bu sitenin yolu ('/…')
    kabul edilir: başka siteye yönlendirme (open redirect, ör. //kotu.site) reddedilir.
    """
    nxt = request.POST.get('next') or request.GET.get('next') or ''
    ok = nxt.startswith('/') and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure())
    return nxt if ok else default


def over_limit(qs, setting):
    """Hız sınırı: FORUM[setting] = (n, dakika). qs'nin son `dakika` içindeki kaydı n'e ulaştıysa True."""
    n, minutes = settings.FORUM[setting]
    return qs.filter(created_at__gte=timezone.now() - timedelta(minutes=minutes)).count() >= n


class ReadOnlyAdmin(admin.ModelAdmin):
    """Admin'de yalnızca görüntüleme: ekleme, değiştirme ve silme kapalı. Kayıtlar sitedeki akıştan
    (form, oylama, moderasyon) değişir; kurucu kural dışı müdahale edemez.
    """
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
