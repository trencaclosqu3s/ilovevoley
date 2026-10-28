import csv
from datetime import timedelta
import io
import json
import zipfile

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db.models import Q
from django.utils import timezone

from ilovevoley.content.models import Image, Video
from ilovevoley.rosters.models import Person

from .models import DataExport, PrivacyAuditEvent

EXPORT_PENDING_MAX_AGE = timedelta(hours=1)
EXPORT_TOKEN_SALT = 'ilovevoley.users.data_export.v1'
EXPORT_TOKEN_MAX_AGE = timedelta(days=7)
ERASURE_TOKEN_SALT = 'ilovevoley.users.account_erasure.v1'
ERASURE_TOKEN_MAX_AGE = timedelta(hours=48)

CSV_COLUMNS = [
    'record_type',
    'organization',
    'role',
    'is_approved',
    'joined_at',
    'category',
    'team',
    'notification_type',
    'is_enabled',
    'person_id',
    'first_name',
    'last_name',
    'birth_year',
    'link',
    'image_consent',
    'title',
    'url',
]


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


def _render_csv(rows, columns):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


def build_export_zip(user) -> bytes:
    profile = {
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'parent_info': user.parent_info,
        'preferred_language': user.preferred_language,
        'date_joined': user.date_joined.isoformat() if user.date_joined else '',
        'last_login': user.last_login.isoformat() if user.last_login else None,
        'is_approved': user.is_approved,
    }

    memberships = []
    for m in user.memberships.select_related('organization').order_by('id'):
        memberships.append({
            'organization': m.organization.name if m.organization else '',
            'role': m.role,
            'is_approved': m.is_approved,
            'joined_at': m.joined_at.isoformat() if m.joined_at else '',
        })

    category_preferences = []
    for cp in user.category_preferences.select_related('organization').prefetch_related('categories', 'teams').order_by('id'):
        category_preferences.append({
            'organization': cp.organization.name if cp.organization else '',
            'categories': [c.name for c in cp.categories.all()],
            'teams': [t.name for t in cp.teams.all()],
        })

    notification_preferences = []
    for np in user.notification_preferences.select_related('organization').order_by('id'):
        notification_preferences.append({
            'organization': np.organization.name if np.organization else '',
            'notification_type': np.notification_type,
            'is_enabled': np.is_enabled,
        })

    persons = []
    self_person = Person.objects.filter(user=user).first()
    if self_person:
        persons.append({
            'id': self_person.id,
            'first_name': self_person.first_name,
            'last_name': self_person.last_name,
            'birth_year': self_person.birth_year,
            'link': 'self',
            'image_consent': self_person.image_consent,
            'image_consent_updated_at': (
                self_person.image_consent_updated_at.isoformat()
                if self_person.image_consent_updated_at
                else None
            ),
        })

    for child in user.children.all().order_by('id'):
        persons.append({
            'id': child.id,
            'first_name': child.first_name,
            'last_name': child.last_name,
            'birth_year': child.birth_year,
            'link': 'child',
            'image_consent': child.image_consent,
            'image_consent_updated_at': (
                child.image_consent_updated_at.isoformat()
                if child.image_consent_updated_at
                else None
            ),
        })

    images = []
    for img in Image.objects.filter(uploaded_by=user).select_related('organization').order_by('id'):
        images.append({
            'id': img.id,
            'title': img.title,
            'url': img.image.name if img.image else '',
            'uploaded_at': img.upload_date.isoformat() if img.upload_date else None,
            'organization': img.organization.name if img.organization else '',
            'status': img.status,
        })

    videos = []
    for vid in Video.objects.filter(created_by=user).select_related('organization').order_by('id'):
        videos.append({
            'id': vid.id,
            'title': vid.title,
            'youtube_url': vid.youtube_url,
            'created_at': vid.created_at.isoformat() if vid.created_at else None,
            'organization': vid.organization.name if vid.organization else '',
        })

    account_data = {
        'profile': profile,
        'memberships': memberships,
        'category_preferences': category_preferences,
        'notification_preferences': notification_preferences,
        'persons': persons,
    }

    content_data = {
        'images': images,
        'videos': videos,
    }

    account_rows = [
        {
            'record_type': 'profile',
            'organization': '',
            'role': '',
            'is_approved': profile['is_approved'],
            'joined_at': profile['date_joined'],
            'category': '',
            'team': '',
            'notification_type': '',
            'is_enabled': '',
            'person_id': '',
            'first_name': profile['first_name'],
            'last_name': profile['last_name'],
            'birth_year': '',
            'link': '',
            'image_consent': '',
            'title': '',
            'url': '',
        }
    ]

    for m in memberships:
        account_rows.append({
            'record_type': 'membership',
            'organization': m['organization'],
            'role': m['role'],
            'is_approved': m['is_approved'],
            'joined_at': m['joined_at'],
            'category': '',
            'team': '',
            'notification_type': '',
            'is_enabled': '',
            'person_id': '',
            'first_name': '',
            'last_name': '',
            'birth_year': '',
            'link': '',
            'image_consent': '',
            'title': '',
            'url': '',
        })

    for cp in category_preferences:
        account_rows.append({
            'record_type': 'category_preference',
            'organization': cp['organization'],
            'role': '',
            'is_approved': '',
            'joined_at': '',
            'category': ', '.join(cp['categories']),
            'team': ', '.join(cp['teams']),
            'notification_type': '',
            'is_enabled': '',
            'person_id': '',
            'first_name': '',
            'last_name': '',
            'birth_year': '',
            'link': '',
            'image_consent': '',
            'title': '',
            'url': '',
        })

    for np in notification_preferences:
        account_rows.append({
            'record_type': 'notification_preference',
            'organization': np['organization'],
            'role': '',
            'is_approved': '',
            'joined_at': '',
            'category': '',
            'team': '',
            'notification_type': np['notification_type'],
            'is_enabled': np['is_enabled'],
            'person_id': '',
            'first_name': '',
            'last_name': '',
            'birth_year': '',
            'link': '',
            'image_consent': '',
            'title': '',
            'url': '',
        })

    for p in persons:
        account_rows.append({
            'record_type': 'person',
            'organization': '',
            'role': '',
            'is_approved': '',
            'joined_at': '',
            'category': '',
            'team': '',
            'notification_type': '',
            'is_enabled': '',
            'person_id': p['id'],
            'first_name': p['first_name'],
            'last_name': p['last_name'],
            'birth_year': p['birth_year'] if p['birth_year'] is not None else '',
            'link': p['link'],
            'image_consent': p['image_consent'],
            'title': '',
            'url': '',
        })

    content_rows = []
    for img in images:
        content_rows.append({
            'record_type': 'image',
            'organization': img['organization'],
            'role': '',
            'is_approved': '',
            'joined_at': img['uploaded_at'] or '',
            'category': '',
            'team': '',
            'notification_type': '',
            'is_enabled': '',
            'person_id': '',
            'first_name': '',
            'last_name': '',
            'birth_year': '',
            'link': '',
            'image_consent': '',
            'title': img['title'],
            'url': img['url'],
        })

    for vid in videos:
        content_rows.append({
            'record_type': 'video',
            'organization': vid['organization'],
            'role': '',
            'is_approved': '',
            'joined_at': vid['created_at'] or '',
            'category': '',
            'team': '',
            'notification_type': '',
            'is_enabled': '',
            'person_id': '',
            'first_name': '',
            'last_name': '',
            'birth_year': '',
            'link': '',
            'image_consent': '',
            'title': vid['title'],
            'url': vid['youtube_url'],
        })

    account_csv = _render_csv(account_rows, CSV_COLUMNS)
    content_csv = _render_csv(content_rows, CSV_COLUMNS)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('account.json', json.dumps(account_data, indent=2, ensure_ascii=False))
        zf.writestr('account.csv', account_csv)
        zf.writestr('content.json', json.dumps(content_data, indent=2, ensure_ascii=False))
        zf.writestr('content.csv', content_csv)

    return zip_buffer.getvalue()


