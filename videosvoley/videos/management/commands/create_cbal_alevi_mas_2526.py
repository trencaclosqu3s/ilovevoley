from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand

from videosvoley.videos.models import Category, Club, League, Match, Team

MADRID = ZoneInfo('Europe/Madrid')
CITY = 'Alaró'
SEASON = '2025-26'
VENUE_BASE = "Poliesportiu Municipal d'Alaró"


GRUPOS_DATA = {
    'A': {
        'orden': 1,
        'equipos': [
            # (nombre, federation_id, club_id, es_nuestro)
            ('Algaida Volei Club', 'cbal_alevi_mas_2526_a1', 4, False),
            ('Club Vòlei Artà', 'cbal_alevi_mas_2526_a2', 16, False),
            ('Voley Palma', 'cbal_alevi_mas_2526_a3', 46, False),
            ('Club Volei Maó', 'cbal_alevi_mas_2526_a4', None, False),
        ],
    },
    'B': {
        'orden': 2,
        'equipos': [
            ('Club Voleibol Pórtol', 'cbal_alevi_mas_2526_b1', 30, False),
            ('Club Voleibol Cide', 'cbal_alevi_mas_2526_b2', 24, False),
            ('Club Deportivo Mestral Ibiza Voley', 'cbal_alevi_mas_2526_b3', 8, False),
            ('Club Voleibol Vilafranca', 'cbal_alevi_mas_2526_b4', 35, False),
        ],
    },
    'C': {
        'orden': 3,
        'equipos': [
            ('Club Esportiu Sant Josep Obrer', 'cbal_alevi_mas_2526_c1', 12, True),
            ('Alaró Volei Club Esportiu', 'cbal_alevi_mas_2526_c2', 3, False),
            ('Club Voleibol Manacor', 'cbal_alevi_mas_2526_c3', 27, False),
            ('CVP La Tribu Ibiza', 'cbal_alevi_mas_2526_c4', 38, False),
        ],
    },
}

# Primera fase: (key_local, key_visitante, fecha, hora, minutos, pista)
# key format: 'a1', 'b3', 'c2' etc.
PRIMERA_FASE = [
    # Grupo A
    ('a1', 'a4', '2026-05-16', 12, 0,  1),
    ('a2', 'a3', '2026-05-16', 12, 30, 1),
    ('a4', 'a3', '2026-05-16', 14, 0,  1),
    ('a1', 'a2', '2026-05-16', 14, 0,  2),
    ('a3', 'a1', '2026-05-16', 14, 30, 2),
    ('a2', 'a4', '2026-05-16', 14, 30, 3),
    # Grupo B
    ('b1', 'b4', '2026-05-16', 12, 0,  2),
    ('b2', 'b3', '2026-05-16', 13, 0,  1),
    ('b4', 'b3', '2026-05-16', 13, 30, 1),
    ('b1', 'b2', '2026-05-16', 13, 30, 2),
    ('b3', 'b1', '2026-05-16', 14, 0,  5),
    ('b2', 'b4', '2026-05-16', 14, 30, 1),
    # Grupo C
    ('c1', 'c4', '2026-05-16', 12, 30, 2),
    ('c2', 'c3', '2026-05-16', 13, 0,  2),
    ('c4', 'c3', '2026-05-16', 14, 0,  3),
    ('c1', 'c2', '2026-05-16', 14, 0,  4),
    ('c3', 'c1', '2026-05-16', 14, 30, 4),
    ('c2', 'c4', '2026-05-16', 14, 30, 5),
]

