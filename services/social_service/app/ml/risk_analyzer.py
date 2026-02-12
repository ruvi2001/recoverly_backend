"""
Risk Analyzer - Wraps your trained ML models for inference
Handles loading models and running predictions
"""

import torch
import numpy as np
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from typing import Dict
import json
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import RISK_MODEL_PATH, ISOLATION_MODEL_PATH, FUSION_CONFIG_PATH, RISK_SETTINGS


class RiskAnalyzer:
    """
    Wrapper around your trained DistilBERT models
    Provides a clean interface for message analysis
    """
    
    def __init__(self):
        """Load models and configuration"""
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")
        
        # Load risk classification model
        print("Loading risk classification model...")
        self.risk_tokenizer = AutoTokenizer.from_pretrained(str(RISK_MODEL_PATH), use_fast=True)
        self.risk_model = AutoModelForSequenceClassification.from_pretrained(
            str(RISK_MODEL_PATH)
        ).to(self.device)
        self.risk_model.eval()
        
        # Load isolation detection model
        print("Loading isolation detection model...")
        self.isolation_tokenizer = AutoTokenizer.from_pretrained(str(ISOLATION_MODEL_PATH), use_fast=True)
        self.isolation_model = AutoModelForSequenceClassification.from_pretrained(
            str(ISOLATION_MODEL_PATH)
        ).to(self.device)
        self.isolation_model.eval()
        
        # Load fusion configuration
        print("Loading fusion configuration...")
        with open(FUSION_CONFIG_PATH, 'r') as f:
            self.fusion_config = json.load(f)
        
        self.thresholds = self.fusion_config['thresholds']
        self.neg_weight = self.fusion_config['risk_score']['neg_weight']
        self.risk_id2label = RISK_SETTINGS['risk_labels']
        
        print("✓ All models loaded successfully")
    
    @staticmethod
    def softmax(x: np.ndarray) -> np.ndarray:
        """Apply softmax to logits"""
        e = np.exp(x - np.max(x))
        return e / e.sum()
    
    @torch.no_grad()
    def predict_risk_probabilities(self, text: str, max_length: int = 256) -> Dict[str, float]:
        """
        Run risk classification model on text
        
        Args:
            text: User message
            max_length: Max token length
            
        Returns:
            Dict with probabilities for each risk class
        """
        # Tokenize
        encoded = self.risk_tokenizer(
            text,
            truncation=True,
            padding=True,
            max_length=max_length,
            return_tensors="pt"
        )
        encoded = {k: v.to(self.device) for k, v in encoded.items()}
        
        # Predict
        logits = self.risk_model(**encoded).logits.detach().cpu().numpy()[0]
        probs = self.softmax(logits)
        
        # Map to labels
        result = {}
        for idx, prob in enumerate(probs):
            label = self.risk_id2label.get(idx, f"LABEL_{idx}")
            result[label] = float(prob)
        
        return result
    
    @torch.no_grad()
    def predict_isolation_probability(self, text: str, max_length: int = 256) -> float:
        """
        Run isolation detection model on text
        
        Args:
            text: User message
            max_length: Max token length
            
        Returns:
            Probability of isolation (0.0 to 1.0)
        """
        # Tokenize
        encoded = self.isolation_tokenizer(
            text,
            truncation=True,
            padding=True,
            max_length=max_length,
            return_tensors="pt"
        )
        encoded = {k: v.to(self.device) for k, v in encoded.items()}
        
        # Predict
        logits = self.isolation_model(**encoded).logits.detach().cpu().numpy()[0]
        probs = self.softmax(logits)
        
        # Binary classification: index 1 is "ISOLATION"
        if len(probs) == 2:
            return float(probs[1])
        
        # Fallback if unexpected output
        return float(np.max(probs))
    
    def compute_risk_score(
        self,
        p_relapse: float,
        p_craving: float,
        p_negative_mood: float
    ) -> float:
        """
        Compute risk score using your fusion formula:
        risk_score = max(p_relapse, p_craving, neg_weight × p_negative_mood)
        
        Args:
            p_relapse: Probability of relapse
            p_craving: Probability of craving
            p_negative_mood: Probability of negative mood
            
        Returns:
            Risk score (0.0 to 1.0)
        """
        return float(max(
            p_relapse,
            p_craving,
            self.neg_weight * p_negative_mood
        ))
    
    def analyze_message(self, text: str) -> Dict[str, float]:
        """
        Complete analysis pipeline for a single message
        
        Args:
            text: User message
            
        Returns:
            Dict with all predictions ready for database storage
        """
        # Run both models
        risk_probs = self.predict_risk_probabilities(text)
        p_isolation = self.predict_isolation_probability(text)
        
        # Extract specific probabilities
        p_craving = risk_probs.get('CRAVING', 0.0)
        p_relapse = risk_probs.get('RELAPSE', 0.0)
        p_negative_mood = risk_probs.get('NEGATIVE_MOOD', 0.0)
        p_neutral = risk_probs.get('NEUTRAL', 0.0)
        p_toxic = risk_probs.get('TOXIC', 0.0)
        
        # Compute risk score
        risk_score = self.compute_risk_score(p_relapse, p_craving, p_negative_mood)
        
        # Return complete prediction
        return {
            'p_craving': p_craving,
            'p_relapse': p_relapse,
            'p_negative_mood': p_negative_mood,
            'p_neutral': p_neutral,
            'p_toxic': p_toxic,
            'p_isolation': p_isolation,
            'risk_score': risk_score
        }
    
    def get_thresholds(self) -> Dict[str, float]:
        """Get fusion thresholds for temporal engine"""
        return self.thresholds


# Singleton instance (load models once)
_analyzer_instance = None

def get_analyzer() -> RiskAnalyzer:
    """
    Get or create the risk analyzer instance
    This ensures models are loaded only once
    """
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = RiskAnalyzer()
    return _analyzer_instance


# Test function
if __name__ == "__main__":
    print("=" * 80)
    print("RISK ANALYZER TEST")
    print("=" * 80)
    
    # Initialize
    analyzer = get_analyzer()
    
    # Test messages
    test_messages = [
        "I'm craving so bad right now",
        "I feel alone and nobody understands me",
        "Everything is going great, 30 days sober!",
        "You guys are all useless"
    ]
    
    print("\nAnalyzing test messages:\n")
    
    for msg in test_messages:
        print(f"Message: '{msg}'")
        predictions = analyzer.analyze_message(msg)
        
        print(f"  Risk Score: {predictions['risk_score']:.3f}")
        print(f"  P(Craving): {predictions['p_craving']:.3f}")
        print(f"  P(Relapse): {predictions['p_relapse']:.3f}")
        print(f"  P(Isolation): {predictions['p_isolation']:.3f}")
        print(f"  P(Negative Mood): {predictions['p_negative_mood']:.3f}")
        print()
    
    print("✓ Test complete!")
