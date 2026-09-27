from django.utils.functional import SimpleLazyObject

from .models import SchoolSettings


def school(request):
    # Lazy: shablon `school` ga murojaat qilmasa kesh/bazaga umuman borilmaydi.
    return {"school": SimpleLazyObject(SchoolSettings.load)}
