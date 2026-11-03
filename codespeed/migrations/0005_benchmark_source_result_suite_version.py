from django.db import migrations, models


def remap_benchmark_type(apps, schema_editor):
    Benchmark = apps.get_model('codespeed', 'Benchmark')
    Benchmark.objects.all().update(source='legacy')


class Migration(migrations.Migration):

    dependencies = [
        ('codespeed', '0004_branch_display_on_comparison_page'),
    ]

    operations = [
        migrations.RenameField(
            model_name='benchmark',
            old_name='benchmark_type',
            new_name='source',
        ),
        migrations.AlterField(
            model_name='benchmark',
            name='source',
            field=models.CharField(
                choices=[('legacy', 'Legacy'), ('pyperformance', 'PyPerformance')],
                default='legacy',
                max_length=14,
            ),
        ),
        migrations.RunPython(remap_benchmark_type, migrations.RunPython.noop),
        migrations.AddField(
            model_name='result',
            name='suite_version',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
    ]
