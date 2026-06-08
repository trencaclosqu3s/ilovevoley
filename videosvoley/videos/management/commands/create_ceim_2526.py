from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand

from videosvoley.videos.models import Category, Club, League, Match, Team

MADRID = ZoneInfo('Europe/Madrid')
CITY = 'Castelló de la Plana'
SEASON = '2025-26'


GRUPOS_DATA = {
    'A': {
        'orden': 1,
        'venue': 'Pabellón Ciutat Esportiva - Pista 1',
        'address': 'C/ Camí Cuadra Tercera 30, Castellón',
        'equipos': [
            ('AD Eliocroca', 'ceim_2526_a1', False),
            ('CV Sant Josep', 'ceim_2526_a2', True),
            ('Cisneros La Laguna', 'ceim_2526_a3', False),
            ("Ube L'Illa Grau", 'ceim_2526_a4', False),
        ],
    },
    'B': {
        'orden': 2,
        'venue': 'Pabellón Ciutat Esportiva - Pista 2',
        'address': 'C/ Camí Cuadra Tercera 30, Castellón',
        'equipos': [
            ('CV Paterna Liceo Osos', 'ceim_2526_b1', False),
            ('MPT CV Pòrtol', 'ceim_2526_b2', False),
            ('CV Aidean', 'ceim_2526_b3', False),
            ('CV Almendralejo Blanco A', 'ceim_2526_b4', False),
        ],
    },
    'C': {
        'orden': 3,
        'venue': 'Pabellón Ciutat Esportiva - Pista 3',
        'address': 'C/ Camí Cuadra Tercera 30, Castellón',
        'equipos': [
            ('Conqueridor Valencia', 'ceim_2526_c1', False),
            ('CV Oviedo', 'ceim_2526_c2', False),
            ('OBV López Guillén', 'ceim_2526_c3', False),
            ('CD Las Viñas', 'ceim_2526_c4', False),
        ],
    },
    'D': {
        'orden': 4,
        'venue': 'Pabellón Pablo Herrera - Pista 1',
        'address': 'C/ Carrer de la Sardina nº 2, Castellón',
        'equipos': [
            ('Rio Duero Sporting', 'ceim_2526_d1', False),
            ('Adesa 80 Casa Gaspar', 'ceim_2526_d2', False),
            ('Jealsa Boiro', 'ceim_2526_d3', False),
            ('CV Mataró', 'ceim_2526_d4', False),
        ],
    },
    'E': {
        'orden': 5,
        'venue': 'Pabellón Pablo Herrera - Pista 2',
        'address': 'C/ Carrer de la Sardina nº 2, Castellón',
        'equipos': [
            ('CD Salesianos Elche', 'ceim_2526_e1', False),
            ('Indescar Zaragoza', 'ceim_2526_e2', False),
            ('Bus Leader San Roque', 'ceim_2526_e3', False),
            ('VCV Esgueva', 'ceim_2526_e4', False),
        ],
    },
    'F': {
        'orden': 6,
        'venue': 'Pabellón Emilio Fabregat',
        'address': 'C/ Sebastián Elcano 35, 12100 Castellón',
        'equipos': [
            ('ADV Miguelturra', 'ceim_2526_f1', False),
            ('Aldebarán San Sadurniño', 'ceim_2526_f2', False),
            ('Wefferent Mintonette Almería', 'ceim_2526_f3', False),
            ('Cvleganés.com', 'ceim_2526_f4', False),
        ],
    },
    'G': {
        'orden': 7,
        'venue': 'Pabellón Chencho Norte - Pista 1',
        'address': 'C/ Cuadra Colomera s/n, Castellón',
        'equipos': [
            ('FC Barcelona', 'ceim_2526_g1', False),
            ('CD Albarena', 'ceim_2526_g2', False),
            ('Club Voleibol Móstoles A', 'ceim_2526_g3', False),
            ('CID Jovellanos', 'ceim_2526_g4', False),
        ],
    },
    'H': {
        'orden': 8,
        'venue': 'Pabellón Chencho Norte - Pista 2',
        'address': 'C/ Cuadra Colomera s/n, Castellón',
        'equipos': [
            ('Playas de Cartagena', 'ceim_2526_h1', False),
            ('+Vóley Badajoz', 'ceim_2526_h2', False),
            ('Escola Voleibol Sant Joan', 'ceim_2526_h3', False),
            ('CN Sabadell', 'ceim_2526_h4', False),
        ],
    },
}

