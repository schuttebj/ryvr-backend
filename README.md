# RYVR Backend

FastAPI backend for the RYVR AI Marketing Automation Platform.

## Features

- **FastAPI** with automatic API documentation
- **JWT Authentication** with secure password hashing
- **SQLAlchemy ORM** with PostgreSQL/SQLite support
- **Multi-tenant architecture** for agencies and clients
- **Credit-based billing system** with transaction tracking
- **Integration framework** for DataForSEO, OpenAI, and other APIs
- **Comprehensive analytics** and reporting endpoints

## Quick Start

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

3. **Run the server**
   ```bash
   uvicorn main:app --reload
   ```

4. **Access API documentation**
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## Deployment

Configured for automatic deployment on Render.com using `render.yaml`.

## Project Structure

```
backend/
├── main.py              # FastAPI application entry point
├── config.py            # Configuration management
├── database.py          # Database setup and session management
├── models.py            # SQLAlchemy database models
├── schemas.py           # Pydantic request/response schemas
├── auth.py              # Authentication utilities
├── routers/             # API route handlers
│   ├── auth.py          # Authentication endpoints
│   ├── clients.py       # Client management
│   ├── workflows.py     # Workflow management
│   ├── integrations.py  # API integrations
│   └── analytics.py     # Analytics and reporting
├── requirements.txt     # Python dependencies
└── render.yaml          # Render deployment configuration
```

## API Endpoints

### Authentication
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/register` - Register new user (admin only)
- `GET /api/v1/auth/me` - Get current user info

### Clients
- `GET /api/v1/clients` - List clients
- `POST /api/v1/clients` - Create client
- `GET /api/v1/clients/{id}` - Get client details
- `PUT /api/v1/clients/{id}` - Update client
- `DELETE /api/v1/clients/{id}` - Delete client

### Workflows
- `GET /api/v1/workflows` - List workflows
- `POST /api/v1/workflows` - Create workflow
- `POST /api/v1/workflows/{id}/execute` - Execute workflow
- `GET /api/v1/workflows/{id}/executions` - Get execution history

### Integrations
- `GET /api/v1/integrations` - List available integrations
- `POST /api/v1/integrations/test` - Test integration

### Analytics
- `GET /api/v1/analytics/dashboard` - Dashboard statistics
- `GET /api/v1/analytics/usage/credits` - Credit usage over time
- `GET /api/v1/analytics/performance/workflows` - Workflow performance metrics

## Environment Variables

```env
DATABASE_URL=sqlite:///./ryvr.db
SECRET_KEY=your-super-secret-jwt-key
OPENAI_API_KEY=your-openai-api-key
DATAFORSEO_USERNAME=your-dataforseo-username
DATAFORSEO_PASSWORD=your-dataforseo-password
DATAFORSEO_BASE_URL=https://sandbox.dataforseo.com
```

## License

Proprietary software. All rights reserved. 