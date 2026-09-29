import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateStorage(FileSystemStorage):
    """Shaxsiy hujjatlar uchun: PRIVATE_MEDIA_ROOT'da, veb-server bermaydi, URL'i yo'q.

    Yo'l har safar sozlamalardan o'qiladi (model yuklangan paytda qotib qolmaydi).
    """

    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None

    def url(self, name):
        raise ValueError("Shaxsiy fayllarning ommaviy URL'i yo'q — ruxsat tekshiradigan view orqali bering.")
