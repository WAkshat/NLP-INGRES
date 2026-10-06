"""Train + evaluate the geographic entity resolver (Phase 6).

    python scripts/train_entity_resolver.py

Entities are partitioned 70/30 (seeded). The ranker is trained ONLY on synthetic noisy mentions of the 70% part.
Evaluation sets:
  synthetic  : held-out 30% entities x noise type (exact, lowercase, typo, transliteration variant, punctuation/space,
               automatic Devanagari / Tamil script), with and without hierarchy context
  hand_script: the 273 benchmark place names written in Devanagari and Tamil by hand (never used in training)
  historical : 445 real INGRES respellings across cycles (old name -> canonical location); history aliases removed
  ambiguous  : unit names shared by units in different states, without vs with state context
  colloquial : renamed / colloquial names (Gurgaon -> Gurugram), without vs with the curated alias table
Writes experiments/entity_resolution/{results.json, per_mention.csv, errors_sample.csv}.
"""
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.entity_resolution.gazetteer import COLLOQUIAL, build_gazetteer, fold  # noqa: E402
from src.entity_resolution.resolver import NOISE, Resolver  # noqa: E402
from src.evaluation.report import bootstrap_ci  # noqa: E402
from src.utils.safe_sql import connect_ro  # noqa: E402

OUT = ROOT / "experiments/entity_resolution"
SEED = 0


