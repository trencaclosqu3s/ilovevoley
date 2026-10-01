import io
import pytest
from ilovevoley.competitions.services.callup_parser import (
    parse_callup_title,
    extract_callup_players_from_pdf,
)


def create_dummy_pdf(lines: list[str]) -> bytes:
    stream_lines = ["BT", "/F1 12 Tf", "50 750 Td"]
    first = True
    for line in lines:
        clean_line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if first:
            stream_lines.append(f"({clean_line}) Tj")
            first = False
        else:
            stream_lines.append("0 -20 Td")
            stream_lines.append(f"({clean_line}) Tj")
    stream_lines.append("ET")
    stream_content = "\n".join(stream_lines).encode("latin-1", errors="replace")
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >> endobj\n"
        b"5 0 obj << /Length " + str(len(stream_content)).encode("ascii") + b" >> stream\n"
        + stream_content + b"\nendstream\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000227 00000 n \n"
        b"0000000298 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"startxref\n500\n%%EOF\n"
    )


def test_parse_callup_title_beach():
    res = parse_callup_title("3ª CONVOCATORIA SELECCIO BALEAR VP INF MASC")
    assert res['modality'] == 'beach'
    assert res['category_name'] == 'Infantil'
    assert res['gender'] == 'M'
    assert res['callup_number'] == '3ª'


def test_parse_callup_title_indoor_and_short_codes():
    res1 = parse_callup_title("CONVOCATORIA 23-30 IF")
    assert res1['modality'] == 'indoor'
    assert res1['category_name'] == 'Infantil'
    assert res1['gender'] == 'F'
    assert res1['callup_number'] == '23-30'

    res2 = parse_callup_title("9ª Y 10ª CONVOCATORIA SELECCION BALEAR VP CAD FEM")
    assert res2['modality'] == 'beach'
    assert res2['category_name'] == 'Cadete'
    assert res2['gender'] == 'F'
    assert res2['callup_number'] == '9ª Y 10ª'


def test_extract_callup_players_from_pdf():
    pdf_bytes = create_dummy_pdf([
        "CONVOCATÒRIA PREPARATÒRIA TREBALL",
        "CLUB          LLINATGES            NOM         ANY",
        "CV SANT JOSEP RIERA MARTÍN         LLUC        2013",
        "CV PÒRTOL     MUÑOZ ALCOCEBA       NORMA       2010",
    ])

    raw_text, players = extract_callup_players_from_pdf(pdf_bytes)
    assert len(players) == 2
    assert players[0]['club'] == 'CV SANT JOSEP'
    assert players[0]['last_name'] == 'RIERA MARTÍN'
    assert players[0]['first_name'] == 'LLUC'
    assert players[0]['birth_year'] == 2013
    assert players[1]['club'] == 'CV PÒRTOL'
    assert players[1]['last_name'] == 'MUÑOZ ALCOCEBA'
    assert players[1]['first_name'] == 'NORMA'
    assert players[1]['birth_year'] == 2010


def test_extract_callup_players_chunking_with_composite_names_and_no_year():
    pdf_bytes = create_dummy_pdf([
        "CONVOCATÒRIA PREPARATÒRIA TREBALL",
        "CLUB                         LLINATGES                          NOM                   ANY DE NAIXEMENT",
        "1    CV SANT JOSEP           MARTÍNEZ FERRER                    PERE ANDREU           2008",
        "2    CV SÓLLER               ALÈS                               MARC",
        "14",
    ])

    raw_text, players = extract_callup_players_from_pdf(pdf_bytes)
    assert len(players) == 2
    assert players[0]['club'] == 'CV SANT JOSEP'
    assert players[0]['last_name'] == 'MARTÍNEZ FERRER'
    assert players[0]['first_name'] == 'PERE ANDREU'
    assert players[0]['birth_year'] == 2008

    assert players[1]['club'] == 'CV SÓLLER'
    assert players[1]['last_name'] == 'ALÈS'
    assert players[1]['first_name'] == 'MARC'
    assert players[1]['birth_year'] is None


