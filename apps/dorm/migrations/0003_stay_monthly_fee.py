from django.db import migrations, models


def copy_room_fee(apps, schema_editor):
    """Mavjud qaydlar uchun o'quvchi narxi = xona narxi."""
    DormStay = apps.get_model("dorm", "DormStay")
    for stay in DormStay.objects.select_related("room"):
        stay.monthly_fee = stay.room.monthly_fee
        stay.save(update_fields=["monthly_fee"])


class Migration(migrations.Migration):

    dependencies = [
        ("dorm", "0002_room_status_type_floor"),
    ]

    operations = [
        migrations.AddField(
            model_name="dormstay",
            name="monthly_fee",
            field=models.DecimalField(decimal_places=2, max_digits=12, null=True, verbose_name="oylik to'lov"),
        ),
        migrations.RunPython(copy_room_fee, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="dormstay",
            name="monthly_fee",
            field=models.DecimalField(
                decimal_places=2, max_digits=12, verbose_name="oylik to'lov",
                help_text="Shu o'quvchi uchun (xona narxidan kam bo'lsa — farq chegirma)"),
        ),
    ]
