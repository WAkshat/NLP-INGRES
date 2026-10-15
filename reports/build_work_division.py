"""Builds reports/Work_Division_INGRES_Text2SQL.pdf: team work split, how/why, main files, viva Q&A.

    python reports/build_work_division.py

All numbers are taken from the repository's experiment files (see PROJECT_OVERVIEW.md). Non-Latin text is written in
transliteration because the PDF uses standard fonts.
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

OUT = Path(__file__).parent / "Work_Division_INGRES_Text2SQL.pdf"
NAVY = colors.HexColor("#2E3A59")
ss = getSampleStyleSheet()
TITLE = ParagraphStyle("t", parent=ss["Title"], fontSize=20, textColor=NAVY)
H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=15, textColor=NAVY, spaceBefore=6)
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, textColor=NAVY, spaceBefore=8)
H3 = ParagraphStyle("h3", parent=ss["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=2)
B = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=13)
BUL = ParagraphStyle("bul", parent=B, leftIndent=12, bulletIndent=2)
Q = ParagraphStyle("q", parent=B, fontName="Helvetica-Bold", spaceBefore=5)
A = ParagraphStyle("a", parent=B, leftIndent=10)
CELL = ParagraphStyle("c", parent=B, fontSize=8.5, leading=11)


def p(x, st=B):
    return Paragraph(x, st)


def bullets(items):
    return [Paragraph(x, BUL, bulletText="•") for x in items]


def code(x):
    return f"<font face='Courier' size='8.5'>{x}</font>"


def table(rows, widths):
    t = Table([[p(c, CELL) for c in r] for r in rows], colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F4F8")])]))
    return t


def qa(pairs):
    out = []
    for q, a in pairs:
        out.append(KeepTogether([p("Q. " + q, Q), p(a, A)]))
    return out


# ============================================================================ content
story = [p("INGRES-Text2SQL", TITLE),
         p("<b>Division of work, methods, and viva preparation</b>", ParagraphStyle("st", parent=B, fontSize=12, alignment=1)),
         Spacer(1, 6),
         p("Multilingual (English / Hindi / Hinglish / Tamil) natural-language interface to India's official groundwater "
           "database (INGRES, Central Ground Water Board + IIT Hyderabad). Repository: github.com/WAkshat/NLP-INGRES. "
           "Team: Akshat, Aryan, Akshit, Waie.", ParagraphStyle("c2", parent=B, alignment=1)),
         Spacer(1, 10)]

story += [p("1. The project in one page", H1),
          p("<b>Problem.</b> INGRES publishes groundwater assessments for about 7,000 blocks/taluks/mandals per cycle "
            "(recharge, extraction, stage of extraction, and a category: Safe / Semi-Critical / Critical / Over-Exploited). "
            "The portal is an English-only, click-through map with no public download and no documented API. The people who "
            "need the data (farmers, district officials, journalists) often ask in Hindi, Hinglish or regional languages, e.g. "
            "<i>\"Ludhiana ke kitne blocks over-exploited hain?\"</i>"),
          p("<b>Goal.</b> Translate such questions into correct SQL over the INGRES data, run it safely, and answer with numbers "
            "that are checked against the data, and <b>measure which components actually improve accuracy</b>."),
          p("<b>Why it is hard.</b> (1) Three scripts (Latin, Devanagari, Tamil) and code-mixing, while the schema is in English; "
            "(2) 8,751 places, 169 unit names shared across states (e.g. 'Ramnagar' x10), idiosyncratic spellings ('TAMILNADU'); "
            "(3) domain conventions ('the 2025 assessment' = assessment_year '2024-2025'; volumes in hectare-metres); "
            "(4) unit IDs change between cycles; (5) a fluent but wrong number is dangerous for official data."),
          p("<b>Main metric.</b> Execution accuracy (EX): a question counts as correct if the predicted SQL returns the same "
            "result as the gold SQL."),
          Spacer(1, 4),
          table([["Result", "Value"],
                 ["Database vs government-published national totals", "match within 0.07% (4 cycles)"],
                 ["Benchmark built (INGRES-Bench v1)", "371 questions x 4 languages = 1,484 instances, 0 QC failures"],
                 ["Keyword/template baseline EX", "38.8% (test split 32.6%)"],
                 ["Local LLM qwen3:8b zero-shot EX", "18.2% (test 18.0%)"],
                 ["Schema linker column recall@3", "0.409 -> 0.896 (fine-tuned); 0.851 on unseen question types"],
                 ["Place resolver, ambiguous names", "0.447 -> 0.973 top-1 with state context"],
                 ["LLM + schema-linker hints (test)", "23.2% EX vs 18.0% (+5.2 points, McNemar p = 0.008)"],
                 ["Unsupported numbers in answers", "0.83% -> 0% with the numeric verifier"],
                 ["<b>Full pipeline EX (test / hard_test)</b>", "<b>71.9% / 57.7%</b> (baselines 32.6% / 30.8% and 18.0% / 13.1%; p < 1e-6)"],
                 ["Biggest contributors (test, leave-one-out)", "retrieved examples +36.5, place hints +4.4, repair +1.6"]],
                [9 * cm, 8 * cm]),
          Spacer(1, 8),
          p("2. Division of work", H1),
          table([["Member", "Role", "Phases / components"],
                 ["Akshat", "Data engineering, system integration, project lead",
                  "Ph 1-2 data access + database, SQL safety layer, Ph 9 full pipeline (71.9% EX), Ph 11 ablations, error analysis, docs"],
                 ["Aryan", "Benchmark, evaluation, baselines",
                  "Ph 3 INGRES-Bench, execution-accuracy evaluator, Ph 4 baselines, LLM clients and prompts"],
                 ["Akshit", "Learned models", "Ph 5 schema linker, Ph 6 entity resolver, place linker"],
                 ["Waie", "Multilingual analysis, answer trust, UI",
                  "Ph 7 tokenization study, Ph 8 numeric verifier, Ph 10 UI, mid-term report and slides"]],
                [2.3 * cm, 5.2 * cm, 9.5 * cm]),
          Spacer(1, 6),
          p("<b>How the pieces connect at run time:</b> question -> schema linker (Akshit) suggests columns -> place linker "
            "(Akshit) gives exact database spellings -> similar training questions retrieved (Aryan's benchmark) -> prompt "
            "(Aryan) -> qwen3:8b on the RTX 5060 writes SQL -> read-only executor (Akshat) runs it, errors are fed back for "
            "repair (Akshat) -> answer sentence -> numeric verifier (Waie) -> UI (Waie). Every step is scored by the evaluator "
            "(Aryan) on the benchmark (Aryan)."),
          PageBreak()]

# ---------------------------------------------------------------------------- AKSHAT
story += [p("3. Akshat: data engineering, integration, project lead", H1),
          p("What was built", H2)] + bullets([
    "<b>Data access (Phase 1).</b> Found INGRES's undocumented public endpoint "
    + code("POST /api/gec/getBusinessDataForUserOpen") + " and crawled 7 assessment cycles: 5,299 requests, 0 failures, ~80 min.",
    "<b>Canonical database (Phase 2).</b> Flattened 6.2 million raw facts into a 9-table SQLite database (21.8 MB): "
    "5 cycles, 37 states, 770 districts, 8,751 units, 34,565 unit-year rows.",
    "<b>Cross-year crosswalk.</b> Links the same unit across cycles even when INGRES re-issued its ID.",
    "<b>Read-only SQL safety layer</b> used by every component.",
    "<b>Full pipeline (Phase 9)</b> that joins all components, with an execution-guided repair loop; final evaluation."]) + [
    p("How and why", H2),
    p("Finding the data", H3),
    p("<b>How:</b> the portal's HTML is an empty Angular shell, so the data had to come from a background API. Reading the "
      "portal's JavaScript bundle revealed the base URL and a function used for non-logged-in users that posts to the "
      "endpoint above without authentication. Opening a location returns its children, so the crawler walks country -> "
      "state -> district, sends one request at a time with a 0.5 s delay, and caches every raw response (gzip, with the "
      "request and timestamp) so the crawl is resumable and reproducible."),
    p("<b>Why:</b> Excel export is admin-only and PDF reports would need error-prone table extraction. The JSON API gives "
      "the same numbers in structured form. Politeness (sequential requests, delay) avoids loading a government server."),
    p("Proving the data is right", H3),
    p("<b>How:</b> national totals computed from our database were compared with the figures the government published in "
      "PIB press releases. Official figures count only fresh groundwater, so fresh = total - saline (poor_quality). "
      "Result: GWRA 2022 recharge 437.61 vs 437.60 BCM, extraction 239.18 vs 239.16; GWRA 2025 448.51 vs 448.52 and "
      "247.22 vs 247.22; largest deviation 0.07%. This is an automated test (" + code("tests/test_db_against_published.py") + ")."),
    p("<b>Why:</b> without this, any later accuracy number could be measuring a broken database. It also caught a real bug: "
      "the API omits the saline key when it is zero; storing it as NULL silently dropped rows and gave a wrong national "
      "extraction of 128 BCM. The database now stores 0 in that case."),
    p("Two cycles were excluded on evidence: 2016-17 (4 states missing, totals about 2x the published values) and 2025-26 "
      "(incomplete, cycle in progress)."),
    p("Cross-year crosswalk", H3),
    p("<b>How:</b> walking backwards from 2024-25, each older unit is matched in order: (1) same ID; (2) same name in the "
      "same district; (3) name unique in the state; (4) fuzzy match within the same district, accepted only if it is the "
      "mutual best match with similarity >= 0.75 and not a split unit (SANGANER vs SANGANER_RURAL) or a different "
      "ordinal (-II vs -III). Ambiguous candidates are never linked. A hand check of 40 fuzzy links: 37 correct (92.5%)."),
    p("<b>Why:</b> unit-ID overlap between 2019-20 and 2021-22 is only 0.14, so naive joins across years are wrong. States "
      "where the unit type changed (e.g. Tamil Nadu firka -> taluk) are recorded in a table and excluded from cross-year "
      "questions, because those units are not comparable."),
    p("SQL safety", H3),
    p("<b>How:</b> the database is opened read-only, and an SQLite authorizer callback allows only SELECT/READ/function "
      "actions, blocks dangerous functions (load_extension, readfile, writefile), enforces a 10 s timeout and a row cap. "
      "13 tests try injections, writes and multiple statements. <b>Why:</b> the SQL is written by an LLM from user text, "
      "so it must be treated as untrusted. Read-only access is enforced by the database engine, not by checking the SQL string."),
    p("Full pipeline and repair loop", H3),
    p("<b>How:</b> " + code("Pipeline.sql") + " builds one prompt from the schema-linker hints, the resolved places and 3 "
      "retrieved examples; if the SQL errors or returns nothing, the error message is sent back to the model (at most 2 "
      "repairs; it stops if the model repeats the same query). Each component can be switched off for ablation. "
      "<b>Why:</b> zero-shot errors were systematic (wrong year label, wrong column, wrong place spelling), and each component "
      "targets one of them; ablations show which ones actually help."),
    p("Final results and ablations (Phases 9 and 11)", H3),
    table([["System", "test EX (n=384)", "hard_test EX (n=260)"],
           ["Keyword/template baseline", "32.6%", "30.8%"],
           ["qwen3:8b zero-shot", "18.0%", "13.1%"],
           ["+ schema hints", "23.2%", "-"],
           ["+ place hints + repair (no examples)", "35.4%", "-"],
           ["<b>Full pipeline (+ 3 retrieved examples)</b>", "<b>71.9%</b> [67.4, 76.0]", "<b>57.7%</b> [51.9, 63.8]"],
           ["Full without place hints", "67.4% (-4.4, p = 0.019)", "-"],
           ["Full, first attempt only (no repair)", "70.3% (-1.6; 6 fixed, 0 broken)", "56.1%"]],
          [7 * cm, 5 * cm, 5 * cm]),
    p("By language (test): English 78.1, Hindi 69.8, Hinglish 77.1, Tamil 62.5. Error analysis of 218 failures: place not "
      "linked 41%, other logic 33%, wrong year 13%, wrong column 8%, wrong aggregation 2%, execution error 2%; place errors "
      "are worst in Tamil. <b>Caveat:</b> 376 of 384 test questions use question types that also appear in training (with "
      "other places, years and wording), so retrieved examples benefit from the template structure; the keyword baseline "
      "has the same advantage and is still beaten by 39 points."),
    p("Main files to show", H2),
    table([["File", "What to point at"],
           [code("src/ingestion/ingres_api.py"), "IngresClient.fetch (line 48): one cached request; crawl_year (85): the country->state->district walk"],
           [code("src/ingestion/flatten.py, build_db.py"), "flatten (44): nested JSON to long table; build (101): creates the 9 SQLite tables"],
           [code("src/normalization/crosswalk.py"), "crosswalk (72): the 4-stage matcher; _mutual_best (56): guarded fuzzy matching"],
           [code("src/utils/safe_sql.py"), "_authorizer (36): allow-list; execute (50): timeout + row cap"],
           [code("src/pipeline/agent.py"), "Pipeline.sql (122): prompt + repair loop; Pipeline.answer (151)"],
           [code("docs/DATA_ACCESS_REPORT.md"), "the full data audit and reconciliation table"]],
          [6.3 * cm, 10.7 * cm]),
    p("Viva questions and answers", H2)] + qa([
    ("How did you get the data if there is no API?",
     "The portal is a JavaScript app. Its bundle contains the API base URL and the request the site itself makes for "
     "non-logged-in visitors. We call that same public endpoint with plain HTTPS POST requests, slowly and sequentially, "
     "and keep every raw response so the dataset can be rebuilt without re-crawling."),
    ("How do you know your database is correct?",
     "We recompute national totals and compare them with the figures the government published (PIB releases): they match "
     "within 0.07% for four cycles, and an automated test checks this. District sums also equal state values in 100% of cases."),
    ("Why did you exclude 2016-17?",
     "Four states were missing and national totals came out about twice the published values, so the data from the API "
     "for that cycle is unreliable. Including it would make every cross-year answer wrong."),
    ("Why do you need a crosswalk?",
     "INGRES gives units new IDs in some cycles; only 14% of unit IDs survive from 2019-20 to 2021-22. Without linking, "
     "a question like 'which blocks moved from Critical to Over-Exploited' would silently miss most units."),
    ("Can a user delete or change data through a question?",
     "No. The connection is read-only at the database level and an authorizer callback rejects anything other than reading. "
     "This is enforced by SQLite itself, not by inspecting the query text, and is covered by 13 tests."),
    ("What does the repair loop do and is it safe?",
     "If the model's SQL fails or returns nothing, we send the error back and ask for a fix, at most twice. It only ever "
     "produces more read-only queries, so the safety layer still applies."),
    ("Which component mattered most in the final system?",
     "Retrieved examples: removing them drops test accuracy from 71.9% to 35.4%. Place hints add 4.4 points (p = 0.019) "
     "and the repair loop 1.6 points (it fixed 6 questions and broke none). Schema hints added 5.2 points over zero-shot."),
    ("Isn't 71.9% inflated because test questions resemble training questions?",
     "Partly, and we say so. Test question types also occur in training, with different places, years and wording, so "
     "retrieved examples are structurally similar. The keyword baseline has the same advantage and scores 32.6%; and "
     "hard_test, with noise and more complex questions, still reaches 57.7%. A leave-intents-out run is the planned check."),
    ("Why SQLite and not PostgreSQL/MySQL?",
     "The data is 22 MB and read-only; SQLite needs no server, ships as one file that teammates can copy, and its authorizer "
     "hook gives fine-grained read-only control.")]) + [PageBreak()]

# ---------------------------------------------------------------------------- ARYAN
story += [p("4. Aryan: benchmark, evaluation, baselines", H1), p("What was built", H2)] + bullets([
    "<b>INGRES-Bench v1 (Phase 3):</b> 371 questions x 4 languages (English, Hindi, Hinglish, Tamil) = 1,484 instances, "
    "each with gold SQL and the gold result from the real database; 38 question types (intents) over 4 difficulty levels.",
    "<b>Quality control</b> with 7 automatic checks and a mutation test.",
    "<b>Execution-accuracy evaluator</b> with bootstrap confidence intervals and per-language/difficulty breakdowns.",
    "<b>Baselines (Phase 4):</b> keyword/template retrieval, BM25 and multilingual-embedding schema retrieval, and the "
    "local LLM (qwen3:8b) with a compact schema prompt."]) + [
    p("How and why", H2),
    p("Building the benchmark", H3),
    p("<b>How:</b> each intent is an SQL template with slots (place, year, metric, category, threshold) plus at least 3 "
      "phrasings per language. A sampler draws real places and years from the database, the SQL is executed, and the item is "
      "kept only if the result is well-formed (non-empty, not NULL, at most 20 rows, exactly the intended unit). All four "
      "language versions are generated from the <b>same slots</b>, so they have identical SQL by construction. Places are "
      "mentioned with just enough context to be unambiguous (name, name + state, or name + district + state)."),
    p("<b>Why:</b> no Text-to-SQL benchmark existed for Indian languages over Indian government data. Slot-aligned "
      "generation means a translation cannot change what the question asks. Difficulty levels: simple lookup (107 items), "
      "filtered aggregate (120), cross-year (80), multi-hop (64)."),
    p("Preventing leakage", H3),
    p("<b>How:</b> splits are by item, so all four languages of a question are in the same split (train 153 / dev 57 / "
      "test 96 / hard_test 65 items). Places are partitioned so test places are mostly unseen in training, and the last "
      "phrasing of every intent is held out of train/dev. hard_test adds noise to 201/260 instances (typos, real historical "
      "respellings, Latin names inside Hindi/Tamil, lowercase, numbers written as words). <b>Why:</b> otherwise a system could "
      "score well by memorising the Hindi version of a question it saw in English."),
    p("Quality control", H3),
    p("<b>How:</b> 7 checks on all 1,484 instances (SQL executes, result reproduces, schema-valid, every SQL literal appears "
      "in the question, cross-language consistency, no split leakage, held-out phrasings): 0 failures. A mutation test "
      "corrupted 2,011 questions (replacing year, place or category); the slot checker caught 97.1%. 546 transliterated "
      "place names were back-transliterated: 543 pass, 3 flagged and judged correct. <b>Why:</b> generated benchmarks can "
      "contain silent errors; the mutation test proves the checker actually detects them."),
    p("Evaluation metric", H3),
    p("<b>How:</b> " + code("execution_match") + " runs predicted and gold SQL and compares results as multisets of rows "
      "(order matters only if the gold SQL has ORDER BY), numbers equal within relative tolerance 1e-6. Errors and refused "
      "SQL count as wrong. 95% confidence intervals by bootstrap; paired comparisons by McNemar's test. "
      "<b>Why:</b> many different SQL strings are correct, so comparing strings would under-count; comparing results "
      "is the standard (Spider/BIRD) way."),
    p("Baselines", H3),
    p("<b>Keyword/template (A):</b> find the most similar training question (character n-gram TF-IDF), reuse its SQL, and "
      "re-fill years, categories, numbers, metric and place names by rules. EX 38.8% overall, 32.6% on test. "
      "<b>LLM (D):</b> qwen3:8b via Ollama, temperature 0. The full schema (~9k tokens) overflowed the 8k context, so we wrote "
      "a compact schema prompt plus explicit conventions (year labels, spellings, join path). EX 18.2%. "
      "<b>Schema retrieval:</b> BM25 recall@3 0.267 (collapses to 0.009 on Hindi and Tamil script), off-the-shelf "
      "multilingual embeddings 0.409."),
    p("<b>Why baselines matter:</b> they define what 'improvement' means. A surprising but honest finding is that the "
      "simple template baseline beats the 8B LLM, because the benchmark is template-based and the LLM makes systematic "
      "convention errors; the later components target exactly those errors."),
    p("<b>Why a local model and not Gemini/ChatGPT:</b> the Gemini free tier allowed 20 requests per day (logged), and one "
      "evaluation pass is 872 requests. A local model is free, private and reproducible (fixed seed, cached responses)."),
    p("Main files to show", H2),
    table([["File", "What to point at"],
           [code("src/benchmark/intents.py"), "INTENTS list: SQL template + phrasings in 4 languages for each question type"],
           [code("src/benchmark/build.py"), "Builder.sample (131): draws real slots; render (236): writes each language version"],
           [code("scripts/qc_benchmark.py"), "the 7 QC checks and the mutation test"],
           [code("src/evaluation/execution.py"), "execution_match (67), results_match (37): the metric"],
           [code("src/evaluation/report.py"), "bootstrap_ci (34): confidence intervals"],
           [code("src/baselines/keyword.py"), "KeywordBaseline.predict (162): retrieve and re-fill"],
           [code("src/baselines/llm.py"), "OllamaClient.generate (134): cached LLM call; compact_schema_prompt (176); CONVENTIONS (221)"],
           [code("docs/INGRES_BENCH.md, docs/BASELINES.md"), "benchmark protocol and baseline results"]],
          [6.3 * cm, 10.7 * cm]),
    p("Viva questions and answers", H2)] + qa([
    ("An AI helped write your questions. Is the benchmark valid?",
     "The SQL and answers come from the real database, and all 4 language versions share the same slots, so the meaning "
     "cannot drift. QC found 0 failures and the checker catches 97% of deliberately corrupted questions. The honest "
     "limitation is that wording is template-like and no native speaker has verified the Hindi/Tamil yet; that check is planned."),
    ("Why execution accuracy and not exact SQL match?",
     "The same answer can be written as many different SQL queries (different aliases, join orders). Comparing the "
     "results is fairer and is the standard metric in Spider and BIRD."),
    ("Why is your keyword baseline better than the LLM?",
     "Because questions come from templates, copying the most similar training question's SQL works well. The 8B model, "
     "with no examples, makes convention errors (e.g. treating 'the 2023 assessment' as 2023-2024). It is a known "
     "limitation of template benchmarks, and it is why the pipeline adds retrieved examples and hints."),
    ("How do you stop the model seeing test questions during training?",
     "Splits are by item, test places are mostly unseen, and one phrasing per question type is held out. QC verifies that "
     "no SQL or question text appears in two splits."),
    ("What is hard_test?",
     "A harder split: more cross-year and multi-hop questions, ambiguous place names, and noise such as typos and Latin names "
     "inside Hindi/Tamil sentences. Baseline D drops from 18.0% (test) to 13.1% on it."),
    ("Why Tamil as the Dravidian language?",
     "Tamil Nadu is data-rich in INGRES, the script is different from both Devanagari and Latin (useful for the tokenizer "
     "study), and open-source support for Tamil is good."),
    ("What does a 95% confidence interval mean here?",
     "We resample the questions 2,000 times and recompute accuracy; 95% of those values fall in the interval. It shows how "
     "much the number could change with a different sample of questions.")]) + [PageBreak()]

# ---------------------------------------------------------------------------- AKSHIT
story += [p("5. Akshit: learned schema linking and entity resolution", H1), p("What was built", H2)] + bullets([
    "<b>Schema linker (Phase 5):</b> multilingual-e5-small (118M parameters) fine-tuned to rank the 106 database columns "
    "for a question in any of the 4 languages.",
    "<b>Geographic entity resolver (Phase 6):</b> maps any spelling or script of a place name to the exact INGRES entry "
    "among 9,558 places.",
    "<b>Place linker:</b> finds place names inside a full question and resolves them (used by the pipeline)."]) + [
    p("How and why", H2),
    p("Schema linking", H3),
    p("<b>Why:</b> the schema is in English ('stage_of_extraction_pct'); a Tamil question shares no words with it. BM25 "
      "scored 0.009 recall@3 on Hindi and Tamil. Off-the-shelf multilingual embeddings reached 0.409 overall but only 0.276 on "
      "Tamil. The LLM picking the wrong column was one of its most common errors."),
    p("<b>How:</b> a bi-encoder: question and column description are embedded separately and ranked by cosine similarity. "
      "Training uses contrastive learning (InfoNCE / multiple-negatives ranking loss): for each (question, correct column) "
      "pair the model is pushed to score the correct column above the others in the batch. The key idea is <b>hard "
      "negatives</b>: for each pair we add 3 columns that are easy to confuse: semantically close ones (recharge vs "
      "extractable resource; extraction vs stage of extraction) and <b>the same column at another administrative level</b> "
      "(unit vs district vs state table). 712 training pairs, 3 epochs, batch 16, lr 2e-5, 386 s on CPU."),
    p("<b>Result:</b> column recall@3 0.409 -> 0.896 (English 0.954, Hindi 0.913, Hinglish 0.872, Tamil 0.846); "
      "recall@1 0.221 -> 0.710. <b>Generalisation test:</b> retraining with 25% of question types removed and testing only on "
      "those gives 0.851 (3 seeds, 0.75-0.91), so it did not just memorise question types. In the LLM prompt, its top-5 "
      "columns raised end-to-end accuracy from 18.0% to 23.2% (p = 0.008)."),
    p("Entity resolution", H3),
    p("<b>Why:</b> 169 unit names are shared across different states, INGRES spellings are unusual ('TAMILNADU', Himachal "
      "district codes like 'KNG'), and users write names in Devanagari or Tamil, with typos or old names."),
    p("<b>How:</b> (1) a gazetteer of 9,558 places with aliases; (2) normalisation: Devanagari/Tamil are romanised, then "
      "'phonetically folded' (aa->a, sh->s, w->v, doubled letters removed) and a consonant skeleton is kept, because vowels vary "
      "most across transliterations; (3) candidates by character n-gram TF-IDF (top 30); (4) a logistic-regression ranker over "
      "12 features: string similarities, e5 embedding similarity, and <b>hierarchy context</b> (is the candidate's state or "
      "district mentioned elsewhere in the question? does it conflict?). It was trained only on synthetic noisy mentions "
      "(typos, transliteration variants, script changes) of 70% of places and tested on the other 30%."),
    p("<b>Result (top-1):</b> held-out synthetic noise 0.841 -> 0.885 with context; hand-written Hindi/Tamil names 0.674 -> "
      "0.740; real historical INGRES respellings 0.623 -> 0.754; <b>ambiguous names 0.447 -> 0.973</b> with context. "
      "Weakest: hand-written Tamil (0.65), because Tamil script does not mark voicing or aspiration."),
    p("<b>Why logistic regression and not a big model:</b> 12 interpretable features, trains in minutes, and the learned "
      "weights can be explained (edit similarity +21.5, embedding similarity +10.6, state conflict -8.8)."),
    p("Place linker", H3),
    p("<b>How:</b> scan every 1-3 word span of the question, resolve it, keep confident (score >= 0.9) non-overlapping "
      "matches, then re-resolve with the detected state as context. Spans made only of common question words are skipped. "
      "<b>Bug found and fixed:</b> the first version treated frequent state names (Punjab, Karnataka) as common words "
      "(F1 0.56); a word is now skipped only if it is frequent and not tied to one place. Dev F1 0.852 (precision 0.906, "
      "recall 0.804)."),
    p("Main files to show", H2),
    table([["File", "What to point at"],
           [code("src/schema_linking/train.py"), "hard_negatives (31): the confusable columns; train (69): the contrastive loop (InfoNCE loss)"],
           [code("src/schema_linking/retrieval.py"), "EmbeddingRetriever (100): ranking; rank_metrics: recall@k, MRR"],
           [code("src/entity_resolution/gazetteer.py"), "fold (42): phonetic folding; build_gazetteer (72)"],
           [code("src/entity_resolution/resolver.py"), "features (57): the 12 features; resolve (86); fit (101): training the ranker"],
           [code("src/pipeline/agent.py"), "PlaceLinker.link (51): finding places in a question"],
           [code("scripts/train_schema_linker.py, train_entity_resolver.py"), "training + evaluation entry points"],
           [code("docs/SCHEMA_LINKING.md, ENTITY_RESOLUTION.md"), "methods and full results"]],
          [6.3 * cm, 10.7 * cm]),
    p("Viva questions and answers", H2)] + qa([
    ("What is a hard negative and why does it help?",
     "A wrong answer that looks very similar to the right one. Random wrong columns are easy to reject and teach little. "
     "Training against 'extraction' vs 'stage of extraction', or the same column in the district table instead of the "
     "unit table, forces the model to learn the distinctions that matter."),
    ("Didn't the model just memorise the question templates?",
     "We tested that: we removed 25% of question types from training and evaluated only on them. Recall@3 was 0.851 "
     "versus 0.454 for the untrained model, so most of the gain transfers to unseen question types."),
    ("What is recall@3?",
     "Of the columns the correct SQL needs, the share that appear among the linker's top 3 suggestions."),
    ("Why fine-tune a small model instead of using a large one?",
     "It has to run for every question in milliseconds (3.8 ms per query) and train on a CPU in minutes. Fine-tuned, the "
     "small model reaches 0.896, which is enough to measurably improve the LLM."),
    ("How do you tell apart two places with the same name?",
     "Hierarchy context. If the question also mentions the state or district, candidates in that state get a strong "
     "boost and conflicting ones a strong penalty. Accuracy on ambiguous names goes from 0.45 to 0.97."),
    ("Why is Tamil the hardest?",
     "Tamil script uses one letter for sounds that are distinct in Hindi/English (k/g, t/d, aspirated or not), so a "
     "romanised Tamil name can differ a lot from the INGRES spelling."),
    ("Why train on synthetic noise?",
     "There is no labelled dataset of misspelled Indian place names. We generate realistic noise (typos, transliteration "
     "variants, script changes) for 70% of places and test on the unseen 30%, plus on real data: hand-written names and 445 "
     "real historical respellings from INGRES itself.")]) + [PageBreak()]

# ---------------------------------------------------------------------------- WAIE
story += [p("6. Waie: multilingual analysis, answer trust, user interface", H1), p("What was built", H2)] + bullets([
    "<b>Tokenization and code-mixing study (Phase 7)</b> with a placebo control, plus three mitigation experiments.",
    "<b>Numeric grounding verifier (Phase 8)</b> that checks every number in an answer against the SQL result.",
    "<b>Streamlit UI (Phase 10)</b>, tested end to end with screenshots; the mid-term report and slides."]) + [
    p("How and why", H2),
    p("Tokenization study", H3),
    p("<b>Why:</b> a common explanation for weaker performance on Indian languages is that tokenizers split their words into "
      "many pieces. We tested whether that explains our accuracy gap."),
    p("<b>How:</b> for 5 tokenizers (Qwen3 = our LLM, XLM-R = our schema linker, mBERT, MuRIL, GPT-4o) and all 1,484 "
      "questions we measured <b>fertility</b> (tokens per word) and the share of words split into pieces. Code-mixing was "
      "measured with the Code-Mixing Index (CMI), using word-level language tags. Then we correlated fertility with "
      "accuracy, within the same question across its 4 languages, and with a <b>placebo</b>: the keyword baseline, "
      "which uses no subword tokenizer at all, so fertility cannot affect it."),
    p("<b>Results:</b> Qwen3 fertility English 2.04, Hindi 5.01, Hinglish 2.25, Tamil 8.96: a Tamil question costs ~111 tokens "
      "vs 28 in English. MuRIL (Indian-language model) is nearly flat (1.38-1.67). Hinglish CMI 33.0, 96% of Hinglish "
      "questions mixed. Fertility vs LLM accuracy: rho = -0.09; but the <b>placebo correlation is stronger (-0.18)</b>. "
      "Conclusion: the correlation reflects language and question difficulty, not fragmentation itself."),
    p("<b>Mitigations:</b> translate to English first: 16.4% vs 18.2% direct (no help; the 8B model mistranslated domain terms, "
      "e.g. 'ati-dohit' (over-exploited) became 'extremely undernourished'). Vocabulary adaptation (78 whole-word tokens added "
      "to the schema linker): Tamil fragmentation 0.63 -> 0.43, but recall unchanged (0.896 -> 0.897). What did help: "
      "schema-linker hints, +5.2 points (36 wins vs 16 losses, McNemar p = 0.008)."),
    p("Numeric verifier", H3),
    p("<b>Why:</b> the LLM writes the final sentence and could invent or mis-scale a number; for official water data a "
      "fluent wrong number is worse than no answer."),
    p("<b>How:</b> all numbers in the answer are extracted after normalising Devanagari and Tamil digits, Indian grouping "
      "(1,23,456) and lakh/crore words. Each must match a value in the SQL result, allowing for the precision it is written "
      "with and unit conversions (hectare-metres <-> BCM, fraction <-> percent), the row count, list positions and numbers in "
      "the question. Years are exempt. If any number fails, the answer falls back to a plain rendering of the table."),
    p("<b>Results (384 test questions):</b> LLM answers with an unsupported number: 0.83% (2/242); both checked by hand and "
      "both real errors ('8 blocks' for a 7-row result; '82.69%' for a true 8.27%). Planted errors caught: 98.1% (211/215; "
      "the 4 misses became 1900-2099 values, treated as years). False alarms: 0%. After the fallback: 0% unsupported numbers. "
      "The evaluation also found two bugs in the verifier (SQL-expression column headers; lakh precision), fixed with tests."),
    p("User interface", H3),
    p("<b>How:</b> a Streamlit page: question box with examples in all 4 languages; shows the answer, a warning if the "
      "verifier replaced the model's wording, the SQL, the result table, and a 'How it got there' panel (schema hints, "
      "resolved places, repair attempts, latency). <b>Why:</b> showing the SQL and table lets a user check the answer instead "
      "of trusting it blindly. Tested end to end: a Hindi question about Ludhiana returned the correct SQL and a Hindi answer "
      "(240,136.75 ham). Screenshots: " + code("reports/screenshots/") + "."),
    p("Main files to show", H2),
    table([["File", "What to point at"],
           [code("src/tokenization/metrics.py"), "tokenizer_stats (34): fertility; LanguageTagger.cmi (91): code-mixing index"],
           [code("scripts/run_tokenization_study.py"), "within-item correlation and the placebo analysis"],
           [code("src/tokenization/mitigation.py"), "translate (22); select_new_tokens (29); adapt_vocabulary (42)"],
           [code("src/grounding/verifier.py"), "numbers (24): Indic digits + lakh; verify (59); grounded_answer (98): fallback"],
           [code("scripts/run_grounding.py"), "the perturbation test and false-alarm checks"],
           [code("app/streamlit_app.py"), "the UI"],
           [code("docs/TOKENIZATION.md, docs/GROUNDING.md"), "methods and full results"]],
          [6.3 * cm, 10.7 * cm]),
    p("Viva questions and answers", H2)] + qa([
    ("What is fertility and why measure it?",
     "The average number of tokens a tokenizer uses per word. High fertility means words are chopped into many pieces, "
     "which costs context, time and possibly accuracy. Qwen3 uses ~9 tokens per Tamil word vs 2 per English word."),
    ("What is a placebo control here?",
     "A variable that should not be affected. The keyword baseline uses no subword tokenizer, so tokenizer fertility "
     "cannot cause its errors. It still correlated with fertility, even more strongly, which shows the original correlation "
     "is caused by something else: harder languages and items."),
    ("So does tokenization not matter at all?",
     "It matters for cost and speed (Tamil prompts are ~4x longer). For accuracy, in our system, it was not the bottleneck: "
     "reducing fragmentation did not raise accuracy, while better schema linking did."),
    ("Why did translating to English first make things worse?",
     "The 8B model translated technical terms into everyday meanings, e.g. 'critical' became 'severe' and 'stage of extraction' "
     "became 'attendance level', and occasionally dropped place names. The original terms were more useful to the SQL model."),
    ("What is code-mixing and how did you measure it?",
     "Using two languages in one sentence, like Hinglish. Each word is tagged by language; the Code-Mixing Index is 0 for a "
     "single language and rises as languages mix. Hinglish averaged 33."),
    ("What does your verifier not catch?",
     "It checks that a number exists in the result, not that it is attached to the right place, and it skips years and "
     "numbers written as words. Small counts can match a list position by chance."),
    ("Why fall back to a table instead of asking the LLM again?",
     "The table rendering is correct by construction and costs nothing; asking again could produce another error.")]) + [PageBreak()]

# ---------------------------------------------------------------------------- COMMON
story += [p("7. Questions any member may be asked", H1)] + qa([
    ("Explain the project in two sentences.",
     "People ask about groundwater in Hindi, Hinglish or Tamil, but the official portal is an English click-through map. We "
     "built the database, a 4-language benchmark and a pipeline that turns such questions into safe SQL with verified "
     "answers, and measured which components actually help."),
    ("What is novel?",
     "A Text-to-SQL benchmark over Indian government data in 4 languages; a schema linker trained with domain and "
     "administrative-level hard negatives; a place resolver using the administrative hierarchy; a placebo-controlled "
     "tokenization study; and a numeric verifier for Indian number formats."),
    ("Why not just use ChatGPT?",
     "Cost and quota (one evaluation is 872 calls; the free Gemini tier allows 20 per day), reproducibility (a local model "
     "with temperature 0 gives identical results), privacy, and a general chatbot does not know INGRES spellings, year "
     "conventions or units. A paid frontier-model comparison is planned as future work."),
    ("What hardware did you use?",
     "An NVIDIA RTX 5060 (8 GB) ran the LLM (qwen3:8b, 4-bit) through Ollama: about 3,700 calls, ~2.1 GPU-hours, ~2.5 s per "
     "question. Our own models (118M-parameter encoder, logistic regression) were trained on the CPU (Ryzen 7 9700X) in about "
     "6 minutes each, because they are small and the installed PyTorch build is CPU-only."),
    ("What is the biggest weakness?",
     "Most of the gain comes from retrieved examples, and test question types also appear in training, so accuracy on truly "
     "new question types is probably below 71.9%. The Hindi/Tamil questions have not been verified by native speakers, and "
     "Tamil place names remain the biggest single error source."),
    ("How do you make sure your numbers are not made up?",
     "Every reported number is written by a script into a results file in the repository; responses from the LLM are cached, "
     "so anyone can rerun and get the same numbers; 61 automated tests cover the data, safety, metrics and verifier."),
    ("What would you do next?",
     "A leave-intents-out evaluation; better Tamil place resolution (41% of errors are place misses); a deterministic year "
     "normaliser (13% of errors); native-speaker review of a sample; a frontier-model comparison; re-timing training on the GPU.")])

story += [Spacer(1, 10), p("8. Glossary", H1),
          table([["Term", "Meaning"],
                 ["EX (execution accuracy)", "share of questions whose predicted SQL returns the same result as the gold SQL"],
                 ["Recall@3", "share of the needed columns that appear in the schema linker's top 3"],
                 ["Fertility", "subword tokens per word"],
                 ["CMI", "Code-Mixing Index: 0 = one language; higher = more mixing"],
                 ["ham / BCM", "hectare-metre / billion cubic metres; 1 BCM = 100,000 ham"],
                 ["Stage of extraction", "annual extraction / extractable resource x 100; above 100% = Over-Exploited"],
                 ["GWRA / GEC-2015", "Ground Water Resource Assessment cycle / the official methodology"],
                 ["McNemar test", "paired significance test counting questions one system gets right and the other wrong"],
                 ["Contrastive learning (InfoNCE)", "training that pulls matching pairs together and pushes non-matching apart"],
                 ["Ablation", "switching one component off to measure its contribution"]],
                [5 * cm, 12 * cm])]


def footer(c, d):
    c.saveState()
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.grey)
    c.drawString(2 * cm, 1.1 * cm, "INGRES-Text2SQL: division of work and viva preparation")
    c.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Page {d.page}")
    c.restoreState()


SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.7 * cm, bottomMargin=1.8 * cm,
                  title="INGRES-Text2SQL: Division of Work and Viva Preparation").build(story, onFirstPage=footer,
                                                                                       onLaterPages=footer)
print(OUT)
