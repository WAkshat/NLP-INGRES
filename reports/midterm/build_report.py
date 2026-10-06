"""Builds the mid-term synopsis report on a copy of the university template (cover, certificate, index kept)."""
import copy
import json
from pathlib import Path

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

R = Path(__file__).resolve().parents[2]
TPL = Path(r"C:\Users\PC\Downloads\Mid term VII sem project synopsis report (1).docx")
OUT = R / "reports/midterm/Midterm_Synopsis_Report_INGRES_Text2SQL.docx"
FIG = R / "reports/midterm/fig"
TITLE = "INGRES-Text2SQL: A Multilingual Natural-Language Interface to India's Groundwater Assessment Data"
REPO = "https://github.com/WAkshat/NLP-INGRES"

d = docx.Document(TPL)
P = d.paragraphs


def set_text(p, text):
    runs = p.runs
    runs[0].text = text
    for r in runs[1:]:
        r.text = ""


# ---------------- cover + certificate
set_text(P[1], TITLE)
set_text(P[9], "<Student Name> (<Roll No.>)")
set_text(P[12], "<Dr./Ms./Mr. Supervisor Name>")
set_text(P[13], "<Designation>,")
cert = P[23]
full = cert.text.replace("<name of project", TITLE).replace("<Student names>", "<Student Name(s)>")
set_text(cert, full)

# ---------------- index
index = ["Abstract", "1. Introduction (description of broad topic)", "2. Background", "3. Feasibility Study",
         "4. Literature Survey", "5. Comparison with Existing Solutions and Literature", "6. Gap Analysis",
         "7. Problem Statement", "8. Objectives", "9. Proposed Methodology and Work Completed", "10. Outcomes",
         "11. Gantt Chart", "12. Responsibility Chart", "13. References",
         "Annexure I: Front page of plagiarism report by guide", "Annexure II: Screenshots of Faculty mail / comments from guide"]
slots = [43, 45, 47, 48, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60]
extra = copy.deepcopy(P[54]._p)            # one more index line than the template has
P[54]._p.addnext(extra)
slot_paras = [P[i] for i in slots[:9]] + [docx.text.paragraph.Paragraph(extra, P[54]._parent)] + [P[i] for i in slots[9:]]
for p, t in zip(slot_paras, index):
    set_text(p, t)
    pPr = p._p.pPr
    if pPr is not None:                    # drop template auto-numbering; our index text carries section numbers
        for num in pPr.findall(qn("w:numPr")):
            pPr.remove(num)
        ind = pPr.find(qn("w:ind"))
        if ind is not None:
            pPr.remove(ind)
for i in (44, 46, 49):                     # stray blank lines between index entries
    if not P[i].text.strip():
        P[i]._p.getparent().remove(P[i]._p)
for i in (64, 65, 66, 67):                 # template instructions, not part of the report
    P[i]._p.getparent().remove(P[i]._p)

body = d.element.body
sectPr = body[-1] if body[-1].tag == qn("w:sectPr") else None


def _font(run, size=12, bold=False, italic=False, color=None):
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    run.font.size = Pt(size)
    run.bold, run.italic = bold, italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def para(text="", size=12, bold=False, italic=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=6, line=1.5):
    p = d.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = line
    if text:
        # **bold** segments
        parts = text.split("**")
        for k, seg in enumerate(parts):
            if seg:
                _font(p.add_run(seg), size, bold or k % 2 == 1, italic)
    return p


def heading(text, level=1):
    p = para(text, size=14 if level == 1 else 12, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT, space_after=6)
    p.paragraph_format.space_before = Pt(12 if level == 1 else 8)
    p.paragraph_format.keep_with_next = True
    return p


def bullets(items):
    for it in items:
        p = para("", align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=2)
        p.paragraph_format.left_indent = Inches(0.35)
        p.paragraph_format.first_line_indent = Inches(-0.2)
        parts = ("\u2022  " + it).split("**")
        for k, seg in enumerate(parts):
            if seg:
                _font(p.add_run(seg), 12, k % 2 == 1)


def page_break():
    p = d.add_paragraph()
    p.add_run().add_break(WD_BREAK.PAGE)