# Segunda fase y finales: (texto_local, texto_visitante, fecha, hora, minutos, pista, fase)
# fase: 'or' | 'plata'
SEGUNDA_FASE_Y_FINALES = [
    # --- Grupo A OR ---
    ('1r Grupo A', '2n Grupo C',  '2026-05-16', 16, 30, 1, 'or'),
    ('2n Grupo C', '2n Grupo B',  '2026-05-16', 17, 0,  3, 'or'),
    ('2n Grupo B', '1r Grupo A',  '2026-05-16', 18, 0,  1, 'or'),
    # --- Grupo B OR ---
    ('1r Grupo B', '2n Grupo A',  '2026-05-16', 16, 30, 2, 'or'),
    ('2n Grupo A', '1r Grupo C',  '2026-05-16', 17, 0,  4, 'or'),
    ('1r Grupo C', '1r Grupo B',  '2026-05-16', 18, 0,  2, 'or'),
    # --- Finals OR (SF + 3r/4t + Final) ---
    ('1r Grupo A OR', '2n Grupo B OR', '2026-05-17', 9,  0,  1, 'or'),
    ('1r Grupo B OR', '2n Grupo A OR', '2026-05-17', 9,  0,  3, 'or'),
    ('Perdedor SF1 OR', 'Perdedor SF2 OR', '2026-05-17', 10, 30, 1, 'or'),
    ('Guanyador SF1 OR', 'Guanyador SF2 OR', '2026-05-17', 12, 0,  1, 'or'),
    # --- Grupo A Plata ---
    ('3r Grupo A', '4t Grupo B',  '2026-05-16', 18, 0,  5, 'plata'),
    ('4t Grupo C', '3r Grupo A',  '2026-05-16', 18, 30, 3, 'plata'),
    ('4t Grupo B', '4t Grupo C',  '2026-05-16', 19, 0,  3, 'plata'),
    # --- Grupo B Plata (corregido: "4t grup D" del PDF es error → 3r Grupo C) ---
    ('3r Grupo B', '4t Grupo A',  '2026-05-16', 18, 0,  6, 'plata'),
    ('3r Grupo C', '3r Grupo B',  '2026-05-16', 18, 30, 4, 'plata'),
    ('4t Grupo A', '3r Grupo C',  '2026-05-16', 19, 0,  4, 'plata'),
    # --- Finals Plata ---
    ('2n Grupo A Plata', '2n Grupo B Plata', '2026-05-17', 10, 0,  5, 'plata'),
    ('1r Grupo A Plata', '1r Grupo B Plata', '2026-05-17', 10, 30, 5, 'plata'),
]


def _venue(pista: int) -> str:
    return f"{VENUE_BASE} - Pista {pista}"


