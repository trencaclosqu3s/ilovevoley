import io
import re
import unicodedata
from typing import Any
import pypdf


def _remove_accents(text: str) -> str:
    """Elimina tildes y diacríticos manteniendo caracteres base."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def parse_callup_title(title: str) -> dict[str, Any]:
    """
    Normaliza el título de una convocatoria federativa extrayendo metadatos:
    - modality: 'beach' | 'indoor'
    - category_name: 'Infantil' | 'Cadete' | 'Juvenil / Sub-19' | 'Sub-21' | 'Senior' | ''
    - gender: 'M' | 'F' | 'X'
    - callup_number: str (ej. '3ª', '9ª Y 10ª', '23-30')
    - event_type: 'selection' | 'training' | 'follow_up' | 'supervision'
    """
    clean_title = title.strip()
    norm_title = _remove_accents(clean_title).upper()

    # 0. Tipo de evento federativo (selección por defecto)
    if 'SUPERVIS' in norm_title:
        event_type = 'supervision'
    elif 'TECNIFICACI' in norm_title:
        event_type = 'training'
    elif 'SEGUIMENT' in norm_title or 'SEGUIMIENTO' in norm_title:
        event_type = 'follow_up'
    else:
        event_type = 'selection'

    # 1. Modalidad
    if re.search(r'\b(VP|VOLEI\s+PLATJA|VOLEY\s+PLAYA|BEACH)\b', norm_title):
        modality = 'beach'
    else:
        modality = 'indoor'

    # 2. Número de convocatoria
    callup_number = ''
    m_ord = re.search(r'\b(\d+[ªºaA](?:\s*(?:Y|I)\s*\d+[ªºaA])?)\b', clean_title)
    if m_ord:
        callup_number = m_ord.group(1).strip()
    else:
        m_num = re.search(r'CONVOCAT[OÒ]RIA\s+(?:N[ºª°]?\s*)?(\d+(?:-\d+)?)', clean_title, re.IGNORECASE)
        if m_num:
            callup_number = m_num.group(1).strip()

    # 3. Categoría y Género
    category_name = ''
    gender = 'X'

    # Detección combinada o por códigos cortos (ej. IF -> Infantil Femenino, CM -> Cadete Masculino)
    short_codes = {
        'IF': ('Infantil', 'F'),
        'IM': ('Infantil', 'M'),
        'CF': ('Cadete', 'F'),
        'CM': ('Cadete', 'M'),
        'JF': ('Juvenil / Sub-19', 'F'),
        'JM': ('Juvenil / Sub-19', 'M'),
    }

    found_short = False
    for code, (cat, gen) in short_codes.items():
        if re.search(rf'\b{code}\b', norm_title):
            category_name = cat
            gender = gen
            found_short = True
            break

    if not found_short:
        # Categoría
        if re.search(r'\b(INF|INFANTIL)\b', norm_title):
            category_name = 'Infantil'
        elif re.search(r'\b(CAD|CADET|CADETE)\b', norm_title):
            category_name = 'Cadete'
        elif re.search(r'\b(SUB[- ]?19|JUV|JUVENIL)\b', norm_title):
            category_name = 'Juvenil / Sub-19'
        elif re.search(r'\b(SUB[- ]?21)\b', norm_title):
            category_name = 'Sub-21'
        elif re.search(r'\b(SEN|SENIOR)\b', norm_title):
            category_name = 'Senior'

        # Género
        if re.search(r'\b(FEM|FEMENI|FEMENINA|FEMENINO)\b', norm_title):
            gender = 'F'
        elif re.search(r'\b(MASC|MASCULI|MASCULINA|MASCULINO)\b', norm_title):
            gender = 'M'
        elif re.search(r'\bF\b', norm_title):
            gender = 'F'
        elif re.search(r'\bM\b', norm_title):
            gender = 'M'

    return {
        'modality': modality,
        'category_name': category_name,
        'gender': gender,
        'callup_number': callup_number,
        'event_type': event_type,
    }


def extract_callup_players_from_pdf(pdf_bytes: bytes) -> tuple[str, list[dict[str, Any]]]:
    """
    Extrae texto y lista de jugadores desde un PDF de circular de convocatoria.
    Retorna (raw_text_completo, lista_jugadores_dict).
    Cada dict de jugador:
      - 'club': str
      - 'last_name': str
      - 'first_name': str
      - 'birth_year': int | None
    """
    if not pdf_bytes:
        return '', []

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    except Exception:
        return '', []

    all_pages_text: list[str] = []
    players: list[dict[str, Any]] = []

    # Mantener el estado de la tabla y posiciones de cabecera entre páginas del PDF
    header_positions: dict[str, int] | None = None
    in_table = False
    in_supervision_list = False
    in_tracking_list = False

    for page in reader.pages:
        try:
            page_text = page.extract_text(extraction_mode='layout') or ''
        except Exception:
            page_text = page.extract_text() or ''

        all_pages_text.append(page_text)
        lines = page_text.splitlines()

        for line in lines:
            norm_line = _remove_accents(line).upper()

            # Comprobar si es cabecera tabular estándar (desactiva modo supervisión si estaba activo)
            if ('CLUB' in norm_line or 'EQUIP' in norm_line) and (
                'LLINATGES' in norm_line or 'APELLIDOS' in norm_line
            ):
                pos_club = norm_line.find('CLUB')
                if pos_club == -1:
                    pos_club = norm_line.find('EQUIP')

                pos_last = norm_line.find('LLINATGES')
                if pos_last == -1:
                    pos_last = norm_line.find('APELLIDOS')

                pos_first = norm_line.find('NOM')
                if pos_first == -1:
                    pos_first = norm_line.find('NOMBRE')

                # _remove_accents quita diacríticos (NFKD), así que Ñ→N: buscar 'ANO', no 'AÑO'
                pos_year = norm_line.find('ANY')
                if pos_year == -1:
                    pos_year = norm_line.find('ANO')
                if pos_year == -1:
                    pos_year = norm_line.find('NAIX')
                if pos_year == -1:
                    pos_year = norm_line.find('DATA')

                # in_table (y el fin del modo supervisión) solo se activan si la cabecera
                # tiene los tres campos mínimos; si no, una nota con CLUB+LLINATGES
                # cortaría el listado de supervisión sin llegar a parsear la tabla
                if pos_club != -1 and pos_last != -1 and pos_first != -1:
                    in_table = True
                    in_supervision_list = False
                    in_tracking_list = False
                    header_positions = {
                        'club': pos_club,
                        'last_name': pos_last,
                        'first_name': pos_first,
                        'birth_year': pos_year if pos_year != -1 else len(line),
                    }
                continue

            # Formato de seguimiento/tecnificación federativa (#288): listado
            # "Nombre Apellidos   Club   Año" bajo un bloque HORARI/ENTRENADORS/LLOC.
            if not in_table and ('SEGUIMENT FEDERATIU' in norm_line or 'TECNIFICACI' in norm_line):
                in_tracking_list = True
                continue

            if in_tracking_list:
                stripped = line.strip()
                if not stripped:
                    continue
                # Fin del listado: pie de circular con instrucciones de pago
                if any(sec in norm_line for sec in ['ESPORTISTES HAN DE PAGAR', 'IBAN', 'ABONAR', 'TARGETA']):
                    in_tracking_list = False
                    continue

                chunks = [c.strip() for c in re.split(r'\s{2,}', stripped) if c.strip()]
                # Cada fila termina en el año de nacimiento; exigirlo descarta el bloque
                # de cabecera (horario, entrenadores, lugar), cuyas líneas no acaban en año
                if len(chunks) >= 2 and re.match(r'^(19|20)\d{2}$', chunks[-1]):
                    full_name = ' '.join(chunks[:-2])
                    tokens = full_name.split()
                    if len(tokens) >= 2:
                        players.append({
                            'club': chunks[-2],
                            'last_name': ' '.join(tokens[1:]),
                            'first_name': tokens[0],
                            'birth_year': int(chunks[-1]),
                        })
                continue

            # Detección de formato alternativo (ej. convocatorias de supervisión CTEIB con listado Nombre   Club)
            if not in_table and any(ph in norm_line for ph in ['ESPORTISTES SELECCIONATS', 'ESPORTISTES SELECCIONADES', 'JUGADORS SELECCIONATS', 'JUGADORES SELECCIONADES']):
                in_supervision_list = True
                continue

            if in_supervision_list:
                stripped = line.strip()
                if not stripped:
                    continue
                if any(sec in norm_line for sec in ['HORARI', 'A TENIR EN COMPTE', 'CONTACTE', 'DIJOUS', 'DIVENDRES', 'DISSABTE', 'DIUMENGE']):
                    in_supervision_list = False
                    continue

                chunks = [c.strip() for c in re.split(r'\s{2,}', stripped) if c.strip()]
                # Una fila de jugador de supervisión requiere al menos nombre y club (2 columnas)
                # Si tiene < 2 chunks suele ser un subtítulo de categoría (ej: "INFANTIL MASCULÍ:") o notas
                if len(chunks) < 2:
                    continue

                full_name = ' '.join(chunks[:-1])
                club_clean = chunks[-1]
                tokens = full_name.split()
                if len(tokens) >= 2:
                    first_str = tokens[0]
                    last_str = ' '.join(tokens[1:])
                    players.append({
                        'club': club_clean,
                        'last_name': last_str,
                        'first_name': first_str,
                        'birth_year': None,
                    })
                continue

            # Si ya tenemos cabecera / estamos dentro de la tabla
            if in_table:
                stripped = line.strip()
                if not stripped:
                    continue

                # Si entramos en otra sección técnica, salir de la tabla
                if any(sec in norm_line for sec in ['ENTRENADOR', 'TECNIC', 'HORARI', 'LLOC', 'OBSERVACI']):
                    in_table = False
                    header_positions = None
                    continue

                # Estrategia 1: división por espacios múltiples (>= 2 espacios entre columnas de tabla)
                chunks = [c.strip() for c in re.split(r'\s{2,}', stripped) if c.strip()]
                # Quitar número de orden inicial si existe (ej. "1", "2)", "14.")
                if chunks and re.match(r'^\d+[\.\)]?$', chunks[0]):
                    chunks = chunks[1:]

                parsed = False
                if len(chunks) >= 3:
                    m_year = re.search(r'^(19\d{2}|20\d{2})$', chunks[-1])
                    if m_year:
                        birth_year = int(m_year.group(1))
                        rem = chunks[:-1]
                    else:
                        year_idx = next((i for i, c in enumerate(chunks) if re.match(r'^(19\d{2}|20\d{2})$', c)), None)
                        if year_idx is not None:
                            birth_year = int(chunks[year_idx])
                            rem = [c for i, c in enumerate(chunks) if i != year_idx]
                        else:
                            birth_year = None
                            rem = chunks

                    if len(rem) >= 3:
                        # Si no hay año, limitar a máximo 4 columnas para evitar falsos positivos con pies de página
                        if birth_year is None and len(rem) > 4:
                            continue
                        club_clean = re.sub(r'^\d+[\.\)]?\s*', '', rem[0]).strip()
                        last_str = rem[1]
                        first_str = ' '.join(rem[2:])
                        if club_clean and last_str and first_str:
                            players.append({
                                'club': club_clean,
                                'last_name': last_str,
                                'first_name': first_str,
                                'birth_year': birth_year,
                            })
                            parsed = True

                # Estrategia 2: Fallback por posiciones fijas según cabecera
                if not parsed and header_positions:
                    p_club = header_positions['club']
                    p_last = header_positions['last_name']
                    p_first = header_positions['first_name']
                    p_year = header_positions['birth_year']

                    club_str = line[p_club:p_last].strip()
                    last_str = line[p_last:p_first].strip()
                    first_str = line[p_first:p_year].strip()
                    year_str = line[p_year:].strip()

                    club_clean = re.sub(r'^\d+[\.\)]?\s*', '', club_str).strip()
                    m_year = re.search(r'\b(19\d{2}|20\d{2})\b', year_str or line)
                    birth_year = int(m_year.group(1)) if m_year else None

                    if not birth_year:
                        m_year_in_first = re.search(r'\b(19\d{2}|20\d{2})\b', first_str)
                        if m_year_in_first:
                            birth_year = int(m_year_in_first.group(1))
                            first_str = re.sub(r'\b(19\d{2}|20\d{2})\b', '', first_str).strip()

                    if club_clean and last_str and first_str:
                        players.append({
                            'club': club_clean,
                            'last_name': last_str,
                            'first_name': first_str,
                            'birth_year': birth_year,
                        })

    raw_text = '\n'.join(all_pages_text)
    return raw_text, players
