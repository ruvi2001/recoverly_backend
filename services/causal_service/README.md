# Causal Analysis Service (Component 4)

## Overview
Social media causal factor analysis using NLP techniques.

## Responsibilities
- Extract causal factors from social media posts
- Sentiment analysis
- Topic modeling
- Ranking and reporting of triggers

## API Endpoints

### `POST /api/analyze`
Analyze posts for causal factors

**Request:**
```json
{
  "user_id": "user_123",
  "posts": [
    {
      "text": "Feeling stressed about work",
      "timestamp": "2024-01-01T10:00:00Z"
    }
  ]
}
```

**Response:**
```json
{
  "root_causes": ["work_stress", "financial_pressure"],
  "topics": [...],
  "sentiment": {
    "overall": -0.6,
    "breakdown": {...}
  },
  "triggers": [...]
}
```

### `GET /api/rankings/{user_id}`
Get ranked causal factors for a user

### `GET /api/health`
Health check endpoint

## Database Schema
Uses `causal` schema in PostgreSQL.

## Setup

```bash
cd services/causal_service
pip install -r requirements.txt
python app/main.py
```

## Tech Stack
- FastAPI
- NLTK / spaCy
- VADER / TextBlob (sentiment)
- LDA (topic modeling)
- PostgreSQL
