from django.db import migrations


def seed(apps, schema_editor):
    """Boshlang'ich tumanlar ro'yxati + mavjud o'quvchilarning mahallalari (erkin matndan) bazaga."""
    from apps.people.domain.regions import DISTRICTS

    District = apps.get_model("people", "District")
    Mahalla = apps.get_model("people", "Mahalla")
    Student = apps.get_model("people", "Student")
    for region, names in DISTRICTS.items():
        for name in names:
            District.objects.get_or_create(region=region, name=name)
    rows = (Student.objects.exclude(district="").exclude(mahalla="")
            .values_list("region", "district", "mahalla").distinct())
    for region, district_name, mahalla in rows:
        district = District.objects.filter(region=region, name__iexact=district_name).first()
        if district and not Mahalla.objects.filter(district=district, name__iexact=mahalla).exists():
            Mahalla.objects.create(district=district, name=mahalla.strip())


class Migration(migrations.Migration):
    dependencies = [("people", "0007_address_directory")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
