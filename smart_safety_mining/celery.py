import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_safety_mining.settings')

app = Celery('smart_safety_mining')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()