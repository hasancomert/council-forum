from django import forms
from django.forms import modelform_factory

from accounts.models import User

from .models import ExpertProposal


class ExpertProposalForm(forms.ModelForm):
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
    return ExpertProposalForm if model is ExpertProposal else modelform_factory(model, fields=model.FORM_FIELDS)
