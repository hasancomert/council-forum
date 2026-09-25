from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import PROPOSAL_MODELS, PROPOSALS, BaseProposal, Vote


def _model(slug):
    if slug not in PROPOSALS:
        raise Http404
    return PROPOSALS[slug]


def proposal_list(request):  # 7. adımda ana sayfadaki yan panel olacak
    open_now = {'status': BaseProposal.Status.VOTING, 'voting_ends_at__gt': timezone.now()}
    # select_related(): boş bırakınca null olamayan tüm FK'leri (topic, target_user) tek sorguda getirir.
    proposals = [p for model in PROPOSAL_MODELS
                 for p in model.objects.filter(**open_now).select_related().annotate(participants=Count('votes'))]
    proposals.sort(key=lambda p: p.voting_ends_at)
    return render(request, 'voting/list.html', {'proposals': proposals, 'title': 'Açık öneriler'})


def detail(request, slug, pk):
    proposal = get_object_or_404(_model(slug), pk=pk)
    proposal.finalize()  # lazy kontrol: süresi dolmuşsa sonuç burada yazılır
    return render(request, 'voting/detail.html', {
        'proposal': proposal,
        'title': str(proposal),
        'my_vote': request.user.is_authenticated and proposal.votes.filter(voter=request.user).first(),
        'tally': proposal.results_visible and proposal.tally(),  # kural 6: sonuç bitince açıklanır
    })


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
