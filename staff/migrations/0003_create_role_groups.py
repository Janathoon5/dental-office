from django.db import migrations


def create_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name='Patient')


def delete_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name='Patient').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('staff', '0002_totpdevice'),
    ]

    operations = [
        migrations.RunPython(create_groups, delete_groups),
    ]
