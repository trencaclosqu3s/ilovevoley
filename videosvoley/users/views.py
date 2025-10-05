from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required
def pending_approval(request):
    """Vista para usuarios que están pendientes de aprobación"""
    return render(request, 'users/pending_approval.html', {
        'user': request.user
    })