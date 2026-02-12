# Recoverly Platform - Research Project

Multi-component recovery support platform with AI-powered risk detection, interventions, peer support, and causal analysis.

## 🏗️ Architecture

This project uses a **microservices architecture** with 4 independent components:

```
├── Component 1: Risk Detection & XAI (risk_service)
├── Component 2: Intervention & Recommendations (reco_service)
├── Component 3: Social Support & Peer Network (social_service) ✅ Implemented
└── Component 4: Causal Factor Analysis (causal_service)
```

## 📁 Project Structure

```
research_project/
├── services/
│   ├── risk_service/         # Component 1
│   ├── reco_service/         # Component 2
│   ├── social_service/       # Component 3 ✅
│   └── causal_service/       # Component 4
├── shared/                   # Common code
├── database/                 # Database schemas
│   ├── init.sql             # Initial setup
│   └── SETUP_GUIDE.md       # Setup instructions
└── docs/                     # Documentation
```

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL 16+
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/your-team/research_project.git
cd research_project
```

### 2. Set Up Environment Variables

```bash
# Copy the template
cp .env.example .env

# Edit .env and add your PostgreSQL password
# DB_PASSWORD=your_actual_password
```

### 3. Create Virtual Environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

### 4. Set Up Database

#### Option A: Using pgAdmin (Recommended)

1. Open pgAdmin
2. Create database: `recoverly_platform`
3. Open Query Tool
4. Run: `database/init.sql`

#### Option B: Using Command Line

```bash
# Create database
createdb -U postgres recoverly_platform

# Run initialization script
psql -U postgres -d recoverly_platform -f database/init.sql
```

See `database/SETUP_GUIDE.md` for detailed instructions.

### 5. Install Dependencies

```bash
# For social_service (Component 3)
cd services/social_service
pip install -r requirements.txt
```

### 6. Run Your Component

```bash
# Example: Run social_service
cd services/social_service
python app/main.py
```

## 📊 Database Schema

The database uses **one database with multiple schemas**:

```
recoverly_platform (database)
├── core       # Shared: users, messages
├── social     # Component 3: Social support
├── risk       # Component 1: Risk detection
├── reco       # Component 2: Recommendations
└── causal     # Component 4: Causal analysis
```

Each component owns its schema and can access `core` for shared data.

## 👥 Team Collaboration

### Adding Your Component's Tables

1. Create a migration file:
   ```bash
   database/migrations/00X_your_component.sql
   ```

2. Add your tables to your schema:
   ```sql
   CREATE TABLE your_schema.your_table (...);
   ```

3. Test locally, then commit:
   ```bash
   git add database/migrations/00X_your_component.sql
   git commit -m "Add tables for [your_component]"
   git push
   ```

4. Other members pull and run your migration:
   ```bash
   git pull
   psql -U postgres -d recoverly_platform -f database/migrations/00X_your_component.sql
   ```

### Git Workflow

```bash
# Create feature branch
git checkout -b feature/your-component-name

# Make changes
git add .
git commit -m "Descriptive message"

# Push to GitHub
git push origin feature/your-component-name

# Create Pull Request on GitHub
```

## 🔧 Component Details

### Component 3: Social Service (Implemented)

**Responsibilities:**
- Analyze user messages with ML models
- Compute risk scores and levels
- Trigger actions based on risk:
  - HIGH_RISK → Escalate to counselor, notify family
  - MODERATE_RISK → Send nudges, suggest activities
  - LOW_RISK → Encouraging messages
  - ISOLATION_ONLY → Encourage peer interaction

**Tech Stack:**
- FastAPI
- PostgreSQL
- PyTorch + Transformers (DistilBERT)
- psycopg2

**Endpoints:**
- `POST /api/analyze_message` - Analyze a message
- `GET /api/user_risk/{user_id}` - Get user risk profile
- `POST /api/trigger_action/{user_id}` - Trigger intervention

### Component 1: Risk Service (Placeholder)

**Schema:** `risk.*`

### Component 2: Reco Service (Placeholder)

**Schema:** `reco.*`

### Component 4: Causal Service (Placeholder)

**Schema:** `causal.*`

## 📝 Development Guidelines

### Code Style

- Follow PEP 8 for Python
- Use type hints
- Write docstrings for functions
- Keep functions focused and small

### Database

- Always use schema prefix: `social.table_name`
- Use migrations for schema changes
- Don't modify other components' schemas
- Shared tables go in `core` schema

### Testing

```bash
# Run tests for your component
cd services/your_service
pytest tests/
```

## 🐛 Troubleshooting

### Database Connection Issues

See `database/SETUP_GUIDE.md` for detailed troubleshooting.

### Common Issues

1. **Password authentication failed**
   - Check `.env` file has correct `DB_PASSWORD`
   - Verify PostgreSQL is running

2. **Database does not exist**
   - Run: `createdb -U postgres recoverly_platform`
   - Then run `database/init.sql`

3. **Table not found**
   - Make sure you're using schema prefix: `social.table_name`
   - Run `database/init.sql` to create tables

## 📚 Documentation

- `database/SETUP_GUIDE.md` - Database setup instructions
- `database/init.sql` - Database initialization script
- `docs/architecture.md` - System architecture (TODO)
- `docs/api_contract.md` - API specifications (TODO)

## 🤝 Contributing

1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Create a Pull Request
5. Wait for review

## 📧 Contact

- Component 1: [Member 1 Email]
- Component 2: [Member 2 Email]
- Component 3: [Your Email]
- Component 4: [Member 4 Email]

## 📄 License

[Your License Here]
