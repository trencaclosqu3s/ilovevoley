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
