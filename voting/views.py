from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from topics.models import Topic

from .forms import proposal_form
from .models import PROPOSALS, BaseProposal, TopicUndoProposal, Vote, active_proposals, required_quorum


def _model(slug):
    if slug not in PROPOSALS:
        raise Http404
    return PROPOSALS[slug]


def proposal_list(request):  # ana sayfa panelinin "tümü" sayfası
    proposals = sorted(active_proposals(), key=lambda p: p.voting_ends_at)
    return render(request, 'voting/list.html', {'proposals': proposals, 'quorum': required_quorum(),
                                                'title': 'Açık öneriler'})


def detail(request, slug, pk):
    proposal = get_object_or_404(_model(slug), pk=pk)
    proposal.finalize()  # lazy kontrol: süresi dolmuşsa sonuç burada yazılır
    masked = proposal.hidden_from(request.user)  # gizli önerinin metnini yalnızca önereni ve yöneticiler görür
    return render(request, 'voting/detail.html', {
        'proposal': proposal, 'masked': masked,
        'title': 'Moderasyonla gizlendi' if masked else str(proposal),
        'my_vote': request.user.is_authenticated and proposal.votes.filter(voter=request.user).first(),
        'tally': proposal.results_visible and proposal.tally(),  # kural 6: sonuç bitince açıklanır
        'quorum': proposal.status == BaseProposal.Status.VOTING and required_quorum(),  # katılım çubuğu
    })


@login_required
def new(request, slug, topic_pk=None):
    model = _model(slug)
    proposal = model(proposer=request.user)
    if model.TARGET and topic_pk is not None:
        # Geri alma kapalı/silinmiş konuya açılır; diğerleri yalnızca görünür konuya (gizli içerik forma dolmasın).
        # Moderasyonla gizlenen konu hiç öneri almaz.
        topics = Topic.objects.filter(is_hidden=False) if model is TopicUndoProposal else Topic.objects.visible()
        setattr(proposal, model.TARGET, get_object_or_404(topics, pk=topic_pk))
        proposal.prefill()
    elif topic_pk is not None or model.TARGET == 'topic':
        raise Http404  # konuya bağlı tipte konu eksik, ya da konu almayan tipe konu verilmiş
    # Öneren ve hedef is_valid()'den önce yazılır; is_valid() modelin clean()'ini de çalıştırır.
    form = proposal_form(model)(request.POST if request.method == 'POST' else None, instance=proposal)
    if form.is_valid():
        form.save()
        messages.success(request, 'Öneri açıldı.')
        return redirect(proposal)
    return render(request, 'voting/new.html', {'form': form, 'proposal': proposal, 'title': f'Yeni {model._meta.verbose_name}'})


@login_required
@require_POST
def vote(request, slug, pk):
    proposal = get_object_or_404(_model(slug), pk=pk)
    try:
        Vote.cast(proposal=proposal, voter=request.user, choice=request.POST.get('choice'))
        messages.success(request, 'Oyun kaydedildi; oylama bitene kadar değiştirebilirsin.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect(proposal)
