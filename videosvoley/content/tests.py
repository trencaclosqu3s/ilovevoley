from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from .models import Category, Video, Comment, Image

User = get_user_model()


class CategoryModelTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Senior",
            description="Categoría senior",
            is_active=True
        )

    def test_category_creation(self):
        self.assertEqual(self.category.name, "Senior")
        self.assertTrue(self.category.is_active)
        self.assertIsNotNone(self.category.created_at)

    def test_category_str(self):
        self.assertEqual(str(self.category), "Senior")


class VideoModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.category = Category.objects.create(
            name="Senior",
            is_active=True
        )
        self.video = Video.objects.create(
            title="Test Video",
            youtube_url="https://www.youtube.com/watch?v=test123",
            description="Test description",
            category=self.category,
            created_by=self.user
        )

    def test_video_creation(self):
        self.assertEqual(self.video.title, "Test Video")
        self.assertEqual(self.video.created_by, self.user)
        self.assertEqual(self.video.category, self.category)

    def test_get_embed_url(self):
        embed_url = self.video.get_embed_url()
        self.assertIn('youtube-nocookie.com/embed/test123', embed_url)
        self.assertIn('rel=0', embed_url)
        self.assertIn('modestbranding=1', embed_url)

    def test_is_livestream(self):
        # Test normal video
        self.assertFalse(self.video.is_livestream())
        
        # Test livestream
        livestream_video = Video.objects.create(
            title="Live Video",
            youtube_url="https://www.youtube.com/live/test123",
            created_by=self.user
        )
        self.assertTrue(livestream_video.is_livestream())

    def test_get_video_type(self):
        self.assertEqual(self.video.get_video_type(), 'video')
        
        livestream_video = Video.objects.create(
            title="Live Video",
            youtube_url="https://www.youtube.com/live/test123",
            created_by=self.user
        )
        self.assertEqual(livestream_video.get_video_type(), 'livestream')


class CommentModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.video = Video.objects.create(
            title="Test Video",
            youtube_url="https://www.youtube.com/watch?v=test123",
            created_by=self.user
        )
        self.comment = Comment.objects.create(
            video=self.video,
            user=self.user,
            content="Test comment"
        )

    def test_comment_creation(self):
        self.assertEqual(self.comment.content, "Test comment")
        self.assertEqual(self.comment.video, self.video)
        self.assertEqual(self.comment.user, self.user)

    def test_comment_str(self):
        expected = f"{self.user.username} - {self.comment.content[:50]}..."
        self.assertEqual(str(self.comment), expected)


class ImageModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.category = Category.objects.create(
            name="Senior",
            is_active=True
        )
        
        # Crear archivo de imagen de prueba
        image_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
        self.test_image = SimpleUploadedFile(
            "test.png",
            image_content,
            content_type="image/png"
        )
        
        self.image = Image.objects.create(
            image=self.test_image,
            title="Test Image",
            description="Test description",
            image_type="match",
            year=2024,
            uploaded_by=self.user
        )

    def test_image_creation(self):
        self.assertEqual(self.image.title, "Test Image")
        self.assertEqual(self.image.uploaded_by, self.user)
        self.assertEqual(self.image.image_type, "match")
        self.assertEqual(self.image.year, 2024)

    def test_image_status_defaults(self):
        self.assertEqual(self.image.status, "pending")
        self.assertFalse(self.image.vision_api_checked)
        self.assertTrue(self.image.vision_api_safe)

    def test_is_approved(self):
        self.assertFalse(self.image.is_approved)
        self.image.status = "approved"
        self.assertTrue(self.image.is_approved)

    def test_is_pending(self):
        self.assertTrue(self.image.is_pending)
        self.image.status = "approved"
        self.assertFalse(self.image.is_pending)

    def test_moderate(self):
        self.image.moderate(self.user, approved=True, notes="Test approval")
        self.assertEqual(self.image.status, "approved")
        self.assertEqual(self.image.moderated_by, self.user)
        self.assertEqual(self.image.moderation_notes, "Test approval")
        self.assertIsNotNone(self.image.moderation_date)

    def test_all_tags(self):
        self.image.tags = "gol, victoria, senior"
        self.image.auto_tags = ["fútbol", "deporte"]
        expected_tags = ["gol", "victoria", "senior", "fútbol", "deporte"]
        self.assertEqual(set(self.image.all_tags), set(expected_tags))

    def test_tags_display(self):
        self.image.tags = "gol, victoria, senior"
        self.image.auto_tags = ["fútbol", "deporte"]
        tags_display = self.image.tags_display
        self.assertIn("gol", tags_display)
        self.assertIn("victoria", tags_display)
        self.assertIn("senior", tags_display)
        self.assertIn("fútbol", tags_display)
        self.assertIn("deporte", tags_display)


class ContentViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_approved=True
        )
        self.category = Category.objects.create(
            name="Senior",
            is_active=True
        )
        self.video = Video.objects.create(
            title="Test Video",
            youtube_url="https://www.youtube.com/watch?v=test123",
            created_by=self.user,
            category=self.category
        )

    def test_video_list_view(self):
        response = self.client.get(reverse('content:video_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Video")

    def test_video_detail_view(self):
        response = self.client.get(reverse('content:video_detail', args=[self.video.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Video")

    def test_image_gallery_view(self):
        response = self.client.get(reverse('content:image_gallery'))
        self.assertEqual(response.status_code, 200)

    def test_video_list_with_filters(self):
        # Test category filter
        response = self.client.get(reverse('content:video_list'), {'category': self.category.id})
        self.assertEqual(response.status_code, 200)
        
        # Test search
        response = self.client.get(reverse('content:video_list'), {'search': 'Test'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Video")