from django.db import migrations

VENUES_DATA = [
    {
        "name": "Pavelló Municipal d'Alaró",
        "short_name": "Pav. Alaró",
        "address": "Camí Vell d'Orient s/n",
        "city": "Alaró",
        "google_maps_url": "https://maps.app.goo.gl/Z66hZm83iKSNzi3f9",
        "aliases": "Pav. Municipal Alaró, Poliesportiu Municipal d'Alaró, Pavelló d'Alaró, Pavello Alaro, Pista 1, Pista 2, Pista 3, Pista 4, Pista 5, Pista 6",
    },
    {
        "name": "Pavelló Andreu Trobat",
        "short_name": "Pav. Andreu Trobat",
        "address": "Carrer Tanqueta, 14",
        "city": "Algaida",
        "google_maps_url": "https://maps.app.goo.gl/wTQiRiLduquRbF9s7",
        "aliases": "Pav. Andreu Trobat, Pavelló Algaida, Poliesportiu Andreu Trobat, Algaida",
    },
    {
        "name": "Poliesportiu Na Caragol",
        "short_name": "Na Caragol",
        "address": "Carrer de les Palmeres, s/n",
        "city": "Artà",
        "google_maps_url": "https://maps.app.goo.gl/rNDxacvpHnYcKJgY7",
        "aliases": "Na Caragol, Pav. Na Caragol, Poliesportiu d'Artà, Artà, Arta",
    },
    {
        "name": "Pavelló Joan Pericás Riera",
        "short_name": "Pav. Joan Pericás",
        "address": "Son Serra s/n",
        "city": "Bunyola",
        "google_maps_url": "https://maps.app.goo.gl/G6ZnG2b3tyY3Gjvb6",
        "aliases": "Pav. Joan Pericas Riera, Pav. Juan Pericas Riera, Pav. Joan Pericás Riera, Pav. Bunyola, Pavello Bunyola, Bunyola",
    },
    {
        "name": "Pavelló Municipal de Campos",
        "short_name": "Pav. Campos",
        "address": "Camí Vell de Ciutat, 0",
        "city": "Campos",
        "google_maps_url": "https://maps.app.goo.gl/T6jG21erGXGw3xDMA",
        "aliases": "Pav. Campos, Pavelló de Campos, Pavelló Municipal Campos, Campos",
    },
    {
        "name": "Pavelló Col·legi CIDE",
        "short_name": "Pav. CIDE",
        "address": "C/ Arner, 3 (Son Rapinya)",
        "city": "Palma",
        "google_maps_url": "https://maps.app.goo.gl/wakHoeUHh4BQAG358",
        "aliases": "Pav. Col. Cide, Pavelló CIDE, Pav. CIDE, Col.legi Cide, CIDE",
    },
    {
        "name": "Pavelló IES Josep Font i Tries",
        "short_name": "Pav. Esporles",
        "address": "C/ Ca l'Amet, 5",
        "city": "Esporles",
        "google_maps_url": "https://maps.app.goo.gl/fTaNxNZWiwgRjpPh7",
        "aliases": "Pav. Esporles, IES Josep Font i Tries, Poliesportiu Esporles, Esporles",
    },
    {
        "name": "Poliesportiu Germans Escalas",
        "short_name": "Germans Escalas",
        "address": "Carrer de Son Gibert s/n",
        "city": "Palma",
        "google_maps_url": "https://maps.app.goo.gl/V59GDYSWXNZUYUto9",
        "aliases": "Germans Escalas, Pav. Germans Escalas, Pol. Germans Escalas",
    },
    {
        "name": "Pavelló Col·legi Madre Alberta",
        "short_name": "Madre Alberta",
        "address": "Camí dels Reis, 102",
        "city": "Palma",
        "google_maps_url": "https://maps.app.goo.gl/YVNo5u8yFVjL31vx8",
        "aliases": "Pav. Col. Madre Alberta, Pav. Madre Alberta, Col. Madre Alberta, Madre Alberta",
    },
    {
        "name": "Pavelló Na Capellera",
        "short_name": "Na Capellera",
        "address": "C/ Ronda de l'Institut, 52",
        "city": "Manacor",
        "google_maps_url": "https://maps.app.goo.gl/tec54UgFASEvwykj7",
        "aliases": "Na Capellera, Pav. Na Capellera, Poliesportiu Na Capellera, Manacor",
    },
    {
        "name": "Pavelló Blanquerna",
        "short_name": "Pav. Blanquerna",
        "address": "Carrer des Caülls, 1",
        "city": "Marratxí",
        "google_maps_url": "https://maps.app.goo.gl/j2o5nsb5rwEFyEj77",
        "aliases": "Pav. Blanquerna, Pavelló Blanquerna, Poliesportiu Blanquerna, Pav. Pòrtol, Pòrtol, Portol",
    },
    {
        "name": "Pavelló Col·legi Sta. Magdalena Sofia",
        "short_name": "Sta. Magdalena Sofia",
        "address": "Carrer de Francesc Martí i Móra, 42",
        "city": "Palma",
        "google_maps_url": "https://maps.app.goo.gl/z66wzV1B16u9w6kM9",
        "aliases": "Pav. Col. Sta. Magdalena Sofia, Sta. Magdalena Sofia, Santa Magdalena Sofia, Pav. Magdalena Sofia, Magdalena Sofia, Mayurqa",
    },
    {
        "name": "Poliesportiu Municipal de Muro",
        "short_name": "Pol. Muro",
        "address": "Carrer de Santa Anna, s/n",
        "city": "Muro",
        "google_maps_url": "https://maps.app.goo.gl/paTrshtehpKm9DBXA",
        "aliases": "Pol. Municipal de Muro, Pav. Muro, Poliesportiu Muro, Muro",
    },
    {
        "name": "Pavelló IES Porto Cristo",
        "short_name": "IES Porto Cristo",
        "address": "Carretera Porto Cristo - Son Carrió, s/n",
        "city": "Porto Cristo",
        "google_maps_url": "https://maps.app.goo.gl/jRjFjSLA5VGBic4Q8",
        "aliases": "Pav. IES Porto Cristo, IES Porto Cristo, Pavelló Porto Cristo, Porto Cristo",
    },
    {
        "name": "Pavelló Son Juny",
        "short_name": "Son Juny",
        "address": "Carrer de Consolació, s/n",
        "city": "Sant Joan",
        "google_maps_url": "https://maps.app.goo.gl/6aVfJ1H5d1nB6C1i8",
        "aliases": "Pav. Son Juny, Son Juny, Pavelló Sant Joan, Poliesportiu Son Juny, Sant Joan",
    },
    {
        "name": "Pavelló Col·legi Sant Josep Obrer",
        "short_name": "Sant Josep Obrer",
        "address": "C/ Sebastià Arrom, 3",
        "city": "Palma",
        "google_maps_url": "https://maps.app.goo.gl/tu27jjSavfm7AoT18",
        "aliases": "Pav. Col. Sant Josep Obrer, Sant Josep Obrer, Pav. Sant Josep Obrer, Sant Josep",
    },
    {
        "name": "Pavelló Son Angelats",
        "short_name": "Son Angelats",
        "address": "Carretera a Deià, s/n",
        "city": "Sóller",
        "google_maps_url": "https://maps.app.goo.gl/YEmNpjuDQWUyx5QT7",
        "aliases": "Pav. Son Angelats, Poliesportiu Son Angelats, Pavelló Sóller, Son Angelats, Sóller, Soller",
    },
    {
        "name": "Palau Municipal d'Esports Son Moix",
        "short_name": "Son Moix",
        "address": "Camí de la Vileta, 40",
        "city": "Palma",
        "google_maps_url": "https://maps.app.goo.gl/4K41P1V8Y42H1m6s9",
        "aliases": "Palau Municipal d'Esports Son Moix, Son Moix, Palau Son Moix, Pav. Son Moix",
    },
    {
        "name": "CampusEsport UIB",
        "short_name": "Campus UIB",
        "address": "Carretera de Valldemossa, km 7.5",
        "city": "Palma",
        "google_maps_url": "https://maps.app.goo.gl/hscF6gydw1WhdWF28",
        "aliases": "CampusEsport UIB, Pav. UIB, Instal·lacions UIB, CampusEsport, UIB",
    },
    {
        "name": "Pavelló Municipal de Valldemossa",
        "short_name": "Pav. Valldemossa",
        "address": "C/ Venerable Sor Aina, s/n",
        "city": "Valldemossa",
        "google_maps_url": "https://maps.app.goo.gl/gZqJp8VqYyZgZgZg8",
        "aliases": "Pav. Municipal Valldemossa, Pavelló Valldemossa, Poliesportiu Valldemossa, Valldemossa",
    },
    {
        "name": "Pavelló Joan Seguí",
        "short_name": "Joan Seguí",
        "address": "Carrer Joan Seguí Garau, s/n",
        "city": "Palma",
        "google_maps_url": "https://maps.app.goo.gl/9ZpZgZgZgZgZgZgZ8",
        "aliases": "Pav. Joan Seguí, Pav. Joan Segui, Poliesportiu Joan Seguí, Joan Seguí, Joan Segui",
    },
    {
        "name": "Poliesportiu Rudy Fernández",
        "short_name": "Rudy Fernández",
        "address": "Camí dels Reis, 128",
        "city": "Palma",
        "google_maps_url": "https://maps.app.goo.gl/8ZpZgZgZgZgZgZgZ8",
        "aliases": "Poliesportiu Rudy Fernandez, Pav. Rudy Fernández, Rudy Fernández, Rudy Fernandez, Gènova, Genova",
    },
    {
        "name": "Poliesportiu Municipal d'Inca",
        "short_name": "Pol. Inca",
        "address": "Carrer dels Menestrals, s/n",
        "city": "Inca",
        "google_maps_url": "https://maps.app.goo.gl/7ZpZgZgZgZgZgZgZ8",
        "aliases": "Poliesportiu Mateu Cañellas, Mateu Cañellas, Pav. Inca, Poliesportiu Inca, Inca",
    },
    {
        "name": "Poliesportiu Municipal de Pollença",
        "short_name": "Pol. Pollença",
        "address": "Carretera de Pollença al Port, km 1.5",
        "city": "Pollença",
        "google_maps_url": "https://maps.app.goo.gl/6ZpZgZgZgZgZgZgZ8",
        "aliases": "Pav. Pollença, Pav. Pollenca, Poliesportiu Pollença, Pollença, Pollenca",
    },
    {
        "name": "Pavelló Municipal de Sa Pobla",
        "short_name": "Pav. Sa Pobla",
        "address": "Carrer Poliesportiu, s/n",
        "city": "Sa Pobla",
        "google_maps_url": "https://maps.app.goo.gl/5ZpZgZgZgZgZgZgZ8",
        "aliases": "Pav. Sa Pobla, Poliesportiu Sa Pobla, Pavelló Sa Pobla, Sa Pobla",
    },
    {
        "name": "Pavelló Col·legi San Pedro",
        "short_name": "San Pedro",
        "address": "Carrer de Joan Miró, 280",
        "city": "Palma",
        "google_maps_url": "https://maps.app.goo.gl/4ZpZgZgZgZgZgZgZ8",
        "aliases": "Pav. Col. San Pedro, Col. San Pedro, San Pedro",
    },
    {
        "name": "Pavelló Guillem Timoner",
        "short_name": "Guillem Timoner",
        "address": "Camí de Son Mas, s/n",
        "city": "Felanitx",
        "google_maps_url": "https://maps.app.goo.gl/3ZpZgZgZgZgZgZgZ8",
        "aliases": "Pav. Guillem Timoner, Poliesportiu Guillem Timoner, Pavelló Felanitx, Felanitx",
    },
    {
        "name": "Poliesportiu Municipal de Sineu",
        "short_name": "Pol. Sineu",
        "address": "Carrer de l'Estació, s/n",
        "city": "Sineu",
        "google_maps_url": "https://maps.app.goo.gl/2ZpZgZgZgZgZgZgZ8",
        "aliases": "Pav. Sineu, Poliesportiu Sineu, Sineu",
    },
    {
        "name": "Pavelló Municipal de Porreres",
        "short_name": "Pav. Porreres",
        "address": "Carrer de Ses Roquetes, s/n",
        "city": "Porreres",
        "google_maps_url": "https://maps.app.goo.gl/1ZpZgZgZgZgZgZgZ8",
        "aliases": "Pav. Porreres, Joan Llaneras, Poliesportiu Joan Llaneras, Porreres",
    },
    {
        "name": "Poliesportiu Municipal d'Andratx",
        "short_name": "Pol. Andratx",
        "address": "Carretera d'Estellencs, s/n",
        "city": "Andratx",
        "google_maps_url": "https://maps.app.goo.gl/0ZpZgZgZgZgZgZgZ8",
        "aliases": "Pav. Andratx, Poliesportiu Andratx, Andratx",
    },
    {
        "name": "Pavelló Galatzó",
        "short_name": "Pav. Galatzó",
        "address": "Carrer de Son Pillo, s/n (Santa Ponça)",
        "city": "Calvià",
        "google_maps_url": "https://maps.app.goo.gl/9ApZgZgZgZgZgZgZ8",
        "aliases": "Pav. Galatzo, Pav. Galatzó, Poliesportiu Galatzó, Calvià, Calvia",
    },
    {
        "name": "Pavelló Poliesportiu de Santa Maria",
        "short_name": "Pav. Santa Maria",
        "address": "Carrer de Batle Pere J. Jaume Toni, s/n",
        "city": "Santa Maria del Camí",
        "google_maps_url": "https://maps.app.goo.gl/8ApZgZgZgZgZgZgZ8",
        "aliases": "Pav. Santa Maria, Poliesportiu Santa Maria, Santa Maria",
    },
    {
        "name": "Pavelló David Calventos",
        "short_name": "David Calventos",
        "address": "Carrer de Bernat Vidal i Tomàs, s/n",
        "city": "Santanyí",
        "google_maps_url": "https://maps.app.goo.gl/7ApZgZgZgZgZgZgZ8",
        "aliases": "Pav. David Calventos, Pav. Santanyí, Poliesportiu Santanyí, Santanyí, Santanyi",
    },
]


