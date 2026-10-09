from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from comments.models import vote_block
from config.errors import RuleError

from .forms import proposal_form
from .models import PROPOSALS, BaseProposal, Vote, active_proposals, required_quorum


def model_for(slug):
    if slug not in PROPOSALS:
        raise Http404
    return PROPOSALS[slug]


def proposal_list(request):  # ana sayfa panelinin "tümü" sayfası; sıra paneldeki gibi (evresinin bitişi)
    return render(request, 'voting/list.html', {'proposals': active_proposals(), 'quorum': required_quorum(),
                                                'title': 'Açık öneriler'})


def page_data(slug, pk, user):
    """Öneri sayfasının verisi (site ve API). Süresi dolmuşsa sonuç burada yazılır (lazy kontrol)."""
    proposal = get_object_or_404(model_for(slug), pk=pk)
    proposal.finalize()
    masked = proposal.hidden_from(user)  # gizli önerinin metnini yalnızca önereni ve yöneticiler görür
    return {
        'proposal': proposal, 'masked': masked,
        'title': 'Moderasyonla gizlendi' if masked else str(proposal),
        'my_vote': user.is_authenticated and proposal.votes.filter(voter=user).first(),
        'tally': proposal.results_visible and proposal.tally(),  # kural 6: sonuç bitince açıklanır
        'quorum': proposal.status == BaseProposal.Status.VOTING and required_quorum(),  # katılım çubuğu
        'why': vote_block(user),  # oy verilemiyorsa nedeni (▲/▼ ve API ile aynı metin)
    }


def detail(request, slug, pk):
    return render(request, 'voting/detail.html', page_data(slug, pk, request.user))


def new_form(slug, topic_pk, user, data=None):
    """Yeni önerinin formu (site ve API): öneren ve URL'deki hedef is_valid()'den önce yazılır, is_valid() modelin
    clean()'ini de çalıştırır (öneri denetimlerinin tek yeri). data None ise boş form.
    """
    model = model_for(slug)
    proposal = model(proposer=user)
    if model.TARGET and topic_pk is not None:
        # Hangi konuların hedef olabileceğini tip söyler (geri alma kapalı/silinmiş konuya da açılır).
        setattr(proposal, model.TARGET, get_object_or_404(model.targets(), pk=topic_pk))
        proposal.prefill()
    elif topic_pk is not None or model.TARGET == 'topic':
        raise Http404  # konuya bağlı tipte konu eksik, ya da konu almayan tipe konu verilmiş
    return proposal, proposal_form(model)(data, instance=proposal)


@login_required
def new(request, slug, topic_pk=None):
    proposal, form = new_form(slug, topic_pk, request.user, request.POST if request.method == 'POST' else None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Öneri açıldı.')
        return redirect(proposal)
    return render(request, 'voting/new.html', {'form': form, 'proposal': proposal,
                                               'title': f'Yeni {proposal._meta.verbose_name}'})


@login_required
@require_POST
def vote(request, slug, pk):
    proposal = get_object_or_404(model_for(slug), pk=pk)
    try:
        Vote.cast(proposal=proposal, voter=request.user, choice=request.POST.get('choice'))
        messages.success(request, 'Oyun kaydedildi; oylama bitene kadar değiştirebilirsin.')
    except RuleError as e:
        messages.error(request, str(e))
    return redirect(proposal)