def generate_export_token(export) -> str:
    signer = TimestampSigner(salt=EXPORT_TOKEN_SALT)
    return signer.sign(str(export.pk))


def export_for_token(token) -> DataExport | None:
    signer = TimestampSigner(salt=EXPORT_TOKEN_SALT)
    try:
        export_id = signer.unsign(token, max_age=EXPORT_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired, ValueError):
        return None

    try:
        export = DataExport.objects.get(pk=export_id)
    except DataExport.DoesNotExist:
        return None

    if export.status != DataExport.Status.READY:
        return None
    if not export.file:
        return None
    if export.expires_at is None or export.expires_at <= timezone.now():
        return None

    return export


def generate_erasure_token(user, content_choice: str) -> str:
    signer = TimestampSigner(salt=ERASURE_TOKEN_SALT)
    return signer.sign(f'{user.pk}:{content_choice}')


def erasure_from_token(token: str):
    from django.contrib.auth import get_user_model

    signer = TimestampSigner(salt=ERASURE_TOKEN_SALT)
    try:
        payload = signer.unsign(token, max_age=ERASURE_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired, ValueError):
        return None

    if ':' not in payload:
        return None

    user_id_str, choice = payload.split(':', 1)
    if choice not in ('delete', 'retain'):
        return None

    try:
        user_id = int(user_id_str)
    except ValueError:
        return None

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return None

    return user, choice


