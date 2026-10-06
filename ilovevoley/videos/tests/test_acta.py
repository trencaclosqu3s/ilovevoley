"""Parsing de los bloques no deportivos del acta (observaciones, firmas, oficiales).

Los fragmentos replican la estructura del HTML real de
``voleibolib.federatio.com/actas/{id}/acta_XXXX.html`` (acta 81210 y 85846):
el mismo recuadro ``sin-borde`` para las observaciones, ``td.espacio-firma``
para cada firma y la tabla OFICIALES con cabecera LOCAL / ROL / VISITANTE.
"""

from django.test import SimpleTestCase

from ilovevoley.videos.scraping import parse_acta_lineup


ACTA_HTML = """
<html><body>
<table class="sin-borde">
  <tr><td>Observaciones:
  Delegado de pista Sr Bibiloni</td></tr>
</table>
<table class="sin-borde">
  <tr>
    <td class="espacio-firma">
      Firma Árbitro<br>
      <strong>GARCIA, PABLO</strong><br>
      <img src="firma_arbitro1.png" height="50">
    </td>
    <td class="espacio-firma">
      Firma Árbitro 2<br>
      <br>
    </td>
  </tr>
  <tr>
    <td class="espacio-firma">
      Firma Entrenador Local<br>
      <strong>ANDREA LOPEZ</strong><br>
      <img src="firma_entrenador_local_ap.png" height="50">
    </td>
    <td class="espacio-firma">
      Firma Entrenador Visitante<br>
      <strong>XIM RODRIGUEZ</strong><br>
      <img src="firma_entrenador_visitante_ap.png" height="50">
    </td>
  </tr>
</table>
<table width="100%" border="1">
  <tr class="seccion">
    <td style="text-align:center;">LOCAL</td>
    <td style="text-align:center;">ROL</td>
    <td style="text-align:center;">VISITANTE</td>
  </tr>
  <tr>
    <td class="textoPeque">ANDREA LOPEZ MORENO<br></td>
    <td class="seccion" style="text-align:center;">C</td>
    <td class="textoPeque">XIM  RODRIGUEZ FORTEZA<br></td>
  </tr>
</table>
</body></html>
"""


class ParseActaExtrasTests(SimpleTestCase):
    def test_extrae_observaciones_y_quita_la_etiqueta(self):
        result = parse_acta_lineup(ACTA_HTML)
        self.assertEqual(result['observations'], 'Delegado de pista Sr Bibiloni')

    def test_extrae_entrenadores_de_las_firmas(self):
        result = parse_acta_lineup(ACTA_HTML)
        self.assertEqual(result['home_coach'], 'ANDREA LOPEZ')
        self.assertEqual(result['away_coach'], 'XIM RODRIGUEZ')

    def test_recoge_solo_los_arbitros_con_nombre(self):
        result = parse_acta_lineup(ACTA_HTML)
        self.assertEqual(result['referees'], ['GARCIA, PABLO'])

    def test_extrae_oficiales_de_la_tabla(self):
        result = parse_acta_lineup(ACTA_HTML)
        self.assertEqual(result['officials'], [{
            'local': 'ANDREA LOPEZ MORENO',
            'role': 'C',
            'visitor': 'XIM RODRIGUEZ FORTEZA',
        }])


class ParseActaExtrasEmptyTests(SimpleTestCase):
    """El acta puede traer las firmas solo como imagen y la tabla OFICIALES vacía."""

    HTML = """
    <html><body>
    <table class="sin-borde">
      <tr><td>Observaciones: Delegado de pista Sr Bibiloni</td></tr>
    </table>
    <table class="sin-borde">
      <tr>
        <td class="espacio-firma">Firma Árbitro<br><strong></strong><br>
          <img src="firma_arbitro1.png"></td>
        <td class="espacio-firma">Firma Árbitro 2<br><br></td>
      </tr>
      <tr>
        <td class="espacio-firma">Firma Entrenador Local<br><strong></strong><br>
          <img src="firma_entrenador_local_ap.png"></td>
        <td class="espacio-firma">Firma Entrenador Visitante<br><strong></strong><br>
          <img src="firma_entrenador_visitante_ap.png"></td>
      </tr>
    </table>
    <table width="100%" border="1">
      <tr class="seccion">
        <td style="text-align:center;">LOCAL</td>
        <td style="text-align:center;">ROL</td>
        <td style="text-align:center;">VISITANTE</td>
      </tr>
    </table>
    </body></html>
    """

    def test_entrenadores_y_arbitros_vacios_si_solo_hay_imagen(self):
        result = parse_acta_lineup(self.HTML)
        self.assertEqual(result['home_coach'], '')
        self.assertEqual(result['away_coach'], '')
        self.assertEqual(result['referees'], [])

    def test_tabla_oficiales_sin_filas(self):
        result = parse_acta_lineup(self.HTML)
        self.assertEqual(result['officials'], [])
