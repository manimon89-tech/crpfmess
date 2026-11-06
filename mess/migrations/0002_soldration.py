from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("mess", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="SoldRation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(default=django.utils.timezone.localdate)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=12)),
                ("name", models.CharField(help_text="Name of the person buying the ration", max_length=150)),
                ("unit_price", models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=12)),
                ("total_amount", models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=12)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ration_sales", to="mess.stockitem")),
            ],
            options={"ordering": ["-date", "-id"]},
        ),
    ]
