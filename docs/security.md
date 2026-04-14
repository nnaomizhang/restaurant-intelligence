# Security Documentation

## API Key Management
- All API keys stored in `.env` file at project root
- `.env` is listed in `.gitignore` — never committed to GitHub
- Keys loaded at runtime via `python-dotenv`
- Docker Compose passes keys via `env_file` directive
- Keys required: Google Places, Companies House, OpenAI

## Data Anonymisation
Before any data is sent to the LLM:
- Phone numbers replaced with `[PHONE]`
- Email addresses replaced with `[EMAIL]`
- Reviewer names stripped from review objects
- Only aggregated/anonymised data reaches external APIs

## Data Storage
Processed datasets stored in PostgreSQL and MongoDB do not contain identifiable personal data. Where sensitive attributes are present in source data, they are removed or anonymised during the data cleaning stage.

- FSA data is public open data and contains no personal information
- Companies House data is sourced from a public register
- Google Places reviews are anonymised prior to embedding and analysis

## Database Security
- PostgreSQL protected by username/password authentication
- MongoDB running on localhost only — not exposed externally
- Docker network isolates containers from external access
- Database credentials stored in `.env`, not hardcoded

## Commercial Data Sensitivity
- Deliveroo menu data collected via public web scraping
- Google Places data used within API terms of service
- FSA data is Crown Copyright open data (OGL v3)
- Companies House data is publicly available under UK regulatory frameworks
No data is redistributed or monetised beyond analytical use within the system.
