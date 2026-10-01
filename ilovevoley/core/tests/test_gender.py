from django.test import TestCase

from ilovevoley.core.models import (
    GENDER_FEMALE,
    GENDER_MALE,
    GENDER_MIXED,
    Organization,
    infer_gender_from_name,
)


class InferGenderFromNameTest(TestCase):
    def test_detects_female(self):
        self.assertEqual(infer_gender_from_name('Senior Femenino'), GENDER_FEMALE)
        self.assertEqual(infer_gender_from_name('Infantil femenina'), GENDER_FEMALE)

    def test_detects_male(self):
        self.assertEqual(infer_gender_from_name('Alevín Masculino'), GENDER_MALE)

    def test_detects_mixed(self):
        self.assertEqual(infer_gender_from_name('Cadete Mixto'), GENDER_MIXED)

    def test_unknown_or_empty_returns_blank(self):
        self.assertEqual(infer_gender_from_name('Senior'), '')
        self.assertEqual(infer_gender_from_name(''), '')


class OrganizationBranchesTest(TestCase):
    def test_default_branches_are_male_only(self):
        org = Organization.objects.create(slug='o-default', name='Org Default')
        self.assertEqual(org.active_branches, {GENDER_MALE})

    def test_active_branches_reflects_flags(self):
        org = Organization.objects.create(
            slug='o-mixed',
            name='Org Mixed',
            has_male_branch=False,
            has_female_branch=True,
            has_mixed_branch=True,
        )
        self.assertEqual(org.active_branches, {GENDER_FEMALE, GENDER_MIXED})
