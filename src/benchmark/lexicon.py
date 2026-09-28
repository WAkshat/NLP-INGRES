"""Per-language surface forms for INGRES-Bench slots.

Languages: english (latin), hindi (devanagari), hinglish (latin, romanised Hindi-English code-mixing),
tamil (tamil script). Hindi/Hinglish metric nouns carry grammatical gender (m/f) so templates can agree
({ka} -> का/की, ka/ki; {tha} -> था/थी, tha/thi).

Year convention (documented in docs/INGRES_BENCH.md): "the N assessment" refers to the published GWRA N report,
i.e. assessment_year '(N-1)-N'; '2024-25' / '2024-2025' refer to '2024-2025'. Bare single years are never used as
year slots (too ambiguous between cycles).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

LANGS = ("english", "hindi", "hinglish", "tamil")
SCRIPT = {"english": "latin", "hindi": "devanagari", "hinglish": "latin", "tamil": "tamil"}

# metric column -> {lang: [(surface, gender)]}
METRICS = {
    "stage_of_extraction_pct": {
        "english": [("stage of groundwater extraction", ""), ("stage of extraction", ""), ("groundwater extraction percentage", "")],
        "hindi": [("भूजल दोहन का स्तर", "m"), ("भूजल निष्कर्षण का प्रतिशत", "m")],
        "hinglish": [("groundwater extraction stage", "m"), ("extraction ka stage", "m"), ("stage of extraction", "m")],
        "tamil": [("நிலத்தடி நீர் எடுப்பு நிலை", ""), ("நிலத்தடி நீர் எடுப்பு சதவீதம்", "")]},
    "annual_recharge_ham": {
        "english": [("annual groundwater recharge", ""), ("total annual recharge", ""), ("yearly groundwater recharge", "")],
        "hindi": [("वार्षिक भूजल पुनर्भरण", "m"), ("कुल वार्षिक रिचार्ज", "m")],
        "hinglish": [("annual recharge", "m"), ("saalana groundwater recharge", "m"), ("total recharge", "m")],
        "tamil": [("ஆண்டு நிலத்தடி நீர் செறிவூட்டல்", ""), ("மொத்த ஆண்டு மீள்நிரப்பு", "")]},
    "extractable_resource_ham": {
        "english": [("annual extractable groundwater resource", ""), ("extractable groundwater resource", "")],
        "hindi": [("वार्षिक निष्कर्षण योग्य भूजल संसाधन", "m"), ("निकालने योग्य भूजल", "m")],
        "hinglish": [("extractable groundwater resource", "m"), ("nikalne layak groundwater", "m")],
        "tamil": [("ஆண்டு எடுக்கக்கூடிய நிலத்தடி நீர் வளம்", ""), ("எடுக்கக்கூடிய நிலத்தடி நீர்", "")]},
    "extraction_total_ham": {
        "english": [("total groundwater extraction", ""), ("annual groundwater extraction", ""), ("groundwater draft", "")],
        "hindi": [("कुल भूजल दोहन", "m"), ("वार्षिक भूजल निष्कर्षण", "m")],
        "hinglish": [("total groundwater extraction", "m"), ("kul extraction", "m"), ("groundwater draft", "m")],
        "tamil": [("மொத்த நிலத்தடி நீர் எடுப்பு", ""), ("ஆண்டு நிலத்தடி நீர் உறிஞ்சுதல்", "")]},
    "extraction_irrigation_ham": {
        "english": [("groundwater extraction for irrigation", ""), ("irrigation draft", "")],
        "hindi": [("सिंचाई के लिए भूजल दोहन", "m")],
        "hinglish": [("irrigation ke liye extraction", "m"), ("sinchai ke liye groundwater extraction", "m")],
        "tamil": [("பாசனத்திற்கான நிலத்தடி நீர் எடுப்பு", "")]},
    "extraction_domestic_ham": {
        "english": [("groundwater extraction for domestic use", ""), ("domestic groundwater extraction", "")],
        "hindi": [("घरेलू उपयोग के लिए भूजल दोहन", "m")],
        "hinglish": [("domestic use ke liye extraction", "m"), ("gharelu extraction", "m")],
        "tamil": [("வீட்டு உபயோகத்திற்கான நிலத்தடி நீர் எடுப்பு", "")]},
    "extraction_industrial_ham": {
        "english": [("groundwater extraction for industrial use", ""), ("industrial groundwater extraction", "")],
        "hindi": [("औद्योगिक भूजल दोहन", "m")],
        "hinglish": [("industry ke liye extraction", "m"), ("industrial extraction", "m")],
        "tamil": [("தொழிற்சாலைகளுக்கான நிலத்தடி நீர் எடுப்பு", "")]},
    "natural_discharge_ham": {
        "english": [("total natural discharge", ""), ("natural groundwater discharge", "")],
        "hindi": [("कुल प्राकृतिक निस्सरण", "m")],
        "hinglish": [("natural discharge", "m")],
        "tamil": [("மொத்த இயற்கை வெளியேற்றம்", "")]},
    "future_availability_ham": {
        "english": [("net groundwater availability for future use", ""), ("groundwater available for future use", "")],
        "hindi": [("भविष्य के उपयोग हेतु शुद्ध भूजल उपलब्धता", "f")],
        "hinglish": [("future use ke liye available groundwater", "m"), ("future availability", "f")],
        "tamil": [("எதிர்கால பயன்பாட்டிற்கான நிகர நிலத்தடி நீர் இருப்பு", "")]},
    "recharge_rainfall_ham": {
        "english": [("recharge from rainfall", ""), ("rainfall recharge", "")],
        "hindi": [("वर्षा से होने वाला पुनर्भरण", "m")],
        "hinglish": [("baarish se recharge", "m"), ("rainfall recharge", "m")],
        "tamil": [("மழையால் ஏற்படும் செறிவூட்டல்", "")]},
    "rainfall_mm": {
        "english": [("rainfall", "")],
        "hindi": [("वर्षा", "f")],
        "hinglish": [("baarish", "f"), ("rainfall", "f")],
        "tamil": [("மழையளவு", "")]},
}
UNIT_OF = {"stage_of_extraction_pct": "%", "rainfall_mm": "mm"}  # everything else: ham

CATEGORIES = {
    "Safe": {"english": ["safe"], "hindi": ["सुरक्षित"], "hinglish": ["safe"], "tamil": ["பாதுகாப்பான"]},
    "Semi-Critical": {"english": ["semi-critical"], "hindi": ["अर्ध-गंभीर"], "hinglish": ["semi-critical", "semi critical"],
                      "tamil": ["ஓரளவு அபாயகரமான"]},
    "Critical": {"english": ["critical"], "hindi": ["गंभीर"], "hinglish": ["critical"], "tamil": ["அபாயகரமான"]},
    "Over-Exploited": {"english": ["over-exploited", "overexploited"], "hindi": ["अति-दोहित"],
                       "hinglish": ["over-exploited", "overexploited"], "tamil": ["அதிகப்படியாக சுரண்டப்பட்ட"]},
}

# assessment-unit type words (singular / plural)
UNIT_TYPES = {
    "BLOCK": {"english": ("block", "blocks"), "hindi": ("ब्लॉक", "ब्लॉक"), "hinglish": ("block", "blocks"), "tamil": ("ஒன்றியம்", "ஒன்றியங்கள்")},
    "TALUK": {"english": ("taluk", "taluks"), "hindi": ("तालुका", "तालुके"), "hinglish": ("taluka", "talukas"), "tamil": ("வட்டம்", "வட்டங்கள்")},
    "TEHSIL": {"english": ("tehsil", "tehsils"), "hindi": ("तहसील", "तहसीलें"), "hinglish": ("tehsil", "tehsils"), "tamil": ("தாலுகா", "தாலுகாக்கள்")},
    "MANDAL": {"english": ("mandal", "mandals"), "hindi": ("मंडल", "मंडल"), "hinglish": ("mandal", "mandals"), "tamil": ("மண்டலம்", "மண்டலங்கள்")},
    "FIRKA": {"english": ("firka", "firkas"), "hindi": ("फिरका", "फिरके"), "hinglish": ("firka", "firkas"), "tamil": ("பிர்கா", "பிர்காக்கள்")},
    "_UNIT": {"english": ("assessment unit", "assessment units"), "hindi": ("आकलन इकाई", "आकलन इकाइयाँ"),
              "hinglish": ("assessment unit", "assessment units"), "tamil": ("மதிப்பீட்டு அலகு", "மதிப்பீட்டு அலகுகள்")},
}

YEARS = ["2019-2020", "2021-2022", "2022-2023", "2023-2024", "2024-2025"]


def year_forms(year: str, lang: str) -> tuple[list[str], list[str]]:
    """(adverbial 'in <year>' forms, bare forms) for an assessment_year."""
    a, b = year.split("-")
    short = f"{a}-{b[2:]}"
    if lang == "english":
        return [f"in {short}", f"in the {b} assessment", f"in {year}"], [short, year]
    if lang == "hindi":
        return [f"{short} में", f"{b} के आकलन में", f"वर्ष {short} में"], [short, year]
    if lang == "hinglish":
        return [f"{short} mein", f"{b} ke assessment mein", f"{short} me"], [short, year]
    return [f"{short} இல்", f"{b} மதிப்பீட்டில்", f"{short} ஆம் ஆண்டில்"], [short, year]


class Names:
    """Language-specific rendering of pool entity display names."""

    def __init__(self, path: Path):
        self.tr = json.loads(path.read_text(encoding="utf-8"))

    def __call__(self, display: str, lang: str, rng: random.Random) -> str:
        if lang in ("english",):
            return display
        if lang == "hinglish":
            return display if rng.random() < 0.7 else display.lower()
        key = {"hindi": "hi", "tamil": "ta"}[lang]
        # people often leave place names in Latin script inside Hindi/Tamil text
        return display if rng.random() < 0.15 else self.tr[display][key]