def shade(cell, hex_fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


def borders(table):
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:color"), "808080")
        b.append(e)
    after = [c for c in tblPr if c.tag in (qn("w:tblLayout"), qn("w:tblCellMar"), qn("w:tblLook"), qn("w:tblCaption"), qn("w:tblDescription"))]
    if after:
        after[0].addprevious(b)   # schema order: tblBorders precedes layout / margins / look
    else:
        tblPr.append(b)


def table(header, rows, widths, size=10):
    t = d.add_table(rows=1, cols=len(header))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    borders(t)
    for j, h in enumerate(header):
        c = t.rows[0].cells[j]
        c.text = ""
        _font(c.paragraphs[0].add_run(h), size, True, color="FFFFFF")
        shade(c, "2E3A59")
    for r in rows:
        cells = t.add_row().cells
        for j, v in enumerate(r):
            cells[j].text = ""
            _font(cells[j].paragraphs[0].add_run(str(v)), size)
    for row in t.rows:
        for j, w in enumerate(widths):
            row.cells[j].width = Inches(w)
    d.add_paragraph()
    return t


def caption(text):
    para(text, size=10, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10, line=1.0)


def figure(path, width, cap):
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Inches(width))
    caption(cap)


# ---------------- numbers from the repository
A = json.loads((R / "experiments/baselines/A_keyword_template/metrics.json").read_text(encoding="utf-8"))
SL = json.loads((R / "experiments/schema_linking/baselines.json").read_text(encoding="utf-8"))["results"]
exA = {r["language"]: r["correct"] for r in A["breakdowns"]["language"]}
pct = lambda x: f"{100 * x:.1f}%"  # noqa: E731

page_break()
# ================= ABSTRACT
heading("Abstract")
para("India's groundwater assessments are published by the Central Ground Water Board (CGWB) through INGRES, a "
     "GIS portal that reports recharge, extraction and the Safe / Semi-Critical / Critical / Over-Exploited category "
     "of about 7,000 assessment units every cycle. The portal can only be explored through maps and tables, and only "
     "in English. This project builds and evaluates a natural-language interface that takes questions in English, "
     "Hindi, romanised Hinglish and Tamil, converts them into SQL over the INGRES data, executes the query safely "
     "and returns an answer whose numbers can be traced to the result. The focus is on measurable research questions "
     "rather than on a chatbot: schema linking under code-mixed Indian input, resolution of ambiguous place names, "
     "tokenizer inefficiency for Indic and romanised text, prevention of numeric hallucination, and the conditions "
     "under which multi-step agentic reasoning helps.")
para("By the mid-term the data layer and the benchmark are complete. The undocumented public data endpoint of the "
     "INGRES portal was identified from its JavaScript bundle and five assessment cycles (GWRA 2020, 2022, 2023, "
     "2024 and 2025) were crawled (5,299 requests, no failures). National totals computed from the resulting "
     "database match the figures published by the Ministry of Jal Shakti to within 0.1%. We also built INGRES-Bench, "
     "a benchmark of 371 question-SQL items in four languages (1,484 instances) with train, dev, test and hard-test "
     "splits. Three local baselines have been evaluated: a keyword/template system reaches "
     f"{pct(A['execution_accuracy'])} execution accuracy, and schema-linking recall@3 is 0.267 for BM25 and 0.409 for "
     "an off-the-shelf multilingual embedding model, with large drops for Hindi and Tamil script.")

# ================= 1 INTRODUCTION
heading("1. Introduction")
para("Groundwater supplies most of India's irrigation and a large share of its drinking water, and its over-use is "
     "one of the country's most serious resource problems. Every assessment cycle, CGWB and the States compute, "
     "for each block, mandal, taluk or similar assessment unit, how much groundwater is recharged, how much can be "
     "extracted sustainably, how much is actually extracted, and the resulting **stage of extraction** (extraction "
     "as a percentage of the extractable resource). Units are then categorised as Safe (up to 70%), Semi-Critical "
     "(70-90%), Critical (90-100%) or Over-Exploited (above 100%). These numbers drive well-permitting, "
     "recharge schemes and agricultural policy.")
para("The results are disseminated through INGRES (India Groundwater Resource Estimation System), built by CGWB "
     "with IIT Hyderabad. INGRES is powerful but is organised around maps and drill-down tables in English. A farmer "
     "leader, a block officer or a journalist who wants to ask \"Ludhiana ke kitne blocks over-exploited hain?\" or "
     "\"which Punjab blocks moved from Critical to Over-Exploited since 2022?\" has to navigate several screens and "
     "combine numbers by hand. **Text-to-SQL**, the task of converting a natural-language question into an "
     "executable database query, is a natural fit. However, published Text-to-SQL research is overwhelmingly "
     "English-centric, and the specific difficulties of Indian users (several scripts, romanised and code-mixed "
     "writing, many places sharing the same name, spelling variation of place names) have not been studied on a "
     "real government dataset.")
