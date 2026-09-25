from django import forms
from django.conf import settings

from .models import ModAction


class ActionForm(forms.Form):
    """Her işlemde gerekçe ve herkese açık kısa not zorunlu ("diğer" gerekçe yok)."""
    reason = forms.ChoiceField(label='Gerekçe', choices=ModAction.Reason.choices, widget=forms.RadioSelect)
    note = forms.CharField(label='Herkese açık not', max_length=settings.FORUM['MOD_NOTE_MAX_LENGTH'])


class UserActionForm(ActionForm):
    kind = forms.ChoiceField(label='İşlem', widget=forms.RadioSelect)
    days = forms.TypedChoiceField(label='Engel süresi (gün)', coerce=int, required=False,
                                  choices=[('', '—'), *((d, d) for d in settings.FORUM['BAN_DAYS'])])
    field_order = ['kind', 'days', 'reason', 'note']

    def __init__(self, *args, kinds=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kind'].choices = [(k, ModAction.Kind(k).label) for k in kinds]  # hesabın durumuna uyanlar

    def clean(self):
        data = super().clean()
        if data.get('kind') == ModAction.Kind.CLOSE and data.get('reason') != ModAction.Reason.FAKE:
            raise forms.ValidationError('Hesap yalnızca "sahte hesap" gerekçesiyle kapatılır.')
        if data.get('kind') == ModAction.Kind.BAN and not data.get('days'):
            self.add_error('days', 'Engel süresini seç.')
        return data
