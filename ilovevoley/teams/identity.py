"""Identidad estable de equipo entre temporadas (#428)."""

from difflib import SequenceMatcher

from django.db import IntegrityError

from ilovevoley.core.email_utils import send_notification_email
from ilovevoley.videos.utils import normalize_team_name

# Umbral solo para CREAR candidatas, nunca para auto-enlace.
CANDIDATE_SIMILARITY_MIN = 0.85


def effective_gender(team) -> str:
    if getattr(team, 'gender', None):
        return team.gender
    category = getattr(team, 'category', None)
    if category is not None and getattr(category, 'gender', None):
        return category.gender
    return ''


def extract_core_name(display_name: str, sponsor_name: str = '') -> str:
    """Nombre núcleo: quita patrocinador solo con señal; conserva color/letra.

    ``sponsor_name`` es la señal ELOCALPAT cuando difiere del nombre base. Si el
    PAT es un fragmento del nombre, se recorta; si es otra cadena de marca
    (p. ej. nombre corto en ELOCAL y branding en PAT), el núcleo es el nombre base.
    """
    name = (display_name or '').strip()
    sponsor = (sponsor_name or '').strip()
    if not name:
        return ''
    norm_name = normalize_team_name(name)
    if not sponsor:
        return norm_name
    norm_sponsor = normalize_team_name(sponsor)
    if not norm_sponsor or norm_sponsor == norm_name:
        return norm_name
    if norm_sponsor in norm_name:
        parts = norm_name.replace(norm_sponsor, ' ').split()
        return ' '.join(parts) if parts else norm_name
    # PAT distinto y no contenido: el nombre federativo base ya es el núcleo.
    return norm_name


def _root_team(team):
    root = team
    seen = set()
    while getattr(root, 'parent_team_id', None) and root.pk not in seen:
        seen.add(root.pk)
        parent = getattr(root, 'parent_team', None)
        if parent is None:
            break
        root = parent
    return root


def create_identity_for_team(team, *, sponsor_name: str = ''):
    from ilovevoley.teams.models import TeamIdentity

    sponsor = sponsor_name or getattr(team, 'sponsor_name', '') or ''
    core = extract_core_name(team.name, sponsor)
    gender = effective_gender(team)
    if team.club_id and team.category_id and core:
        try:
            identity, _ = TeamIdentity.objects.get_or_create(
                club_id=team.club_id,
                category_id=team.category_id,
                gender=gender,
                core_name_normalized=core,
                defaults={
                    'club_id': team.club_id,
                    'category_id': team.category_id,
                    'core_name': core,
                },
            )
            return identity
        except IntegrityError:
            return TeamIdentity.objects.get(
                club_id=team.club_id,
                category_id=team.category_id,
                gender=gender,
                core_name_normalized=core,
            )
    return TeamIdentity.objects.create(
        club=team.club,
        category=team.category,
        gender=gender,
        core_name=core,
        core_name_normalized=core,
    )


def resolve_team_identity(team, *, sponsor_name: str = ''):
    """Devuelve ``(identity|None, candidate|None)``.

    Exacto → asigna identity. Duda → candidata con identity NULL.
    Ninguno → crea identity nueva y la asigna.
    Variantes: heredan la identidad del root.
    """
    from ilovevoley.teams.models import TeamIdentity, TeamIdentityCandidate

    sponsor = sponsor_name or getattr(team, 'sponsor_name', '') or ''

    root = _root_team(team)
    if root is not team:
        if not root.identity_id:
            resolve_team_identity(root, sponsor_name=sponsor)
            root.refresh_from_db()
        if root.identity_id:
            team.identity = root.identity
            team.save(update_fields=['identity'])
            return root.identity, None

    core = extract_core_name(team.name, sponsor)
    gender = effective_gender(team)

    # Sin club/categoría no hay clave fiable: dejar NULL para reintentar luego
    # (alineado con el backfill; evita identidades huérfanas permanentes).
    if not team.club_id or not team.category_id or not core:
        return None, None

    qs = TeamIdentity.objects.filter(
        club_id=team.club_id,
        category_id=team.category_id,
        gender=gender,
    )
    exact = qs.filter(core_name_normalized=core).first()
    if exact:
        team.identity = exact
        team.save(update_fields=['identity'])
        return exact, None

    best, best_score = None, 0.0
    for identity in qs.iterator():
        score = SequenceMatcher(None, core, identity.core_name_normalized).ratio()
        if score > best_score:
            best, best_score = identity, score

    if best and CANDIDATE_SIMILARITY_MIN <= best_score < 1.0:
        if TeamIdentityCandidate.objects.filter(new_team=team, status='pending').exists():
            return None, None
        suggested_team = best.teams.order_by('-created_at').first()
        candidate = TeamIdentityCandidate.objects.create(
            new_team=team,
            suggested_identity=best,
            suggested_team=suggested_team,
            score=best_score,
            reason=f'similaridad {best_score:.2f}; mismo club+categoría',
            status='pending',
        )
        return None, candidate

    identity = create_identity_for_team(team, sponsor_name=sponsor)
    team.identity = identity
    team.save(update_fields=['identity'])
    return identity, None