para("This project therefore treats the problem as a research study. We build a clean, reproducible database from "
     "the official INGRES data, construct a multilingual benchmark over it, establish strong baselines, and then "
     "add and measure individual components: learned schema linking, geographic entity resolution, tokenizer "
     "adaptation, a numeric grounding verifier and an agent for multi-step questions. Execution accuracy on the "
     "benchmark is the primary metric throughout.")

# ================= 2 BACKGROUND
heading("2. Background")
heading("2.1 Groundwater resource assessment and INGRES", 2)
para("Assessments follow the Ground Water Resource Estimation Committee methodology of 2015 (GEC-2015) [19]. "
     "Recharge is estimated from rainfall and from other sources (canal seepage, return flow of surface-water and "
     "groundwater irrigation, tanks and ponds, water-conservation structures). The annual extractable resource is "
     "recharge minus natural discharge, and extraction is estimated separately for irrigation, domestic and "
     "industrial use. The national reports are named by year (GWRA 2024, GWRA 2025, ...) and are summarised in "
     "Press Information Bureau releases [20]. INGRES is an Angular single-page application: its HTML contains no "
     "data, and there is no documented public API or bulk download for ordinary users.")
heading("2.2 Text-to-SQL", 2)
para("Modern Text-to-SQL is evaluated mainly with execution accuracy (EX): a predicted query is correct if running "
     "it returns the same result as the gold query. Benchmarks such as Spider [1] and BIRD [2] drove progress from "
     "schema-aware neural parsers (RAT-SQL [3], RESDSQL [6]) to large-language-model prompting pipelines "
     "(DIN-SQL [4], DAIL-SQL [5]) and multi-agent systems (MAC-SQL [22], CHESS [21]). A recurring finding is that "
     "**schema linking**, deciding which tables and columns a question refers to, is a main source of errors.")
heading("2.3 Multilingual and code-mixed language processing", 2)
para("Indian users frequently write Hindi in Latin script mixed with English (Hinglish), or keep place names in "
     "Latin script inside Devanagari or Tamil text. Code-mixing is commonly quantified with the Code-Mixing Index "
     "[12] and is known to degrade models trained on monolingual text [11]. Sub-word tokenizers also split Indic and "
     "romanised words into many more tokens than English words (high \"fertility\"), which raises cost and can "
     "lower accuracy [9, 10].")

# ================= 3 FEASIBILITY
heading("3. Feasibility Study")
para("Feasibility was assessed along the four dimensions of technical, economic, operational and schedule "
     "feasibility. The deciding risk, whether official data can be obtained at all, was resolved first and "
     "is no longer open.")
heading("3.1 Technical feasibility", 2)
bullets([
    "**Data access (verified).** The INGRES portal's public endpoint POST /api/gec/getBusinessDataForUserOpen was "
    "located in its JavaScript bundle. It returns JSON for country, state and district drill-downs without login. "
    "A polite, resumable crawler downloaded 7 cycle labels (5,299 responses) with zero failed requests.",
    "**Data quality (verified).** After removing the saline (poor-quality) component, national recharge, extractable "
    "resource, extraction and stage of extraction match the published GWRA 2022-2025 figures within 0.1%. District "
    "values add up exactly to state values, and unit categories agree 100% with the official thresholds for "
    "2021-22 onwards. These checks run as automated tests.",
    "**Compute.** The data fits in a 22 MB SQLite database. Retrieval baselines run on a CPU in milliseconds. The "
    "planned fine-tuning of small multilingual encoders (about 120 M parameters) fits on the available NVIDIA RTX "
    "5060 (8 GB) once a CUDA build of PyTorch is installed.",
    "**Large language models.** A Gemini API key (free tier) is available. The free tier is rate-limited and "
    "frequently overloaded, so all calls are cached on disk and runs are resumable.",
])
heading("3.2 Tools, technologies and datasets", 2)
table(["Category", "Tools / resources"],
      [["Language & libraries", "Python 3.12, pandas, pyarrow, SQLite, scikit-learn, sentence-transformers, indic_transliteration, pytest"],
       ["Models", "intfloat/multilingual-e5-small (embeddings), Gemini 3.x Flash (LLM baseline and agent)"],
       ["Data", "INGRES assessment data 2019-20 to 2024-25 (official), PIB national figures for validation"],
       ["Benchmark", "INGRES-Bench v1 (built in this project): 371 items x 4 languages"],
       ["Hardware", "Laptop CPU; NVIDIA GeForce RTX 5060 8 GB for fine-tuning"],
       ["Version control", "Git + GitHub: " + REPO]],
      [1.6, 4.8])
