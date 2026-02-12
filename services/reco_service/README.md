# Recommendation Service (Component 2)

## Overview
Intervention and environment recommendation service with adaptive learning.

## Responsibilities
- Context-aware recommendations
- Intervention suggestions
- Adaptive learning from user feedback
- Personalized recovery plans

## API Endpoints

### `POST /api/recommend`
Get recommendations for a user

**Request:**
```json
{
  "user_id": "user_123",
  "risk_level": "MODERATE_RISK",
  "context": {
    "time_of_day": "evening",
    "location": "home"
  }
}
```

**Response:**
```json
{
  "interventions": [
    {
      "type": "activity",
      "title": "Take a walk",
      "description": "...",
      "priority": "high"
    }
  ],
  "recommendations": [...]
}
```

### `POST /api/feedback`
Submit user feedback on recommendations

### `GET /api/health`
Health check endpoint

## Database Schema
Uses `reco` schema in PostgreSQL.

## Setup

```bash
cd services/reco_service
pip install -r requirements.txt
python app/main.py
```

## Tech Stack
- FastAPI
- Recommendation algorithms
- PostgreSQL
