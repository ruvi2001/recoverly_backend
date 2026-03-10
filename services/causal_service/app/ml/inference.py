# app/ml/inference.py
import joblib
import numpy as np
import re
from pathlib import Path
from collections import Counter

ART_DIR = Path(__file__).resolve().parent / "artifacts"
tfidf = joblib.load(ART_DIR / "tfidf.pkl")
clf   = joblib.load(ART_DIR / "classifier.pkl")

def clean_text(t: str) -> str:
    t = str(t).lower()
    t = re.sub(r"http\S+|www\.\S+", " ", t)
    t = re.sub(r"[^a-z0-9\s']", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def level_from_ratio(r: float) -> str:
    if r >= 0.75:
        return "high"
    elif r >= 0.5:
        return "medium"
    elif r >= 0.3:
        return "low"
    else:
        return "very_low"

def predict_top3_levels(text: str):
    text_clean = clean_text(text)
    X = tfidf.transform([text_clean])

    probs = clf.predict_proba(X)[0]
    classes = clf.classes_

    idxs = np.argsort(probs)[::-1][:3]
    top = [(classes[i], float(probs[i])) for i in idxs]

    best = top[0][1] if top else 1.0

    top3 = []
    for label, score in top:
        ratio = score / best if best > 0 else 0.0
        top3.append({
            "label": label,
            "level": level_from_ratio(ratio),
            "score": score,   # <-- use this for bar fill
            "ratio": ratio    # <-- optional (relative strength)
        })

    return {
        "most_impactful": top[0][0],
        "top3": top3,
        "cleaned_text": text_clean
    }

def group_distribution(texts: list[str]):
    main_labels = []
    for t in texts:
        t = clean_text(t)
        X = tfidf.transform([t])
        probs = clf.predict_proba(X)[0]
        classes = clf.classes_
        main_labels.append(classes[int(np.argmax(probs))])

    counts = Counter(main_labels)
    total = len(main_labels)

    dist = [{"label": lab, "percentage": round((cnt / total) * 100, 2)}
            for lab, cnt in counts.items()]
    dist.sort(key=lambda x: x["percentage"], reverse=True)

    return {"total_analyzed": total, "distribution": dist}