caption("Table 1: Required tools, technologies and resources")
heading("3.3 Economic, operational and schedule feasibility", 2)
bullets([
    "**Economic.** All software is open source. The data is public. The LLM is used on the free tier, so the "
    "monetary cost is zero; the constraint is the daily request quota, handled by caching.",
    "**Operational.** Every stage is a script (crawl, audit, build database, build benchmark, run baselines), so the "
    "whole pipeline can be rerun and audited. The raw data snapshot is archived with per-file checksums, so the "
    "results remain reproducible if the portal changes.",
    "**Schedule.** Phases 1-3 of 11 are complete at the mid-term and phase 4 is in progress (Gantt chart, "
    "Section 11). The riskiest phases (data access and benchmark) are behind us. The main remaining schedule risk is "
    "LLM availability, which is mitigated by caching and by running local baselines first.",
])

# ================= 4 LITERATURE
heading("4. Literature Survey")
para("The survey covers Text-to-SQL benchmarks and systems, multilingual and code-mixed NLP, tokenization, "
     "retrieval, and hallucination. Table 2 summarises the most relevant works.")
table(["Work", "Approach", "Data / evaluation", "Limitation for our setting"],
      [["Spider, Yu et al., EMNLP 2018 [1]", "Cross-domain Text-to-SQL benchmark", "10,181 questions, 200 databases; exact match and execution accuracy", "English only; academic databases"],
       ["BIRD, Li et al., NeurIPS 2023 [2]", "Large benchmark with dirty values and external knowledge", "12,751 pairs, 95 databases; reports a large gap between ChatGPT and humans", "English only; no geographic ambiguity"],
       ["RAT-SQL, Wang et al., ACL 2020 [3]", "Relation-aware transformer that encodes schema links", "Spider", "Needs training data per language; English schema text"],
       ["DIN-SQL, Pourreza & Rafiei, NeurIPS 2023 [4]", "Decomposed in-context learning with self-correction", "Spider, BIRD with GPT-4", "Always decomposes, extra cost on easy questions; English only"],
       ["DAIL-SQL, Gao et al., PVLDB 2024 [5]", "Systematic study of prompt design and example selection", "Spider with GPT-4", "English only"],
       ["RESDSQL, Li et al., AAAI 2023 [6]", "Decouples schema linking (ranking) from SQL skeleton parsing", "Spider", "Ranking model trained on English questions"],
       ["CSpider, Min et al., EMNLP 2019 [7]", "Chinese translation of Spider", "Chinese Text-to-SQL", "Single language; no code-mixing"],
       ["MultiSpider, Dou et al., AAAI 2023 [8]", "Spider in seven languages", "Shows accuracy drops outside English", "No Indian languages, scripts or code-mixing"],
       ["MAC-SQL [22], CHESS [21]", "Multi-agent / pipeline LLM systems with schema selection and refinement", "BIRD, Spider", "Cost and latency; benefit per question type not isolated"],
       ["Petrov et al., NeurIPS 2023 [9]; Rust et al., ACL 2021 [10]", "Tokenizer fertility and unfairness across languages", "Many languages", "Not linked to downstream Text-to-SQL"],
       ["GLUECoS, Khanuja et al., ACL 2020 [11]; CMI [12]", "Code-switched NLP benchmark; code-mixing index", "Hindi-English, Spanish-English tasks", "No semantic parsing / SQL task"],
       ["IndicTrans2 [13], Multilingual E5 [14]", "Indic machine translation; multilingual embeddings", "22 Indian languages; retrieval benchmarks", "Generic; not adapted to database schemas"],
       ["FActScore [16], hallucination survey [17]", "Measuring unsupported facts in generated text", "Long-form generation", "Not specific to numbers derived from SQL results"]],
      [1.55, 1.7, 1.55, 1.6], size=9)
caption("Table 2: Summary of the literature survey")
para("Three observations follow. First, strong LLM pipelines (DIN-SQL, DAIL-SQL, MAC-SQL, CHESS) are evaluated "
     "almost entirely on English benchmarks. Second, the multilingual Text-to-SQL work (CSpider, MultiSpider) "
     "translates English benchmarks into other languages but does not cover Indian scripts, romanised text or "
     "code-mixing. Third, tokenizer-fairness studies measure fertility but rarely connect it to accuracy on a "
     "structured task such as SQL generation.")

