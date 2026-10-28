import csv
from datetime import timedelta
import io
import json
import zipfile

from django.db.models import Q
from django.utils import timezone

from ilovevoley.content.models import Image, Video
from ilovevoley.rosters.models import Person

from .models import DataExport

EXPORT_PENDING_MAX_AGE = timedelta(hours=1)

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