class Command(BaseCommand):
    help = 'Crea el CBAL Alevín Masculino 2025-26: liga, 3 grupos, 12 equipos y todos los partidos'

    def handle(self, *args, **options):
        category = Category.objects.get(id=3)  # Alevín

        # --- Liga principal ---
        main_league, created = League.objects.get_or_create(
            federation_id='cbal_alevi_mas_2526',
            season=SEASON,
            defaults={
                'name': 'CBAL - Campionat de Balears Alevín Masculino',
                'competition_type': 'cup',
                'match_format': 'tournament_3sets',
                'visibility_type': 'main',
                'is_our_team_related': True,
            },
        )
        main_league.categories.add(category)
        label = 'CREADA' if created else 'ya existe'
        self.stdout.write(self.style.SUCCESS(f'Liga principal [{label}]: {main_league.name}'))

        # --- Sub-ligas primera fase ---
        grupo_leagues = {}
        grupo_teams = {}   # {'a1': Team, 'a2': Team, ...}

        for grupo, data in GRUPOS_DATA.items():
            gl, created = League.objects.get_or_create(
                federation_id=f'cbal_alevi_mas_2526_grupo_{grupo.lower()}',
                season=SEASON,
                defaults={
                    'name': f'CBAL Alevín Mas. 2025-26 - Grupo {grupo}',
                    'competition_type': 'cup',
                    'match_format': 'tournament_3sets',
                    'visibility_type': 'main',
                    'parent_league': main_league,
                    'phase_name': f'Grupo {grupo}',
                    'phase_order': data['orden'],
                    'is_our_team_related': grupo == 'C',
                },
            )
            gl.categories.add(category)
            label = 'CREADO' if created else 'ya existe'
            self.stdout.write(f'  Grupo {grupo} [{label}]')
            grupo_leagues[grupo] = gl

            for i, (name, fed_id, club_id, _) in enumerate(data['equipos'], 1):
                club = Club.objects.filter(id=club_id).first() if club_id else None
                team, created = Team.objects.get_or_create(
                    federation_id=fed_id,
                    defaults={
                        'name': name,
                        'category': category,
                        'club': club,
                        'is_active': True,
                    },
                )
                label = 'CREADO' if created else 'ya existe'
                self.stdout.write(f'    {grupo}{i}. {team.name} [{label}]')
                grupo_teams[f'{grupo.lower()}{i}'] = team

        # --- Sub-ligas segunda fase ---
        fase_or, created = League.objects.get_or_create(
            federation_id='cbal_alevi_mas_2526_or',
            season=SEASON,
            defaults={
                'name': 'CBAL Alevín Mas. 2025-26 - Fase OR',
                'competition_type': 'cup',
                'match_format': 'tournament_3sets',
                'visibility_type': 'main',
                'parent_league': main_league,
                'phase_name': 'Fase OR',
                'phase_order': 4,
                'is_our_team_related': True,
            },
        )
        fase_or.categories.add(category)
        label = 'CREADA' if created else 'ya existe'
        self.stdout.write(f'  Fase OR [{label}]')

        fase_plata, created = League.objects.get_or_create(
            federation_id='cbal_alevi_mas_2526_plata',
            season=SEASON,
            defaults={
                'name': 'CBAL Alevín Mas. 2025-26 - Fase Plata',
                'competition_type': 'cup',
                'match_format': 'tournament_3sets',
                'visibility_type': 'main',
                'parent_league': main_league,
                'phase_name': 'Fase Plata',
                'phase_order': 5,
                'is_our_team_related': False,
            },
        )
        fase_plata.categories.add(category)
        label = 'CREADA' if created else 'ya existe'
        self.stdout.write(f'  Fase Plata [{label}]')

        # --- Partidos primera fase ---
        self.stdout.write('\nCreando partidos de primera fase...')
        creados = existentes = 0

        for (key_home, key_away, fecha, hora, mins, pista) in PRIMERA_FASE:
            home = grupo_teams[key_home]
            away = grupo_teams[key_away]
            grupo_letra = key_home[0].upper()
            league = grupo_leagues[grupo_letra]
            match_date = datetime(
                *[int(x) for x in fecha.split('-')], hora, mins, 0, tzinfo=MADRID
            )
            m, created = Match.objects.get_or_create(
                league=league,
                home_team=home,
                away_team=away,
                match_date=match_date,
                defaults={
                    'status': 'scheduled',
                    'round_number': 1,
                    'venue': _venue(pista),
                    'city': CITY,
                },
            )
            if created:
                creados += 1
            else:
                existentes += 1

        self.stdout.write(f'  Creados: {creados} | ya existían: {existentes}')

        # --- Partidos segunda fase y finales (placeholders) ---
        self.stdout.write('Creando partidos segunda fase y finales (placeholders)...')
        creados = existentes = 0

        for (txt_home, txt_away, fecha, hora, mins, pista, fase) in SEGUNDA_FASE_Y_FINALES:
            league = fase_or if fase == 'or' else fase_plata
            match_date = datetime(
                *[int(x) for x in fecha.split('-')], hora, mins, 0, tzinfo=MADRID
            )
            round_num = 3 if any(
                w in txt_home for w in ('Guanyador', 'Perdedor', 'Plata')
            ) else 2
            m, created = Match.objects.get_or_create(
                league=league,
                home_team_text=txt_home,
                away_team_text=txt_away,
                match_date=match_date,
                defaults={
                    'status': 'scheduled',
                    'round_number': round_num,
                    'venue': _venue(pista),
                    'city': CITY,
                },
            )
            if created:
                creados += 1
            else:
                existentes += 1

        self.stdout.write(f'  Creados: {creados} | ya existían: {existentes}')

        total = Match.objects.filter(league__parent_league=main_league).count()
        total += Match.objects.filter(league=main_league).count()
        self.stdout.write(
            self.style.SUCCESS(
                f'\nCBAL Alevín Masculino 2025-26 configurado. '
                f'Liga ID: {main_league.id} | Partidos totales: {total}'
            )
        )
