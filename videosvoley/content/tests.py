"""
Tests para la app content.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import Video, Comment, Category, Image
from videosvoley.competitions.models import League, Match
from videosvoley.teams.models import Team

User = get_user_model()


class ContentModelsTestCase(TestCase):
    def setUp(self):
        """Configurar datos de prueba"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_approved=True
        )
        
        self.category = Category.objects.create(
            name='Senior',
            description='Categoría Senior',
            is_active=True
        )
        
        self.team = Team.objects.create(
            name='SANT JOSEP Senior',
            category=self.category,
            is_active=True
        )
        
        self.league = League.objects.create(
            name='Liga Test',
            category=self.category,
            season='2024-25',
            is_active=True
        )
        
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team,
            match_date='2024-01-15 18:00:00',
            venue='Polideportivo Test'
        )

    def test_video_creation(self):
        """Test creación de video"""
        video = Video.objects.create(
            title='Test Video',
            youtube_url='https://www.youtube.com/watch?v=test123',
            description='Video de prueba',
            category=self.category,
            match=self.match,
            created_by=self.user
        )
        
        self.assertEqual(video.title, 'Test Video')
        self.assertEqual(video.youtube_url_id, 'test123')
        self.assertEqual(video.category, self.category)
        self.assertEqual(video.match, self.match)
        self.assertEqual(video.created_by, self.user)

    def test_comment_creation(self):
        """Test creación de comentario"""
        video = Video.objects.create(
            title='Test Video',
            youtube_url='https://www.youtube.com/watch?v=test123',
            category=self.category,
            created_by=self.user
        )
        
        comment = Comment.objects.create(
            video=video,
            user=self.user,
            content='Comentario de prueba'
        )
        
        self.assertEqual(comment.video, video)
        self.assertEqual(comment.user, self.user)
        self.assertEqual(comment.content, 'Comentario de prueba')

    def test_image_creation(self):
        """Test creación de imagen"""
        # Crear archivo de imagen de prueba
        image_file = SimpleUploadedFile(
            "test_image.jpg",
            b"fake image content",
            content_type="image/jpeg"
        )
        
        image = Image.objects.create(
            image=image_file,
            title='Test Image',
            description='Imagen de prueba',
            image_type='match',
            uploaded_by=self.user,
            match=self.match
        )
        
        self.assertEqual(image.title, 'Test Image')
        self.assertEqual(image.image_type, 'match')
        self.assertEqual(image.uploaded_by, self.user)
        self.assertEqual(image.match, self.match)
        self.assertEqual(image.status, 'pending')

    def test_category_creation(self):
        """Test creación de categoría"""
        category = Category.objects.create(
            name='Test Category',
            description='Categoría de prueba',
            is_active=True
        )
        
        self.assertEqual(category.name, 'Test Category')
        self.assertTrue(category.is_active)
        self.assertEqual(str(category), 'Test Category')


class ContentViewsTestCase(TestCase):
    def setUp(self):
        """Configurar datos de prueba"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_approved=True
        )
        
        self.category = Category.objects.create(
            name='Senior',
            description='Categoría Senior',
            is_active=True
        )

    def test_video_list_view(self):
        """Test vista de lista de videos"""
        response = self.client.get('/content/')
        self.assertEqual(response.status_code, 302)  # Redirect to login
        
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/content/')
        self.assertEqual(response.status_code, 200)

    def test_image_gallery_view(self):
        """Test vista de galería de imágenes"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/content/imagenes/')
        self.assertEqual(response.status_code, 200)

    def test_video_create_view_permission(self):
        """Test permisos para crear video"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/content/nuevo/')
        self.assertEqual(response.status_code, 403)  # No permission
        
        # Agregar usuario al grupo VideoManagers
        from django.contrib.auth.models import Group
        group = Group.objects.create(name='VideoManagers')
        self.user.groups.add(group)
        
        response = self.client.get('/content/nuevo/')
        self.assertEqual(response.status_code, 200)


class ContentFormsTestCase(TestCase):
    def setUp(self):
        """Configurar datos de prueba"""
        self.category = Category.objects.create(
            name='Senior',
            description='Categoría Senior',
            is_active=True
        )

    def test_video_form(self):
        """Test formulario de video"""
        from .forms import VideoForm
        
        form_data = {
            'title': 'Test Video',
            'youtube_url': 'https://www.youtube.com/watch?v=test123',
            'description': 'Video de prueba',
            'category': self.category.id,
        }
        
        form = VideoForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_comment_form(self):
        """Test formulario de comentario"""
        from .forms import CommentForm
        
        form_data = {
            'content': 'Comentario de prueba'
        }
        
        form = CommentForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_image_upload_form(self):
        """Test formulario de subida de imagen"""
        from .forms import ImageUploadForm
        
        form_data = {
            'title': 'Test Image',
            'description': 'Imagen de prueba',
            'image_type': 'match',
        }
        
        form = ImageUploadForm(data=form_data)
        # El formulario será válido sin imagen para este test
        self.assertTrue(form.is_valid())


class ContentUtilsTestCase(TestCase):
    def test_extract_youtube_id(self):
        """Test extracción de ID de YouTube"""
        from .utils import extract_youtube_id
        
        # URLs válidas
        self.assertEqual(extract_youtube_id('https://www.youtube.com/watch?v=test123'), 'test123')
        self.assertEqual(extract_youtube_id('https://youtu.be/test123'), 'test123')
        self.assertEqual(extract_youtube_id('https://www.youtube.com/embed/test123'), 'test123')
        
        # URL inválida
        self.assertIsNone(extract_youtube_id('https://example.com'))
        self.assertIsNone(extract_youtube_id(''))

    def test_generate_thumbnail_url(self):
        """Test generación de URL de thumbnail"""
        from .utils import generate_thumbnail_url
        
        expected_url = 'https://img.youtube.com/vi/test123/mqdefault.jpg'
        self.assertEqual(generate_thumbnail_url('test123'), expected_url)
        
        # Con calidad específica
        expected_high = 'https://img.youtube.com/vi/test123/hqdefault.jpg'
        self.assertEqual(generate_thumbnail_url('test123', 'high'), expected_high)
        
        # ID inválido
        self.assertIsNone(generate_thumbnail_url(''))

    def test_normalize_text(self):
        """Test normalización de texto"""
        from .utils import normalize_text
        
        # Texto con acentos
        self.assertEqual(normalize_text('Café'), 'cafe')
        self.assertEqual(normalize_text('Niño'), 'nino')
        
        # Texto con caracteres especiales
        self.assertEqual(normalize_text('¡Hola! ¿Cómo estás?'), 'hola como estas')
        
        # Texto vacío
        self.assertEqual(normalize_text(''), '')
        self.assertEqual(normalize_text(None), '')