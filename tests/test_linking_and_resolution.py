import random

from src.entity_resolution.gazetteer import Entity, fold, skeleton
from src.entity_resolution.resolver import Resolver, typo
from src.schema_linking.train import hard_negatives


def test_fold_is_transliteration_robust():
    from difflib import SequenceMatcher
    assert fold("Ludhiana") == fold("LUDHIYAANA")
    assert skeleton("Sonkatch") == skeleton("Sonkutch")      # vowel-only respelling
    # Devanagari is romanised; not identical ('pamjab' vs 'punjab': anusvara -> m, vowel a vs u) but close
    assert SequenceMatcher(None, fold("पंजाब"), fold("Punjab")).ratio() >= 0.66


def test_hard_negatives_are_adjacent_not_random():
    keys = ["unit_assessments.annual_recharge_ham", "unit_assessments.extractable_resource_ham",
            "district_assessments.annual_recharge_ham", "state_assessments.annual_recharge_ham",
            "unit_assessments.category", "states.state_name"]
    neg = hard_negatives("unit_assessments.annual_recharge_ham", keys, {"unit_assessments.annual_recharge_ham"}, 3,
                         random.Random(0))
    assert set(neg) == {"unit_assessments.extractable_resource_ham", "district_assessments.annual_recharge_ham",
                        "state_assessments.annual_recharge_ham"}


def test_resolver_uses_state_context_for_homonyms():
    gaz = [Entity("s1", "state", "BIHAR", "Bihar", "BIHAR", None), Entity("s2", "state", "ASSAM", "Assam", "ASSAM", None),
           Entity("u1", "unit", "RAMPUR", "Rampur", "BIHAR", "KAIMUR"), Entity("u2", "unit", "RAMPUR", "Rampur", "ASSAM", "KAMRUP")]
    for e in gaz:
        e.aliases |= {e.db_name, e.display}
    r = Resolver(gaz)
    mentions = [("Rampur", 2, {"states": {"BIHAR"}}), ("Rampur", 3, {"states": {"ASSAM"}}),
                ("Rampr", 2, {"states": {"BIHAR"}}), ("Ramppur", 3, {"states": {"ASSAM"}}), ("Bihar", 0, None), ("Assam", 1, None)]
    r.fit(mentions * 5)
    assert r.resolve("rampur", {"states": {"ASSAM"}})[0][0].entity_id == "u2"
    assert r.resolve("Rampur", {"states": {"BIHAR"}})[0][0].entity_id == "u1"


def test_typo_changes_name():
    rng = random.Random(1)
    assert all(typo("Ludhiana", rng) != "Ludhiana" for _ in range(30))
