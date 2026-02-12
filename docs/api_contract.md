# API Contracts - Recoverly Platform

This document defines the API contracts between services and with the mobile app.

## Service Ports

| Service | Port | Base URL |
|---------|------|----------|
| Social Service | 8003 | http://localhost:8003 |
| Risk Service | 8001 | http://localhost:8001 |
| Reco Service | 8002 | http://localhost:8002 |
| Causal Service | 8004 | http://localhost:8004 |

---

## Social Service API

### `POST /api/analyze_message`
Analyze a user message and compute risk.

**Request:**
```json
{
  "user_id": "user_123",
  "message_text": "I'm feeling really stressed today",
  "conversation_type": "buddy",
  "timestamp": "2024-01-01T10:00:00Z"
}
```

**Response:**
```json
{
  "user_id": "user_123",
  "risk_score": 0.65,
  "risk_level": "MODERATE_RISK",
  "predictions": {
    "p_craving": 0.3,
    "p_relapse": 0.4,
    "p_isolation": 0.2,
    "p_negative_mood": 0.7
  },
  "action_triggered": "nudge",
  "action_details": {
    "type": "peer_interaction",
    "message": "Consider reaching out to a buddy"
  }
}
```

### `GET /api/user_risk/{user_id}`
Get current risk profile for a user.

**Response:**
```json
{
  "user_id": "user_123",
  "current_risk_label": "MODERATE_RISK",
  "risk_score": 0.65,
  "risk_trend": "stable",
  "last_updated": "2024-01-01T10:00:00Z",
  "reasons": [
    "Increased negative mood in recent messages",
    "Reduced peer interaction"
  ]
}
```

### `POST /api/trigger_action/{user_id}`
Manually trigger an action for a user.

**Request:**
```json
{
  "action_type": "escalation",
  "urgency": "high",
  "reason": "User expressed suicidal ideation"
}
```

**Response:**
```json
{
  "action_id": 12345,
  "status": "triggered",
  "timestamp": "2024-01-01T10:00:00Z"
}
```

---

## Risk Service API

### `POST /api/predict`
Get risk prediction for a message.

**Request:**
```json
{
  "user_id": "user_123",
  "message_text": "I'm struggling today",
  "context": {
    "time_of_day": "evening",
    "day_of_week": "friday"
  }
}
```

**Response:**
```json
{
  "risk_score": 0.75,
  "risk_level": "HIGH_RISK",
  "predictions": {
    "p_relapse": 0.8,
    "p_craving": 0.7
  },
  "explanation": {
    "top_features": [
      {"feature": "negative_words", "importance": 0.45},
      {"feature": "time_of_day", "importance": 0.30}
    ],
    "shap_values": [...]
  }
}
```

---

## Reco Service API

### `POST /api/recommend`
Get personalized recommendations.

**Request:**
```json
{
  "user_id": "user_123",
  "risk_level": "MODERATE_RISK",
  "context": {
    "time_of_day": "evening",
    "location": "home",
    "mood": "stressed"
  }
}
```

**Response:**
```json
{
  "interventions": [
    {
      "id": "int_001",
      "type": "activity",
      "title": "Take a 10-minute walk",
      "description": "Physical activity can help reduce stress",
      "priority": "high",
      "estimated_duration_minutes": 10
    },
    {
      "id": "int_002",
      "type": "social",
      "title": "Call a buddy",
      "description": "Connect with your support network",
      "priority": "medium"
    }
  ],
  "recommendations": [
    {
      "category": "environment",
      "suggestion": "Spend time outdoors",
      "reason": "Based on your preferences and past positive feedback"
    }
  ]
}
```

### `POST /api/feedback`
Submit feedback on a recommendation.

**Request:**
```json
{
  "user_id": "user_123",
  "intervention_id": "int_001",
  "feedback": "positive",
  "completed": true,
  "notes": "Felt better after the walk"
}
```

**Response:**
```json
{
  "status": "recorded",
  "message": "Thank you for your feedback"
}
```

---

## Causal Service API

### `POST /api/analyze`
Analyze posts for causal factors.

**Request:**
```json
{
  "user_id": "user_123",
  "posts": [
    {
      "text": "Work has been really stressful lately",
      "timestamp": "2024-01-01T10:00:00Z",
      "source": "facebook"
    },
    {
      "text": "Financial worries keeping me up at night",
      "timestamp": "2024-01-02T22:00:00Z",
      "source": "twitter"
    }
  ]
}
```

**Response:**
```json
{
  "user_id": "user_123",
  "root_causes": [
    {
      "cause": "work_stress",
      "frequency": 5,
      "sentiment_intensity": -0.7,
      "score": 3.5
    },
    {
      "cause": "financial_pressure",
      "frequency": 3,
      "sentiment_intensity": -0.8,
      "score": 2.4
    }
  ],
  "topics": ["work", "finances", "sleep"],
  "overall_sentiment": -0.65,
  "triggers": ["work_deadlines", "bills"]
}
```

### `GET /api/rankings/{user_id}`
Get ranked causal factors for a user.

**Response:**
```json
{
  "user_id": "user_123",
  "time_period": "last_30_days",
  "ranked_causes": [
    {
      "rank": 1,
      "cause": "work_stress",
      "score": 3.5,
      "trend": "increasing"
    },
    {
      "rank": 2,
      "cause": "financial_pressure",
      "score": 2.4,
      "trend": "stable"
    }
  ]
}
```

---

## Common Endpoints (All Services)

### `GET /api/health`
Health check endpoint.

**Response:**
```json
{
  "service": "social_service",
  "status": "healthy",
  "timestamp": "2024-01-01T10:00:00Z",
  "version": "1.0.0",
  "database": "connected"
}
```

---

## Error Responses

All services use consistent error format:

```json
{
  "error": "ValidationError",
  "detail": "user_id is required",
  "timestamp": "2024-01-01T10:00:00Z"
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 404 | Not Found |
| 500 | Internal Server Error |

---

## Authentication

### API Keys (Current)
```
X-API-Key: your_api_key_here
```

### JWT Tokens (Future)
```
Authorization: Bearer <token>
```
