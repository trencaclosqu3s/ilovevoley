from decimal import Decimal

from django.db import migrations

# Coordenadas exactas obtenidas y verificadas para las 8 sedes que no se
# geocodificaron en la migración 0014_venue_coordinates.
ADDITIONAL_VENUE_COORDINATES = {
    ('Pavelló Municipal de Campos', 'Campos'): ('39.434391', '3.008076'),
    ('Pavelló IES Porto Cristo', 'Porto Cristo'): ('39.548610', '3.338634'),
    ('Pavelló Son Angelats', 'Sóller'): ('39.770560', '2.700530'),
    ('Pavelló Joan Seguí', 'Palma'): ('39.586942', '2.620204'),
    ('Poliesportiu Municipal de Pollença', 'Pollença'): ('39.878599', '3.023232'),
    ('Pavelló Guillem Timoner', 'Felanitx'): ('39.466226', '3.136743'),
    ('Pavelló Municipal de Porreres', 'Porreres'): ('39.511987', '3.027637'),
    ('Pavelló Poliesportiu de Santa Maria', 'Santa Maria del Camí'): ('39.646719', '2.771425'),
}

# Enlaces cortos maps.app.goo.gl sembrados erróneamente en la migración 0013.
# Estaban desplazados/cruzados entre pabellones (ej: Algaida apuntando a Ágora Portals,
# Pòrtol a Pollença, Alaró a Germans Escalas) o eran enlaces sintéticos que dan 404.
SEED_GOOGLE_MAPS_URLS = [
    'https://maps.app.goo.gl/Z66hZm83iKSNzi3f9',
    'https://maps.app.goo.gl/wTQiRiLduquRbF9s7',
    'https://maps.app.goo.gl/rNDxacvpHnYcKJgY7',
    'https://maps.app.goo.gl/G6ZnG2b3tyY3Gjvb6',
    'https://maps.app.goo.gl/T6jG21erGXGw3xDMA',
    'https://maps.app.goo.gl/wakHoeUHh4BQAG358',
    'https://maps.app.goo.gl/fTaNxNZWiwgRjpPh7',
    'https://maps.app.goo.gl/V59GDYSWXNZUYUto9',
    'https://maps.app.goo.gl/YVNo5u8yFVjL31vx8',
    'https://maps.app.goo.gl/tec54UgFASEvwykj7',
    'https://maps.app.goo.gl/j2o5nsb5rwEFyEj77',
    'https://maps.app.goo.gl/z66wzV1B16u9w6kM9',
    'https://maps.app.goo.gl/paTrshtehpKm9DBXA',
    'https://maps.app.goo.gl/jRjFjSLA5VGBic4Q8',
    'https://maps.app.goo.gl/6aVfJ1H5d1nB6C1i8',
    'https://maps.app.goo.gl/tu27jjSavfm7AoT18',
    'https://maps.app.goo.gl/YEmNpjuDQWUyx5QT7',
    'https://maps.app.goo.gl/4K41P1V8Y42H1m6s9',
    'https://maps.app.goo.gl/hscF6gydw1WhdWF28',
    'https://maps.app.goo.gl/gZqJp8VqYyZgZgZg8',
    'https://maps.app.goo.gl/9ZpZgZgZgZgZgZgZ8',
    'https://maps.app.goo.gl/8ZpZgZgZgZgZgZgZ8',
    'https://maps.app.goo.gl/7ZpZgZgZgZgZgZgZ8',
    'https://maps.app.goo.gl/6ZpZgZgZgZgZgZgZ8',
    'https://maps.app.goo.gl/5ZpZgZgZgZgZgZgZ8',
    'https://maps.app.goo.gl/4ZpZgZgZgZgZgZgZ8',
    'https://maps.app.goo.gl/3ZpZgZgZgZgZgZgZ8',
    'https://maps.app.goo.gl/2ZpZgZgZgZgZgZgZ8',
    'https://maps.app.goo.gl/1ZpZgZgZgZgZgZgZ8',
    'https://maps.app.goo.gl/0ZpZgZgZgZgZgZgZ8',
    'https://maps.app.goo.gl/9ApZgZgZgZgZgZgZ8',
    'https://maps.app.goo.gl/8ApZgZgZgZgZgZgZ8',
    'https://maps.app.goo.gl/7ApZgZgZgZgZgZgZ8',
]


def clean_maps_urls_and_add_coordinates(apps, schema_editor):
    Venue = apps.get_model('competitions', 'Venue')

    # 1. Rellenar coordenadas de las 8 sedes restantes
    for (name, city), (lat, lon) in ADDITIONAL_VENUE_COORDINATES.items():
        Venue.objects.filter(
            name=name, city=city, latitude__isnull=True, longitude__isnull=True
        ).update(latitude=Decimal(lat), longitude=Decimal(lon))

    # 2. Limpiar los enlaces erróneos o ficticios sembrados en la migración 0013.
    # Al quedar vacíos, Venue.maps_url usará dinámicamente las coordenadas precisas.
    Venue.objects.filter(google_maps_url__in=SEED_GOOGLE_MAPS_URLS).update(google_maps_url='')
    Venue.objects.filter(google_maps_url__contains='ZgZgZgZ').update(google_maps_url='')


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0019_federationcallup_callup_type'),
    ]

    operations = [
        migrations.RunPython(clean_maps_urls_and_add_coordinates, migrations.RunPython.noop),
    ]
