from django.test import TestCase

from ilovevoley.competitions.models import Venue


class VenueSeedDataTest(TestCase):
    def test_canonical_venues_seeded(self):
        """Verifica que la migración seed cargó los pabellones baleares principales."""
        self.assertTrue(Venue.objects.filter(name="Pavelló Joan Pericás Riera").exists())
        self.assertTrue(Venue.objects.filter(name="Pavelló Son Angelats").exists())
        self.assertTrue(Venue.objects.filter(name="Poliesportiu Germans Escalas").exists())
        self.assertTrue(Venue.objects.filter(name="Pavelló Municipal d'Alaró").exists())
        self.assertGreaterEqual(Venue.objects.count(), 30)
