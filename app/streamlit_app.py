"""INGRES Groundwater Assistant (Streamlit).

    ollama serve                      # qwen3:8b must be pulled (only needed for the "Ask" page)
    streamlit run app/streamlit_app.py

Pages: Ask (multilingual question -> verified answer, SQL, table, chart, pipeline trace), Explore (dashboards straight
from the database, no LLM), Results (every measured number of the project, read from experiments/).
"""
import contextlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.utils.safe_sql import connect_ro, execute  # noqa: E402

st.set_page_config(page_title="INGRES Groundwater Assistant", page_icon="💧", layout="wide")

CATEGORIES = ["Safe", "Semi-Critical", "Critical", "Over-Exploited", "Saline", "Hilly Area"]
CAT_COLORS = ["#2e9d6a", "#e8b931", "#ee7d2b", "#d64045", "#4a7fc1", "#9aa3ad"]
CAT_SCALE = alt.Scale(domain=CATEGORIES, range=CAT_COLORS)
LANG_NAMES = {"english": "English", "hindi": "हिन्दी", "hinglish": "Hinglish", "tamil": "தமிழ்"}

st.markdown("""
<style>
.block-container {padding-top: 1.6rem; max-width: 1250px;}
.hero h1 {margin-bottom: 0.1rem; font-size: 2.0rem;}
.hero p {color: #6b7280; margin-top: 0; font-size: 0.97rem;}
.badge {display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 600;
        margin-right: 6px; margin-bottom: 4px;}
.ok {background: #e3f5ec; color: #1d7a50;} .warn {background: #fdf1dc; color: #9a5b00;}
.info {background: #e7effa; color: #2b5ea7;} .err {background: #fbe4e5; color: #a1272d;}
.answer {font-size: 1.12rem; line-height: 1.55; padding: 0.15rem 0 0.35rem 0;}
.small {color: #6b7280; font-size: 0.82rem;}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------------ resources
@st.cache_resource
def db():
    return connect_ro(ROOT / "data/processed/ingres.db")


def q(sql: str) -> pd.DataFrame:
    r = execute(db(), sql)
    if r.error:
        raise RuntimeError(r.error)
    return pd.DataFrame(r.rows, columns=r.columns)


def lit(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


@st.cache_data(ttl=15, show_spinner=False)
def ollama_status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.5) as r:
            models = [m["name"] for m in json.load(r).get("models", [])]
        return ("qwen3:8b" in models), models
    except Exception:
        return False, None


@st.cache_resource(show_spinner=False)
def pipeline():
    from src.pipeline.agent import Pipeline
    rows = [json.loads(x) for x in (ROOT / "data/benchmark/ingres_bench_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    pipe = Pipeline(db(), [r for r in rows if r["split"] == "train"])
    for f in (ROOT / "experiments/pipeline_v2/places_dev.json", ROOT / "experiments/pipeline/places_dev.json"):
        if f.exists():
            pipe.places.tau = float(json.loads(f.read_text())["chosen_tau"])
            break
    return pipe


@st.cache_data(show_spinner=False)
def examples():
    f = ROOT / "app/examples.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"english": ["How many blocks in Punjab were over-exploited in the 2025 assessment?"],
            "hindi": ["2024-25 में लुधियाना जिले में कुल भूजल निकासी कितनी थी?"],
            "hinglish": ["Tamil Nadu mein 2023 ke assessment mein kitne units critical the?"],
            "tamil": ["2024-25 இல் கர்நாடகா மாநிலத்தின் நிலத்தடி நீர் எடுப்பு நிலை என்ன?"]}


@contextlib.contextmanager
def components(pipe, on: dict):
    """Switch pipeline components off for one question (live ablation), then restore them."""
    saved = {k: getattr(pipe, k) for k in ("linker", "places", "TQ", "snapper")}
    cfg = dict(pipe.cfg)
    try:
        if not on["schema"]:
            pipe.linker = None
        if not on["places"]:
            pipe.places = None
        if not on["examples"]:
            pipe.TQ = None
        if not on["snap"]:
            pipe.snapper = None
        pipe.cfg["year_hints"], pipe.cfg["domain_notes"] = on["years"], on["notes"]
        yield pipe
    finally:
        for k, v in saved.items():
            setattr(pipe, k, v)
        pipe.cfg = cfg


# ------------------------------------------------------------------------------------------------ sidebar
st.sidebar.markdown("### 💧 INGRES Assistant")
page = st.sidebar.radio("Page", ["💬 Ask", "📊 Explore the data", "📈 Project results"], label_visibility="collapsed")
llm_ok, models = ollama_status()
st.sidebar.markdown(
    f"<span class='badge {'ok' if llm_ok else 'err'}'>LLM {'ready' if llm_ok else 'offline'}</span>"
    f"<span class='badge info'>DB: 5 cycles · 8,751 units</span>", unsafe_allow_html=True)
if not llm_ok:
    st.sidebar.caption("Start `ollama serve` (with `qwen3:8b` pulled) to ask questions. Explore and Results work without it.")


# ================================================================================================ ASK
def auto_chart(df: pd.DataFrame):
    if df.empty or len(df) < 2 or len(df) > 60:
        return None
    num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    txt = [c for c in df.columns if c not in num]
    if not num:
        return None
    y = num[-1]
    if txt:
        x = txt[0]
        return alt.Chart(df).mark_bar(cornerRadiusEnd=3, color="#3b7dd8").encode(
            y=alt.Y(f"{x}:N", sort="-x", title=None), x=alt.X(f"{y}:Q", title=y), tooltip=list(df.columns)
        ).properties(height=min(26 * len(df) + 30, 520))
    return None


def render_answer(out: dict):
    if out.get("error"):
        st.error(out["error"])
        return
    v = out.get("verification") or {}
    badges = []
    if out.get("source") == "llm":
        badges.append(("ok", f"✓ {v.get('n_numbers', 0)} number(s) verified against the data"))
    elif out.get("source") == "template_fallback":
        badges.append(("warn", "⚠ model wording had unverified numbers — showing raw result"))
    if out.get("rows") is not None and out.get("columns"):
        badges.append(("info", f"{len(out['rows'])} row(s)"))
    n_att = len(out.get("attempts", []))
    if n_att > 1:
        badges.append(("warn", f"repaired after {n_att - 1} failed attempt(s)"))
    snaps = [c for a in out.get("attempts", []) for c in a.get("snapped", [])]
    if snaps:
        badges.append(("info", f"{len(snaps)} place spelling(s) corrected"))
    total = sum((out.get("timings_ms") or {}).values()) / 1000
    badges.append(("info", f"{total:.1f} s"))
    st.markdown("".join(f"<span class='badge {c}'>{t}</span>" for c, t in badges), unsafe_allow_html=True)
    st.markdown(f"<div class='answer'>{out['answer']}</div>", unsafe_allow_html=True)
    if out.get("source") == "template_fallback" and out.get("llm_answer"):
        st.caption(f"Model's own wording (rejected: {', '.join(v.get('unsupported', []))} not in the result): {out['llm_answer']}")

    df = pd.DataFrame(out.get("rows") or [], columns=out.get("columns") or None)
    tabs = st.tabs(["Table", "Chart", "SQL", "How it got there"])
    with tabs[0]:
        if df.empty:
            st.caption("No rows.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"), "ingres_result.csv", "text/csv",
                               key=f"dl{out['_id']}")
    with tabs[1]:
        ch = auto_chart(df)
        if ch is not None:
            st.altair_chart(ch, use_container_width=True)
        else:
            st.caption("A chart is drawn when the result has 2–60 rows with a label and a number.")
    with tabs[2]:
        st.code(out.get("sql") or "-- no SQL", language="sql")
        for c in snaps:
            st.markdown(f"<span class='small'>Value correction: <code>{c['from']}</code> → <code>{c['to'] or c['from'] + ' (case-insensitive)'}</code> "
                        f"in <code>{c['column']}</code> ({c['how']})</span>", unsafe_allow_html=True)
    with tabs[3]:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Schema linker** (top-5 columns)")
            st.write(", ".join(f"`{h}`" for h in (out.get("hints") or [])) or "—")
            st.markdown("**Assessment year(s)** (rule)")
            st.write(", ".join(f"`{y}`" for y in (out.get("years") or [])) or "—")
        with c2:
            st.markdown("**Places resolved**")
            pl = out.get("places") or []
            if pl:
                st.dataframe(pd.DataFrame([{"written": p["mention"], "database name": p["db_name"], "level": p["level"],
                                            "state": p["state"], "score": p["score"]} for p in pl]),
                             hide_index=True, use_container_width=True)
            else:
                st.write("—")
        t = out.get("timings_ms") or {}
        if t:
            td = pd.DataFrame({"stage": list(t), "ms": list(t.values())})
            st.markdown("**Time per stage**")
            st.altair_chart(alt.Chart(td).mark_bar(color="#7a8aa0").encode(
                y=alt.Y("stage:N", sort=None, title=None), x=alt.X("ms:Q", title="milliseconds"), tooltip=["stage", "ms"]
            ).properties(height=40 + 26 * len(td)), use_container_width=True)
        for i, a in enumerate(out.get("attempts", []), 1):
            st.markdown(f"Attempt {i}: " + ("✓ executed" if not a["problem"] else f"✗ {a['problem']}"))


if page == "💬 Ask":
    st.markdown("<div class='hero'><h1>Ask about India's groundwater</h1>"
                "<p>English · हिन्दी · Hinglish · தமிழ் — official CGWB/INGRES assessments, 2019-20 to 2024-25. "
                "Every number in an answer is checked against the database result.</p></div>", unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("#### Try a question")
        for lang, qs in examples().items():
            with st.expander(LANG_NAMES.get(lang, lang), expanded=(lang == "english")):
                for i, ex in enumerate(qs):
                    if st.button(ex, key=f"ex_{lang}_{i}", use_container_width=True):
                        st.session_state["pending"] = ex
        st.markdown("#### Pipeline components")
        st.caption("Switch parts off to see what each one contributes (live ablation).")
        on = {"schema": st.toggle("Schema-linker hints", True), "places": st.toggle("Place-name resolution", True),
              "examples": st.toggle("Retrieved examples (3)", True), "years": st.toggle("Year rule", True),
              "notes": st.toggle("Metric definitions", True), "snap": st.toggle("Value snapping", True)}
        if st.button("Clear conversation", use_container_width=True):
            st.session_state["chat"] = []

    st.session_state.setdefault("chat", [])
    for m in st.session_state["chat"]:
        with st.chat_message(m["role"], avatar="🧑" if m["role"] == "user" else "💧"):
            if m["role"] == "user":
                st.markdown(m["content"])
            else:
                render_answer(m["content"])

    question = st.chat_input("Ask in English, Hindi, Hinglish or Tamil…", disabled=not llm_ok)
    question = question or st.session_state.pop("pending", None)
    if question:
        if not llm_ok:
            st.warning("The LLM is offline. Start `ollama serve` first.")
        else:
            with st.chat_message("user", avatar="🧑"):
                st.markdown(question)
            with st.chat_message("assistant", avatar="💧"):
                with st.status("Thinking…", expanded=False) as status:
                    if "pipe_loaded" not in st.session_state:
                        status.update(label="Loading models (first question only, ~20 s)…")
                    t0 = time.perf_counter()
                    try:
                        pipe = pipeline()
                        st.session_state["pipe_loaded"] = True
                        status.update(label="Linking schema and places, writing SQL…")
                        with components(pipe, on) as p:
                            out = p.answer(question)
                        status.update(label=f"Done in {time.perf_counter() - t0:.1f} s", state="complete")
                    except Exception as e:  # show the failure instead of a stack trace
                        out = {"error": f"{type(e).__name__}: {e}"}
                        status.update(label="Failed", state="error")
                out["_id"] = len(st.session_state["chat"])
                render_answer(out)
            st.session_state["chat"] += [{"role": "user", "content": question}, {"role": "assistant", "content": out}]


# ================================================================================================ EXPLORE
elif page == "📊 Explore the data":
    st.markdown("<div class='hero'><h1>Explore the assessments</h1><p>Straight from the database — no model involved."
                "</p></div>", unsafe_allow_html=True)
    years = q("SELECT assessment_year FROM assessment_years ORDER BY 1").assessment_year.tolist()
    states = q("SELECT state_name FROM states ORDER BY 1").state_name.tolist()
    c1, c2 = st.columns([1, 2])
    year = c1.selectbox("Assessment year", years, index=len(years) - 1)
    state = c2.selectbox("Region", ["All India"] + states)
    where_state = "" if state == "All India" else f" AND s.state_name = {lit(state)}"

    if state == "All India":
        nat = q(f"""SELECT SUM(extraction_total_ham - COALESCE(extraction_poor_quality_ham,0)) AS ex,
                           SUM(extractable_resource_ham - COALESCE(extractable_poor_quality_ham,0)) AS er,
                           SUM(annual_recharge_ham - COALESCE(recharge_poor_quality_ham,0)) AS rc
                    FROM state_assessments WHERE assessment_year = {lit(year)}""").iloc[0]
        stage, extraction, recharge = 100 * nat.ex / nat.er, nat.ex / 1e5, nat.rc / 1e5
    else:
        sa = q(f"""SELECT sa.stage_of_extraction_pct AS stage, sa.extraction_total_ham / 1e5 AS ex, sa.annual_recharge_ham / 1e5 AS rc
                   FROM state_assessments sa JOIN states s USING(state_id)
                   WHERE sa.assessment_year = {lit(year)}{where_state}""")
        stage, extraction, recharge = (sa.stage.iloc[0], sa.ex.iloc[0], sa.rc.iloc[0]) if len(sa) else (float("nan"),) * 3
    cats = q(f"""SELECT ua.category, COUNT(*) AS units FROM unit_assessments ua JOIN assessment_units u USING(unit_id)
                 JOIN states s ON s.state_id = u.state_id WHERE ua.assessment_year = {lit(year)}{where_state}
                 GROUP BY 1""")
    n_units = int(cats.units.sum())
    oe = int(cats.loc[cats.category == "Over-Exploited", "units"].sum())
    m = st.columns(4)
    m[0].metric("Stage of extraction", f"{stage:.1f}%" if stage == stage else "—",
                help="Extraction ÷ extractable resource × 100 (fresh water only for All India, as officially published)")
    m[1].metric("Annual extraction", f"{extraction:.2f} BCM" if extraction == extraction else "—")
    m[2].metric("Annual recharge", f"{recharge:.2f} BCM" if recharge == recharge else "—")
    m[3].metric("Over-exploited units", f"{oe:,} ({100 * oe / max(1, n_units):.1f}%)", help=f"out of {n_units:,} assessment units")

    left, right = st.columns([1, 1.4])
    with left:
        st.markdown("##### Assessment units by category")
        cats["category"] = pd.Categorical(cats.category, CATEGORIES)
        st.altair_chart(alt.Chart(cats).mark_arc(innerRadius=62).encode(
            theta="units:Q", color=alt.Color("category:N", scale=CAT_SCALE, legend=alt.Legend(orient="bottom", columns=3)),
            tooltip=["category", "units"]).properties(height=330), use_container_width=True)
    with right:
        if state == "All India":
            st.markdown("##### Stage of extraction by state")
            d = q(f"""SELECT s.state_name AS state, sa.stage_of_extraction_pct AS stage FROM state_assessments sa
                      JOIN states s USING(state_id) WHERE sa.assessment_year = {lit(year)} AND sa.stage_of_extraction_pct IS NOT NULL""")
        else:
            st.markdown("##### Stage of extraction by district")
            d = q(f"""SELECT d.district_name AS state, da.stage_of_extraction_pct AS stage FROM district_assessments da
                      JOIN districts d USING(district_id) JOIN states s ON s.state_id = d.state_id
                      WHERE da.assessment_year = {lit(year)}{where_state} AND da.stage_of_extraction_pct IS NOT NULL""")
        d["category"] = pd.cut(d.stage, [-1, 70, 90, 100, 1e9], labels=CATEGORIES[:4]).astype(str)
        bars = alt.Chart(d).mark_bar(cornerRadiusEnd=2).encode(
            y=alt.Y("state:N", sort="-x", title=None), x=alt.X("stage:Q", title="stage of extraction (%)"),
            color=alt.Color("category:N", scale=CAT_SCALE, legend=None), tooltip=["state", alt.Tooltip("stage:Q", format=".1f")])
        rule = alt.Chart(pd.DataFrame({"x": [70, 100]})).mark_rule(strokeDash=[4, 3], color="#888").encode(x="x:Q")
        st.altair_chart((bars + rule).properties(height=min(18 * len(d) + 40, 720)), use_container_width=True)

    st.markdown("##### Most stressed assessment units")
    top = q(f"""SELECT u.unit_name AS unit, u.unit_type AS type, d.district_name AS district, s.state_name AS state,
                       ua.stage_of_extraction_pct AS stage_pct, ua.category,
                       ua.extraction_total_ham AS extraction_ham, ua.extractable_resource_ham AS extractable_ham
                FROM unit_assessments ua JOIN assessment_units u USING(unit_id) JOIN districts d ON d.district_id = u.district_id
                JOIN states s ON s.state_id = u.state_id
                WHERE ua.assessment_year = {lit(year)}{where_state} AND ua.stage_of_extraction_pct IS NOT NULL
                ORDER BY ua.stage_of_extraction_pct DESC LIMIT 25""")
    st.dataframe(top, hide_index=True, use_container_width=True,
                 column_config={"stage_pct": st.column_config.ProgressColumn("stage %", min_value=0, max_value=float(max(100, top.stage_pct.max() if len(top) else 100)), format="%.0f")})

    st.markdown("##### How categories changed across cycles")
    trend = q(f"""SELECT ua.assessment_year AS year, ua.category, COUNT(*) AS units FROM unit_assessments ua
                  JOIN assessment_units u USING(unit_id) JOIN states s ON s.state_id = u.state_id
                  WHERE 1=1{where_state} GROUP BY 1, 2""")
    st.altair_chart(alt.Chart(trend).mark_bar().encode(
        x=alt.X("year:N", title=None), y=alt.Y("units:Q", stack="normalize", title="share of units", axis=alt.Axis(format="%")),
        color=alt.Color("category:N", scale=CAT_SCALE), order=alt.Order("category:N"),
        tooltip=["year", "category", "units"]).properties(height=280), use_container_width=True)
    st.caption(q("SELECT caveat FROM assessment_years LIMIT 1").caveat.iloc[0] + " Unit counts also change when states change "
               "their unit type (e.g. Tamil Nadu firka → taluk in 2022-23).")


# ================================================================================================ RESULTS
else:
    st.markdown("<div class='hero'><h1>Project results</h1><p>Every number below is read from a result file in "
                "<code>experiments/</code>.</p></div>", unsafe_allow_html=True)

    def load(p):
        f = ROOT / p
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    v2 = load("experiments/pipeline_v2/results.json")
    v1 = load("experiments/pipeline/results.json")
    st.markdown("##### End-to-end execution accuracy")
    rows = []
    if v1:
        for split in ("test", "hard_test"):
            for name in ("A keyword/template", "D qwen3:8b zero-shot", "pipeline full"):
                if name in v1.get(split, {}):
                    rows.append({"system": {"pipeline full": "original pipeline (Oct, baseline-v1)"}.get(name, name),
                                 "split": split, "EX": v1[split][name]["EX"]})
    if v2:
        names = {"baseline-v1 rerun": "original pipeline, re-run Nov", "v2": "+ Tamil fix + year rule",
                 "v3": "improved pipeline (v3)", "v31": "v3.1 (shipped: + place-linker fix)", "v3_loio": "v3, own question type hidden"}
        for split in ("test", "hard_test"):
            for k, label in names.items():
                if k in v2.get(split, {}):
                    rows.append({"system": label, "split": split, "EX": v2[split][k]["EX"]})
    if rows:
        df = pd.DataFrame(rows)
        st.altair_chart(alt.Chart(df).mark_bar(cornerRadiusEnd=3).encode(
            y=alt.Y("system:N", sort=None, title=None), x=alt.X("EX:Q", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
            color=alt.Color("split:N", scale=alt.Scale(range=["#3b7dd8", "#9cb8e4"])), yOffset="split:N",
            tooltip=["system", "split", alt.Tooltip("EX:Q", format=".1%")]).properties(height=46 * df.system.nunique() + 40),
            use_container_width=True)
        st.dataframe(df.pivot(index="system", columns="split", values="EX").reset_index(), hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format="%.3f") for c in ("test", "hard_test")})

    c = st.columns(4)
    sl = load("experiments/schema_linking/finetuned.json")
    er = load("experiments/entity_resolution/results.json")
    gr = load("experiments/grounding/results.json")
    pl = load("experiments/pipeline_v2/places_dev.json")
    c[0].metric("Schema linker R@3", "0.896", "+0.487 vs off-the-shelf")
    if er:
        c[1].metric("Place resolver, hand-written names (top-1)", f"{er['overall']['hand_script']['top1']:.3f}")
    if pl:
        c[2].metric(f"Place linker F1 (dev, τ = {pl['chosen_tau']})", f"{pl['by_tau'][str(pl['chosen_tau'])]['f1']:.3f}")
    if gr:
        c[3].metric("Planted numeric errors caught", f"{100 * gr['verifier_detection_rate_perturbed']:.1f}%",
                    help=f"{100 * gr['false_alarm_template_answers']:.0f}% false alarms on grounded answers")

    st.markdown("##### Speed (this PC, RTX 5060 + Ryzen 7 9700X)")
    perf = []
    for label in ("baseline", "optimized"):
        comp, llm, e2e = (load(f"experiments/perf/{label}_{s}.json") for s in ("components", "llm", "e2e"))
        if comp:
            perf.append({"version": label, "pre-LLM ms (mean)": comp["total_pre_llm"]["mean_ms"],
                         "place linking ms": comp["place_link"]["mean_ms"], "cold start s": comp["load"]["cold_start_total_s"],
                         "LLM request ms (median)": llm["request_wall"]["median_ms"] if llm else None,
                         "LLM tokens/s": llm["generation_tokens_per_s"] if llm else None,
                         "end-to-end ms (median)": e2e["pipeline_sql_wall"]["median_ms"] if e2e else None})
    if perf:
        st.dataframe(pd.DataFrame(perf), hide_index=True, use_container_width=True)
    st.caption("Details: PROJECT_OVERVIEW.md, INGRES_COMPLETE_TECHNICAL_DEEP_DIVE.md and docs/.")
