# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ccx', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='customcourseforedx',
            name='enable_discussion',
            field=models.BooleanField(
                default=False,
                help_text='Enable discussion forum for CCX by setting this to true.',
                verbose_name='Enable or disable discussion forum'
            )
        )
    ]