# ================= 5 COMPARISON
heading("5. Comparison with Existing Solutions and Literature")
para("Existing ways of querying INGRES data were also examined. The INGRES portal itself supports map- and "
     "table-based exploration but no natural-language queries. Some public student and hackathon prototypes describe "
     "INGRES chatbots, and a paid third-party scraping API for INGRES exists; the prototypes we inspected do not "
     "document how the data was obtained or report any evaluation. Table 3 compares these options and the "
     "literature with the proposed work.")
table(["Parameter", "INGRES portal", "English Text-to-SQL (Spider/BIRD systems)", "Multilingual Text-to-SQL (MultiSpider)", "Proposed work"],
      [["Natural-language questions", "No", "Yes", "Yes", "Yes"],
       ["Indian languages / scripts", "No", "No", "No", "Hindi, Tamil"],
       ["Romanised code-mixed input (Hinglish)", "No", "No", "No", "Yes"],
       ["Ambiguous place-name resolution", "Manual navigation", "Not addressed", "Not addressed", "Gazetteer + context resolver"],
       ["Cross-year comparison with methodology caveats", "Manual", "No", "No", "Yes (crosswalk + caveats)"],
       ["Numbers in answers verified against data", "N/A", "Rarely", "No", "Grounding verifier"],
       ["Evaluation on a public benchmark", "N/A", "Yes", "Yes", "INGRES-Bench (built here)"],
       ["Official government data", "Yes", "No", "No", "Yes"]],
      [1.6, 0.95, 1.3, 1.25, 1.3], size=9)
caption("Table 3: Comparison of existing solutions and literature with the proposed work")

# ================= 6 GAP
heading("6. Gap Analysis")
bullets([
    "**No multilingual benchmark for Indian public data.** No existing Text-to-SQL benchmark covers Hindi, "
    "romanised Hinglish or a Dravidian language, and none is built on Indian government data. Claims about "
    "Indian-language performance therefore cannot be measured.",
    "**Schema linking across scripts is unmeasured.** Schemas are written in English while questions arrive in "
    "Devanagari, Tamil or romanised text. Our baselines show the size of this gap: BM25 schema recall collapses to "
    "about 1% for Hindi and Tamil script, and an off-the-shelf multilingual encoder still trails English by 26-32 points.",
    "**Place names are ambiguous and inconsistently spelled.** In INGRES, 169 unit names are shared by units in "
    "different states (for example \"Ramnagar\" appears 10 times), and the data itself contains hundreds of "
    "respellings across cycles (NOWGAON vs NOWGONG). General Text-to-SQL systems assume exact value matching.",
    "**Cross-year comparisons are unsafe.** Assessment-unit identifiers and even the unit type change between "
    "cycles (for example Tamil Nadu moved from firkas to taluks). Naive year-to-year joins produce wrong answers, "
    "and no existing system records such comparability caveats.",
    "**Numbers in generated answers are not verified.** LLM answers can state numbers that are not in the query "
    "result, and this matters for policy data.",
    "**The benefit of agents is not isolated.** Multi-step agents add cost and latency, and it is not known on which "
    "question types they actually help.",
])

# ================= 7 PROBLEM
heading("7. Problem Statement")
para("To design, build and rigorously evaluate a natural-language interface that converts questions about India's "
     "groundwater assessments, written in English, Hindi, romanised Hinglish or Tamil, into correct and safe SQL "
     "over the official INGRES data, and returns answers whose numbers are grounded in the query results. The study "
     "will measure, using execution accuracy on a purpose-built benchmark, how much schema linking, geographic entity "
     "resolution, tokenizer adaptation, numeric grounding and agentic decomposition each contribute, with particular "
     "attention to code-mixed and noisy input and to historical comparisons across assessment cycles.")

# ================= 8 OBJECTIVES
heading("8. Objectives")
bullets([
    "**O1.** Build a validated, reproducible relational database of official INGRES assessments for multiple cycles, "
    "reconciled against published national figures. (Completed.)",
    "**O2.** Construct INGRES-Bench, a multilingual (English, Hindi, Hinglish, Tamil) Text-to-SQL benchmark with "
    "difficulty levels, leakage-free splits and a hard test set with realistic noise. (Completed.)",
    "**O3.** Establish baselines: keyword/template, BM25 and embedding schema retrieval, and a frontier LLM. (In progress.)",
    "**O4.** Train a multilingual schema linker with hard negatives, and compare it with the baselines by recall@k and MRR per language.",
    "**O5.** Build a hierarchical geographic entity resolver robust to misspellings, transliteration and ambiguous names (top-1 / top-3 accuracy).",
    "**O6.** Measure tokenizer fertility across languages and its relationship with schema-linking and execution accuracy, "
    "and compare translation, direct multilingual processing and vocabulary adaptation.",
    "**O7.** Implement a numeric grounding verifier that checks every number in an answer against the SQL result and "
    "can regenerate or abstain.",
    "**O8.** Compare single-shot generation with agentic decomposition and self-correction on accuracy, calls, latency and cost.",
])

