# CoolBreeze AI Support

An AI-powered customer support application built with Python, Django and MySQL.

CoolBreeze AI Support is being developed for a fictional air-conditioning company. The application will coordinate specialised AI agents to answer customer questions, investigate orders, assess refund requests and escalate cases for further review.

The project focuses on implementing agent loops, tool calling and multi-agent coordination directly in Python, with Django providing the application and data layer.

> **Status:** Active development. The Django and MySQL foundation is configured. Agent workflows, document retrieval and the support dashboard are planned.

## Project Goals

- Build customer support agents that can retrieve business information and take controlled actions.
- Connect AI tool calls to application data through the Django ORM.
- Coordinate support, management and risk assessment workflows.
- Ground responses in company documents and policies.
- Make agent activity visible through a live staff dashboard.
- Deploy the application with environment-based configuration.

## Planned Agent Workflows

### Maya — Customer Support Agent

Maya will serve as the first point of contact for customer enquiries.

Planned responsibilities:

- Answer product, delivery and policy questions.
- Retrieve order information through dedicated tools.
- Check delivery status.
- Identify cases that require further review.
- Escalate requests outside its permitted scope.

### Manager Agent

The manager agent will review cases escalated by Maya.

Planned responsibilities:

- Review the customer request and available order information.
- Consult company policies.
- Request a risk assessment when appropriate.
- Decide refund eligibility within defined rules and permissions.
- Record the outcome and an explanation for staff review.

### Risk Agent

The risk agent will provide supporting assessments for sensitive requests.

Planned responsibilities:

- Review available order and customer history.
- Identify suspicious patterns or inconsistencies.
- Return a structured risk assessment.
- Provide supporting findings to the manager agent.

Risk assessments will support case decisions; they will not constitute proof of fraud.

## Document Retrieval

A retrieval-augmented generation (RAG) pipeline is planned to provide agents with relevant company information.

The pipeline will:

1. Extract text from PDF documents using pypdf.
2. Split documents into searchable sections.
3. Generate embeddings.
4. Store and retrieve document sections using ChromaDB.
5. Supply relevant context to the language model.

Example sources include refund policies, delivery procedures and product documentation.

Retrieval is intended to improve grounding. It does not eliminate incorrect answers, so missing or conflicting information should trigger uncertainty or escalation.

## Live Support Dashboard

A staff dashboard is planned to display agent activity using Server-Sent Events (SSE).

Planned information includes:

- Incoming customer conversations.
- Agent tool calls and their results.
- Transfers between agents.
- Case status and escalation events.
- Decision summaries and outcomes.

The dashboard will expose operational events and explanations, rather than private model reasoning.

## Technology Stack

| Technology | Role | Status |
|---|---|---|
| Python | Backend and agent logic | In use |
| Django | Application framework and ORM | In use |
| MySQL | Relational database | Configured |
| PyMySQL | MySQL database driver | Configured |
| python-decouple | Environment-based configuration | In use |
| Anthropic API | Language model and tool calling | Planned |
| ChromaDB | Vector storage and document retrieval | Planned |
| pypdf | PDF text extraction | Planned |
| Django templates, HTML, CSS and JavaScript | Application interface | Planned |
| Server-Sent Events | Live agent activity updates | Planned |
| Railway | Application deployment | Planned |

The initial implementation will use direct Python orchestration. A future LangChain implementation may be explored after the core workflows are established.

Installed Python dependencies and their versions are recorded in `requirements.txt`.

## Current Project Structure

```text
dj_ai_employees/
├── dj_ai_employee_main/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── .env                 # Local configuration; excluded from Git
├── .gitignore
├── manage.py
├── README.md
└── requirements.txt
```

Additional Django apps and agent modules will be added as development progresses.

## Local Setup

### Prerequisites

- Python compatible with the Django version in `requirements.txt`.
- A running MySQL server.
- Git.
- A MySQL account with access to the application database.

An Anthropic API key will be needed when the AI integration is implemented. It is not required for the current Django foundation.

### 1. Get the project

Clone this repository and open its root directory—the folder containing `manage.py`.

### 2. Create a virtual environment

On macOS or Linux:

```bash
python3 -m venv env
source env/bin/activate
```

On Windows PowerShell:

