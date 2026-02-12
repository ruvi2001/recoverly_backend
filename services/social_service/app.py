import json
import numpy as np
import streamlit as st
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

#Rolling window config 

ROLLING_WINDOW_SIZE = 5

#Setup

st.set_page_config(page_title="Risk Engine Demo", layout="wide")

# Initialize rolling conversation state
if "history" not in st.session_state:
    st.session_state.history = []

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

RISK_MODEL_DIR = "D:/research_project/models/risk_classification/Risk_Classification_final"
ISO_MODEL_DIR  = "D:/research_project/models/isolation/isolation_model_final"
FUSION_JSON    = "D:/research_project/risk_engine/fusion_v2.json"

# risk label mapping (from LabelEncoder classes)
# 0: CRAVING, 1: NEGATIVE_MOOD, 2: NEUTRAL, 3: RELAPSE, 4: TOXIC
RISK_ID2LABEL = {
    0: "CRAVING",
    1: "NEGATIVE_MOOD",
    2: "NEUTRAL",
    3: "RELAPSE",
    4: "TOXIC",
}


# 1) Load models + config (cached)

@st.cache_resource
def load_models_and_config():
    with open(FUSION_JSON, "r") as f:
        cfg = json.load(f)

    risk_tok = AutoTokenizer.from_pretrained(RISK_MODEL_DIR, use_fast=True)
    risk_model = AutoModelForSequenceClassification.from_pretrained(RISK_MODEL_DIR).to(DEVICE)
    risk_model.eval()

    iso_tok = AutoTokenizer.from_pretrained(ISO_MODEL_DIR, use_fast=True)
    iso_model = AutoModelForSequenceClassification.from_pretrained(ISO_MODEL_DIR).to(DEVICE)
    iso_model.eval()

    return cfg, risk_tok, risk_model, iso_tok, iso_model

def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()


@torch.no_grad()
def predict_risk_probs(text: str, tokenizer, model, max_len=256) -> dict:
    enc = tokenizer(text, truncation=True, padding=True, max_length=max_len, return_tensors="pt")
    enc = {k: v.to(DEVICE) for k, v in enc.items()}
    logits = model(**enc).logits.detach().cpu().numpy()[0]
    probs = softmax(logits)

    out = {}
    for i, p in enumerate(probs):
        label = RISK_ID2LABEL.get(i, f"LABEL_{i}")
        out[label] = float(p)
    return out

@torch.no_grad()
def predict_iso_prob(text: str, tokenizer, model, max_len=256) -> float:
    enc = tokenizer(text, truncation=True, padding=True, max_length=max_len, return_tensors="pt")
    enc = {k: v.to(DEVICE) for k, v in enc.items()}
    logits = model(**enc).logits.detach().cpu().numpy()[0]
    probs = softmax(logits)

    # binary: index 1 is "ISOLATION"
    
    if len(probs) == 2:
        return float(probs[1])
    # fallback
    return float(np.max(probs))

def compute_risk_score(p_relapse: float, p_craving: float, p_negative_mood: float, neg_weight: float) -> float:
    return float(max(p_relapse, p_craving, neg_weight * p_negative_mood))

def apply_fusion_v2(
    risk_score: float,
    p_relapse: float,
    p_craving: float,
    p_isolation: float,
    thresholds: dict
):
    T_relapse = thresholds["T_relapse"]
    T_craving = thresholds["T_craving"]
    T_high = thresholds["T_high"]
    T_mid = thresholds["T_mid"]
    T_iso = thresholds["T_iso"]
    T_iso_escalate = thresholds["T_iso_escalate"]

    # Decision logic
    if (p_relapse >= T_relapse) or (p_craving >= T_craving) or (risk_score >= T_high):
        return "HIGH_RISK", ["Acute addiction-risk trigger (relapse/craving/high risk_score)"]

    if (risk_score >= T_iso_escalate) and (p_isolation >= T_iso):
        return "HIGH_RISK", ["Isolation escalated risk because risk_score was already high-ish"]

    if risk_score >= T_mid:
        return "MODERATE_RISK", ["Moderate vulnerability detected (risk_score >= T_mid)"]

    if p_isolation >= T_iso:
        return "ISOLATION_ONLY", ["High isolation without high addiction-risk"]

    return "LOW_RISK", ["No thresholds triggered"]

def toxic_flag(p_toxic: float, T_toxic: float) -> int:
    return int(p_toxic >= T_toxic)

# 2) UI

cfg, risk_tok, risk_model, iso_tok, iso_model = load_models_and_config()
T = cfg["thresholds"]
neg_weight = cfg["risk_score"]["neg_weight"]

st.title("Risk Engine Demo")

colL, colR = st.columns([1, 1])

with colL:
    st.subheader("Input")
    example = st.selectbox(
        "Quick examples",
        [
            "you guys are useless",
            "I'm craving so bad it's hard to think of anything else.",
            "I've stopped answering my friends; I just lie in bed.",
            "Everything feels pointless right now.",
            "I need someone to stop me. I'm about to call my dealer."
        ],
    )

    text = st.text_area("Enter a user message", value=example, height=160)
    run = st.button("Analyze")

