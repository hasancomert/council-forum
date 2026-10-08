"""Kural sayılarının (settings.FORUM) açılış denetimi. Yanlış girilen değer sayfada 500 olarak değil, runserver,
migrate ve check --deploy'da açık bir hata olarak çıkar (slayttaki "yapılandırma borcu": dağınık, doğrulanmamış ayar).
"""
from django.apps import apps
from django.conf import settings
from django.core.checks import Error

COUNTS = ('ACTIVE_DAYS', 'QUORUM_MIN', 'MAX_OPEN_PROPOSALS', 'COMMENT_MAX_LENGTH', 'TOPICS_PER_PAGE',
          'COMMENTS_PER_PAGE', 'PANEL_VOTING', 'PANEL_DISCUSSION', 'MOD_NOTE_MAX_LENGTH', 'MOD_PER_PAGE')
DAYS = ('PROPOSAL_VOTING_DAYS', 'REQUEST_DISCUSSION_DAYS', 'REQUEST_VOTING_DAYS', 'POPULAR_DAYS', 'API_TOKEN_DAYS')


def number(v, low=0):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= low


def count(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 1


def forum_settings(app_configs, **kwargs):
    f, errors = settings.FORUM, []

    def need(ok, key, what):
        if not ok:
            errors.append(Error(f"FORUM['{key}'] {what} olmalı, şu an: {f.get(key)!r}", id='forum.E001'))

    for key in COUNTS:
        need(count(f.get(key)), key, 'en az 1 olan bir tam sayı')
    for key in DAYS:  # sunumda kısaltmak için kesirli gün olabilir
        need(number(f.get(key)) and f[key] > 0, key, "0'dan büyük bir sayı")
    for key in ('MIN_ACCOUNT_AGE_DAYS', 'REJECTED_COOLDOWN_DAYS'):
        need(number(f.get(key)), key, 'negatif olmayan bir sayı')
    for key in ('COMMENT_RATE', 'REPORT_RATE'):  # (en fazla kaç kayıt, kaç dakikada)
        need(isinstance(f.get(key), (tuple, list)) and len(f[key]) == 2 and all(map(count, f[key])), key,
             '(sayı, dakika) çifti')
    roles = apps.get_model(settings.AUTH_USER_MODEL).Role.values
    need(isinstance(f.get('VOTE_WEIGHT'), dict) and all(count(f['VOTE_WEIGHT'].get(r)) for r in roles),
         'VOTE_WEIGHT', f'her rol ({", ".join(roles)}) için en az 1')
    need(number(f.get('QUORUM_PERCENT')) and f['QUORUM_PERCENT'] <= 100, 'QUORUM_PERCENT', '0–100 arası')
    need(count(f.get('EXPERT_APPROVAL_NUM')) and count(f.get('EXPERT_APPROVAL_DEN'))
         and f['EXPERT_APPROVAL_NUM'] <= f['EXPERT_APPROVAL_DEN'], 'EXPERT_APPROVAL_NUM', 'payda (DEN) ile 1 arası')
    weights = f.get('POPULAR_WEIGHTS')
    need(isinstance(weights, dict) and all(number(weights.get(k)) for k in ('comment', 'vote')),
         'POPULAR_WEIGHTS', "'comment' ve 'vote' katsayıları")
    need(isinstance(f.get('BAN_DAYS'), (tuple, list)) and f['BAN_DAYS'] and all(map(count, f['BAN_DAYS'])),
         'BAN_DAYS', 'gün sayılarının boş olmayan listesi')
    need(isinstance(f.get('FOUNDING'), bool), 'FOUNDING', 'True ya da False')
    return errors
