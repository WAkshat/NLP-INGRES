from src.grounding.verifier import numbers, template_answer, verify

ROWS = [("LUDHIANA", 123456.789, 0.4521)]


def test_numbers_normalises_scripts_and_skips_years():
    assert [v for _, v, _ in numbers("2024-25 में १२३ और ௪௫.௫")] == [123.0, 45.5]
    assert [v for _, v, _ in numbers("1,23,456 ham in 2025")] == [123456.0]
    assert numbers("1.2 lakh ham")[0][1] == 120000.0


def test_supported_values_and_conversions():
    assert verify("Ludhiana extracted 1,23,456.79 ham (1.23 BCM), 45.21%.", ROWS)["grounded"]
    assert verify("about 1.2 lakh ham", ROWS)["grounded"]
    assert verify("लुधियाना में 123456.8 हेक्टेयर मीटर", ROWS)["grounded"]


def test_unsupported_numbers_flagged():
    v = verify("Ludhiana extracted 135,000 ham, 52% of recharge.", ROWS)
    assert v["unsupported"] == ["135,000", "52"]


def test_question_numbers_and_counts_allowed():
    rows = [("A",), ("B",), ("C",)]
    assert verify("3 blocks are above 70%: A, B, C", rows, "Which blocks are above 70%?")["grounded"]
    assert not verify("4 blocks", rows)["grounded"]


def test_template_answer_is_grounded():
    t = template_answer(["unit", "extraction", "share"], ROWS)
    assert verify(t, ROWS)["grounded"]


def test_lakh_precision_below_one_lakh_and_expression_headers():
    assert verify("0.9 lakh ham", [(88788.42,)])["grounded"]
    assert verify("share: 100.0 * a / b = 8.27", [(8.2712,)], columns=["100.0 * a / b"])["grounded"]
