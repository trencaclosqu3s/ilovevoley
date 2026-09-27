"""Descarga de álbumes de partido/grupo en ZIP (#127)."""
import io
import uuid
import zipfile
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from ilovevoley.competitions.models import League, Match
from ilovevoley.content.models import Image
from ilovevoley.core.models import Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import Membership

TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)


@override_settings(
    ALLOWED_HOSTS=['testclub.ilovevoley.es', 'other.ilovevoley.es', 'localhost'],
    ALBUM_ZIP_LINK_MAX_AGE=3600,
)
class AlbumZipFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.club = Club.objects.create(
            federation_id='ZIP-CLUB', official_name='Test Club Fed',
        )
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', is_active=True, club=self.club,
        )
        self.other = Organization.objects.create(slug='other', name='Other', is_active=True)
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        self.season = Season.objects.create(
            name='2026-27', start_year=2026, end_year=2027, is_current=True,
        )
        self.league = League.objects.create(
            name='Liga', federation_id='ZIP-L', season=self.season,
        )
        self.team_a = Team.objects.create(name='A', federation_id='ZIP-A', club=self.club)
        self.team_b = Team.objects.create(name='B', federation_id='ZIP-B', club=self.club)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='ZIP-M1',
        )
        self.album_group_id = uuid.uuid4()

    def _img(self, **kwargs):
        kwargs.setdefault('uploaded_by', self.user)
        kwargs.setdefault('status', 'approved')
        kwargs.setdefault('season', self.season)
        kwargs.setdefault('organization', self.org)
        title = kwargs.get('title', 'foto')
        kwargs.setdefault(
            'image',
            SimpleUploadedFile(f'{title}.gif', TINY_GIF, content_type='image/gif'),
        )
        return Image.objects.create(**kwargs)

    def test_download_rejects_expired_signature(self):
        self._img(title='a', match=self.match)
        self.client.force_login(self.user)
        host = 'testclub.ilovevoley.es'
        job_id = self.client.post(
            reverse('content:match_album_zip', args=[self.match.id]),
            HTTP_HOST=host,
        ).json()['job_id']
        download_url = self.client.get(
            reverse('content:album_zip_status', args=[job_id]),
            HTTP_HOST=host,
        ).json()['download_url']

        with mock.patch(
            'ilovevoley.content.views_album_zip.parse_download_token',
            return_value=None,
        ):
            response = self.client.get(download_url, HTTP_HOST=host)
        self.assertEqual(response.status_code, 404)

    def test_build_zip_includes_only_approved_images_for_match(self):
        from django.conf import settings

        from ilovevoley.content.album_zip import build_album_zip_file

        approved = self._img(title='ok', match=self.match)
        self._img(title='pending', match=self.match, status='pending')
        self._img(title='rejected', match=self.match, status='rejected')
        self._img(title='other-org', match=self.match, organization=self.other)

        out = Path(settings.MEDIA_ROOT) / 'tmp' / 'album_zips' / 'job-test.zip'
        count = build_album_zip_file(
            queryset=Image.objects.filter(
                match=self.match, organization=self.org, status='approved',
            ),
            dest_path=out,
        )
        self.assertEqual(count, 1)
        self.assertTrue(out.is_file())
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            self.assertEqual(len(names), 1)
            self.assertTrue(names[0].startswith(f'{approved.pk}_'))

    def test_match_zip_request_poll_and_download(self):
        self._img(title='a', match=self.match)
        self._img(title='b', match=self.match)

        self.client.force_login(self.user)
        host = 'testclub.ilovevoley.es'
        start = self.client.post(
            reverse('content:match_album_zip', args=[self.match.id]),
            HTTP_HOST=host,
        )
        self.assertEqual(start.status_code, 200)
        payload = start.json()
        self.assertIn('job_id', payload)
        job_id = payload['job_id']

        status = self.client.get(
            reverse('content:album_zip_status', args=[job_id]),
            HTTP_HOST=host,
        )
        self.assertEqual(status.status_code, 200)
        status_payload = status.json()
        self.assertEqual(status_payload['status'], 'ready')
        self.assertIn('download_url', status_payload)

        download = self.client.get(status_payload['download_url'], HTTP_HOST=host)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download['Content-Type'], 'application/zip')
        data = (
            b''.join(download.streaming_content)
            if hasattr(download, 'streaming_content')
            else download.content
        )
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertEqual(len(zf.namelist()), 2)

    def test_album_group_zip_request_and_download(self):
        self._img(title='g1', album_group_id=self.album_group_id, album_name='Entreno')
        self._img(title='g2', album_group_id=self.album_group_id, album_name='Entreno')

        self.client.force_login(self.user)
        host = 'testclub.ilovevoley.es'
        start = self.client.post(
            reverse('content:album_group_zip', args=[self.album_group_id]),
            HTTP_HOST=host,
        )
        self.assertEqual(start.status_code, 200)
        job_id = start.json()['job_id']
        status = self.client.get(
            reverse('content:album_zip_status', args=[job_id]),
            HTTP_HOST=host,
        ).json()
        self.assertEqual(status['status'], 'ready')
        download = self.client.get(status['download_url'], HTTP_HOST=host)
        self.assertEqual(download.status_code, 200)
        data = (
            b''.join(download.streaming_content)
            if hasattr(download, 'streaming_content')
            else download.content
        )
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertEqual(len(zf.namelist()), 2)

    def test_empty_match_album_returns_400(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('content:match_album_zip', args=[self.match.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 400)

    def test_signed_token_expires(self):
        from django.core.signing import SignatureExpired

        from ilovevoley.content.album_zip import (
            sign_download_token,
            unsign_download_token,
        )

        token = sign_download_token('job-1', 'tmp/album_zips/job-1.zip', 'a.zip')
        with self.assertRaises(SignatureExpired):
            unsign_download_token(token, max_age=-1)
