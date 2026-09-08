# Django AI Employees

A learning project built while following the Udemy course
**Build AI Employees with Django – Agentic AI for Developers**.

The goal is to learn how to build AI-powered employee workflows with Django,
then apply those skills to an independent project.

## Current progress

- Django project scaffold
- Local configuration using python-decouple
- SQLite database configuration

AI employee features will be added as I progress through the course.

## Technology

- Python
- Django
- SQLite
- python-decouple

## Local setup

After cloning the repository, open its folder and run:

```bash
python3 -m venv env
source env/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Generate a local secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Copy the generated value into `SECRET_KEY` in `.env`.

Prepare the database and start Django:

```bash
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/ in your browser.

## Configuration

Local credentials belong in `.env`, which is excluded from Git.
The `.env.example` file documents the required variables.

The project currently uses SQLite. MySQL integration is not yet configured.

## Validation

```bash
python manage.py check
```

## Acknowledgement

This repository documents my implementation of the course exercises.
It is a learning project under active development.