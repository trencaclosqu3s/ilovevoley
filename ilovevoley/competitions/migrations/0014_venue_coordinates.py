from decimal import Decimal

from django.db import migrations

# Coordenadas obtenidas con Nominatim (OpenStreetMap) a partir de la dirección de cada sede y
# verificadas a menos de 8 km del centro de su municipio. Las sedes que Nominatim no resolvió
# (Campos, Felanitx, Joan Seguí, Pollença, Porreres, Porto Cristo, Santa Maria y Son Angelats)
# no figuran aquí y se completan a mano.
VENUE_COORDINATES = {
    ("Pavelló Municipal d'Alaró", 'Alaró'): ('39.698457', '2.802078'),
    ('Pavelló Andreu Trobat', 'Algaida'): ('39.564230', '2.895819'),
    ("Poliesportiu Municipal d'Andratx", 'Andratx'): ('39.623251', '2.423965'),
    ('Poliesportiu Na Caragol', 'Artà'): ('39.696066', '3.344408'),
    ('Pavelló Joan Pericás Riera', 'Bunyola'): ('39.688633', '2.700215'),
    ('Pavelló Galatzó', 'Calvià'): ('39.538246', '2.505650'),
    ('Pavelló IES Josep Font i Tries', 'Esporles'): ('39.662879', '2.580172'),
    ("Poliesportiu Municipal d'Inca", 'Inca'): ('39.713971', '2.909879'),
    ('Pavelló Na Capellera', 'Manacor'): ('39.565700', '3.218314'),
    ('Pavelló Blanquerna', 'Marratxí'): ('39.646906', '2.743698'),
    ('Poliesportiu Municipal de Muro', 'Muro'): ('39.734219', '3.053229'),
    ('CampusEsport UIB', 'Palma'): ('39.637366', '2.650424'),
    ("Palau Municipal d'Esports Son Moix", 'Palma'): ('39.587556', '2.626515'),
    ('Pavelló Col·legi CIDE', 'Palma'): ('39.590764', '2.609330'),
    ('Pavelló Col·legi Madre Alberta', 'Palma'): ('39.583584', '2.616585'),
    ('Pavelló Col·legi San Pedro', 'Palma'): ('39.553291', '2.606515'),
    ('Pavelló Col·legi Sant Josep Obrer', 'Palma'): ('39.579050', '2.677980'),
    ('Pavelló Col·legi Sta. Magdalena Sofia', 'Palma'): ('39.582514', '2.637773'),
    ('Poliesportiu Germans Escalas', 'Palma'): ('39.584580', '2.684350'),
    ('Poliesportiu Rudy Fernández', 'Palma'): ('39.586958', '2.621715'),
    ('Pavelló Municipal de Sa Pobla', 'Sa Pobla'): ('39.763306', '3.019391'),
    ('Pavelló Son Juny', 'Sant Joan'): ('39.595344', '3.039590'),
    ('Pavelló David Calventos', 'Santanyí'): ('39.351874', '3.132239'),
    ('Poliesportiu Municipal de Sineu', 'Sineu'): ('39.644550', '3.014033'),
    ('Pavelló Municipal de Valldemossa', 'Valldemossa'): ('39.712023', '2.617843'),
}


def set_venue_coordinates(apps, schema_editor):
    """Rellena latitud/longitud solo en sedes sin coordenadas; nunca pisa un valor manual."""
    Venue = apps.get_model('competitions', 'Venue')
    for (name, city), (latitude, longitude) in VENUE_COORDINATES.items():
        Venue.objects.filter(name=name, city=city, latitude__isnull=True, longitude__isnull=True).update(
            latitude=Decimal(latitude), longitude=Decimal(longitude)
        )


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0013_seed_venues_and_backfill'),
    ]

    operations = [
        migrations.RunPython(set_venue_coordinates, migrations.RunPython.noop),
    ]