```powershell
py -m venv env
.\env\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Create the MySQL database

Log in using an account that can create databases:

```bash
mysql -u root -p
```

Create the application database:

```sql
CREATE DATABASE IF NOT EXISTS ai_employee_db
CHARACTER SET utf8mb4;
```

Exit the MySQL client:

```sql
exit;
```

For shared or deployed environments, use a dedicated application database account with appropriate permissions.

### 5. Configure environment variables

Create a file named `.env` beside `manage.py`.

The configuration below assumes Django settings read these variable names through python-decouple:

```dotenv
SECRET_KEY=replace_with_a_generated_secret_key
DB_NAME=ai_employee_db
DB_USER=your_mysql_username
DB_PASSWORD=your_mysql_password
DB_HOST=localhost
DB_PORT=3306
```

Generate a Django secret key locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Copy the generated value into `SECRET_KEY` in `.env`.

Keep `.env` private. Never commit real credentials or API keys.

### 6. Check the application and prepare the database

```bash
python manage.py check
python manage.py migrate
```

### 7. Create an administrator account

Optional:

```bash
python manage.py createsuperuser
```

### 8. Start the development server

```bash
python manage.py runserver
```

Open:

- Application: http://127.0.0.1:8000/
- Django administration: http://127.0.0.1:8000/admin/

During the initial setup phase, the application may display Django’s default welcome page.

## Development Commands

Check Django configuration:

```bash
python manage.py check
```

Create migrations after changing models:

```bash
python manage.py makemigrations
```

Apply migrations:

```bash
python manage.py migrate
```

Open the configured database shell:

```bash
python manage.py dbshell
```

Run available tests:

```bash
python manage.py test
```

A successful system check validates configuration; it does not verify agent behaviour. Workflow tests will be added alongside implemented features.

## Roadmap

- [x] Initialise the Django project.
- [x] Configure MySQL connectivity using PyMySQL.
- [x] Introduce environment-based secret configuration.
- [ ] Build customer, order and support case models.
- [ ] Create the customer support interface.
- [ ] Implement business data tools using the Django ORM.
- [ ] Integrate the language model.
- [ ] Build Maya’s agent loop.
- [ ] Implement manager and risk agent coordination.
- [ ] Add document ingestion and retrieval.
- [ ] Stream activity to the staff dashboard.
- [ ] Add workflow tests, permission checks and failure handling.
- [ ] Deploy to Railway.

## Security and Operational Boundaries

Before deployment, the application will need:

- Protected credentials and production-specific Django settings.
- Authentication and authorisation for customer and staff actions.
- Tool permissions that restrict what each agent can access or change.
- Validation and safeguards around refund operations.
- Limits on agent iterations, API usage and execution time.
- Handling for tool failures, unavailable services and missing information.
- Protection against instructions embedded in untrusted documents.
- Appropriate handling of customer data in logs and dashboards.

The application is currently under development and is not presented as production-ready.


## Development Cheat Sheet

### Recommended VS Code Extensions

Install these from the Extensions panel (`Cmd + Shift + X` on macOS):

| Extension | Publisher | Purpose |
|---|---|---|
| Python | Microsoft | Python development support |
| Pylance | Microsoft | Code completion, import suggestions and type checking |
| Ruff | Astral | Python formatting and linting |
| Django | Baptiste Darthenay | Django template highlighting and snippets |
| GitHub Copilot | GitHub | Optional AI-assisted code suggestions |

Editor extensions are optional development tools. They are installed in VS Code, not through `pip`.

### Editor Setup

1. Open the Command Palette with `Cmd + Shift + P`.
2. Run `Python: Select Interpreter`.
3. Select the project's `env/bin/python`.
4. Open a Python file and run `Format Document With…`.
5. Choose `Configure Default Formatter`, then select Ruff.
6. Enable `Editor: Format On Save` in Settings.

### Useful macOS Shortcuts

| Shortcut | Action |
|---|---|
| `Cmd + Shift + P` | Open Command Palette |
| `Cmd + Shift + X` | Open Extensions |
| `Cmd + P` | Find a file |
| `Cmd + S` | Save the current file |
| `Cmd + /` | Toggle a line comment |
| `Cmd + Shift + V` | Preview a Markdown file |

### Common Project Commands

Run these from the directory containing `manage.py`.

```bash
# Activate the virtual environment on macOS/Linux
source env/bin/activate

# Start the development server
python manage.py runserver

# Check Django configuration
python manage.py check

# Create migrations after changing models
python manage.py makemigrations

# Apply database migrations
python manage.py migrate

# Open the configured MySQL database
python manage.py dbshell

# Create an administrator account
python manage.py createsuperuser

# Run tests
python manage.py test
```

### Git Workflow

```bash
# Review changed files
git status
git diff

# Stage a README update
git add README.md

# Review staged changes
git diff --cached

# Commit the documentation update
git commit -m "docs: update development cheat sheet"

# Push to the connected remote branch
git push
```

Stage files intentionally and review changes before committing.
Keep `.env`, passwords and API keys out of Git.

## Author

Sandra — Python and Django developer building AI-powered applications.