"""Descubrimiento de ligas desde el menú de competiciones de voleibolib.

El menú es HTML con tres niveles: sección (AUTONÓMICA, INSULAR ESCOLAR
MALLORCA…) → categoría → fase con enlace ``clasificaciones?id={federation_id}``.
Solo se proponen las ligas donde juega algún equipo de un tenant: la clasificación
solo trae nombres de equipo (sin ids), así que se cruza con ``club_team_names``,
igual que el resto de filtros por tenant (nunca difuso, ver #380).
"""
import html
import logging
import re
import unicodedata

import requests

from ilovevoley.core.models import Category, Organization, infer_gender_from_name

from .balearic_callups_client import DEFAULT_HEADERS, calculate_federation_temp

BASE_URL = 'https://www.voleibolib.net'
MENU_URL = BASE_URL + '/JSON/get_Menu_Competiciones.asp?temp={temp}'
STANDINGS_URL = BASE_URL + '/JSON/get_clasificacion.asp?id={federation_id}'
TIMEOUT = 20

logger = logging.getLogger(__name__)

_MENU_TOKEN = re.compile(
    r'<a data-toggle="collapse"[^>]*?href="#\d+"[^>]*?(?P<is_category>class="category")?>\s*(?P<label>.*?)\s*(?:<i class|</a>)'
    r'|<p class="fase">(?P<fase>[^<]*)</p>'
    # Con grupos el enlace lleva ``title=`` y un icono dentro: ``<a href="…" title="…"><i></i> GRUP A</a>``
    r'|<a href="clasificaciones\?id=(?P<id>\d+)[^"]*"[^>]*>(?P<phase>.*?)</a>',
    re.S,
)
_TAG = re.compile(r'<[^>]+>')
_TEAM_CELL = re.compile(r"<tr><td>\d+\.</td><td>(.*?)</td>", re.S)
_CATEGORY_KEYWORDS = ('benjamin', 'alevin', 'infantil', 'cadete', 'juvenil', 'junior', 'senior')
# Categorías de formación cuyo histórico alimenta el H2H (#404).
BASE_CATEGORY_KEYWORDS = ('alevin', 'infantil', 'cadete', 'juvenil')