# ================= 9 METHODOLOGY + WORK DONE
heading("9. Proposed Methodology and Work Completed")
figure(FIG / "architecture.png", 6.3, "Figure 1: System architecture (filled: built and validated; outlined: planned)")
heading("9.1 Data layer (completed)", 2)
para("Raw responses are cached verbatim with request metadata, flattened into a lossless long table (6.2 million "
     "values, 235 raw fields), audited, and loaded into a SQLite database with state, district and assessment-unit "
     "tables and one assessment table per level. Five complete cycles are included: 2019-20, 2021-22, 2022-23, "
     "2023-24 and 2024-25, i.e. GWRA 2020 and 2022-2025. The 2016-17 and 2025-26 labels were excluded because they "
     "are incomplete or inconsistent. Because INGRES re-issues location identifiers for some states between "
     "cycles, a conservative crosswalk links units by identifier, then by exact normalised name within state and "
     "unit type, then by fuzzy match within the same district. A manual check of 40 fuzzy links found 37 correct. "
     "The database is only ever queried through a read-only executor that rejects any write, ATTACH or PRAGMA "
     "statement (13 injection tests).")
table(["Cycle", "States/UTs", "Districts", "Assessment units", "Published extraction (BCM)", "Database (BCM)"],
      [["2021-22 (GWRA 2022)", "37", "746", "7,168", "239.16", "239.18"],
       ["2022-23 (GWRA 2023)", "37", "734", "6,670", "241.34", "241.31"],
       ["2023-24 (GWRA 2024)", "37", "730", "6,965", "245.64", "245.65"],
       ["2024-25 (GWRA 2025)", "37", "735", "6,984", "247.22", "247.22"]],
      [1.5, 0.8, 0.8, 1.1, 1.2, 1.0], size=10)
caption("Table 4: Coverage of the database and reconciliation with published national extraction")
heading("9.2 INGRES-Bench (completed)", 2)
para("The benchmark contains 371 items over 38 question types in four difficulty levels (simple lookup 107, "
     "filtered aggregate 120, cross-year comparison 80, multi-hop 64). Each item is rendered in English, Hindi "
     "(Devanagari), Hinglish (romanised) and Tamil from the same slots (place, year, metric, category, number), so all "
     "four versions share one gold SQL query whose result is stored. All language versions of an item stay in the "
     "same split. The units used in test questions are kept apart from those in training questions, and one phrasing "
     "per question type is reserved for testing. The hard-test split contains more cross-year and multi-hop "
     "questions and realistic noise: typos in place names, real historical INGRES respellings, place names in Latin "
     "script inside Hindi or Tamil text, and numbers written as words. An automatic quality check found no failures "
     "across eight checks on all 1,484 instances. A manual review of a stratified sample of 24 instances found all "
     "semantically correct. The text has not yet been verified by native speakers, which is a stated limitation.")
table(["Split", "Items", "Instances", "Simple", "Aggregate", "Cross-year", "Multi-hop"],
      [["Train", "153", "612", "47", "46", "34", "26"], ["Dev", "57", "228", "11", "25", "6", "15"],
       ["Test", "96", "384", "30", "39", "15", "12"], ["Hard-test", "65", "260", "19", "10", "25", "11"]],
      [1.0, 0.7, 0.9, 0.8, 0.9, 0.9, 0.9], size=10)
caption("Table 5: INGRES-Bench v1 splits")
heading("9.3 Baselines (in progress)", 2)
para("Execution accuracy is computed by running the predicted query with the read-only executor and comparing its "
     "result with the stored gold result (order-sensitive only when the gold query sorts, with a small numeric "
     "tolerance). Results on the 872 dev, test and hard-test instances are shown in Figure 2 and Table 6. The "
     "keyword/template system reaches "
     f"{pct(A['execution_accuracy'])} overall ({pct(exA['english'])} English, {pct(exA['hindi'])} Hindi, "
     f"{pct(exA['hinglish'])} Hinglish, {pct(exA['tamil'])} Tamil). It fails most on questions with ambiguous place "
     "names (9.4% vs 39.9%). Schema-linking results show that lexical retrieval breaks down completely for native "
     "scripts, and that multilingual embeddings recover only part of the gap. The frontier-LLM baseline "
     "(Gemini, zero-shot with schema and documentation) is implemented, but it could not yet be run because the "
     "free tier was overloaded.")
