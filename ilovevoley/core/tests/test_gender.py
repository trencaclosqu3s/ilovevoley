from django.test import TestCase

from ilovevoley.core.models import (
    GENDER_FEMALE,
    GENDER_MALE,
    GENDER_MIXED,
    Organization,
    infer_gender_from_name,
)


class InferGenderFromNameTest(TestCase):
    def test_detects_gender_from_name(self):
        self.assertEqual(infer_gender_from_name('Senior Femenino'), GENDER_FEMALE)
        self.assertEqual(infer_gender_from_name('Infantil femenina'), GENDER_FEMALE)
        self.assertEqual(infer_gender_from_name('Alevín Masculino'), GENDER_MALE)
        self.assertEqual(infer_gender_from_name('Cadete Mixto'), GENDER_MIXED)

    def test_unknown_or_empty_returns_blank(self):
        self.assertEqual(infer_gender_from_name('Senior'), '')
        self.assertEqual(infer_gender_from_name(''), '')


class OrganizationBranchesTest(TestCase):
    def test_default_branches_are_male_only(self):
        org = Organization.objects.create(slug='o-default', name='Org Default')
        self.assertEqual(org.active_branches, {GENDER_MALE})
