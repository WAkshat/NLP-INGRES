"""Minimal UI (Phase 10).   streamlit run app/streamlit_app.py   (needs `ollama serve` with qwen3:8b)"""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.pipeline.agent import Pipeline  # noqa: E402
from src.utils.safe_sql import connect_ro  # noqa: E402

EXAMPLES = ["How many blocks in Punjab were over-exploited in the 2025 assessment?",
            "2024-25 में लुधियाना जिले में कुल भूजल निकासी कितनी थी?",
            "Tamil Nadu mein 2023 ke assessment mein kitne units critical the?",
            "2024-25 இல் கோயம்புத்தூர் மாவட்டத்தின் நிலத்தடி நீர் எடுப்பு சதவீதம் என்ன?"]


@st.cache_resource
def pipeline():
    rows = [json.loads(x) for x in (ROOT / "data/benchmark/ingres_bench_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    pipe = Pipeline(connect_ro(ROOT / "data/processed/ingres.db"), [r for r in rows if r["split"] == "train"])
    tau = ROOT / "experiments/pipeline/places_dev.json"
    if tau.exists():
        pipe.places.tau = float(json.loads(tau.read_text())["chosen_tau"])
    return pipe


st.set_page_config(page_title="INGRES groundwater Q&A", layout="wide")
st.title("INGRES groundwater Q&A")
st.caption("Ask in English, Hindi, Hinglish or Tamil. Data: CGWB/INGRES assessments 2019-20 to 2024-25. "
           "Research prototype: check the SQL before trusting an answer.")
q = st.selectbox("Example", [""] + EXAMPLES)
q = st.text_input("Question", value=q)
if q:
    with st.spinner("Thinking ..."):
        out = pipeline().answer(q)
    st.subheader("Answer")
    st.write(out["answer"])
    if out.get("source") == "template_fallback":
        st.warning(f"The model's own wording contained numbers not in the result ({', '.join(out['verification']['unsupported'])}); "
                   "showing the raw result instead.")
    st.code(out["sql"] or "-- no SQL", language="sql")
    if out["rows"]:
        st.dataframe(pd.DataFrame(out["rows"], columns=out["columns"]), use_container_width=True)
    with st.expander("How it got there"):
        st.write({"schema hints": out["hints"], "places": out["places"], "attempts": out["attempts"],
                  "llm latency (s)": out["latency_s"]})