figure(FIG / "baseline_results.png", 6.3, "Figure 2: Schema-linking recall@3 (left) and execution accuracy of baseline A (right) by language")
bm, em, rn = SL["B_bm25"]["column"], SL["C_multilingual_e5_small"]["column"], SL["random (no linking)"]["column"]
table(["Method", "English", "Hindi", "Hinglish", "Tamil", "Overall R@3", "MRR"],
      [[n, *[f"{m['by_language'][l]['R@3']:.3f}" for l in ("english", "hindi", "hinglish", "tamil")], f"{m['R@3']:.3f}", f"{m['MRR']:.3f}"]
       for n, m in (("Random (no linking)", rn), ("BM25", bm), ("multilingual-e5-small", em))],
      [1.7, 0.8, 0.8, 0.8, 0.8, 1.0, 0.7], size=10)
caption("Table 6: Column recall@3 and MRR of schema-linking baselines (dev + test + hard-test)")
heading("9.4 Planned components", 2)
bullets([
    "**Learned schema linking:** contrastive fine-tuning of a multilingual bi-encoder with hard negatives drawn from "
    "semantically adjacent columns (recharge vs extractable resource, extraction vs stage of extraction, district vs unit).",
    "**Geographic entity resolution:** a gazetteer of all states, districts and units with aliases and "
    "transliterations, candidate generation by fuzzy and embedding similarity, and ranking with the state or district "
    "context mentioned in the question.",
    "**Tokenization study:** tokens per word, proportion of fragmented words and code-mixing index per language, "
    "correlated with schema-linking and execution accuracy. Translate-then-parse, direct multilingual parsing and "
    "vocabulary adaptation will be compared.",
    "**Numeric grounding:** extraction of integers, decimals, percentages and years from generated answers; each is "
    "matched against the result set up to equivalent formatting, and the system passes, regenerates or abstains.",
    "**Agent:** used only for multi-step questions. It decomposes the question, runs sub-queries and corrects itself "
    "on execution errors or unexpectedly empty results. It will be compared with single-shot generation on the hard split.",
])

# ================= 10 OUTCOMES
heading("10. Outcomes")
bullets([
    "A validated, reproducible database of official INGRES groundwater assessments for five cycles, with a documented "
    "data-access report and a raw-data snapshot. (Achieved.)",
    "INGRES-Bench, to our knowledge the first multilingual and code-mixed Text-to-SQL benchmark over Indian government "
    "data, with a construction protocol and quality control. (Achieved.)",
    "Measured baselines and, for each component, ablation results showing its effect on execution accuracy per "
    "language and difficulty, including negative results where a component does not help.",
    "A working prototype (read-only, multilingual) with a minimal interface that shows the generated SQL, the result "
    "and a grounded answer, with methodology caveats for cross-year questions.",
    "An open-source repository with scripts to reproduce every number: " + REPO,
])

# ================= 11 GANTT
heading("11. Gantt Chart")
figure(FIG / "gantt.png", 6.5, "Figure 3: Project timeline (Project-I: Jul-Dec 2026, Project-II: Jan-May 2027)")

# ================= 12 RESPONSIBILITY
heading("12. Responsibility Chart")
para("<Replace the member names below with the actual team members.>", italic=True)
table(["Task", "<Member 1>", "<Member 2>", "<Member 3>", "<Member 4>"],
      [["Data access, crawling and audit", "R", "A", "C", "I"],
       ["Canonical database and crosswalk", "R", "C", "A", "I"],
       ["INGRES-Bench construction and QC", "A", "R", "R", "C"],
       ["Baselines and evaluation harness", "C", "R", "A", "R"],
       ["Schema linking and tokenization study", "C", "A", "R", "C"],
       ["Entity resolution and numeric grounding", "R", "C", "C", "A"],
       ["Agent, UI and documentation", "A", "C", "C", "R"]],
      [2.6, 0.9, 0.9, 0.9, 0.9], size=10)
caption("Table 7: Responsibility chart (R = responsible, A = accountable, C = consulted, I = informed)")

