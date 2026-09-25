from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Topic


class TopicTests(TestCase):
    def setUp(self):
        self.main = Topic.objects.create(title='Ana')
        self.sub = Topic.objects.create(title='Alt', parent=self.main)
        self.deleted_sub = Topic.objects.create(title='Silinmiş alt', parent=self.main, is_deleted=True)

    def set(self, topic, **fields):
        Topic.objects.filter(pk=topic.pk).update(**fields)

    def test_two_levels_only(self):
        Topic(title='Alt 2', parent=self.main).full_clean()
        with self.assertRaises(ValidationError):
            Topic(title='Torun', parent=self.sub).full_clean()

    def test_visible(self):
        self.assertQuerySetEqual(Topic.objects.visible(), [self.main, self.sub], ordered=False)
        self.set(self.main, is_deleted=True)
        self.assertFalse(Topic.objects.visible().exists())  # üst konusu silinen de gizli
        self.set(self.main, is_deleted=False)
        # Ana konu geri gelince her alt konu kendi durumuna döner
        self.assertQuerySetEqual(Topic.objects.visible(), [self.main, self.sub], ordered=False)

    def test_locked_is_inherited_not_written(self):
        self.assertFalse(Topic.objects.get(pk=self.sub.pk).is_locked)
        self.set(self.main, is_closed=True)
        sub = Topic.objects.get(pk=self.sub.pk)
        self.assertTrue(sub.is_locked)
        self.assertFalse(sub.is_closed)

    def test_pages(self):
        home = self.client.get('/')
        self.assertContains(home, self.main.get_absolute_url())
        self.assertNotContains(home, self.sub.get_absolute_url())  # ana sayfada yalnızca ana konular
        page = self.client.get(self.main.get_absolute_url())
        self.assertContains(page, self.sub.get_absolute_url())
        self.assertNotContains(page, self.deleted_sub.get_absolute_url())
        self.assertEqual(self.client.get(self.deleted_sub.get_absolute_url()).status_code, 404)
        self.set(self.main, is_deleted=True)
        self.assertEqual(self.client.get(self.sub.get_absolute_url()).status_code, 404)
