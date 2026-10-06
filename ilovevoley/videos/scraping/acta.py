"""Parsing de actas oficiales de partidos."""

import re

from bs4 import BeautifulSoup, NavigableString


def _extract_player_text_from_cell(td):
    """
    Extrae solo el texto directo de una celda textoPeque,
    ignorando spans de sustitución (ej: ↑6 (4-7)).
    """
    parts = []
    for child in td.children:
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                parts.append(text)
    return ' '.join(parts).strip()


def _parse_lineup_table(table):
    """Extrae lista de jugadores (número, apellido) de una tabla de alineación del acta."""
    players = []
    for row in table.find_all('tr'):
        if 'seccion' in row.get('class', []):
            continue
        td = row.find('td', class_='textoPeque')
        if not td:
            continue
        player_text = _extract_player_text_from_cell(td)
        if player_text:
            players.append(player_text)
    return players


def _parse_set_table(table):
    """
    Extrae nombre de equipo, alineación inicial (I-VI) y puntos de una tabla-set.

    Retorna (team_name, lineup, points) donde lineup es una lista de 6 dicts:
        [{'position': 'I', 'number': 9, 'sub': None}, ...]
    El campo 'sub', si existe: {'number': 22, 'score': '(15-21)'}
    """
    team_name = ''
    lineup = []
    points = None

    rows = table.find_all('tr')
    if not rows:
        return team_name, lineup, points

    position_labels = []
    data_row = None
    positions_found = False

    for row in rows:
        is_seccion = 'seccion' in row.get('class', [])
        cells = row.find_all('td')

        if is_seccion:
            texts = [c.get_text(strip=True) for c in cells]
            if not team_name and texts and texts[0] not in ('I', 'II', 'III', 'IV', 'V', 'VI'):
                team_name = texts[0]
            if 'I' in texts and 'II' in texts and 'III' in texts:
                position_labels = [t for t in texts if t not in ('Ptos', '')]
                positions_found = True
        elif positions_found and data_row is None:
            data_row = row

    if not data_row or not position_labels:
        return team_name, lineup, points

    all_cells = data_row.find_all('td')

    # Puntos desde td-puntos
    for td in all_cells:
        if 'td-puntos' in td.get('class', []):
            for child in td.children:
                if isinstance(child, NavigableString):
                    t = str(child).strip()
                    if t and t.isdigit():
                        points = int(t)
                        break
            break

    data_cells = [td for td in all_cells if 'td-puntos' not in td.get('class', [])]

    for pos, td in zip(position_labels, data_cells):
        number = None
        for child in td.children:
            if isinstance(child, NavigableString):
                t = str(child).strip()
                if t and t.isdigit():
                    number = int(t)
                    break

        sub = None
        sub_span = td.find('span', class_='sustitucion')
        if sub_span:
            sub_text = sub_span.get_text(separator=' ', strip=True)
            m_sub = re.search(r'↑\s*(\d+)', sub_text)
            score_m = re.search(r'\(\d+-\d+\)', sub_text)
            if m_sub:
                sub = {
                    'number': int(m_sub.group(1)),
                    'score': score_m.group(0) if score_m else '',
                }

        lineup.append({'position': pos, 'number': number, 'sub': sub})

    return team_name, lineup, points


def _normalize_ws(text):
    """Colapsa saltos de línea y espacios repetidos de los textos libres del acta."""
    return re.sub(r'\s+', ' ', text or '').strip()


def _parse_observations(soup):
    """Texto libre del bloque ``Observaciones:`` del acta (vacío si no existe)."""
    for td in soup.find_all('td'):
        text = _normalize_ws(td.get_text(' ', strip=True))
        match = re.match(r'^Observaciones:\s*(.*)$', text, re.DOTALL)
        if match:
            return match.group(1).strip()
    return ''


def _parse_signatures(soup):
    """Nombre escrito junto a cada firma, indexado por la etiqueta del recuadro.

    Cada ``td.espacio-firma`` empieza por una etiqueta ("Firma Entrenador Local",
    "Firma Árbitro"…) y a veces lleva el nombre en un ``<strong>``. Muchas firmas
    solo traen imagen, así que el nombre puede quedar vacío.
    """
    signatures = {}
    for td in soup.find_all('td', class_='espacio-firma'):
        label = ''
        for child in td.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    label = text
                    break
        if not label:
            continue
        strong = td.find('strong')
        name = _normalize_ws(strong.get_text(' ', strip=True)) if strong else ''
        # La primera firma con nombre gana; una repetición vacía no lo borra.
        if not signatures.get(label):
            signatures[label] = name
    return signatures


