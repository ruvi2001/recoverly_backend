# Risk Service (Component 1)

## Overview
Risk detection and explainable AI (XAI) service for relapse risk prediction.

## Responsibilities
- ML-based risk detection
- Feature extraction and preprocessing
- Temporal pattern analysis
- Explainable AI (SHAP/LIME)
- Risk score calculation

## API Endpoints

### `POST /api/predict`
Predict risk for a message or user

**Request:**
```json
{
  "user_id": "user_123",
  "message_text": "I'm feeling stressed today",
  "context": {}
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
    "top_features": [...],
    "shap_values": [...]
  }
}
```

### `GET /api/health`
Health check endpoint

## Database Schema
Uses `risk` schema in PostgreSQL.

## Setup

```bash
cd services/risk_service
pip install -r requirements.txt
python app/main.py
```

## Tech Stack
- FastAPI
- PyTorch / TensorFlow
- SHAP / LIME
- PostgreSQL