def cleanup_expired_data_exports() -> None:
    cutoff_pending = timezone.now() - EXPORT_PENDING_MAX_AGE
    DataExport.objects.filter(
        status=DataExport.Status.PENDING,
        created_at__lt=cutoff_pending,
    ).update(status=DataExport.Status.FAILED)

    expired_ready = DataExport.objects.filter(
        status=DataExport.Status.READY,
        expires_at__lt=timezone.now(),
    )
    for export in expired_ready:
        if export.file:
            export.file.delete(save=False)
        export.delete()

    cutoff_failed = timezone.now() - timedelta(days=7)
    DataExport.objects.filter(
        status=DataExport.Status.FAILED,
        created_at__lt=cutoff_failed,
    ).delete()


def cleanup_expired_privacy_audit_events() -> None:
    cutoff_audit = timezone.now() - timedelta(days=365)
    PrivacyAuditEvent.objects.filter(created_at__lt=cutoff_audit).delete()


class ErasureRefused(Exception):
    def __init__(self, code, clubs=()):
        super().__init__(code)
        self.code = code
        self.clubs = tuple(clubs)


def blocking_admin_clubs(user):
    from .models import Membership

    clubs = []
    memberships = Membership.objects.filter(
        user=user,
        role='admin',
        is_approved=True,
    ).select_related('organization')
    for membership in memberships:
        has_other = Membership.objects.filter(
            organization_id=membership.organization_id,
            role='admin',
            is_approved=True,
            user__is_active=True,
        ).exclude(user_id=user.pk).exists()
        if not has_other:
            clubs.append(membership.organization)
    return clubs


def _storage_names(field):
    name = getattr(field, 'name', '') or ''
    return [name] if name else []


def _clear_sessions(user):
    from django.contrib.sessions.models import Session

    user_id = str(user.pk)
    for session in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        if session.get_decoded().get('_auth_user_id') == user_id:
            session.delete()