def notify_new_identity_candidates(candidates):
    """Email a técnicos cuando hay vínculos pendientes (como ligas candidatas)."""
    if not candidates:
        return 0

    from django.urls import reverse
    from django.utils.translation import gettext as _

    from ilovevoley.core.email_utils import get_technical_alert_emails
    from ilovevoley.core.tenant_utils import build_absolute_url

    send_notification_email(
        subject=lambda: _('%(count)s vínculos de equipo pendientes de validar') % {
            'count': len(candidates),
        },
        template_name='emails/team_identity_candidates_pending.html',
        context={
            'candidates': candidates,
            'count': len(candidates),
            'site_name': 'I Love Voley',
            'admin_url': build_absolute_url(
                reverse('admin:teams_teamidentitycandidate_changelist') + '?status__exact=pending'
            ),
        },
        recipient_list=get_technical_alert_emails(),
    )
    return len(candidates)


def _gender_for_backfill(team, category_by_id):
    gender = getattr(team, 'gender', None) or ''
    if gender:
        return gender
    category = category_by_id.get(team.category_id)
    if category is not None:
        return getattr(category, 'gender', None) or ''
    return ''


def backfill_team_identities(
    team_model=None,
    identity_model=None,
    candidate_model=None,
    category_model=None,
):
    """Agrupa apariciones exactas; deja fuzzy como candidatas. Idempotente."""
    from collections import defaultdict

    from ilovevoley.teams.models import Team, TeamIdentity, TeamIdentityCandidate

    TeamModel = team_model or Team
    IdentityModel = identity_model or TeamIdentity
    CandidateModel = candidate_model or TeamIdentityCandidate
    CategoryModel = category_model
    if CategoryModel is None:
        from ilovevoley.core.models import Category
        CategoryModel = Category

    stats = {
        'linked_exact': 0,
        'identities_created': 0,
        'candidates_created': 0,
        'skipped': 0,
    }

    categories = {c.pk: c for c in CategoryModel.objects.all()}
    pending = list(
        TeamModel.objects.filter(
            identity__isnull=True,
            club__isnull=False,
            category__isnull=False,
        ).select_related('parent_team')
    )

    roots = []
    variants = []
    for team in pending:
        if getattr(team, 'parent_team_id', None):
            variants.append(team)
        else:
            roots.append(team)

    groups = defaultdict(list)
    for team in roots:
        core = extract_core_name(team.name, getattr(team, 'sponsor_name', '') or '')
        if not core:
            stats['skipped'] += 1
            continue
        key = (team.club_id, team.category_id, _gender_for_backfill(team, categories), core)
        groups[key].append(team)

    for key, members in groups.items():
        club_id, category_id, gender, core = key
        identity = IdentityModel.objects.filter(
            club_id=club_id,
            category_id=category_id,
            gender=gender,
            core_name_normalized=core,
        ).first()
        if identity is None:
            identity = IdentityModel.objects.create(
                club_id=club_id,
                category_id=category_id,
                gender=gender,
                core_name=core,
                core_name_normalized=core,
            )
            stats['identities_created'] += 1
        for team in members:
            if team.identity_id:
                continue
            team.identity_id = identity.pk
            team.save(update_fields=['identity'])
            stats['linked_exact'] += 1

    # Variantes: heredar del root ya resuelto en esta pasada
    for team in variants:
        root = team
        seen = set()
        while getattr(root, 'parent_team_id', None) and root.pk not in seen:
            seen.add(root.pk)
            parent = getattr(root, 'parent_team', None)
            if parent is None:
                break
            root = parent
        root = TeamModel.objects.filter(pk=root.pk).first() or root
        if getattr(root, 'identity_id', None):
            team.identity_id = root.identity_id
            team.save(update_fields=['identity'])
            stats['linked_exact'] += 1

    # Fuzzy entre identidades distintas del mismo club+categoría
    identities = list(IdentityModel.objects.filter(club__isnull=False, category__isnull=False))
    seen_pairs = set()
    for i, left in enumerate(identities):
        for right in identities[i + 1:]:
            if left.club_id != right.club_id or left.category_id != right.category_id:
                continue
            if left.gender != right.gender:
                continue
            score = SequenceMatcher(
                None, left.core_name_normalized, right.core_name_normalized,
            ).ratio()
            if not (CANDIDATE_SIMILARITY_MIN <= score < 1.0):
                continue
            pair = tuple(sorted((left.pk, right.pk)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            new_team = TeamModel.objects.filter(identity_id=left.pk).order_by('-id').first()
            if new_team is None:
                continue
            if CandidateModel.objects.filter(
                new_team_id=new_team.pk, suggested_identity_id=right.pk, status='pending',
            ).exists():
                continue
            suggested_team = TeamModel.objects.filter(identity_id=right.pk).order_by('-id').first()
            CandidateModel.objects.create(
                new_team_id=new_team.pk,
                suggested_identity_id=right.pk,
                suggested_team_id=suggested_team.pk if suggested_team else None,
                score=score,
                reason=f'backfill similaridad {score:.2f}; mismo club+categoría',
                status='pending',
            )
            stats['candidates_created'] += 1

    stats['skipped'] = TeamModel.objects.filter(identity__isnull=True).count()
    return stats