def _parse_officials(soup):
    """Filas de la tabla OFICIALES (LOCAL / ROL / VISITANTE).

    La cabecera existe aunque no haya filas, así que una lista vacía significa
    que el acta no designa oficiales.
    """
    officials = []
    for table in soup.find_all('table'):
        header = table.find('tr', class_='seccion')
        if not header:
            continue
        header_cells = [cell.get_text(strip=True) for cell in header.find_all('td')]
        if header_cells != ['LOCAL', 'ROL', 'VISITANTE']:
            continue
        for row in table.find_all('tr'):
            if 'seccion' in row.get('class', []):
                continue
            cells = row.find_all('td')
            if len(cells) != 3:
                continue
            local = _normalize_ws(cells[0].get_text(' ', strip=True))
            role = cells[1].get_text(strip=True)
            visitor = _normalize_ws(cells[2].get_text(' ', strip=True))
            if local or role or visitor:
                officials.append({'local': local, 'role': role, 'visitor': visitor})
    return officials


def parse_acta_lineup(html_content):
    """
    Parsea el HTML del acta oficial.

    Retorna dict con:
        home_team (str), away_team (str),
        home_captain (str), away_captain (str),
        home_convocados (list[str]),   # ej: ["1 Raya", "4 Oliver", ...]
        away_convocados (list[str]),
        sets (list[dict]),             # cada set con título, tiempo y equipos I-VI
        observations (str),            # texto libre del bloque "Observaciones:"
        home_coach (str), away_coach (str),  # vacíos si la firma es solo imagen
        referees (list[str]),          # nombres de árbitro presentes en las firmas
        officials (list[dict])         # tabla OFICIALES: local/role/visitor
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    home_captain = ''
    away_captain = ''

    # Capitanes
    for row in soup.find_all('tr', class_='seccion'):
        cells = row.find_all('td')
        if len(cells) >= 4 and 'Capit' in cells[0].get_text() and 'Local' in cells[0].get_text():
            home_captain = cells[1].get_text(strip=True)
            away_captain = cells[3].get_text(strip=True)
            break

    # Convocados: tablas "Alineación Local" / "Alineación Visitante" dentro de <td colspan="2">
    home_convocados_raw = []
    away_convocados_raw = []
    fallback_tables = []  # si no hay "Local"/"Visitante" en el header
    for td in soup.find_all('td', attrs={'colspan': '2'}):
        inner_table = td.find('table')
        if not inner_table:
            continue
        header = inner_table.find('tr', class_='seccion')
        if not header:
            continue
        header_text = header.get_text()
        if 'Alineaci' not in header_text:
            continue
        players = _parse_lineup_table(inner_table)
        if 'Local' in header_text:
            home_convocados_raw = players
        elif 'Visitan' in header_text:
            away_convocados_raw = players
        else:
            fallback_tables.append(players)
    # Fallback: primer tabla = local, segundo = visitante
    if not home_convocados_raw and len(fallback_tables) >= 1:
        home_convocados_raw = fallback_tables[0]
    if not away_convocados_raw and len(fallback_tables) >= 2:
        away_convocados_raw = fallback_tables[1]

    # Sets: un set-container por set, con dos tabla-set inmediatamente después en el mismo div padre
    sets = []
    for set_container in soup.find_all('div', class_='set-container'):
        parent = set_container.parent
        if not parent:
            continue
        tables = parent.find_all('table', class_='tabla-set')
        if not tables:
            continue

        h5 = set_container.find('h5')
        set_title = ''
        set_time = ''
        if h5:
            for child in h5.children:
                if isinstance(child, NavigableString):
                    t = str(child).strip()
                    if t:
                        set_title = t
                        break
            time_span = h5.find('span', class_='textoPeque')
            if time_span:
                set_time = time_span.get_text(strip=True)

        set_teams = []
        for table in tables:
            team_name, lineup, pts = _parse_set_table(table)
            set_teams.append({'name': team_name, 'lineup': lineup, 'points': pts})

        sets.append({'title': set_title, 'time': set_time, 'teams': set_teams})

    # Nombres canónicos de equipos: primera y segunda aparición única en tabla-set
    home_team = ''
    away_team = ''
    seen = []
    for tbl in soup.find_all('table', class_='tabla-set'):
        header = tbl.find('tr', class_='seccion')
        if header:
            name = header.get_text(strip=True)
            if name and name not in seen:
                seen.append(name)
    if len(seen) >= 1:
        home_team = seen[0]
    if len(seen) >= 2:
        away_team = seen[1]

    signatures = _parse_signatures(soup)
    referees = [
        signatures[label]
        for label in ('Firma Árbitro', 'Firma Árbitro 2')
        if signatures.get(label)
    ]

    return {
        'home_team': home_team,
        'away_team': away_team,
        'home_captain': home_captain,
        'away_captain': away_captain,
        'home_convocados': home_convocados_raw,
        'away_convocados': away_convocados_raw,
        'sets': sets,
        'observations': _parse_observations(soup),
        'home_coach': signatures.get('Firma Entrenador Local', ''),
        'away_coach': signatures.get('Firma Entrenador Visitante', ''),
        'referees': referees,
        'officials': _parse_officials(soup),
    }




__all__ = [
    'parse_acta_lineup',
]