with colR:
    st.subheader("Output")

    if run and text.strip():

        # update rolling history
        st.session_state.history.append(text.strip())

        # keep only last N messages
        if len(st.session_state.history) > ROLLING_WINDOW_SIZE:
            st.session_state.history = st.session_state.history[-ROLLING_WINDOW_SIZE:]

        # run models on each message
        per_msg_outputs = []

        for msg in st.session_state.history:
            # model probabilities
            risk_probs = predict_risk_probs(msg, risk_tok, risk_model)
            p_iso = predict_iso_prob(msg, iso_tok, iso_model)

            # risk_score
            p_relapse = risk_probs.get("RELAPSE", 0.0)
            p_craving = risk_probs.get("CRAVING", 0.0)
            p_neg = risk_probs.get("NEGATIVE_MOOD", 0.0)
            p_neu     = risk_probs.get("NEUTRAL", 0.0)
            p_toxic = risk_probs.get("TOXIC", 0.0)

            risk_score = compute_risk_score(
                p_relapse=p_relapse,
                p_craving=p_craving, 
                p_negative_mood=p_neg, 
                neg_weight=neg_weight)
            
            per_msg_outputs.append({
                "text": msg,
                "risk_score": risk_score,
                "p_isolation": p_iso,
                "p_relapse": p_relapse,
                "p_craving": p_craving,
                "p_negative_mood": p_neg,
                "p_neutral": p_neu,
                "p_toxic": p_toxic,
            })
        
        # Rolling aggregation
        # rolling_risk_score = max(x["risk_score"] for x in per_msg_outputs)
        # rolling_p_isolation = max(x["p_isolation"] for x in per_msg_outputs)
        # rolling_p_relapse = max(x["p_relapse"] for x in per_msg_outputs)
        # rolling_p_craving = max(x["p_craving"] for x in per_msg_outputs)
        # rolling_p_toxic = max(x["p_toxic"] for x in per_msg_outputs)

        p_craving_list = [x["p_craving"] for x in per_msg_outputs]
        p_relapse_list = [x["p_relapse"] for x in per_msg_outputs]
        p_neg_list     = [x["p_negative_mood"] for x in per_msg_outputs]
        p_neu_list     = [x["p_neutral"] for x in per_msg_outputs]
        p_toxic_list   = [x["p_toxic"] for x in per_msg_outputs]
        p_iso_list     = [x["p_isolation"] for x in per_msg_outputs]

        # Safety-first spikes
        roll_p_craving = float(np.max(p_craving_list))
        roll_p_relapse = float(np.max(p_relapse_list))
        roll_p_toxic   = float(np.max(p_toxic_list))

        # Pattern / baseline
        roll_p_neg_mean     = float(np.mean(p_neg_list))
        roll_p_neu_mean     = float(np.mean(p_neu_list))

        roll_p_iso_max  = float(np.max(p_iso_list))  # trend-based

        # Risk score rolling: MAX (safety)
        rolling_risk_score = float(np.max([x["risk_score"] for x in per_msg_outputs]))

        rolling_p_isolation = roll_p_iso_max

        # 3) Apply fusion decision once
        fused_label, reasons = apply_fusion_v2(
            risk_score=rolling_risk_score,
            p_relapse=roll_p_relapse,
            p_craving=roll_p_craving,
            p_isolation=rolling_p_isolation,
            thresholds=T
        )

        # 4) toxic flag (separate axis)
        tox_flag = toxic_flag(roll_p_toxic, T["T_toxic"])

        # Display
        st.markdown(f"## Final Decision: **{fused_label}**")
        st.metric("Rolling Risk Score", f"{rolling_risk_score:.3f}")
        st.metric("Rolling Isolation Probability", f"{rolling_p_isolation:.3f}")
        st.metric("Toxic_Flag", str(bool(tox_flag)))

        st.write("### Rolling Class Probabilities (aggregated)")
        st.json({
            "p_relapse_max": roll_p_relapse,
            "p_craving_max": roll_p_craving,
            "p_toxic_max": roll_p_toxic,
            "p_isolation_max": roll_p_iso_max,
            "p_negative_mood_mean": roll_p_neg_mean,
            "p_neutral_mean": roll_p_neu_mean,
        })

        st.write("### Why?")
        for r in reasons:
            st.write(f"- {r}")

        with st.expander("Conversation Window (last messages)"):
            for i, x in enumerate(per_msg_outputs, 1):
             st.write(
                f"**{i}.** {x['text']}\n"
                f"- risk_score={x['risk_score']:.3f}, "
                f"p_isolation={x['p_isolation']:.3f},"
                f"p_craving={x['p_craving']:.3f},"
                f"p_relapse={x['p_relapse']:.3f}"
            )

    else:
        st.info("Enter a message and click Analyze.")


if st.button("Clear conversation"):
    st.session_state.history = []
   