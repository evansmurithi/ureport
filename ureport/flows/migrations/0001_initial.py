# Generated by Django 2.2.20 on 2021-07-14 17:27

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("orgs", "0026_fix_org_config_rapidpro"),
    ]

    operations = [
        migrations.CreateModel(
            name="FlowResult",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True)),
                ("flow_uuid", models.CharField(max_length=36)),
                ("result_uuid", models.CharField(max_length=36)),
                ("result_name", models.CharField(blank=True, max_length=255, null=True)),
                ("org", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="orgs.Org")),
            ],
            options={
                "unique_together": {("org", "flow_uuid", "result_uuid")},
            },
        ),
        migrations.CreateModel(
            name="FlowResultCategory",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True)),
                ("category", models.TextField(null=True)),
                (
                    "flow_result",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="result_categories",
                        to="flows.FlowResult",
                    ),
                ),
            ],
        ),
    ]
