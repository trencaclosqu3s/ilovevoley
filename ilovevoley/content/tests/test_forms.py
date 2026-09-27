from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from ilovevoley.content.forms import ImageUploadForm, VideoEntryForm, VideoForm

TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)


class SetNumberFormFieldTest(TestCase):
    def test_video_form_accepts_set_number(self):
        form = VideoForm(data={
            'title': 'Set 2',
            'youtube_url': 'https://youtu.be/abc',
            'set_number': '2',
        }, organization=None)
        self.assertIn('set_number', form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['set_number'], 2)

    def test_video_entry_formset_row_accepts_set_number(self):
        form = VideoEntryForm(data={
            'title': 'Set 1',
            'youtube_url': 'https://youtu.be/abc',
            'set_number': '1',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['set_number'], 1)

    def test_image_upload_form_has_set_number_field(self):
        # El nombre debe tener extensión permitida por clean_image(): jpg.
        form = ImageUploadForm(
            data={'title': 'Foto', 'image_type': 'match', 'set_number': '3'},
            files={'image': SimpleUploadedFile('x.jpg', TINY_GIF, content_type='image/jpeg')},
            organization=None,
        )
        self.assertIn('set_number', form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['set_number'], 3)
