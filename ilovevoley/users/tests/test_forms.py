from django.contrib.auth import get_user_model
from django.test import TestCase

from ilovevoley.users.forms import UserProfileForm


class UserProfileFormTest(TestCase):
    """El email no se edita desde el perfil: el cambio pasa por la verificación
    de allauth. Con el campo 'readonly' en el widget un POST manipulado
    bastaba para dejar el email de otra persona en la cuenta.
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='jugador', email='mio@example.com', password='contrasena'
        )

    def test_posted_email_is_ignored(self):
        form = UserProfileForm(
            data={
                'username': 'jugador',
                'email': 'victima@example.com',
                'first_name': 'Jugador',
                'last_name': 'Uno',
            },
            instance=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn('email', form.fields)
        form.save()

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'mio@example.com')