# (grupo, pos_local, pos_visitante, fecha_iso, hora, round_number)
# Posiciones 1-based; grupo en letra mayúscula
PARTIDOS_PRIMERA_FASE = [
    # Miércoles 27 mayo — Jornada 1
    ('A', 1, 4, '2026-05-27', 17, 0, 1),
    ('A', 2, 3, '2026-05-27', 19, 0, 1),
    ('B', 1, 4, '2026-05-27', 17, 0, 1),
    ('B', 2, 3, '2026-05-27', 19, 0, 1),
    ('C', 1, 4, '2026-05-27', 17, 0, 1),
    ('C', 2, 3, '2026-05-27', 19, 0, 1),
    ('D', 1, 4, '2026-05-27', 17, 0, 1),
    ('D', 2, 3, '2026-05-27', 19, 0, 1),
    ('E', 1, 4, '2026-05-27', 17, 0, 1),
    ('E', 2, 3, '2026-05-27', 19, 0, 1),
    ('F', 1, 4, '2026-05-27', 17, 0, 1),
    ('F', 2, 3, '2026-05-27', 19, 0, 1),
    ('G', 1, 4, '2026-05-27', 17, 0, 1),
    ('G', 2, 3, '2026-05-27', 19, 0, 1),
    ('H', 1, 4, '2026-05-27', 17, 0, 1),
    ('H', 2, 3, '2026-05-27', 19, 0, 1),
    # Jueves 28 mayo — Jornada 2
    ('A', 1, 2, '2026-05-28', 9, 30, 2),
    ('A', 3, 4, '2026-05-28', 11, 30, 2),
    ('B', 1, 2, '2026-05-28', 9, 30, 2),
    ('B', 3, 4, '2026-05-28', 11, 30, 2),
    ('C', 1, 2, '2026-05-28', 9, 30, 2),
    ('C', 3, 4, '2026-05-28', 11, 30, 2),
    ('D', 1, 2, '2026-05-28', 9, 30, 2),
    ('D', 3, 4, '2026-05-28', 11, 30, 2),
    ('E', 1, 2, '2026-05-28', 9, 30, 2),
    ('E', 3, 4, '2026-05-28', 11, 30, 2),
    ('F', 1, 2, '2026-05-28', 9, 30, 2),
    ('F', 3, 4, '2026-05-28', 11, 30, 2),
    ('G', 1, 2, '2026-05-28', 9, 30, 2),
    ('G', 3, 4, '2026-05-28', 11, 30, 2),
    ('H', 1, 2, '2026-05-28', 9, 30, 2),
    ('H', 3, 4, '2026-05-28', 11, 30, 2),
    # Jueves 28 mayo — Jornada 3
    ('A', 1, 3, '2026-05-28', 17, 0, 3),
    ('A', 2, 4, '2026-05-28', 19, 0, 3),
    ('B', 1, 3, '2026-05-28', 17, 0, 3),
    ('B', 2, 4, '2026-05-28', 19, 0, 3),
    ('C', 1, 3, '2026-05-28', 17, 0, 3),
    ('C', 2, 4, '2026-05-28', 19, 0, 3),
    ('D', 1, 3, '2026-05-28', 17, 0, 3),
    ('D', 2, 4, '2026-05-28', 19, 0, 3),
    ('E', 1, 3, '2026-05-28', 17, 0, 3),
    ('E', 2, 4, '2026-05-28', 19, 0, 3),
    ('F', 1, 3, '2026-05-28', 17, 0, 3),
    ('F', 2, 4, '2026-05-28', 19, 0, 3),
    ('G', 1, 3, '2026-05-28', 17, 0, 3),
    ('G', 2, 4, '2026-05-28', 19, 0, 3),
    ('H', 1, 3, '2026-05-28', 17, 0, 3),
    ('H', 2, 4, '2026-05-28', 19, 0, 3),
]