def _erase_account(user, content_choice):
    from allauth.account.models import EmailAddress
    from allauth.socialaccount.models import SocialAccount

    from ilovevoley.competitions.models.callups import CallUpPlayer
    from ilovevoley.competitions.models.competitions import (
        MatchActaPhoto,
        MatchChangeLogReview,
        MatchLineupPersonLink,
        MatchShareLink,
    )
    from ilovevoley.competitions.models.story import StoryComposition
    from ilovevoley.content.models import (
        Comment,
        ImageFavorite,
        ImageRemovalRequest,
        SharedUpload,
    )
    from ilovevoley.rosters.models import PersonLinkRequest

    paths = []
    Comment.objects.filter(user=user).delete()
    ImageFavorite.objects.filter(user=user).delete()
    StoryComposition.objects.filter(user=user).delete()
    for upload in SharedUpload.objects.filter(owner=user):
        paths.extend(_storage_names(upload.file))
    SharedUpload.objects.filter(owner=user).delete()
    PersonLinkRequest.objects.filter(user=user).delete()

    images = Image.objects.filter(uploaded_by=user)
    videos = Video.objects.filter(created_by=user)
    if content_choice == 'delete':
        for image in images:
            for field_name in (
                'image',
                'thumbnail_small',
                'thumbnail_large',
                'thumbnail_small_avif',
                'thumbnail_large_avif',
            ):
                paths.extend(_storage_names(getattr(image, field_name)))
        images.delete()
        videos.delete()
    else:
        images.update(uploaded_by=None)
        videos.update(created_by=None)

    Image.objects.filter(moderated_by=user).update(moderated_by=None)
    ImageRemovalRequest.objects.filter(requested_by=user).update(requested_by=None, reason='')
    ImageRemovalRequest.objects.filter(resolved_by=user).update(resolved_by=None)
    PersonLinkRequest.objects.filter(resolved_by=user).update(resolved_by=None)
    MatchShareLink.objects.filter(created_by=user).update(created_by=None)
    MatchLineupPersonLink.objects.filter(created_by=user).update(created_by=None)
    MatchChangeLogReview.objects.filter(reviewed_by=user).update(reviewed_by=None)
    MatchActaPhoto.objects.filter(reviewed_by=user).update(reviewed_by=None)
    CallUpPlayer.objects.filter(reviewed_by=user).update(reviewed_by=None)

    Person.objects.filter(user=user).update(user=None)
    user.children.clear()

    club_count = user.memberships.count()
    user.memberships.all().delete()
    user.category_preferences.all().delete()
    user.notification_preferences.all().delete()
    user.web_push_subscriptions.all().delete()
    _clear_sessions(user)
    SocialAccount.objects.filter(user=user).delete()
    EmailAddress.objects.filter(user=user).delete()

    for export in user.data_exports.all():
        paths.extend(_storage_names(export.file))
    user.data_exports.all().delete()

    paths.extend(_storage_names(user.avatar))
    user.username = f'deleted-{user.pk}'
    user.email = ''
    user.first_name = ''
    user.last_name = ''
    user.parent_info = ''
    user.preferred_language = ''
    user.calendar_token = None
    user.avatar = ''
    user.is_active = False
    user.is_approved = False
    user.inactivity_warning_level = 0
    user.inactivity_warning_sent_at = None
    user.pending_profile_review = False
    user.reactivation_requested_at = None
    user.onboarding_dismissed_at = None
    user.set_unusable_password()
    user.save()
    PrivacyAuditEvent.objects.create(
        user_id=user.pk,
        action=PrivacyAuditEvent.Action.ERASURE,
        content_choice=content_choice,
        club_count=club_count,
    )
    return paths


def apply_erasure(user, content_choice):
    from django.core.files.storage import default_storage
    from django.db import transaction

    if content_choice not in ('delete', 'retain'):
        raise ValueError(content_choice)
    if is_erased(user):
        return
    if user.is_staff or user.is_superuser:
        raise ErasureRefused('staff')
    clubs = blocking_admin_clubs(user)
    if clubs:
        raise ErasureRefused('last_admin', clubs)
    with transaction.atomic():
        paths = _erase_account(user, content_choice)
    for name in paths:
        if name:
            default_storage.delete(name)


