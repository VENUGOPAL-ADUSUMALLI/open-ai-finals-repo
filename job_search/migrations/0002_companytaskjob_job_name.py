from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('job_search', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='companytaskjob',
            name='job_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
