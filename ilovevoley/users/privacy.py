from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import DataExport

EXPORT_PENDING_MAX_AGE = timedelta(hours=1)


def is_erased(user):
    return user.username == f'deleted-{user.pk}'


def active_export_for(user):
    cutoff = timezone.now() - EXPORT_PENDING_MAX_AGE
    DataExport.objects.filter(
        user=user,
        status=DataExport.Status.PENDING,
        created_at__lt=cutoff,
    ).update(status=DataExport.Status.FAILED)
    return (
        DataExport.objects.filter(user=user)
        .filter(
            Q(status=DataExport.Status.PENDING)
            | Q(status=DataExport.Status.READY, expires_at__gt=timezone.now())
        )
        .order_by('-created_at')
        .first()
    )
