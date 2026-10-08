from django.db import migrations

# Built-in categories available to every household (household=NULL).
DEFAULT_CATEGORIES = [
    ("Rent", "#059669"),
    ("Mortgage", "#0d9488"),
    ("Electricity", "#ca8a04"),
    ("Gas", "#ea580c"),
    ("Water", "#0284c7"),
    ("Internet", "#4f46e5"),
    ("Phone", "#7c3aed"),
    ("Insurance", "#db2777"),
    ("Subscriptions", "#dc2626"),
    ("Groceries", "#16a34a"),
    ("Maintenance", "#64748b"),
    ("Other", "#94a3b8"),
]


def seed(apps, schema_editor):
    Category = apps.get_model("bills", "Category")
    for name, color in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(household=None, name=name, defaults={"color": color})


def unseed(apps, schema_editor):
    Category = apps.get_model("bills", "Category")
    Category.objects.filter(
        household=None, name__in=[n for n, _ in DEFAULT_CATEGORIES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("bills", "0002_initial")]

    operations = [migrations.RunPython(seed, unseed)]
