# Security Documentation

## API Key Management
- All API keys stored in `.env` file at project root
- `.env` is listed in `.gitignore` — never committed to GitHub
- Keys loaded at runtime via `python-dotenv`
- Docker Compose passes keys via `env_file` directive
- Keys required: Google Places, Companies House, Anthropic, OpenAI

## Data Anonymisation
Before any data is sent to the LLM:
- Phone numbers replaced with `[PHONE]`
- Email addresses replaced with `[EMAIL]`
- Full postcodes replaced with `[POSTCODE]`
- Reviewer names stripped from review objects
- Only aggregated/anonymised data reaches external APIs

## Data Storage
- Raw personal data stays in MongoDB and PostgreSQL locally
- No personal data is sent to OpenAI or any external API
- FSA data is public open data — no personal information
- Google Places reviews are anonymised before embedding
- Companies House data is public register data

## Database Security
- PostgreSQL protected by username/password authentication
- MongoDB running on localhost only — not exposed externally
- Docker network isolates containers from external access
- Database credentials stored in `.env`, not hardcoded

## Commercial Data Sensitivity
- Deliveroo menu data collected via public web scraping
- Google Places data used within API terms of service
- FSA data is Crown Copyright open data (OGL v3)
- Companies House data is public register under GDPR exemption
- No data is resold or redistributed