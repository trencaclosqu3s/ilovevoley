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
    """
    clean_title = title.strip()
    norm_title = _remove_accents(clean_title).upper()

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

    for page in reader.pages:
        try:
            page_text = page.extract_text(extraction_mode='layout') or ''
        except Exception:
            page_text = page.extract_text() or ''

        all_pages_text.append(page_text)
        lines = page_text.splitlines()

        # Buscar línea de cabecera tabular
        header_positions: dict[str, int] | None = None

        for line in lines:
            norm_line = _remove_accents(line).upper()

            # Comprobar si es cabecera
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

                pos_year = norm_line.find('ANY')
                if pos_year == -1:
                    pos_year = norm_line.find('ANO')
                if pos_year == -1:
                    pos_year = norm_line.find('DATA')

                if pos_club != -1 and pos_last != -1 and pos_first != -1:
                    header_positions = {
                        'club': pos_club,
                        'last': pos_last,
                        'first': pos_first,
                        'year': pos_year if pos_year != -1 else len(line),
                    }
                    continue

            # Si ya tenemos cabecera, intentar parsear fila
            if header_positions:
                stripped = line.strip()
                if not stripped:
                    continue

                # Si entramos en otra sección técnica, reiniciar cabecera
                if any(sec in norm_line for sec in ['ENTRENADOR', 'TECNIC', 'HORARI', 'LLOC', 'OBSERVACI']):
                    header_positions = None
                    continue

                p_club = header_positions['club']
                p_last = header_positions['last']
                p_first = header_positions['first']
                p_year = header_positions['year']

                club_str = line[p_club:p_last].strip()
                last_str = line[p_last:p_first].strip()
                first_str = line[p_first:p_year].strip()
                year_str = line[p_year:].strip()

                # Quitar número de orden inicial si estuviera en club (ej. "1 CV SANT JOSEP")
                club_clean = re.sub(r'^\d+[\.\)]?\s*', '', club_str).strip()

                # Extraer año si existe
                m_year = re.search(r'\b(19\d{2}|20\d{2})\b', year_str or line)
                birth_year = int(m_year.group(1)) if m_year else None

                # Si first_str tiene el año incrustado por desajuste de columnas
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
                    continue

            # Fallback sin header_positions: intentar dividir por 2 o más espacios
            chunks = [c.strip() for c in re.split(r'\s{2,}', line.strip()) if c.strip()]
            # Quitar índice inicial si existe
            if chunks and re.match(r'^\d+[\.\)]?$', chunks[0]):
                chunks = chunks[1:]

            if len(chunks) >= 3:
                # Caso: [club, apellidos, nombre, año]
                m_year = re.search(r'\b(19\d{2}|20\d{2})\b', chunks[-1])
                if m_year and len(chunks) >= 4:
                    club_val = chunks[0]
                    last_val = chunks[1]
                    first_val = chunks[2]
                    year_val = int(m_year.group(1))
                    players.append({
                        'club': club_val,
                        'last_name': last_val,
                        'first_name': first_val,
                        'birth_year': year_val,
                    })

    raw_text = '\n'.join(all_pages_text)
    return raw_text, players
