@echo off
cd backend
set DJANGO_DEBUG=True
python manage.py runserver 0.0.0.0:8000
