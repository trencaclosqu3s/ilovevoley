from django.db import migrations, models


def deduplicate_mirror_matches(apps, schema_editor):
    """Backfill #485: retira los duplicados en espejo ya existentes.

    Las dos fuentes del calendario (HTML sin id federativo y JSON con id)
    dejaron cruces programados dos veces el mismo día cuando la federación
    cambió la localía del partido. Un cruce no puede estar programado dos
    veces la misma fecha.

    La lógica en vivo usa la confirmación de cada scrape (la federación es la
    autoridad); esta corrección puntual decide sin datos en línea:
    si del grupo solo una fila lleva federation_id, gana esa; si ninguna lo
    lleva, gana la creada más tarde, que es la que nació de los datos
    federativos vigentes. Los grupos con más de una fila con id se dejan
    para revisión manual.
    """
    Match = apps.get_model('competitions', 'Match')

    unfinished = list(
        Match.objects.filter(
            status__in=['scheduled', 'postponed'],
            is_friendly=False,
            home_team__isnull=False,
            away_team__isnull=False,
        ).exclude(
            home_team=models.F('away_team'),
        )
    )

    groups = {}
    for fixture in unfinished:
        key = (
            fixture.league_id,
            fixture.match_date.date(),
            frozenset({fixture.home_team_id, fixture.away_team_id}),
        )
        groups.setdefault(key, []).append(fixture)

    to_withdraw = []
    for members in groups.values():
        if len(members) < 2:
            continue
        identified = [
            fixture for fixture in members if str(fixture.federation_id or '').strip()
        ]
        if len(identified) > 1:
            continue
        if len(identified) == 1:
            keep = identified[0]
        else:
            # La nacida más tarde salió de los datos federativos vigentes; la
            # pareja es un reflejo de una ejecución con la orientación antigua.
            keep = max(members, key=lambda fixture: (fixture.created_at, fixture.pk))
        to_withdraw.extend(fixture.pk for fixture in members if fixture.pk != keep.pk)

    for chunk_start in range(0, len(to_withdraw), 500):
        Match.objects.filter(pk__in=to_withdraw[chunk_start:chunk_start + 500]).update(
            status='withdrawn'
        )


class Migration(migrations.Migration):
    dependencies = [
        ('competitions', '0035_alter_matchactaphoto_status'),
    ]

    operations = [
        migrations.RunPython(deduplicate_mirror_matches, migrations.RunPython.noop),
    ]