def main():
    t0 = time.time()
    from sentence_transformers import SentenceTransformer
    emb = SentenceTransformer("intfloat/multilingual-e5-small", device="cpu")
    con = connect_ro(ROOT / "data/processed/ingres.db")
    rng = random.Random(SEED)
    gaz = build_gazetteer(con, include_colloquial=False)
    idx = {(e.level, e.entity_id): i for i, e in enumerate(gaz)}
    by_db = defaultdict(list)
    for i, e in enumerate(gaz):
        by_db[e.db_name.lower()].append(i)
    ids = list(range(len(gaz)))
    rng.shuffle(ids)
    train_ids = set(ids[: int(0.7 * len(ids))])
    print(f"gazetteer: {len(gaz)} entities; building resolver index ...", flush=True)
    res = Resolver(gaz, embedder=emb, seed=SEED)

    def ctx_for(e, with_ctx):
        if not with_ctx or e.level == "state":
            return None
        return {"states": {e.state}, "districts": {e.district} if e.level == "unit" and rng.random() < 0.5 else set()}

    # ---------------- training mentions (train partition only; sample units to keep it fast)
    train_mentions = []
    tr = [i for i in train_ids if gaz[i].level != "unit"] + rng.sample([i for i in train_ids if gaz[i].level == "unit"], 2500)
    for i in tr:
        e = gaz[i]
        for noise in ("exact", "typo", "translit_variant", "punct_space", "auto_devanagari", "auto_tamil", "lowercase"):
            if noise in ("auto_devanagari", "auto_tamil") and rng.random() < 0.5:
                continue
            train_mentions.append((NOISE[noise](e.display, rng), i, ctx_for(e, rng.random() < 0.6)))
    print(f"training ranker on {len(train_mentions)} mentions ...", flush=True)
    coefs = res.fit(train_mentions)

    recs = []

    def run(evalset, mention, gold_i, ctx, **meta):
        out = res.resolve(mention, ctx)
        ranks = [k for k, (e, _) in enumerate(out) if (e.level, e.entity_id) == (gaz[gold_i].level, gaz[gold_i].entity_id)]
        recs.append({"set": evalset, "mention": mention, "gold": gaz[gold_i].db_name, "gold_level": gaz[gold_i].level,
                     "gold_state": gaz[gold_i].state, "pred": out[0][0].db_name if out else None,
                     "pred_state": out[0][0].state if out else None, "pred_level": out[0][0].level if out else None,
                     "top1": int(bool(ranks) and ranks[0] == 0), "top3": int(bool(ranks) and ranks[0] < 3), **meta})

    # ---------------- synthetic, held-out entities
    ev = [i for i in ids if i not in train_ids]
    ev = [i for i in ev if gaz[i].level != "unit"] + rng.sample([i for i in ev if gaz[i].level == "unit"], 600)
    for i in ev:
        for noise in ("exact", "lowercase", "typo", "translit_variant", "punct_space", "auto_devanagari", "auto_tamil"):
            m = NOISE[noise](gaz[i].display, rng)
            for with_ctx in (False, True):
                run("synthetic", m, i, ctx_for(gaz[i], with_ctx), noise=noise, context=with_ctx)
    # ---------------- hand-written Devanagari / Tamil (benchmark pool names)
    tr_names = json.loads((ROOT / "data/benchmark/transliterations.json").read_text(encoding="utf-8"))
    pool = pd.read_csv(ROOT / "data/benchmark/entity_pool.csv")
    disp2gold = {}
    for r in pool.itertuples():
        disp2gold.setdefault(r.unit_display, ("unit", r.unit_id))
        disp2gold.setdefault(r.district_display, ("district", r.district_id))
        disp2gold.setdefault(r.state_display, ("state", r.state_id))
    for disp, forms in tr_names.items():
        if disp.startswith("_") or disp not in disp2gold or disp2gold[disp] not in idx:
            continue
        gi = idx[disp2gold[disp]]
        for lang in ("hi", "ta"):
            for with_ctx in (False, True):
                run("hand_script", forms[lang], gi, ctx_for(gaz[gi], with_ctx), noise=f"hand_{lang}", context=with_ctx)
    # ---------------- historical INGRES respellings (real-world noise)
    ren = pd.read_csv(ROOT / "reports/crosswalk_renames.csv")
    for r in ren.itertuples():
        key = (r.level, r.canonical_id)
        if key in idx and fold(str(r.name_in_year)) != fold(gaz[idx[key]].display):
            gi = idx[key]
            for with_ctx in (False, True):
                run("historical", str(r.name_in_year).replace("_", " "), gi, ctx_for(gaz[gi], with_ctx),
                    noise=f"history_{r.match_method}", context=with_ctx)
    # ---------------- ambiguous names (shared across states)
    amb = [v for v in by_db.values() if len({gaz[i].state for i in v}) >= 2 and all(gaz[i].level == "unit" for i in v)]
    for group in rng.sample(amb, min(150, len(amb))):
        gi = rng.choice(group)
        for with_ctx in (False, True):
            run("ambiguous", gaz[gi].display, gi, ctx_for(gaz[gi], with_ctx), noise=f"shared_by_{len(group)}", context=with_ctx)
    # ---------------- colloquial / renamed
    res_alias = Resolver(build_gazetteer(con, include_colloquial=True), embedder=emb, seed=SEED)
    res_alias.ranker = res.ranker
    for alias, target in COLLOQUIAL.items():
        cands = [i for i in by_db.get(target.lower(), []) if gaz[i].level in ("district", "state")]
        if not cands:
            continue
        gi = cands[0]
        run("colloquial", alias, gi, None, noise="no_alias_table", context=False)
        out = res_alias.resolve(alias)
        ok = out and (out[0][0].level, out[0][0].entity_id) == (gaz[gi].level, gaz[gi].entity_id)
        recs.append({"set": "colloquial", "mention": alias, "gold": gaz[gi].db_name, "gold_level": gaz[gi].level,
                     "pred": out[0][0].db_name if out else None, "top1": int(bool(ok)),
                     "top3": int(any((e.level, e.entity_id) == (gaz[gi].level, gaz[gi].entity_id) for e, _ in out[:3])),
                     "noise": "with_alias_table", "context": False})

    df = pd.DataFrame(recs)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "per_mention.csv", index=False)
    summary = {}
    for (s, n, c), g in df.groupby(["set", "noise", "context"], dropna=False):
        lo, hi = bootstrap_ci(g.top1)
        summary.setdefault(s, []).append({"noise": n, "context": bool(c), "n": len(g), "top1": round(g.top1.mean(), 4),
                                          "top1_ci95": [round(lo, 4), round(hi, 4)], "top3": round(g.top3.mean(), 4)})
    overall = {s: {"top1": round(g.top1.mean(), 4), "top3": round(g.top3.mean(), 4), "n": len(g)} for s, g in df.groupby("set")}
    # error analysis: categorise top-1 failures
    err = df[df.top1 == 0].copy()

    def category(r):
        if r.pred is None:
            return "no candidate"
        if fold(str(r.pred)) == fold(str(r.gold)):
            return "right name, wrong place (homonym)"
        if r.get("pred_level") is not None and r.pred_level != r.gold_level:
            return "wrong administrative level"
        if r.get("pred_state") is not None and r.pred_state == r.gold_state:
            return "similar name, same state"
        return "similar name, other state"
    err["error_category"] = err.apply(category, axis=1)
    summary["error_categories"] = err.groupby(["set", "error_category"]).size().unstack(fill_value=0).to_dict(orient="index")
    err.sample(min(60, len(err)), random_state=SEED).to_csv(OUT / "errors_sample.csv", index=False)
    (OUT / "results.json").write_text(json.dumps({"seed": SEED, "gazetteer_entities": len(gaz), "train_entities": len(train_ids),
                                                  "train_mentions": len(train_mentions), "ranker_coefficients": coefs,
                                                  "overall": overall, "detail": summary,
                                                  "runtime_s": round(time.time() - t0, 1)}, indent=1, default=str), encoding="utf-8")
    print(json.dumps(overall, indent=1))
    piv = df[df.set.isin(["synthetic", "hand_script", "historical", "ambiguous"])].pivot_table(
        index=["set", "noise"], columns="context", values="top1", aggfunc="mean").round(3)
    print(piv.to_string())
    print("colloquial:", df[df.set == "colloquial"].groupby("noise").top1.mean().to_dict())
    print("ranker coefficients:", coefs)


if __name__ == "__main__":
    main()
