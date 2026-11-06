import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

def assign_existing_data(apps, schema_editor):
    Mess = apps.get_model("mess", "Mess")
    Access = apps.get_model("mess", "UserMessAccess")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    db = schema_editor.connection.alias
    mess, _ = Mess.objects.using(db).get_or_create(
        code="DEFAULT", defaults={"name": "Default Mess", "is_active": True}
    )
    tenant_models = [
        "MessSetting", "Member", "StockItem", "Purchase", "StockAddition",
        "Consumption", "Attendance", "Payment", "SoldRation"
    ]
    for model_name in tenant_models:
        Model = apps.get_model("mess", model_name)
        Model.objects.using(db).all().update(mess_id=mess.pk)
    # Existing ordinary accounts retain access to the existing data as accountants.
    for user in User.objects.using(db).filter(is_superuser=False):
        Access.objects.using(db).get_or_create(
            user_id=user.pk, mess_id=mess.pk,
            defaults={"role": "ACCOUNTANT"}
        )

class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("mess", "0002_soldration"),
    ]
    operations = [
        migrations.CreateModel(
            name="Mess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150, unique=True)),
                ("code", models.CharField(blank=True, max_length=30, unique=True)),
                ("address", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="UserMessAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("CO", "Commanding Officer (CO) – dashboards of assigned messes"), ("OC", "Officer Commanding (OC) – dashboard of one assigned mess"), ("ACCOUNTANT", "Accountant – full access to one assigned mess")], max_length=20)),
                ("mess", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="user_accesses", to="mess.mess")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mess_accesses", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["user__username", "mess__name"]},
        ),
        migrations.AddConstraint(
            model_name="usermessaccess",
            constraint=models.UniqueConstraint(fields=("user", "mess"), name="uniq_user_mess_access"),
        ),
        *[
            migrations.AddField(
                model_name=model.lower(),
                name="mess",
                field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name=f"{model.lower()}_records", to="mess.mess"),
            )
            for model in ["MessSetting", "Member", "StockItem", "Purchase", "StockAddition", "Consumption", "Attendance", "Payment", "SoldRation"]
        ],
        migrations.RunPython(assign_existing_data, migrations.RunPython.noop),
        *[
            migrations.AlterField(
                model_name=model.lower(),
                name="mess",
                field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name=f"{model.lower()}_records", to="mess.mess"),
            )
            for model in ["MessSetting", "Member", "StockItem", "Purchase", "StockAddition", "Consumption", "Attendance", "Payment", "SoldRation"]
        ],
        migrations.AlterField(model_name="member", name="member_no", field=models.CharField(max_length=30)),
        migrations.AlterField(model_name="stockitem", name="name", field=models.CharField(max_length=150)),
        migrations.AddConstraint(
            model_name="member",
            constraint=models.UniqueConstraint(fields=("mess", "member_no"), name="uniq_member_no_per_mess"),
        ),
        migrations.AddConstraint(
            model_name="stockitem",
            constraint=models.UniqueConstraint(fields=("mess", "name"), name="uniq_stock_name_per_mess"),
        ),
    ]
