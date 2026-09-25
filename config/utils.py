from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme


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
