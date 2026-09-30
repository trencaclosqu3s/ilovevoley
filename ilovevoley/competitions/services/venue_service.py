import urllib.parse

from ilovevoley.competitions.models import Venue


def get_match_location_info(match) -> dict:
    """Resuelve la ubicación estructurada y enlace de navegación de un partido.

    Orden de prioridad estricto:
    1. Asignación directa en match.venue_ref (asignado manual o por scraping)
    2. Texto de match.venue normalizado y cruzado con catálogo Venue (la pista del partido manda)
    3. Fallback a match.home_team.club.default_venue solo si venue viene vacío (ej. partidos lejanos)
    4. Fallback a texto plano residual de match (venue, field_address, city)
    5. Fallback a 'Por confirmar'
    """
    # 1. Asignación directa
    if match.venue_ref_id:
        v = match.venue_ref
        return {
            'venue': v,
            'location_text': v.full_address,
            'maps_url': v.maps_url,
            'is_inferred': False,
        }

    # 2. Matching por texto de match.venue
    venue_text = (match.venue or '').strip()
    if venue_text:
        venues = list(Venue.objects.filter(is_active=True))
        matched = next((v for v in venues if v.matches_text(venue_text)), None)
        if matched:
            return {
                'venue': matched,
                'location_text': matched.full_address,
                'maps_url': matched.maps_url,
                'is_inferred': False,
            }

    # 3. Fallback por club local si venue viene vacío
    if match.home_team_id and match.home_team.club_id:
        club = match.home_team.club
        if club.default_venue_id:
            dv = club.default_venue
            return {
                'venue': dv,
                'location_text': dv.full_address,
                'maps_url': dv.maps_url,
                'is_inferred': True,
            }

    # 4. Fallback a texto plano de Match
    parts = []
    if match.venue:
        parts.append(match.venue.strip())
    if match.field_address:
        fa = match.field_address.strip()
        if not match.venue or fa.lower() not in match.venue.lower():
            parts.append(fa)
    if match.city:
        c = match.city.strip()
        if not any(c.lower() in p.lower() for p in parts):
            parts.append(c)

    if parts:
        loc_str = ', '.join(parts)
        q = urllib.parse.quote_plus(loc_str)
        return {
            'venue': None,
            'location_text': loc_str,
            'maps_url': f'https://www.google.com/maps/search/?api=1&query={q}',
            'is_inferred': False,
        }

    return {
        'venue': None,
        'location_text': 'Por confirmar',
        'maps_url': None,
        'is_inferred': False,
    }