def _strip_accents(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')


def _normalize(text):
    return re.sub(r'\s+', ' ', _strip_accents(html.unescape(text or '')).lower()).strip()


def parse_menu(menu_html):
    """Lista de dicts ``section, category_label, phase_label, federation_id``."""
    section = category = fase = ''
    rows = []
    for match in _MENU_TOKEN.finditer(menu_html):
        if match['fase'] is not None:
            fase = html.unescape(match['fase']).strip()
        elif match['id']:
            label = html.unescape(_TAG.sub('', match['phase'])).strip()
            rows.append({
                'section': section,
                'category_label': category,
                # Fase con grupos: "Liga Regular - GRUP A"; con un solo enlace, la fase es el propio enlace
                'phase_label': f'{fase} - {label}' if fase and match['phase'].lstrip().startswith('<i') else label,
                'federation_id': match['id'],
            })
        elif match['is_category']:
            category = html.unescape(match['label']).strip()
            fase = ''
        else:
            section = html.unescape(match['label']).strip()
            category = fase = ''
    return rows


def detect_category(category_label):
    """``Category`` que casa con la etiqueta del menú, o ``None`` si es ambigua.

    Hace falta palabra de categoría y género claros ("Categoria unificada" o
    "ALEVIN" a secas no casan: el superuser las asigna al aprobar).
    """
    normalized = _normalize(category_label)
    gender = infer_gender_from_name(normalized)
    keyword = next((k for k in _CATEGORY_KEYWORDS if k in normalized), None)
    if not (gender and keyword):
        return None
    # Pocas categorías, se compara en Python sin depender de la extensión unaccent
    return next(
        (c for c in Category.objects.filter(gender=gender) if keyword in _normalize(c.name)), None,
    )


def fetch_menu(temp, session=requests):
    response = session.get(MENU_URL.format(temp=temp), headers=DEFAULT_HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def fetch_team_names(federation_id, session=requests):
    response = session.get(STANDINGS_URL.format(federation_id=federation_id), headers=DEFAULT_HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return [html.unescape(name).strip() for name in _TEAM_CELL.findall(response.text)]


def matching_tenants(team_names, organizations):
    """``{Organization: [equipos]}`` de los tenants con algún equipo en ``team_names``."""
    normalized = [(name, _normalize(name)) for name in team_names]
    result = {}
    for organization in organizations:
        # Sin fallback de settings: un tenant sin nombres no debe casar con equipos ajenos
        club_names = [norm for n in (organization.club_team_names or {}).values() if n and (norm := _normalize(n))]
        teams = [name for name, norm in normalized if any(club in norm for club in club_names)]
        if teams:
            result[organization] = teams
    return result


def discover(season):
    """Crea ``LeagueCandidate`` pendientes para las ligas nuevas con equipos de un tenant.

    Devuelve las candidatas nuevas por validar (las ligas manuales enlazadas no cuentan). Las ya conocidas (liga o candidata, también
    rechazadas) no se vuelven a pedir. Las clasificaciones vacías o caídas se
    reintentan en la siguiente ejecución (al inicio aún no hay equipos). Una
    clasificación con equipos pero ninguno de un tenant se guarda como rechazada,
    sin equipos coincidentes, para no pedirla cada día; si un tenant cambia sus
    ``club_team_names`` hay que reabrirla a mano.
    """
    if season is None:
        return []

    from ..models import League, LeagueCandidate

    # Ligas dadas de alta a mano: se enlazan con su fila del menú (mismo federation_id)
    # para que cuenten como posible liga padre de fases nuevas
    manual = {league.federation_id: league for league in League.objects.filter(candidate__isnull=True)}
    known = set(League.objects.values_list('federation_id', flat=True))
    known |= set(LeagueCandidate.objects.values_list('federation_id', flat=True))
    organizations = list(Organization.objects.filter(is_active=True))

    created = []
    with requests.Session() as session:
        for row in parse_menu(fetch_menu(calculate_federation_temp(season), session)):
            if row['federation_id'] in manual:
                # update_or_create: si antes se guardó como rechazada (ajena), ya existe la fila
                LeagueCandidate.objects.update_or_create(
                    federation_id=row['federation_id'],
                    defaults={
                        **row, 'season': season, 'status': 'approved',
                        'league': manual.pop(row['federation_id']),
                        'category': detect_category(row['category_label']),
                    },
                )
                continue
            if row['federation_id'] in known:
                continue
            try:
                team_names = fetch_team_names(row['federation_id'], session)
            except requests.RequestException:
                logger.warning('No se pudo leer la clasificación federativa %s', row['federation_id'])
                continue
            if not team_names:
                continue
            tenants = matching_tenants(team_names, organizations)
            if not tenants:
                LeagueCandidate.objects.create(season=season, status='rejected', **row)
                known.add(row['federation_id'])
                continue
            # La federación a veces crea otra sección con la misma categoría y a veces
            # cuelga la fase de la liga existente: solo se sugiere, decide el superuser
            parent = (
                League.objects.filter(
                    candidate__season=season, candidate__category_label__iexact=row['category_label'],
                    parent_league__isnull=True,
                ).order_by('created_at').first()
                if row['category_label'] else None
            )
            candidate = LeagueCandidate.objects.create(
                season=season, parent_league=parent,
                category=detect_category(row['category_label']),
                matched_teams={org.slug: teams for org, teams in tenants.items()},
                **row,
            )
            created.append(candidate)
            known.add(row['federation_id'])
    return created


def is_base_category(category_label):
    """True si la etiqueta es una categoría de formación (Alevín/Infantil/Cadete/Juvenil).

    No exige género: el histórico puede incluir masculino, femenino o mixto, y
    es el superuser quien decide en la cola qué candidatas valida.
    """
    normalized = _normalize(category_label)
    return any(keyword in normalized for keyword in BASE_CATEGORY_KEYWORDS)


def discover_historical(seasons):
    """Propone como candidatas las ligas base de temporadas pasadas con equipos de un tenant.

    A diferencia de ``discover``, marca las candidatas con ``is_historical=True``
    para que al aprobarlas se creen como ligas históricas inactivas (fuera de la
    navegación y de las tareas periódicas). No crea ligas: el superuser elige en
    la cola cuáles sincroniza. Omite federaciones ya conocidas (liga o candidata),
    así la ingesta histórica no colisiona con las de la temporada activa.

    Devuelve las candidatas nuevas (idempotente entre ejecuciones).
    """
    if not seasons:
        return []

    from ..models import League, LeagueCandidate

    organizations = list(Organization.objects.filter(is_active=True))
    known = set(League.objects.values_list('federation_id', flat=True))
    known |= set(LeagueCandidate.objects.values_list('federation_id', flat=True))

    created = []
    with requests.Session() as session:
        for season in seasons:
            try:
                menu = parse_menu(fetch_menu(calculate_federation_temp(season), session))
            except requests.RequestException:
                logger.warning('No se pudo leer el menú federativo de %s', season)
                continue
            for row in menu:
                if row['federation_id'] in known or not is_base_category(row['category_label']):
                    continue
                try:
                    team_names = fetch_team_names(row['federation_id'], session)
                except requests.RequestException:
                    logger.warning('No se pudo leer la clasificación federativa %s', row['federation_id'])
                    continue
                tenants = matching_tenants(team_names, organizations)
                if not tenants:
                    continue
                candidate = LeagueCandidate.objects.create(
                    season=season, status='pending', is_historical=True,
                    category=detect_category(row['category_label']),
                    matched_teams={org.slug: teams for org, teams in tenants.items()},
                    **row,
                )
                created.append(candidate)
                known.add(row['federation_id'])
    return created
