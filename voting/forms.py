from django import forms
from django.forms import modelform_factory

from accounts.models import User
from config.templatetags import capfirst

from .models import ExpertProposal


class ProposalForm(forms.ModelForm):
    """Etiketler Türkçe capfirst'le (Django'nunki 'işlem'i 'Işlem' yapar)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        names = {f.name: f.verbose_name for f in self._meta.model._meta.fields}
        for name, field in self.fields.items():
            if name in names:
                field.label = capfirst(names[name])


class ExpertProposalForm(ProposalForm):
    # Kural 2: başvuru (ver) kişinin kendisi için yapılır; geri almada hedef üye takma adıyla yazılır.
    username = forms.CharField(label='Üye (takma ad)', required=False, help_text='Yalnızca geri alma önerisinde.')

    class Meta:
        model = ExpertProposal
        fields = ('action', 'username', 'reason')

    def clean(self):
        data = super().clean()
        if data.get('action') != ExpertProposal.Action.REVOKE:
            self.instance.target_user = self.instance.proposer
        elif user := User.objects.filter(username__iexact=data.get('username')).first():  # takma ad harf duyarsız
            self.instance.target_user = user
        else:
            self.add_error('username', 'Bu takma adla bir üye yok.')
        return data


def proposal_form(model):
    if model is ExpertProposal:
        return ExpertProposalForm
    return modelform_factory(model, ProposalForm, fields=model.FORM_FIELDS)