def seed_venues_and_backfill(apps, schema_editor):
    Venue = apps.get_model('competitions', 'Venue')
    Match = apps.get_model('competitions', 'Match')
    Club = apps.get_model('teams', 'Club')

    # 1. Crear o actualizar pabellones canónicos
    venue_map = {}
    for item in VENUES_DATA:
        v, _ = Venue.objects.update_or_create(
            name=item['name'],
            defaults={
                'short_name': item.get('short_name', ''),
                'address': item.get('address', ''),
                'city': item.get('city', ''),
                'google_maps_url': item.get('google_maps_url', ''),
                'aliases': item.get('aliases', ''),
                'is_active': True,
            }
        )
        venue_map[v.name] = v

    all_venues = list(Venue.objects.filter(is_active=True))

    def venue_matches_string(v, raw_text):
        if not raw_text:
            return False
        clean = raw_text.strip().lower()
        if clean == v.name.lower() or (v.short_name and clean == v.short_name.lower()):
            return True
        aliases = [a.strip().lower() for a in (v.aliases or '').replace('\n', ',').split(',') if a.strip()]
        for a in aliases:
            if clean == a or a in clean or clean in a:
                return True
        return False

    # 2. Vincular Club.default_venue para clubes existentes
    for club in Club.objects.all():
        if club.default_venue_id:
            continue
        c_name = club.official_name.lower()
        c_venue = (club.venue_name or '').strip().lower()

        matched_venue = None
        # Intentar por nombre de sede en club
        if c_venue:
            for v in all_venues:
                if venue_matches_string(v, c_venue):
                    matched_venue = v
                    break

        # Fallback por nombre del club
        if not matched_venue:
            for v in all_venues:
                if venue_matches_string(v, c_name):
                    matched_venue = v
                    break

        # Fallback por municipio si coincide exactamente
        if not matched_venue:
            for v in all_venues:
                if v.city and v.city.lower() in c_name:
                    matched_venue = v
                    break

        if matched_venue:
            club.default_venue = matched_venue
            club.save(update_fields=['default_venue'])

    # 3. Backfill Match.venue_ref para partidos con texto de pista
    for match in Match.objects.filter(venue_ref__isnull=True).exclude(venue=''):
        m_venue = match.venue.strip()
        for v in all_venues:
            if venue_matches_string(v, m_venue):
                match.venue_ref = v
                match.save(update_fields=['venue_ref'])
                break


def reverse_seed_venues(apps, schema_editor):
    Venue = apps.get_model('competitions', 'Venue')
    Match = apps.get_model('competitions', 'Match')
    Club = apps.get_model('teams', 'Club')

    Match.objects.all().update(venue_ref=None)
    Club.objects.all().update(default_venue=None)
    Venue.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0012_venue_match_venue_ref'),
        ('teams', '0004_club_default_venue'),
    ]

    operations = [
        migrations.RunPython(seed_venues_and_backfill, reverse_seed_venues),
    ]
