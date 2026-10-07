from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from ilovevoley.core.models import Category
from ilovevoley.teams.identity import (
    backfill_team_identities,
    extract_core_name,
    normalize_core_name,
    notify_new_identity_candidates,
    resolve_team_identity,
)
from ilovevoley.teams.models import Club, Team, TeamIdentity, TeamIdentityCandidate


class BackfillTeamIdentityTests(TestCase):
    """Backfill exacto agrupa; fuzzy → candidata; idempotente (#428)."""

    def test_exact_groups_share_identity(self):
        club = Club.objects.create(federation_id='c1', official_name='Alaro')
        cat = Category.objects.create(name='Senior')
        a = Team.objects.create(
            name='ALARO X', federation_id='a', club=club, category=cat, sponsor_name='X',
        )
        b = Team.objects.create(
            name='ALARO Y', federation_id='b', club=club, category=cat, sponsor_name='Y',
        )
        backfill_team_identities()
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.identity_id, b.identity_id)
        self.assertIsNotNone(a.identity_id)

    def test_fuzzy_creates_candidate_not_merge(self):
        club = Club.objects.create(federation_id='c1', official_name='Luci')
        cat = Category.objects.create(name='Senior')
        a = Team.objects.create(name="LUCI'S WORD", federation_id='a', club=club, category=cat)
        b = Team.objects.create(name="LUCI'S WORK", federation_id='b', club=club, category=cat)
        backfill_team_identities()
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertNotEqual(a.identity_id, b.identity_id)
        self.assertTrue(TeamIdentityCandidate.objects.filter(status='pending').exists())

    def test_idempotent(self):
        club = Club.objects.create(federation_id='c1', official_name='Alaro')
        cat = Category.objects.create(name='Senior')
        Team.objects.create(name='ALARO', federation_id='a', club=club, category=cat)
        backfill_team_identities()
        n = TeamIdentity.objects.count()
        backfill_team_identities()
        self.assertEqual(TeamIdentity.objects.count(), n)

    def test_skips_without_club_or_category(self):
        Team.objects.create(name='HUERFANO', federation_id='h')
        backfill_team_identities()
        self.assertIsNone(Team.objects.get(federation_id='h').identity_id)


class NotifyIdentityCandidatesTests(TestCase):
    """Aviso técnico al crear candidatas, como ligas (#428)."""

    @override_settings(TECHNICAL_ALERT_EMAILS=['tech@example.com'], NOTIFICATION_EMAIL_ENABLED=True)
    @patch('ilovevoley.teams.identity.send_notification_email')
    def test_sends_email_to_technical_alerts(self, mock_send):
        club = Club.objects.create(federation_id='c1', official_name='CV Portol')
        category = Category.objects.create(name='Infantil')
        identity = TeamIdentity.objects.create(
            club=club, category=category, gender='',
            core_name='PORTOL', core_name_normalized='PORTOL',
        )
        team = Team.objects.create(
            name='PORTOL X', federation_id='t-mail', club=club, category=category,
        )
        candidate = TeamIdentityCandidate.objects.create(
            new_team=team, suggested_identity=identity, reason='similar', status='pending',
        )
        n = notify_new_identity_candidates([candidate])
        self.assertEqual(n, 1)
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs['recipient_list'], ['tech@example.com'])