class Command(BaseCommand):
    help = 'Crea el CEIM 2025-26: liga principal, 8 grupos, 32 equipos y 48 partidos de primera fase'

    def handle(self, *args, **options):
        category = Category.objects.get(id=1)
        sant_josep_club = Club.objects.filter(id=12).first()

        # --- Liga principal ---
        main_league, created = League.objects.get_or_create(
            federation_id='ceim_2526',
            season=SEASON,
            defaults={
                'name': 'CEIM - Campeonato de España Infantil Masculino',
                'competition_type': 'cup',
                'match_format': 'standard',
                'visibility_type': 'main',
                'is_our_team_related': True,
            },
        )
        main_league.categories.add(category)
        label = 'CREADA' if created else 'ya existe'
        self.stdout.write(self.style.SUCCESS(f'Liga principal [{label}]: {main_league.name}'))

        # --- Sub-ligas, equipos y partidos por grupo ---
        grupo_leagues = {}
        grupo_teams = {}

        for grupo, data in GRUPOS_DATA.items():
            grupo_lower = grupo.lower()

            sub_league, created = League.objects.get_or_create(
                federation_id=f'ceim_2526_grupo_{grupo_lower}',
                season=SEASON,
                defaults={
                    'name': f'CEIM 2025-26 - Grupo {grupo}',
                    'competition_type': 'cup',
                    'match_format': 'standard',
                    'visibility_type': 'main',
                    'parent_league': main_league,
                    'phase_name': f'Grupo {grupo}',
                    'phase_order': data['orden'],
                    'is_our_team_related': grupo == 'A',
                },
            )
            sub_league.categories.add(category)
            label = 'CREADO' if created else 'ya existe'
            self.stdout.write(f'  Grupo {grupo} [{label}]')
            grupo_leagues[grupo] = sub_league

            teams_in_grupo = []
            for i, (name, fed_id, is_sant_josep) in enumerate(data['equipos'], 1):
                club = sant_josep_club if is_sant_josep else None
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
                teams_in_grupo.append(team)

            grupo_teams[grupo] = teams_in_grupo

        # --- Partidos primera fase ---
        self.stdout.write('\nCreando partidos de primera fase...')
        partidos_creados = 0
        partidos_existentes = 0

        for (grupo, pos_local, pos_visitante, fecha, hora, minutos, jornada) in PARTIDOS_PRIMERA_FASE:
            league = grupo_leagues[grupo]
            home_team = grupo_teams[grupo][pos_local - 1]
            away_team = grupo_teams[grupo][pos_visitante - 1]
            match_date = datetime(
                *[int(x) for x in fecha.split('-')],
                hora, minutos, 0,
                tzinfo=MADRID,
            )
            venue = GRUPOS_DATA[grupo]['venue']
            address = GRUPOS_DATA[grupo]['address']

            match, created = Match.objects.get_or_create(
                league=league,
                home_team=home_team,
                away_team=away_team,
                match_date=match_date,
                defaults={
                    'status': 'scheduled',
                    'round_number': jornada,
                    'venue': venue,
                    'city': CITY,
                    'field_address': address,
                },
            )
            if created:
                partidos_creados += 1
            else:
                partidos_existentes += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\nPartidos creados: {partidos_creados} | ya existían: {partidos_existentes}'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'\nCEIM 2025-26 configurado. '
                f'Liga principal ID: {main_league.id} (federation_id: ceim_2526)'
            )
        )
