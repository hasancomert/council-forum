from django.utils.http import url_has_allowed_host_and_scheme


def back(request, default):
    """Formdaki gizli `next` alanının (ya da ?next=) adresi, yoksa default. Yalnızca bu sitenin yolu ('/…')
    kabul edilir: başka siteye yönlendirme (open redirect, ör. //kotu.site) reddedilir.
    """
    nxt = request.POST.get('next') or request.GET.get('next') or ''
    ok = nxt.startswith('/') and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure())
    return nxt if ok else default