class ResolveTeamIdentityTests(TestCase):
    """Auto-enlace solo exacto; duda → candidata; colores distintos (#428)."""

    def setUp(self):
        self.club = Club.objects.create(federation_id='c1', official_name='CV Portol')
        self.category = Category.objects.create(name='Infantil', gender='male')

    def _team(self, name, fed, **kwargs):
        return Team.objects.create(
            name=name, federation_id=fed, club=self.club, category=self.category, **kwargs,
        )

    def test_exact_core_name_links_existing_identity(self):
        old = self._team('ALARO CLINICA DENTAL', 'old', sponsor_name='CLINICA DENTAL')
        identity, _ = resolve_team_identity(old, sponsor_name='CLINICA DENTAL')
        self.assertIsNotNone(identity)

        new = self._team('ALARO CONSTRUCCIONES NIU', 'new', sponsor_name='CONSTRUCCIONES NIU')
        linked, candidate = resolve_team_identity(new, sponsor_name='CONSTRUCCIONES NIU')
        new.refresh_from_db()
        self.assertEqual(linked.pk, identity.pk)
        self.assertEqual(new.identity_id, identity.pk)
        self.assertIsNone(candidate)

    def test_portol_rojo_and_negro_are_distinct_identities(self):
        rojo = self._team('PORTOL ROJO', 'r1')
        id_rojo, _ = resolve_team_identity(rojo)
        negro = self._team('PORTOL NEGRO', 'n1')
        id_negro, candidate = resolve_team_identity(negro)
        negro.refresh_from_db()
        self.assertNotEqual(id_negro.pk, id_rojo.pk)
        self.assertEqual(negro.identity_id, id_negro.pk)
        self.assertIsNone(candidate)

    def test_similar_but_not_exact_creates_pending_candidate(self):
        old = self._team("LUCI'S WORD", 'old')
        identity, _ = resolve_team_identity(old)
        new = self._team("LUCI'S WORK", 'new')
        linked, candidate = resolve_team_identity(new)
        new.refresh_from_db()
        self.assertIsNone(linked)
        self.assertIsNone(new.identity_id)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.status, 'pending')
        self.assertEqual(candidate.suggested_identity_id, identity.pk)

    def test_does_not_duplicate_pending_candidate_on_resolve(self):
        old = self._team("LUCI'S WORD", 'old')
        resolve_team_identity(old)
        new = self._team("LUCI'S WORK", 'new')
        _, first = resolve_team_identity(new)
        self.assertIsNotNone(first)
        _, second = resolve_team_identity(new)
        self.assertIsNone(second)
        self.assertEqual(
            TeamIdentityCandidate.objects.filter(new_team=new, status='pending').count(),
            1,
        )

    def test_without_club_leaves_identity_null(self):
        team = Team.objects.create(
            name='SIN CLUB', federation_id='orphan', category=self.category,
        )
        identity, candidate = resolve_team_identity(team)
        team.refresh_from_db()
        self.assertIsNone(identity)
        self.assertIsNone(candidate)
        self.assertIsNone(team.identity_id)

    def test_reject_when_team_already_has_identity_just_marks_rejected(self):
        a = self._team('EQUIPO ALPHA', 'a')
        b = self._team('EQUIPO BETA', 'b')
        id_a, _ = resolve_team_identity(a)
        id_b, _ = resolve_team_identity(b)
        self.assertIsNotNone(id_a)
        self.assertIsNotNone(id_b)
        candidate = TeamIdentityCandidate.objects.create(
            new_team=a, suggested_identity=id_b, status='pending', reason='backfill',
        )
        candidate.reject()
        a.refresh_from_db()
        candidate.refresh_from_db()
        self.assertEqual(a.identity_id, id_a.pk)
        self.assertEqual(candidate.status, 'rejected')

    def test_approve_moves_all_appearances_of_source_identity(self):
        a1 = self._team('EQUIPO ALPHA', 'a1')
        id_alpha, _ = resolve_team_identity(a1)
        a2 = self._team('EQUIPO ALPHA DOS', 'a2')
        a2.identity = id_alpha
        a2.save(update_fields=['identity'])
        b = self._team('EQUIPO BETA', 'b')
        id_beta, _ = resolve_team_identity(b)
        candidate = TeamIdentityCandidate.objects.create(
            new_team=a1, suggested_identity=id_beta, status='pending', reason='backfill',
        )
        candidate.approve()
        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertEqual(a1.identity_id, id_beta.pk)
        self.assertEqual(a2.identity_id, id_beta.pk)


class CoreNameTests(TestCase):
    """Strip de sponsor solo con señal; conservar color (#428)."""

    def test_strips_sponsor_when_signal_present(self):
        self.assertEqual(
            extract_core_name('ALARO CONSTRUCCIONES NIU', sponsor_name='CONSTRUCCIONES NIU'),
            'ALARO',
        )

    def test_does_not_strip_color_tokens(self):
        self.assertEqual(extract_core_name('PORTOL ROJO'), 'PORTOL ROJO')
        self.assertEqual(extract_core_name('PORTOL NEGRO'), 'PORTOL NEGRO')
        self.assertNotEqual(
            normalize_core_name('PORTOL ROJO'),
            normalize_core_name('PORTOL NEGRO'),
        )

    def test_no_blind_strip_without_sponsor_signal(self):
        self.assertEqual(
            extract_core_name('ALARO CONSTRUCCIONES NIU'),
            'ALARO CONSTRUCCIONES NIU',
        )


class TeamIdentityModelTests(TestCase):
    """Unique de identidad y efecto de aprobar/rechazar candidata (#428)."""

    def setUp(self):
        self.club = Club.objects.create(federation_id='c1', official_name='CV Portol')
        self.category = Category.objects.create(name='Infantil')

    def test_unique_club_category_gender_core_name(self):
        TeamIdentity.objects.create(
            club=self.club, category=self.category, gender='male',
            core_name='PORTOL ROJO', core_name_normalized='PORTOL ROJO',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TeamIdentity.objects.create(
                    club=self.club, category=self.category, gender='male',
                    core_name='PORTOL ROJO', core_name_normalized='PORTOL ROJO',
                )

    def test_approve_candidate_links_team_to_suggested_identity(self):
        identity = TeamIdentity.objects.create(
            club=self.club, category=self.category, gender='',
            core_name='PORTOL', core_name_normalized='PORTOL',
        )
        team = Team.objects.create(
            name='PORTOL CLINICA', federation_id='t-new', club=self.club, category=self.category,
        )
        candidate = TeamIdentityCandidate.objects.create(
            new_team=team, suggested_identity=identity, reason='similar', status='pending',
        )
        candidate.approve()
        team.refresh_from_db()
        candidate.refresh_from_db()
        self.assertEqual(team.identity_id, identity.pk)
        self.assertEqual(candidate.status, 'approved')

    def test_reject_candidate_creates_fresh_identity(self):
        suggested = TeamIdentity.objects.create(
            club=self.club, category=self.category, gender='',
            core_name='OTRO', core_name_normalized='OTRO',
        )
        team = Team.objects.create(
            name='PORTOL ROJO', federation_id='t-new', club=self.club, category=self.category,
        )
        candidate = TeamIdentityCandidate.objects.create(
            new_team=team, suggested_identity=suggested, reason='similar', status='pending',
        )
        candidate.reject()
        team.refresh_from_db()
        candidate.refresh_from_db()
        self.assertIsNotNone(team.identity_id)
        self.assertNotEqual(team.identity_id, suggested.pk)
        self.assertEqual(candidate.status, 'rejected')