def test_extract_callup_players_multipage_continuation_without_header():
    import pypdf
    page1_bytes = create_dummy_pdf([
        "CONVOCATÒRIA SELECCIÓ",
        "CLUB                         LLINATGES                          NOM                   ANY",
        "1    CV SANT JOSEP           RIERA MARTÍN                       LLUC                  2013",
    ])
    page2_bytes = create_dummy_pdf([
        "2    CV PÒRTOL               MUÑOZ ALCOCEBA                     NORMA                 2010",
        "3    CV MANACOR              GALMÉS                             JOAN                  2011",
    ])
    writer = pypdf.PdfWriter()
    writer.append(io.BytesIO(page1_bytes))
    writer.append(io.BytesIO(page2_bytes))
    buf = io.BytesIO()
    writer.write(buf)
    multipage_pdf = buf.getvalue()

    raw_text, players = extract_callup_players_from_pdf(multipage_pdf)
    assert len(players) == 3
    assert players[0]['club'] == 'CV SANT JOSEP'
    assert players[1]['club'] == 'CV PÒRTOL'
    assert players[2]['club'] == 'CV MANACOR'


def test_extract_callup_players_composite_name_without_year_and_middle_year():
    pdf_bytes = create_dummy_pdf([
        "CONVOCATÒRIA SELECCIÓ",
        "CLUB                         LLINATGES                          NOM                   ANY",
        "1    CV SANT JOSEP           GARCÍA FERRER                      MARÍA JOSÉ",
        "2    CV PÒRTOL               2011                               SÁNCHEZ               MIQUEL",
    ])
    raw_text, players = extract_callup_players_from_pdf(pdf_bytes)
    assert len(players) == 2
    assert players[0]['club'] == 'CV SANT JOSEP'
    assert players[0]['last_name'] == 'GARCÍA FERRER'
    assert players[0]['first_name'] == 'MARÍA JOSÉ'
    assert players[0]['birth_year'] is None
    assert players[1]['club'] == 'CV PÒRTOL'
    assert players[1]['birth_year'] == 2011


def test_extract_callup_players_ignores_long_footers_without_year():
    pdf_bytes = create_dummy_pdf([
        "CONVOCATÒRIA SELECCIÓ",
        "CLUB                         LLINATGES                          NOM                   ANY",
        "1    CV SANT JOSEP           RIERA MARTÍN                       LLUC                  2013",
        "Palma de Mallorca             a 12 de febrer de             Federació de Voleibol       de les Illes Balears  Signatura",
    ])
    raw_text, players = extract_callup_players_from_pdf(pdf_bytes)
    assert len(players) == 1
    assert players[0]['club'] == 'CV SANT JOSEP'


def test_extract_callup_players_supervision_format():
    pdf_bytes = create_dummy_pdf([
        "SUPERVISIÓ CTEIB / SELECCIÓ BALEAR",
        "En el següent llistat teniu els esportistes seleccionats:",
        "INFANTIL MASCULÍ:",
        "Marc Buades Sepúlveda         Sant Josep",
        "Tymur Luilchenko              Sant Josep",
        "Joan Servera                  CV Manacor",
        "HORARIS:",
        "Dissabte a les 10:00 h",
    ])
    raw_text, players = extract_callup_players_from_pdf(pdf_bytes)
    assert len(players) == 3
    assert players[0]['first_name'] == 'Marc'
    assert players[0]['last_name'] == 'Buades Sepúlveda'
    assert players[0]['club'] == 'Sant Josep'
    assert players[0]['birth_year'] is None
    assert players[1]['first_name'] == 'Tymur'
    assert players[1]['last_name'] == 'Luilchenko'
    assert players[1]['club'] == 'Sant Josep'
    assert players[2]['first_name'] == 'Joan'
    assert players[2]['last_name'] == 'Servera'
    assert players[2]['club'] == 'CV Manacor'


def test_extract_callup_players_supervision_subirats_not_discarded():
    """Un apellido que contiene 'Sub' (Subirats) no debe confundirse con subtítulo de categoría."""
    pdf_bytes = create_dummy_pdf([
        "En el següent llistat teniu els esportistes seleccionats:",
        "Joan Subirats               CV Manacor",
        "Pere Subirà Valls            CV Pòrtol",
        "HORARIS:",
    ])
    raw_text, players = extract_callup_players_from_pdf(pdf_bytes)
    assert len(players) == 2
    assert players[0]['last_name'] == 'Subirats'
    assert players[1]['last_name'] == 'Subirà Valls'
