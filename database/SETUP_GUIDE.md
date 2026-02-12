# PostgreSQL Database Setup Guide

## 🎯 Overview

You'll create **ONE database** (`recoverly_platform`) with **FIVE schemas**:
- `core` - Shared tables (users, messages)
- `social` - Your component (social support & peer network)
- `risk` - Component 1 (placeholder for now)
- `reco` - Component 2 (placeholder for now)
- `causal` - Component 4 (placeholder for now)

---

## 📋 Step-by-Step Setup

### **Method 1: Using pgAdmin (GUI) - Recommended**

#### Step 1: Create the Database

1. Open **pgAdmin 4**
2. Right-click **Databases** → **Create** → **Database**
3. Name: `recoverly_platform`
4. Click **Save**

#### Step 2: Run the Initialization Script

1. Right-click on `recoverly_platform` → **Query Tool**
2. Open the file: `d:\research_project\database\init.sql`
3. Click **Execute** (F5)
4. You should see: "Query returned successfully"

#### Step 3: Verify the Setup

Run this query to check schemas:
```sql
SELECT schema_name 
FROM information_schema.schemata 
WHERE schema_name IN ('core', 'social', 'risk', 'reco', 'causal')
ORDER BY schema_name;
```

You should see all 5 schemas.

Run this to check tables in `social` schema:
```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'social'
ORDER BY table_name;
```

You should see: `actions`, `escalations`, `meetings`, `message_predictions`, `nudges`, `user_risk_profiles`

---

### **Method 2: Using Command Line (psql)**

#### Step 1: Open Command Prompt as Administrator

```cmd
cd "C:\Program Files\PostgreSQL\16\bin"
```

#### Step 2: Create the Database

```cmd
createdb -U postgres recoverly_platform
```

Enter your PostgreSQL password when prompted.

#### Step 3: Run the Initialization Script

```cmd
psql -U postgres -d recoverly_platform -f "d:\research_project\database\init.sql"
```

#### Step 4: Verify

```cmd
psql -U postgres -d recoverly_platform
```

Then in psql:
```sql
\dn  -- List schemas
\dt social.*  -- List tables in social schema
\q  -- Quit
```

---

## 🔧 Update Your `.env` File

Change your database name from `recoverly_chatrisk` to `recoverly_platform`:

```env
# OLD
DB_NAME=recoverly_chatrisk

# NEW
DB_NAME=recoverly_platform
```

---

## 🔄 Update Your Code

### Update `temporal_engine.py`

Change the default database name:

```python
# OLD
def __init__(
    self,
    database: str = "recoverly_chatrisk",
    ...
):

# NEW
def __init__(
    self,
    database: str = "recoverly_platform",
    ...
):
```

### Update Table References to Use Schema

In your `temporal_engine.py`, update all table references to include the `social.` schema prefix:

```python
# OLD
cursor.execute("""
    CREATE TABLE IF NOT EXISTS message_predictions (
        ...
    )
""")

# NEW
cursor.execute("""
    CREATE TABLE IF NOT EXISTS social.message_predictions (
        ...
    )
""")
```

**All tables in your component should be prefixed with `social.`**:
- `social.message_predictions`
- `social.user_risk_profiles`
- `social.actions`
- `social.nudges`
- `social.escalations`
- `social.meetings`

---

## ✅ Test the Connection

Run your test script with the new database:

```bash
python test_db.py
```

Expected output:
```
✓ Configuration loaded for environment: development
✓ Connected to PostgreSQL successfully!
postgresql version: PostgreSQL 16.11 ...
```

---

## 📊 Database Schema Overview

```
recoverly_platform (database)
│
├── core (schema) - Shared by all components
│   ├── users
│   └── messages
│
├── social (schema) - YOUR COMPONENT
│   ├── message_predictions
│   ├── user_risk_profiles
│   ├── actions
│   ├── nudges
│   ├── escalations
│   └── meetings
│
├── risk (schema) - Component 1 (empty for now)
├── reco (schema) - Component 2 (empty for now)
└── causal (schema) - Component 4 (empty for now)
```

---

## 🎯 Next Steps

1. ✅ Create database: `recoverly_platform`
2. ✅ Run `init.sql` script
3. ✅ Update `.env` file with new database name
4. ✅ Update `temporal_engine.py` to use `social.` schema prefix
5. ✅ Test connection with `python test_db.py`
6. ✅ Your component is ready to use the new database!

---

## 💡 Benefits of This Setup

✅ **Organized** - Each component has its own schema
✅ **Shared Data** - All components can access `core.users` and `core.messages`
✅ **No Conflicts** - Each team member works in their own schema
✅ **Easy Queries** - Can JOIN across schemas when needed
✅ **Clear Ownership** - `social` schema belongs to you

---

## 🔍 Useful Queries

### Check all schemas
```sql
\dn
```

### List all tables in social schema
```sql
\dt social.*
```

### View table structure
```sql
\d social.user_risk_profiles
```

### Query with schema prefix
```sql
SELECT * FROM social.user_risk_profiles;
SELECT * FROM core.users;
```

### JOIN across schemas
```sql
SELECT 
    u.username,
    r.current_risk_label,
    r.risk_score
FROM core.users u
JOIN social.user_risk_profiles r ON u.user_id = r.user_id
WHERE r.current_risk_label = 'HIGH_RISK';
```