# ================= 13 REFERENCES
heading("13. References")
refs = [
    "T. Yu et al., \"Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task,\" in Proc. EMNLP, 2018.",
    "J. Li et al., \"Can LLM Already Serve as a Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs,\" in Proc. NeurIPS (Datasets and Benchmarks), 2023.",
    "B. Wang, R. Shin, X. Liu, O. Polozov and M. Richardson, \"RAT-SQL: Relation-Aware Schema Encoding and Linking for Text-to-SQL Parsers,\" in Proc. ACL, 2020.",
    "M. Pourreza and D. Rafiei, \"DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction,\" in Proc. NeurIPS, 2023.",
    "D. Gao et al., \"Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation,\" Proc. VLDB Endowment, vol. 17, no. 5, 2024.",
    "H. Li, J. Zhang, C. Li and H. Chen, \"RESDSQL: Decoupling Schema Linking and Skeleton Parsing for Text-to-SQL,\" in Proc. AAAI, 2023.",
    "Q. Min, Y. Shi and Y. Zhang, \"A Pilot Study for Chinese SQL Semantic Parsing,\" in Proc. EMNLP-IJCNLP, 2019.",
    "L. Dou et al., \"MultiSpider: Towards Benchmarking Multilingual Text-to-SQL Semantic Parsing,\" in Proc. AAAI, 2023.",
    "A. Petrov, E. La Malfa, P. Torr and A. Bibi, \"Language Model Tokenizers Introduce Unfairness Between Languages,\" in Proc. NeurIPS, 2023.",
    "P. Rust, J. Pfeiffer, I. Vulić, S. Ruder and I. Gurevych, \"How Good is Your Tokenizer? On the Monolingual Performance of Multilingual Language Models,\" in Proc. ACL, 2021.",
    "S. Khanuja, S. Dandapat, A. Srinivasan, S. Sitaram and M. Choudhury, \"GLUECoS: An Evaluation Benchmark for Code-Switched NLP,\" in Proc. ACL, 2020.",
    "B. Gambäck and A. Das, \"Comparing the Level of Code-Switching in Corpora,\" in Proc. LREC, 2016.",
    "J. Gala et al., \"IndicTrans2: Towards High-Quality and Accessible Machine Translation Models for all 22 Scheduled Indian Languages,\" Transactions on Machine Learning Research, 2023.",
    "L. Wang et al., \"Multilingual E5 Text Embeddings: A Technical Report,\" arXiv:2402.05672, 2024.",
    "S. Robertson and H. Zaragoza, \"The Probabilistic Relevance Framework: BM25 and Beyond,\" Foundations and Trends in Information Retrieval, vol. 3, no. 4, 2009.",
    "S. Min et al., \"FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation,\" in Proc. EMNLP, 2023.",
    "Z. Ji et al., \"Survey of Hallucination in Natural Language Generation,\" ACM Computing Surveys, vol. 55, no. 12, 2023.",
    "G. Katsogiannis-Meimarakis and G. Koutrika, \"A Survey on Deep Learning Approaches for Text-to-SQL,\" The VLDB Journal, vol. 32, 2023.",
    "Central Ground Water Board, \"Report of the Ground Water Resource Estimation Committee (GEC-2015),\" Ministry of Water Resources, River Development and Ganga Rejuvenation, Government of India, 2017.",
    "Press Information Bureau, Ministry of Jal Shakti, releases on the Dynamic Ground Water Resource Assessment of India for 2022, 2023, 2024 and 2025 (PRID 1874808, 1981600, 2089039, 2220203).",
    "M. Talaei et al., \"CHESS: Contextual Harnessing for Efficient SQL Synthesis,\" arXiv:2405.16755, 2024.",
    "B. Wang et al., \"MAC-SQL: A Multi-Agent Collaborative Framework for Text-to-SQL,\" in Proc. COLING, 2025.",
    "Central Ground Water Board and IIT Hyderabad, \"India Groundwater Resource Estimation System (INGRES),\" https://ingres.iith.ac.in/home (accessed 28 Sep 2026).",
]
for i, r in enumerate(refs, 1):
    p = para(f"[{i}] {r}", align=WD_ALIGN_PARAGRAPH.LEFT, space_after=3, line=1.15)
    p.paragraph_format.left_indent = Inches(0.4)
    p.paragraph_format.first_line_indent = Inches(-0.4)

page_break()
heading("Annexure I: Front page of plagiarism report by guide")
para("<Insert the front page of the Turnitin report generated through the guide's official email ID "
     "(overall and AI similarity each 10% or less).>", italic=True, align=WD_ALIGN_PARAGRAPH.LEFT)
page_break()
heading("Annexure II: Screenshots of Faculty mail / comments from guide")
para("<Insert screenshots of the supervisor's e-mails / comments.>", italic=True, align=WD_ALIGN_PARAGRAPH.LEFT)

if sectPr is not None:                      # keep the section properties as the last element of the body
    body.remove(sectPr)
    body.append(sectPr)
d.save(OUT)
print("saved", OUT)
