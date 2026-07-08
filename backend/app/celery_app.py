from .jobs import build_celery_app, register_tasks

celery_app = build_celery_app()
register_tasks(celery_app)
