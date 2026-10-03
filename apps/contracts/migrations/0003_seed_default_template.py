from pathlib import Path

from django.db import migrations

TEMPLATE_FILE = Path(__file__).resolve().parent.parent / "default_template.txt"


def seed(apps, schema_editor):
    """Sukut shablon: "Ota-ona shartnomasi". Mavjud (bekor qilinmagan) shartnomalarga biriktiriladi."""
    ContractTemplate = apps.get_model("contracts", "ContractTemplate")
    Contract = apps.get_model("contracts", "Contract")
    template, _ = ContractTemplate.objects.get_or_create(
        name="Ota-ona shartnomasi", defaults={"body": TEMPLATE_FILE.read_text(encoding="utf-8"), "is_default": True})
    Contract.objects.filter(template__isnull=True).exclude(status="cancelled").update(template=template)


class Migration(migrations.Migration):
    dependencies = [("contracts", "0002_contract_templates")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
