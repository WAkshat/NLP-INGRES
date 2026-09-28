"""INGRES-Bench question intents: SQL template + sampler + multilingual phrasings.

Placeholders (rendered per language by src/benchmark/build.py):
  {unit_ref}  unit with just enough context (name / name+state / name+district) to be unambiguous
  {utype} {utypes}  unit-type word (singular/plural) of the state's units; {district} {state} {state2}
  {metric} + Hindi/Hinglish agreement {ka} {tha} {kitna}; {cat} {cat2} category adjectives
  {year} adverbial ("in 2024-25"), {year_a} {year_b} bare years; {k} {t} {t2} numbers
SQL params: {uf} unit filter, {y} {ya} {yb} years, {s} {s2} {d} names, {m} metric column, {c} {c2} categories, {k} {t} {t2}.
The LAST phrasing per language is held out for test / hard-test splits.
"""

UJ = ("unit_assessments ua JOIN assessment_units u ON u.unit_id = ua.unit_id "
      "JOIN districts d ON d.district_id = u.district_id JOIN states s ON s.state_id = u.state_id")
RANK = "CASE {x} WHEN 'Safe' THEN 1 WHEN 'Semi-Critical' THEN 2 WHEN 'Critical' THEN 3 WHEN 'Over-Exploited' THEN 4 END"
UNIT_METRICS = ["stage_of_extraction_pct", "annual_recharge_ham", "extractable_resource_ham", "extraction_total_ham",
                "extraction_irrigation_ham", "extraction_domestic_ham", "extraction_industrial_ham",
                "future_availability_ham", "natural_discharge_ham", "recharge_rainfall_ham", "rainfall_mm"]
AGG_METRICS = ["stage_of_extraction_pct", "annual_recharge_ham", "extractable_resource_ham", "extraction_total_ham",
               "extraction_irrigation_ham", "future_availability_ham"]
VOLUME_METRICS = ["annual_recharge_ham", "extractable_resource_ham", "extraction_total_ham", "extraction_irrigation_ham"]

INTENTS = [
    # ------------------------------------------------------------------ D1 simple lookup
    dict(id="unit_metric", difficulty="simple_lookup", sampler="unit_year_metric", n=40, shape="scalar",
         metrics=UNIT_METRICS,
         sql=f"SELECT ua.{{m}} FROM {UJ} WHERE {{uf}} AND ua.assessment_year = '{{y}}'",
         templates={
             "english": ["What was the {metric} of {unit_ref} {year}?", "Give me the {metric} for {unit_ref} {year}.",
                         "{year}, what was the {metric} in {unit_ref}?", "How much was the {metric} of {unit_ref} {year}?"],
             "hindi": ["{year} {unit_ref} {ka} {metric} क्या {tha}?", "{unit_ref} में {year} {metric} {kitna} {tha}?",
                       "{year} {unit_ref} {ka} {metric} बताइए।"],
             "hinglish": ["{year} {unit_ref} {ka} {metric} kya {tha}?", "{unit_ref} mein {year} {metric} {kitna} {tha}?",
                          "{unit_ref} {ka} {metric} batao {year}", "bhai {unit_ref} {ka} {metric} {year} {kitna} {tha}?"],
             "tamil": ["{year} {unit_ref} பகுதியில் {metric} என்ன?", "{unit_ref} பகுதியின் {year} {metric} எவ்வளவு?",
                       "{year} {unit_ref} பகுதியில் {metric} எவ்வளவு இருந்தது?"]}),
    dict(id="unit_category", difficulty="simple_lookup", sampler="unit_year", n=15, shape="scalar",
         sql=f"SELECT ua.category FROM {UJ} WHERE {{uf}} AND ua.assessment_year = '{{y}}'",
         templates={
             "english": ["Which category was {unit_ref} placed in {year}?", "What was the groundwater category of {unit_ref} {year}?",
                         "Was {unit_ref} safe or over-exploited {year}? Give its category.", "Category of {unit_ref} {year}?"],
             "hindi": ["{year} {unit_ref} किस श्रेणी में था?", "{year} {unit_ref} की भूजल श्रेणी क्या थी?",
                       "{unit_ref} की श्रेणी {year} क्या थी?"],
             "hinglish": ["{year} {unit_ref} kis category mein tha?", "{unit_ref} ki groundwater category {year} kya thi?",
                          "{unit_ref} safe tha ya over-exploited, {year}?", "{unit_ref} category {year}??"],
             "tamil": ["{year} {unit_ref} எந்த வகையில் இருந்தது?", "{year} {unit_ref} பகுதியின் நிலத்தடி நீர் வகை என்ன?",
                       "{unit_ref} பகுதியின் வகை {year} என்ன?"]}),
    dict(id="district_metric", difficulty="simple_lookup", sampler="district_year_metric", n=15, shape="scalar",
         metrics=AGG_METRICS,
         sql=("SELECT da.{m} FROM district_assessments da JOIN districts d ON d.district_id = da.district_id "
              "JOIN states s ON s.state_id = d.state_id WHERE d.district_name = '{d}' AND s.state_name = '{s}' "
              "AND da.assessment_year = '{y}'"),
         templates={
             "english": ["What was the {metric} of {district} district ({state}) {year}?",
                         "District-level {metric} for {district}, {state} {year}?",
                         "Tell me the {metric} of the whole {district} district in {state} {year}."],
             "hindi": ["{year} {state} के {district} ज़िले {ka} {metric} क्या {tha}?", "{state} के {district} ज़िले में {year} {metric} {kitna} {tha}?",
                       "{district} ज़िला ({state}) {ka} {metric} {year} बताइए।"],
             "hinglish": ["{year} {state} ke {district} district {ka} {metric} kya {tha}?",
                          "{district} district ({state}) mein {year} {metric} {kitna} {tha}?",
                          "poore {district} zile {ka} {metric} {year}, {state} mein?"],
             "tamil": ["{year} {state} மாநிலத்தின் {district} மாவட்டத்தில் {metric} என்ன?",
                       "{state}, {district} மாவட்டம் முழுவதும் {year} {metric} எவ்வளவு?",
                       "{district} மாவட்டத்தின் ({state}) {metric} {year} எவ்வளவு இருந்தது?"]}),
    dict(id="state_metric", difficulty="simple_lookup", sampler="state_year_metric", n=15, shape="scalar",
         metrics=AGG_METRICS,
         sql=("SELECT sa.{m} FROM state_assessments sa JOIN states s ON s.state_id = sa.state_id "
              "WHERE s.state_name = '{s}' AND sa.assessment_year = '{y}'"),
         templates={
             "english": ["What was {state}'s {metric} {year}?", "State-wide {metric} of {state} {year}?",
                         "For {state} as a whole, what was the {metric} {year}?"],
             "hindi": ["{year} {state} {ka} {metric} क्या {tha}?", "पूरे {state} में {year} {metric} {kitna} {tha}?",
                       "{state} राज्य {ka} {metric} {year} बताइए।"],
             "hinglish": ["{year} {state} {ka} {metric} kya {tha}?", "poore {state} mein {year} {metric} {kitna} {tha}?",
                          "{state} state {ka} overall {metric} {year}?"],
             "tamil": ["{year} {state} மாநிலத்தின் {metric} என்ன?", "{state} மாநிலம் முழுவதும் {year} {metric} எவ்வளவு?",
                       "{year} {state} மாநில அளவில் {metric} எவ்வளவு இருந்தது?"]}),
    dict(id="state_volume_bcm", difficulty="simple_lookup", sampler="state_year_metric", n=8, shape="scalar",
         metrics=VOLUME_METRICS,
         sql=("SELECT sa.{m} / 100000.0 FROM state_assessments sa JOIN states s ON s.state_id = sa.state_id "
              "WHERE s.state_name = '{s}' AND sa.assessment_year = '{y}'"),
         templates={
             "english": ["What was the {metric} of {state} {year}, in billion cubic metres?",
                         "{state}: {metric} {year} in BCM?", "Express {state}'s {metric} {year} in bcm."],
             "hindi": ["{year} {state} {ka} {metric} अरब घन मीटर (BCM) में कितना था?", "{state} {ka} {metric} {year} BCM में बताइए।",
                       "{year} {state} में {metric} कितने BCM {tha}?"],
             "hinglish": ["{year} {state} {ka} {metric} BCM mein kitna tha?", "{state} {ka} {metric} {year} billion cubic metre mein?",
                          "{state} {metric} {year} kitne bcm?"],
             "tamil": ["{year} {state} மாநிலத்தின் {metric} பில்லியன் கன மீட்டரில் (BCM) எவ்வளவு?",
                       "{state} மாநிலத்தின் {metric} {year} BCM அளவில் என்ன?",
                       "{year} {state} {metric} எத்தனை BCM?"]}),
    dict(id="unit_district_lookup", difficulty="simple_lookup", sampler="unit_any", n=8, shape="scalar",
         sql=("SELECT d.district_name FROM assessment_units u JOIN districts d ON d.district_id = u.district_id "
              "JOIN states s ON s.state_id = u.state_id WHERE {uf}"),
         templates={
             "english": ["Which district is {unit_ref} in?", "Name the district that contains {unit_ref}.",
                         "{unit_ref} falls under which district?"],
             "hindi": ["{unit_ref} किस ज़िले में है?", "{unit_ref} किस ज़िले के अंतर्गत आता है?", "{unit_ref} का ज़िला कौन सा है?"],
             "hinglish": ["{unit_ref} kis district mein hai?", "{unit_ref} kaunse zile mein aata hai?", "{unit_ref} ka district?"],
             "tamil": ["{unit_ref} எந்த மாவட்டத்தில் உள்ளது?", "{unit_ref} எந்த மாவட்டத்தின் கீழ் வருகிறது?",
                       "{unit_ref} அமைந்துள்ள மாவட்டம் எது?"]}),
    dict(id="state_unit_type", difficulty="simple_lookup", sampler="state_year", n=6, shape="list",
         sql=("SELECT g.unit_type FROM state_unit_granularity g JOIN states s ON s.state_id = g.state_id "
              "WHERE s.state_name = '{s}' AND g.assessment_year = '{y}'"),
         templates={
             "english": ["What type of assessment units did {state} use {year}?",
                         "{year}, was {state} assessed by blocks, taluks or some other unit?",
                         "Which assessment-unit type applies to {state} {year}?"],
             "hindi": ["{year} {state} में किस प्रकार की आकलन इकाइयाँ थीं?", "{year} {state} का आकलन ब्लॉक, तालुका या किस इकाई से हुआ?",
                       "{state} में {year} आकलन इकाई का प्रकार क्या था?"],
             "hinglish": ["{year} {state} mein kis type ki assessment units thi?", "{state} ka assessment {year} block wise hua ya taluka wise?",
                          "{state} unit type {year}?"],
             "tamil": ["{year} {state} மாநிலத்தில் எந்த வகை மதிப்பீட்டு அலகுகள் பயன்படுத்தப்பட்டன?",
                       "{year} {state} ஒன்றிய அளவிலா வட்ட அளவிலா மதிப்பிடப்பட்டது?",
                       "{state} மாநிலத்தின் மதிப்பீட்டு அலகு வகை {year} என்ன?"]}),
    # ------------------------------------------------------------------ D2 filtered aggregate
    dict(id="count_category_state", difficulty="filtered_aggregate", sampler="state_year_category", n=14, shape="scalar",
         sql=f"SELECT COUNT(*) FROM {UJ} WHERE s.state_name = '{{s}}' AND ua.assessment_year = '{{y}}' AND ua.category = '{{c}}'",
         templates={
             "english": ["How many {utypes} in {state} were {cat} {year}?", "Number of {cat} assessment units in {state} {year}?",
                         "Count the {cat} {utypes} of {state} {year}.", "{year}, how many of {state}'s {utypes} were classified {cat}?"],
             "hindi": ["{year} {state} में कितने {utypes} {cat} थे?", "{state} में {year} {cat} आकलन इकाइयों की संख्या कितनी थी?",
                       "{year} {state} के कितने {utypes} {cat} श्रेणी में थे?"],
             "hinglish": ["{year} {state} mein kitne {utypes} {cat} the?", "{state} ke kitne {utypes} {cat} category mein the {year}?",
                          "{state} mein {cat} units kitne hai {year}?", "{year} {state} ke {cat} {utypes} ka count?"],
             "tamil": ["{year} {state} மாநிலத்தில் எத்தனை {utypes} {cat} நிலையில் இருந்தன?",
                       "{state} மாநிலத்தில் {year} {cat} மதிப்பீட்டு அலகுகள் எத்தனை?",
                       "{year} {state} மாநிலத்தின் {cat} {utypes} எண்ணிக்கை என்ன?"]}),
    dict(id="count_category_district", difficulty="filtered_aggregate", sampler="district_year_category", n=10, shape="scalar",
         sql=(f"SELECT COUNT(*) FROM {UJ} WHERE d.district_name = '{{d}}' AND s.state_name = '{{s}}' "
              "AND ua.assessment_year = '{y}' AND ua.category = '{c}'"),
         templates={
             "english": ["How many {utypes} in {district} district, {state}, were {cat} {year}?",
                         "Number of {cat} units in {district} ({state}) {year}?", "{year}, count {district} district's {cat} {utypes} ({state})."],
             "hindi": ["{year} {state} के {district} ज़िले में कितने {utypes} {cat} थे?", "{district} ज़िले ({state}) में {year} कितनी इकाइयाँ {cat} थीं?",
                       "{year} {district} ({state}) के {cat} {utypes} कितने थे?"],
             "hinglish": ["{year} {state} ke {district} district mein kitne {utypes} {cat} the?",
                          "{district} ({state}) mein {cat} {utypes} kitne the {year}?", "{district} zile ke {cat} units {year}, {state}?"],
             "tamil": ["{year} {state} மாநிலத்தின் {district} மாவட்டத்தில் எத்தனை {utypes} {cat} நிலையில் இருந்தன?",
                       "{district} மாவட்டத்தில் ({state}) {year} {cat} அலகுகள் எத்தனை?",
                       "{year} {district} ({state}) மாவட்டத்தின் {cat} {utypes} எண்ணிக்கை?"]}),
    dict(id="list_category_district", difficulty="filtered_aggregate", sampler="district_year_category", n=10, shape="list",
         sql=(f"SELECT u.unit_name FROM {UJ} WHERE d.district_name = '{{d}}' AND s.state_name = '{{s}}' "
              "AND ua.assessment_year = '{y}' AND ua.category = '{c}'"),
         templates={
             "english": ["Which {utypes} of {district} district, {state}, were {cat} {year}?", "List the {cat} units in {district} ({state}) {year}.",
                         "Name every {cat} {utype} in {district}, {state}, {year}."],
             "hindi": ["{year} {state} के {district} ज़िले के कौन से {utypes} {cat} थे?", "{district} ({state}) के {cat} {utypes} की सूची {year} दीजिए।",
                       "{year} {district} ज़िले ({state}) में कौन कौन से {utypes} {cat} श्रेणी में थे?"],
             "hinglish": ["{year} {state} ke {district} district ke kaunse {utypes} {cat} the?", "{district} ({state}) ke {cat} {utypes} ki list do {year}",
                          "{district} mein {cat} wale {utypes} kaun se hai {year}, {state}?"],
             "tamil": ["{year} {state} மாநிலத்தின் {district} மாவட்டத்தில் எந்த {utypes} {cat} நிலையில் இருந்தன?",
                       "{district} ({state}) மாவட்டத்தின் {cat} அலகுகளைப் பட்டியலிடுங்கள் {year}.",
                       "{year} {district} மாவட்டத்தில் ({state}) {cat} {utypes} எவை?"]}),
    dict(id="avg_unit_soe_state", difficulty="filtered_aggregate", sampler="state_year", n=10, shape="scalar",
         sql=f"SELECT AVG(ua.stage_of_extraction_pct) FROM {UJ} WHERE s.state_name = '{{s}}' AND ua.assessment_year = '{{y}}'",
         templates={
             "english": ["What was the average stage of extraction across {state}'s {utypes} {year}?",
                         "Mean unit-level stage of groundwater extraction in {state} {year}?",
                         "Averaged over all assessment units of {state}, what was the stage of extraction {year}?"],
             "hindi": ["{year} {state} के सभी {utypes} का औसत भूजल दोहन स्तर क्या था?", "{state} की आकलन इकाइयों का औसत दोहन स्तर {year} कितना था?",
                       "{year} {state} में इकाइयों का औसत भूजल निष्कर्षण प्रतिशत?"],
             "hinglish": ["{year} {state} ke saare {utypes} ka average extraction stage kya tha?",
                          "{state} ki units ka average stage of extraction {year}?", "{state} mein unit wise average SoE {year} kitna tha?"],
             "tamil": ["{year} {state} மாநிலத்தின் அனைத்து {utypes} சராசரி நிலத்தடி நீர் எடுப்பு நிலை என்ன?",
                       "{state} மாநில மதிப்பீட்டு அலகுகளின் சராசரி எடுப்பு நிலை {year} எவ்வளவு?",
                       "{year} {state} அலகுகளின் சராசரி நிலத்தடி நீர் எடுப்பு சதவீதம்?"]}),
    dict(id="top_k_units_state", difficulty="filtered_aggregate", sampler="state_year_metric_k", n=12, shape="table_ordered",
         metrics=["stage_of_extraction_pct", "extraction_total_ham", "annual_recharge_ham"],
         sql=(f"SELECT u.unit_name, ua.{{m}} FROM {UJ} WHERE s.state_name = '{{s}}' AND ua.assessment_year = '{{y}}' "
              "AND ua.{m} IS NOT NULL ORDER BY ua.{m} DESC LIMIT {k}"),
         templates={
             "english": ["Which {k} {utypes} of {state} had the highest {metric} {year}? Show the values.",
                         "Top {k} units in {state} by {metric} {year}, with values.", "List {state}'s {k} highest-{metric} {utypes} {year} and their values."],
             "hindi": ["{year} {state} के किन {k} {utypes} {ka} {metric} सबसे अधिक {tha}? मान भी बताइए।",
                       "{state} में {metric} के हिसाब से शीर्ष {k} इकाइयाँ {year} (मान सहित)?",
                       "{year} {state} के सबसे ज़्यादा {metric} वाले {k} {utypes} और उनके मान?"],
             "hinglish": ["{year} {state} ke kaunse {k} {utypes} {ka} {metric} sabse zyada tha? values bhi batao",
                          "{state} ke top {k} units by {metric} {year} with values", "{state} mein {metric} sabse high wale {k} {utypes} {year}?"],
             "tamil": ["{year} {state} மாநிலத்தில் {metric} அதிகமாக இருந்த {k} {utypes} எவை? மதிப்புகளுடன் கூறுங்கள்.",
                       "{metric} அடிப்படையில் {state} மாநிலத்தின் முதல் {k} அலகுகள் {year} (மதிப்புகளுடன்)?",
                       "{year} {state} மாநிலத்தில் அதிக {metric} கொண்ட {k} {utypes} மற்றும் அவற்றின் மதிப்புகள்?"]}),
    dict(id="pct_category_state", difficulty="filtered_aggregate", sampler="state_year_category", n=10, shape="scalar",
         sql=(f"SELECT 100.0 * SUM(ua.category = '{{c}}') / COUNT(*) FROM {UJ} "
              "WHERE s.state_name = '{s}' AND ua.assessment_year = '{y}'"),
         templates={
             "english": ["What percentage of {state}'s assessment units were {cat} {year}?", "Share of {cat} units in {state} {year}, in percent?",
                         "{year}, what fraction (as a percentage) of {state}'s {utypes} were {cat}?"],
             "hindi": ["{year} {state} की कितने प्रतिशत आकलन इकाइयाँ {cat} थीं?", "{state} में {cat} इकाइयों का प्रतिशत {year} क्या था?",
                       "{year} {state} के {utypes} में से कितने प्रतिशत {cat} थे?"],
             "hinglish": ["{year} {state} ki kitne percent units {cat} thi?", "{state} mein {cat} units ka percentage {year}?",
                          "{state} ke kitne % {utypes} {cat} the {year}?"],
             "tamil": ["{year} {state} மாநிலத்தின் மதிப்பீட்டு அலகுகளில் எத்தனை சதவீதம் {cat} நிலையில் இருந்தன?",
                       "{state} மாநிலத்தில் {cat} அலகுகளின் சதவீதம் {year} என்ன?",
                       "{year} {state} {utypes} இல் {cat} நிலையில் உள்ளவை எத்தனை சதவீதம்?"]}),
    dict(id="count_districts_soe_above", difficulty="filtered_aggregate", sampler="state_year_threshold", n=8, shape="scalar",
         sql=("SELECT COUNT(*) FROM district_assessments da JOIN districts d ON d.district_id = da.district_id "
              "JOIN states s ON s.state_id = d.state_id WHERE s.state_name = '{s}' AND da.assessment_year = '{y}' "
              "AND da.stage_of_extraction_pct > {t}"),
         templates={
             "english": ["How many districts of {state} had a district-level stage of extraction above {t}% {year}?",
                         "Number of {state} districts with stage of extraction over {t} percent {year}?",
                         "{year}, in how many districts of {state} did extraction exceed {t}% of the extractable resource?"],
             "hindi": ["{year} {state} के कितने ज़िलों में ज़िला-स्तरीय भूजल दोहन {t}% से अधिक था?",
                       "{state} में {year} कितने ज़िलों का दोहन स्तर {t} प्रतिशत से ऊपर था?",
                       "{year} {state} के कितने ज़िले {t}% दोहन स्तर से ज़्यादा थे?"],
             "hinglish": ["{year} {state} ke kitne districts mein extraction stage {t}% se zyada tha?",
                          "{state} mein {t} percent se upar SoE wale districts kitne the {year}?", "{state} districts with SoE > {t} {year}, count?"],
             "tamil": ["{year} {state} மாநிலத்தின் எத்தனை மாவட்டங்களில் நிலத்தடி நீர் எடுப்பு நிலை {t}% ஐ விட அதிகமாக இருந்தது?",
                       "{state} மாநிலத்தில் {year} எடுப்பு நிலை {t} சதவீதத்திற்கு மேல் உள்ள மாவட்டங்கள் எத்தனை?",
                       "{year} {state} மாநிலத்தில் {t}% க்கு மேல் எடுப்பு நிலை கொண்ட மாவட்டங்களின் எண்ணிக்கை?"]}),
    dict(id="state_extreme_metric", difficulty="filtered_aggregate", sampler="year_metric_dir", n=8, shape="scalar",
         metrics=["stage_of_extraction_pct", "annual_recharge_ham", "extraction_total_ham"],
         sql=("SELECT s.state_name FROM state_assessments sa JOIN states s ON s.state_id = sa.state_id "
              "WHERE sa.assessment_year = '{y}' AND sa.{m} IS NOT NULL ORDER BY sa.{m} {dir} LIMIT 1"),
         templates={
             "english": ["Which state or UT had the {dir_word} {metric} {year}?", "{year}, which state recorded the {dir_word} {metric}?",
                         "Name the state/UT with the {dir_word} {metric} {year}."],
             "hindi": ["{year} किस राज्य या केंद्र शासित प्रदेश {ka} {metric} {dir_word} {tha}?", "{year} {dir_word} {metric} किस राज्य में दर्ज हुआ?",
                       "{year} {metric} के मामले में {dir_word} राज्य कौन सा था?"],
             "hinglish": ["{year} kis state {ka} {metric} {dir_word} tha?", "{year} {dir_word} {metric} wala state kaunsa tha?",
                          "{metric} mein {dir_word} state {year}?"],
             "tamil": ["{year} எந்த மாநிலத்தில் {metric} {dir_word} இருந்தது?", "{year} {dir_word} {metric} பதிவான மாநிலம் எது?",
                       "{metric} அடிப்படையில் {year} {dir_word} மாநிலம் எது?"]}),
    dict(id="count_soe_between_state", difficulty="filtered_aggregate", sampler="state_year_range", n=8, shape="scalar",
         sql=(f"SELECT COUNT(*) FROM {UJ} WHERE s.state_name = '{{s}}' AND ua.assessment_year = '{{y}}' "
              "AND ua.stage_of_extraction_pct BETWEEN {t} AND {t2}"),
         templates={
             "english": ["How many {utypes} in {state} had a stage of extraction between {t}% and {t2}% {year}?",
                         "Count of {state} units with extraction stage from {t} to {t2} percent {year}?",
                         "{year}, number of {state}'s {utypes} whose stage of extraction lay between {t} and {t2}%?"],
             "hindi": ["{year} {state} के कितने {utypes} का दोहन स्तर {t}% से {t2}% के बीच था?",
                       "{state} में {year} {t} से {t2} प्रतिशत दोहन स्तर वाली इकाइयाँ कितनी थीं?",
                       "{year} {state} में {t}-{t2}% दोहन वाले {utypes} कितने?"],
             "hinglish": ["{year} {state} ke kitne {utypes} ka extraction stage {t}% se {t2}% ke beech tha?",
                          "{state} mein {t} se {t2} percent SoE wali units kitni thi {year}?", "{state} {t}-{t2}% wale {utypes} {year}?"],
             "tamil": ["{year} {state} மாநிலத்தில் எடுப்பு நிலை {t}% முதல் {t2}% வரை இருந்த {utypes} எத்தனை?",
                       "{state} மாநிலத்தில் {year} {t} முதல் {t2} சதவீதம் வரை எடுப்பு நிலை கொண்ட அலகுகள் எத்தனை?",
                       "{year} {state} மாநிலத்தில் {t}-{t2}% எடுப்பு நிலையில் இருந்த {utypes} எண்ணிக்கை?"]}),
    dict(id="irrigation_share_state", difficulty="filtered_aggregate", sampler="state_year", n=8, shape="scalar",
         sql=("SELECT 100.0 * sa.extraction_irrigation_ham / sa.extraction_total_ham FROM state_assessments sa "
              "JOIN states s ON s.state_id = sa.state_id WHERE s.state_name = '{s}' AND sa.assessment_year = '{y}'"),
         templates={
             "english": ["What share of {state}'s total groundwater extraction went to irrigation {year}, in percent?",
                         "Irrigation as a percentage of all groundwater extraction in {state} {year}?",
                         "{year}, how much of {state}'s groundwater draft (in %) was for irrigation?"],
             "hindi": ["{year} {state} के कुल भूजल दोहन का कितना प्रतिशत सिंचाई के लिए था?", "{state} में {year} सिंचाई का हिस्सा कुल दोहन का कितने प्रतिशत था?",
                       "{year} {state} में कुल निष्कर्षण में सिंचाई का प्रतिशत?"],
             "hinglish": ["{year} {state} ke total extraction ka kitna percent irrigation ke liye tha?",
                          "{state} mein {year} sinchai ka share total extraction mein kitna %?", "{state} irrigation share of extraction {year}?"],
             "tamil": ["{year} {state} மாநிலத்தின் மொத்த நிலத்தடி நீர் எடுப்பில் பாசனத்தின் பங்கு எத்தனை சதவீதம்?",
                       "{state} மாநிலத்தில் {year} மொத்த எடுப்பில் பாசனத்திற்கான சதவீதம் என்ன?",
                       "{year} {state} மாநிலத்தில் பாசனத்திற்காக எடுக்கப்பட்ட நிலத்தடி நீர் மொத்தத்தில் எத்தனை சதவீதம்?"]}),
    dict(id="top_states_by_category", difficulty="filtered_aggregate", sampler="year_category_k", n=8, shape="table_ordered",
         sql=(f"SELECT s.state_name, COUNT(*) AS n FROM {UJ} WHERE ua.assessment_year = '{{y}}' AND ua.category = '{{c}}' "
              "GROUP BY s.state_name ORDER BY n DESC, s.state_name LIMIT {k}"),
         templates={
             "english": ["Which {k} states had the most {cat} assessment units {year}, and how many each?",
                         "Top {k} states by number of {cat} units {year}, with counts.", "Rank the {k} states with the largest count of {cat} units {year}."],
             "hindi": ["{year} किन {k} राज्यों में सबसे अधिक {cat} आकलन इकाइयाँ थीं, और प्रत्येक में कितनी?",
                       "{cat} इकाइयों की संख्या के आधार पर शीर्ष {k} राज्य {year} (संख्या सहित)?",
                       "{year} सबसे ज़्यादा {cat} इकाइयों वाले {k} राज्य कौन से थे?"],
             "hinglish": ["{year} kaunse {k} states mein sabse zyada {cat} units thi, count ke saath?",
                          "{cat} units ke hisaab se top {k} states {year}?", "sabse zyada {cat} units wale {k} states {year} batao"],
             "tamil": ["{year} அதிக {cat} மதிப்பீட்டு அலகுகளைக் கொண்ட {k} மாநிலங்கள் எவை, ஒவ்வொன்றிலும் எத்தனை?",
                       "{cat} அலகுகளின் எண்ணிக்கை அடிப்படையில் முதல் {k} மாநிலங்கள் {year} (எண்ணிக்கையுடன்)?",
                       "{year} அதிக {cat} அலகுகள் கொண்ட {k} மாநிலங்களை வரிசைப்படுத்துங்கள்."]}),
    dict(id="district_min_soe_state", difficulty="filtered_aggregate", sampler="state_year", n=8, shape="scalar",
         sql=("SELECT d.district_name FROM district_assessments da JOIN districts d ON d.district_id = da.district_id "
              "JOIN states s ON s.state_id = d.state_id WHERE s.state_name = '{s}' AND da.assessment_year = '{y}' "
              "AND da.stage_of_extraction_pct IS NOT NULL ORDER BY da.stage_of_extraction_pct ASC LIMIT 1"),
         templates={
             "english": ["Which district of {state} had the lowest stage of groundwater extraction {year}?",
                         "Least-stressed district in {state} by stage of extraction {year}?", "{year}, the {state} district with the minimum extraction stage?"],
             "hindi": ["{year} {state} के किस ज़िले का भूजल दोहन स्तर सबसे कम था?", "{state} में {year} सबसे कम दोहन स्तर वाला ज़िला कौन सा था?",
                       "{year} {state} का न्यूनतम दोहन स्तर वाला ज़िला?"],
             "hinglish": ["{year} {state} ke kis district ka extraction stage sabse kam tha?", "{state} ka sabse kam SoE wala district {year}?",
                          "{state} mein lowest extraction stage district {year}"],
             "tamil": ["{year} {state} மாநிலத்தின் எந்த மாவட்டத்தில் நிலத்தடி நீர் எடுப்பு நிலை மிகக் குறைவாக இருந்தது?",
                       "{state} மாநிலத்தில் {year} மிகக் குறைந்த எடுப்பு நிலை கொண்ட மாவட்டம் எது?",
                       "{year} {state} மாநிலத்தில் குறைந்தபட்ச எடுப்பு நிலை மாவட்டம்?"]}),
    dict(id="national_category_count", difficulty="filtered_aggregate", sampler="year_category", n=6, shape="scalar",
         sql="SELECT COUNT(*) FROM unit_assessments ua WHERE ua.assessment_year = '{y}' AND ua.category = '{c}'",
         templates={
             "english": ["How many assessment units in India were {cat} {year}?", "Nationwide count of {cat} units {year}?",
                         "{year}, total number of {cat} groundwater assessment units across the country?"],
             "hindi": ["{year} भारत में कितनी आकलन इकाइयाँ {cat} थीं?", "{year} देश भर में {cat} इकाइयों की कुल संख्या?",
                       "पूरे देश में {year} {cat} आकलन इकाइयाँ कितनी थीं?"],
             "hinglish": ["{year} India mein kitni units {cat} thi?", "poore desh mein {cat} units {year} kitni?", "all india {cat} units count {year}"],
             "tamil": ["{year} இந்தியாவில் எத்தனை மதிப்பீட்டு அலகுகள் {cat} நிலையில் இருந்தன?",
                       "{year} நாடு முழுவதும் {cat} அலகுகளின் மொத்த எண்ணிக்கை?",
                       "நாடு முழுவதும் {year} {cat} நிலத்தடி நீர் மதிப்பீட்டு அலகுகள் எத்தனை?"]}),
    # ------------------------------------------------------------------ D3 cross-year comparison
    dict(id="unit_metric_change", difficulty="cross_year", sampler="unit_two_years_metric", n=12, shape="scalar", caveat=True,
         metrics=["stage_of_extraction_pct", "extraction_total_ham", "annual_recharge_ham"],
         sql=(f"SELECT b.{{m}} - a.{{m}} FROM unit_assessments a JOIN unit_assessments b ON b.unit_id = a.unit_id "
              f"JOIN assessment_units u ON u.unit_id = a.unit_id JOIN districts d ON d.district_id = u.district_id "
              f"JOIN states s ON s.state_id = u.state_id WHERE {{uf}} AND a.assessment_year = '{{ya}}' AND b.assessment_year = '{{yb}}'"),
         templates={
             "english": ["By how much did the {metric} of {unit_ref} change between {year_a} and {year_b}?",
                         "Change in {metric} for {unit_ref} from {year_a} to {year_b}?",
                         "What is the {year_b} value minus the {year_a} value of {metric} for {unit_ref}?"],
             "hindi": ["{year_a} से {year_b} के बीच {unit_ref} {ka} {metric} कितना बदला?", "{unit_ref} {ka} {metric} {year_a} और {year_b} में कितना अंतर?",
                       "{year_a} की तुलना में {year_b} में {unit_ref} {ka} {metric} कितना बदला?"],
             "hinglish": ["{year_a} se {year_b} ke beech {unit_ref} {ka} {metric} kitna change hua?",
                          "{unit_ref} {ka} {metric} {year_a} vs {year_b} difference?", "{year_b} minus {year_a}: {unit_ref} {ka} {metric} kitna badla?"],
             "tamil": ["{year_a} முதல் {year_b} வரை {unit_ref} பகுதியில் {metric} எவ்வளவு மாறியது?",
                       "{unit_ref} பகுதியின் {metric} {year_a} மற்றும் {year_b} இடையே உள்ள வேறுபாடு என்ன?",
                       "{year_a} உடன் ஒப்பிடும்போது {year_b} இல் {unit_ref} பகுதியின் {metric} மாற்றம் எவ்வளவு?"]}),
    dict(id="unit_category_two_years", difficulty="cross_year", sampler="unit_two_years", n=10, shape="table", caveat=True,
         sql=(f"SELECT a.category, b.category FROM unit_assessments a JOIN unit_assessments b ON b.unit_id = a.unit_id "
              f"JOIN assessment_units u ON u.unit_id = a.unit_id JOIN districts d ON d.district_id = u.district_id "
              f"JOIN states s ON s.state_id = u.state_id WHERE {{uf}} AND a.assessment_year = '{{ya}}' AND b.assessment_year = '{{yb}}'"),
         templates={
             "english": ["What category was {unit_ref} in {year_a} and in {year_b}?", "Did {unit_ref}'s category change between {year_a} and {year_b}? Give both.",
                         "Compare the groundwater category of {unit_ref} in {year_a} versus {year_b}."],
             "hindi": ["{year_a} और {year_b} में {unit_ref} की श्रेणी क्या थी?", "क्या {year_a} और {year_b} के बीच {unit_ref} की श्रेणी बदली? दोनों बताइए।",
                       "{unit_ref} की भूजल श्रेणी {year_a} बनाम {year_b}?"],
             "hinglish": ["{year_a} aur {year_b} mein {unit_ref} ki category kya thi?", "{unit_ref} ki category {year_a} se {year_b} tak badli kya? dono batao",
                          "{unit_ref} category {year_a} vs {year_b}"],
             "tamil": ["{year_a} மற்றும் {year_b} இல் {unit_ref} எந்த வகையில் இருந்தது?",
                       "{year_a} மற்றும் {year_b} இடையே {unit_ref} பகுதியின் வகை மாறியதா? இரண்டையும் கூறுங்கள்.",
                       "{unit_ref} பகுதியின் நிலத்தடி நீர் வகை: {year_a} எதிர் {year_b}?"]}),
    dict(id="category_transition_state", difficulty="cross_year", sampler="state_two_years_transition", n=12, shape="list", caveat=True,
         sql=(f"SELECT u.unit_name FROM unit_assessments a JOIN unit_assessments b ON b.unit_id = a.unit_id "
              f"JOIN assessment_units u ON u.unit_id = a.unit_id JOIN states s ON s.state_id = u.state_id "
              f"WHERE s.state_name = '{{s}}' AND a.assessment_year = '{{ya}}' AND b.assessment_year = '{{yb}}' "
              f"AND a.category = '{{c}}' AND b.category = '{{c2}}'"),
         templates={
             "english": ["Which {utypes} in {state} moved from {cat} in {year_a} to {cat2} in {year_b}?",
                         "List {state}'s units that were {cat} in {year_a} but {cat2} in {year_b}.",
                         "Name the {state} {utypes} whose category changed from {cat} ({year_a}) to {cat2} ({year_b})."],
             "hindi": ["{state} के कौन से {utypes} {year_a} में {cat} थे और {year_b} में {cat2} हो गए?",
                       "{state} की वे इकाइयाँ बताइए जो {year_a} में {cat} थीं लेकिन {year_b} में {cat2} थीं।",
                       "{year_a} ({cat}) से {year_b} ({cat2}) तक श्रेणी बदलने वाले {state} के {utypes}?"],
             "hinglish": ["{state} ke kaunse {utypes} {year_a} mein {cat} the aur {year_b} mein {cat2} ho gaye?",
                          "{state} ki units jo {year_a} mein {cat} thi par {year_b} mein {cat2}, list do",
                          "{cat} se {cat2} bane {state} ke {utypes} ({year_a} -> {year_b})"],
             "tamil": ["{state} மாநிலத்தின் எந்த {utypes} {year_a} இல் {cat} நிலையிலிருந்து {year_b} இல் {cat2} நிலைக்கு மாறின?",
                       "{year_a} இல் {cat} ஆக இருந்து {year_b} இல் {cat2} ஆன {state} அலகுகளைப் பட்டியலிடுங்கள்.",
                       "{year_a} ({cat}) இலிருந்து {year_b} ({cat2}) க்கு மாறிய {state} {utypes} எவை?"]}),
    dict(id="count_category_two_years", difficulty="cross_year", sampler="state_two_years_category", n=10, shape="table", caveat=True,
         sql=(f"SELECT ua.assessment_year, COUNT(*) FROM {UJ} WHERE s.state_name = '{{s}}' AND ua.category = '{{c}}' "
              "AND ua.assessment_year IN ('{ya}', '{yb}') GROUP BY ua.assessment_year ORDER BY ua.assessment_year"),
         templates={
             "english": ["How many {cat} {utypes} did {state} have in {year_a} compared with {year_b}?",
                         "{cat} unit count in {state}: {year_a} vs {year_b}?", "Give the number of {cat} units in {state} for {year_a} and for {year_b}."],
             "hindi": ["{state} में {year_a} और {year_b} में कितने {cat} {utypes} थे?", "{state} में {cat} इकाइयों की संख्या: {year_a} बनाम {year_b}?",
                       "{year_a} और {year_b} दोनों वर्षों में {state} के {cat} {utypes} की संख्या बताइए।"],
             "hinglish": ["{state} mein {year_a} aur {year_b} mein kitne {cat} {utypes} the?", "{state} {cat} units {year_a} vs {year_b}?",
                          "{year_a} aur {year_b} dono ke liye {state} ke {cat} units ka count do"],
             "tamil": ["{state} மாநிலத்தில் {year_a} மற்றும் {year_b} இல் எத்தனை {cat} {utypes} இருந்தன?",
                       "{state} {cat} அலகுகளின் எண்ணிக்கை: {year_a} எதிர் {year_b}?",
                       "{year_a} மற்றும் {year_b} ஆண்டுகளுக்கு {state} மாநிலத்தின் {cat} அலகுகளின் எண்ணிக்கையைத் தாருங்கள்."]}),
    dict(id="state_soe_change", difficulty="cross_year", sampler="state_two_years_any", n=8, shape="scalar", caveat=True,
         sql=("SELECT b.stage_of_extraction_pct - a.stage_of_extraction_pct FROM state_assessments a "
              "JOIN state_assessments b ON b.state_id = a.state_id JOIN states s ON s.state_id = a.state_id "
              "WHERE s.state_name = '{s}' AND a.assessment_year = '{ya}' AND b.assessment_year = '{yb}'"),
         templates={
             "english": ["By how many percentage points did {state}'s stage of extraction change from {year_a} to {year_b}?",
                         "Change in {state}'s state-level stage of groundwater extraction between {year_a} and {year_b}?",
                         "{state}: stage of extraction in {year_b} minus {year_a}, in percentage points?"],
             "hindi": ["{year_a} से {year_b} तक {state} का भूजल दोहन स्तर कितने प्रतिशत अंक बदला?",
                       "{state} के राज्य-स्तरीय दोहन स्तर में {year_a} और {year_b} के बीच कितना परिवर्तन हुआ?",
                       "{state} का दोहन स्तर {year_b} में {year_a} की तुलना में कितने अंक अलग था?"],
             "hinglish": ["{year_a} se {year_b} tak {state} ka extraction stage kitne percentage points badla?",
                          "{state} ke SoE mein {year_a} aur {year_b} ke beech kitna change?", "{state} SoE {year_b} minus {year_a}?"],
             "tamil": ["{year_a} முதல் {year_b} வரை {state} மாநிலத்தின் எடுப்பு நிலை எத்தனை சதவீதப் புள்ளிகள் மாறியது?",
                       "{year_a} மற்றும் {year_b} இடையே {state} மாநில அளவிலான நிலத்தடி நீர் எடுப்பு நிலையின் மாற்றம் என்ன?",
                       "{state}: {year_b} எடுப்பு நிலையிலிருந்து {year_a} எடுப்பு நிலையைக் கழித்தால் எவ்வளவு?"]}),
    dict(id="district_largest_increase", difficulty="cross_year", sampler="state_two_years_metric", n=8, shape="scalar", caveat=True,
         metrics=["extraction_total_ham", "stage_of_extraction_pct"],
         sql=("SELECT d.district_name FROM district_assessments a JOIN district_assessments b ON b.district_id = a.district_id "
              "JOIN districts d ON d.district_id = a.district_id JOIN states s ON s.state_id = d.state_id "
              "WHERE s.state_name = '{s}' AND a.assessment_year = '{ya}' AND b.assessment_year = '{yb}' "
              "AND a.{m} IS NOT NULL AND b.{m} IS NOT NULL ORDER BY b.{m} - a.{m} DESC LIMIT 1"),
         templates={
             "english": ["Which district of {state} saw the largest increase in {metric} between {year_a} and {year_b}?",
                         "Biggest rise in district-level {metric} in {state} from {year_a} to {year_b}: which district?",
                         "In {state}, whose {metric} grew the most from {year_a} to {year_b}, district-wise?"],
             "hindi": ["{year_a} से {year_b} के बीच {state} के किस ज़िले में {metric} सबसे अधिक बढ़ा?",
                       "{state} में {year_a} से {year_b} तक ज़िला-स्तरीय {metric} में सबसे बड़ी वृद्धि किस ज़िले में हुई?",
                       "{state} का कौन सा ज़िला {metric} में {year_a}-{year_b} के दौरान सबसे ज़्यादा बढ़ा?"],
             "hinglish": ["{year_a} se {year_b} ke beech {state} ke kis district mein {metric} sabse zyada badha?",
                          "{state} mein {metric} ka sabse bada increase kis district mein {year_a} to {year_b}?",
                          "{state} district with max {metric} rise {year_a}-{year_b}"],
             "tamil": ["{year_a} மற்றும் {year_b} இடையே {state} மாநிலத்தின் எந்த மாவட்டத்தில் {metric} அதிகமாக உயர்ந்தது?",
                       "{year_a} முதல் {year_b} வரை {state} மாநிலத்தில் மாவட்ட அளவிலான {metric} மிக அதிகமாக உயர்ந்த மாவட்டம் எது?",
                       "{state} மாநிலத்தில் {year_a}-{year_b} காலத்தில் {metric} அதிகம் வளர்ந்த மாவட்டம்?"]}),
    dict(id="count_improved_state", difficulty="cross_year", sampler="state_two_years_comparable", n=8, shape="scalar", caveat=True,
         sql=(f"SELECT COUNT(*) FROM unit_assessments a JOIN unit_assessments b ON b.unit_id = a.unit_id "
              f"JOIN assessment_units u ON u.unit_id = a.unit_id JOIN states s ON s.state_id = u.state_id "
              f"WHERE s.state_name = '{{s}}' AND a.assessment_year = '{{ya}}' AND b.assessment_year = '{{yb}}' "
              f"AND {RANK.format(x='b.category')} < {RANK.format(x='a.category')}"),
         templates={
             "english": ["How many {utypes} in {state} moved to a less stressed category between {year_a} and {year_b}?",
                         "Number of {state} units whose groundwater category improved from {year_a} to {year_b}?",
                         "Count {state}'s {utypes} that improved (e.g. Over-Exploited to Critical) between {year_a} and {year_b}."],
             "hindi": ["{year_a} और {year_b} के बीच {state} के कितने {utypes} बेहतर श्रेणी में आए?",
                       "{year_a} से {year_b} तक {state} की कितनी इकाइयों की भूजल श्रेणी में सुधार हुआ?",
                       "{state} में कितने {utypes} की श्रेणी {year_a} से {year_b} के बीच सुधरी (जैसे अति-दोहित से गंभीर)?"],
             "hinglish": ["{year_a} aur {year_b} ke beech {state} ke kitne {utypes} better category mein aaye?",
                          "{state} ki kitni units ki category improve hui {year_a} se {year_b}?", "{state} improved units count {year_a} -> {year_b}"],
             "tamil": ["{year_a} மற்றும் {year_b} இடையே {state} மாநிலத்தின் எத்தனை {utypes} மேம்பட்ட வகைக்கு மாறின?",
                       "{year_a} முதல் {year_b} வரை {state} மாநிலத்தில் நிலத்தடி நீர் வகை மேம்பட்ட அலகுகள் எத்தனை?",
                       "{state} மாநிலத்தில் {year_a}-{year_b} இடையே வகை மேம்பட்ட {utypes} எண்ணிக்கை (எ.கா. அதிகப்படியாக சுரண்டப்பட்டதிலிருந்து அபாயகரமானதற்கு)?"]}),
    dict(id="national_category_by_year", difficulty="cross_year", sampler="category_only", n=4, shape="table_ordered", caveat=True,
         sql=("SELECT ua.assessment_year, COUNT(*) FROM unit_assessments ua WHERE ua.category = '{c}' "
              "GROUP BY ua.assessment_year ORDER BY ua.assessment_year"),
         templates={
             "english": ["How has the number of {cat} assessment units in India changed across all assessment cycles? Give the count per cycle.",
                         "Year-by-year count of {cat} units nationwide.", "For every available assessment, how many units were {cat}?"],
             "hindi": ["सभी आकलन चक्रों में भारत में {cat} इकाइयों की संख्या कैसे बदली? हर चक्र की संख्या बताइए।",
                       "देश भर में {cat} इकाइयों की वर्षवार संख्या?", "हर उपलब्ध आकलन में कितनी इकाइयाँ {cat} थीं?"],
             "hinglish": ["saare assessment cycles mein India ke {cat} units kaise badle? har cycle ka count do",
                          "all india {cat} units year wise count", "har assessment mein kitni units {cat} thi?"],
             "tamil": ["அனைத்து மதிப்பீட்டு சுழற்சிகளிலும் இந்தியாவில் {cat} அலகுகளின் எண்ணிக்கை எப்படி மாறியது? ஒவ்வொரு சுழற்சிக்கும் கூறுங்கள்.",
                       "நாடு முழுவதும் {cat} அலகுகளின் ஆண்டு வாரியான எண்ணிக்கை?",
                       "கிடைக்கும் ஒவ்வொரு மதிப்பீட்டிலும் எத்தனை அலகுகள் {cat} நிலையில் இருந்தன?"]}),
    dict(id="unit_first_year_category", difficulty="cross_year", sampler="unit_ever_category", n=8, shape="scalar", caveat=True,
         sql=f"SELECT MIN(ua.assessment_year) FROM {UJ} WHERE {{uf}} AND ua.category = '{{c}}'",
         templates={
             "english": ["In which assessment cycle was {unit_ref} first classified {cat}?", "When did {unit_ref} first become {cat}?",
                         "Earliest assessment in which {unit_ref} appears as {cat}?"],
             "hindi": ["{unit_ref} पहली बार किस आकलन वर्ष में {cat} घोषित हुआ?", "{unit_ref} सबसे पहले कब {cat} हुआ?",
                       "किस आकलन में {unit_ref} पहली बार {cat} श्रेणी में आया?"],
             "hinglish": ["{unit_ref} pehli baar kis assessment mein {cat} hua?", "{unit_ref} sabse pehle kab {cat} bana?",
                          "{unit_ref} first time {cat} kab hua"],
             "tamil": ["எந்த மதிப்பீட்டு ஆண்டில் {unit_ref} முதன்முதலில் {cat} என வகைப்படுத்தப்பட்டது?",
                       "{unit_ref} முதன்முறையாக எப்போது {cat} நிலைக்கு வந்தது?",
                       "{unit_ref} {cat} ஆகக் காணப்படும் முதல் மதிப்பீடு எது?"]}),
    # ------------------------------------------------------------------ D4 multi-hop
    dict(id="transition_vs_state", difficulty="multi_hop", sampler="state_two_years_transition", n=8, shape="table", caveat=True,
         sql=("SELECT AVG(b.stage_of_extraction_pct), (SELECT sa.stage_of_extraction_pct FROM state_assessments sa "
              "JOIN states s2 ON s2.state_id = sa.state_id WHERE s2.state_name = '{s}' AND sa.assessment_year = '{yb}') "
              "FROM unit_assessments a JOIN unit_assessments b ON b.unit_id = a.unit_id JOIN assessment_units u ON u.unit_id = a.unit_id "
              "JOIN states s ON s.state_id = u.state_id WHERE s.state_name = '{s}' AND a.assessment_year = '{ya}' "
              "AND b.assessment_year = '{yb}' AND a.category = '{c}' AND b.category = '{c2}'"),
         templates={
             "english": ["For the {state} {utypes} that went from {cat} in {year_a} to {cat2} in {year_b}, what was their average stage of extraction in {year_b}, and how does it compare with {state}'s state-level figure that year?",
                         "Take {state}'s units that moved {cat} ({year_a}) to {cat2} ({year_b}). Give their mean {year_b} stage of extraction alongside the state's {year_b} stage of extraction.",
                         "Average {year_b} extraction stage of {state}'s {cat}-to-{cat2} movers ({year_a} to {year_b}) versus the whole state in {year_b}?"],
             "hindi": ["{state} के जो {utypes} {year_a} में {cat} थे और {year_b} में {cat2} हो गए, उनका {year_b} में औसत दोहन स्तर क्या था, और यह उस वर्ष के राज्य-स्तरीय स्तर से कैसे तुलना करता है?",
                       "{year_a} ({cat}) से {year_b} ({cat2}) बदली {state} की इकाइयों का {year_b} औसत दोहन स्तर और {year_b} में राज्य का दोहन स्तर बताइए।",
                       "{state} में {cat} से {cat2} ({year_a}→{year_b}) बनी इकाइयों का औसत {year_b} दोहन स्तर बनाम पूरे राज्य का?"],
             "hinglish": ["{state} ke jo {utypes} {year_a} mein {cat} the aur {year_b} mein {cat2} ho gaye, unka {year_b} mein average extraction stage kya tha aur state level figure se compare karo",
                          "{year_a} {cat} se {year_b} {cat2} wale {state} units ka avg {year_b} SoE aur state ka {year_b} SoE do",
                          "{state} {cat}->{cat2} movers ({year_a}-{year_b}) avg SoE vs state SoE {year_b}?"],
             "tamil": ["{year_a} இல் {cat} ஆக இருந்து {year_b} இல் {cat2} ஆன {state} {utypes} {year_b} இல் சராசரி எடுப்பு நிலை என்ன, அது அந்த ஆண்டின் மாநில அளவிலான எடுப்பு நிலையுடன் எப்படி ஒப்பிடுகிறது?",
                       "{year_a} ({cat}) இலிருந்து {year_b} ({cat2}) க்கு மாறிய {state} அலகுகளின் {year_b} சராசரி எடுப்பு நிலையையும் {year_b} மாநில எடுப்பு நிலையையும் தாருங்கள்.",
                       "{state} மாநிலத்தில் {cat}→{cat2} ({year_a}→{year_b}) மாறிய அலகுகளின் சராசரி {year_b} எடுப்பு நிலை எதிர் முழு மாநிலம்?"]}),
    dict(id="districts_majority_oe", difficulty="multi_hop", sampler="state_year_oe_rich", n=8, shape="table_ordered",
         sql=("WITH per AS (SELECT u.district_id, COUNT(*) AS n, SUM(ua.category = 'Over-Exploited') AS oe FROM unit_assessments ua "
              "JOIN assessment_units u ON u.unit_id = ua.unit_id JOIN states s ON s.state_id = u.state_id "
              "WHERE s.state_name = '{s}' AND ua.assessment_year = '{y}' GROUP BY u.district_id) "
              "SELECT d.district_name, da.extraction_total_ham FROM per JOIN districts d ON d.district_id = per.district_id "
              "JOIN district_assessments da ON da.district_id = per.district_id AND da.assessment_year = '{y}' "
              "WHERE per.oe * 2 > per.n ORDER BY da.extraction_total_ham DESC"),
         templates={
             "english": ["Which districts of {state} had more than half of their assessment units over-exploited {year}? Rank them by total groundwater extraction, with values.",
                         "{year}: districts in {state} where over-exploited units are the majority, ordered by district extraction (show extraction).",
                         "Find {state} districts with a majority of over-exploited units {year} and sort them by their total groundwater extraction."],
             "hindi": ["{year} {state} के किन ज़िलों में आधी से अधिक आकलन इकाइयाँ अति-दोहित थीं? उन्हें कुल भूजल दोहन के अनुसार क्रम में मान सहित बताइए।",
                       "{year} {state} के वे ज़िले जिनमें अधिकांश इकाइयाँ अति-दोहित थीं, ज़िला दोहन के क्रम में (मान सहित)?",
                       "{state} में {year} बहुसंख्यक अति-दोहित इकाइयों वाले ज़िले, कुल भूजल दोहन के अनुसार क्रमबद्ध?"],
             "hinglish": ["{year} {state} ke kaunse districts mein aadhe se zyada units over-exploited thi? unhe total extraction ke hisaab se rank karo values ke saath",
                          "{state} ke majority over-exploited wale districts {year}, extraction ke order mein", "{state} districts >50% OE units {year} sorted by extraction"],
             "tamil": ["{year} {state} மாநிலத்தின் எந்த மாவட்டங்களில் பாதிக்கு மேற்பட்ட அலகுகள் அதிகப்படியாக சுரண்டப்பட்டவை? மொத்த நிலத்தடி நீர் எடுப்பின்படி மதிப்புகளுடன் வரிசைப்படுத்துங்கள்.",
                       "{year}: பெரும்பான்மை அலகுகள் அதிகப்படியாக சுரண்டப்பட்ட {state} மாவட்டங்கள், மாவட்ட எடுப்பு வரிசையில் (மதிப்புடன்)?",
                       "{year} {state} மாநிலத்தில் பெரும்பான்மை அதிகப்படியாக சுரண்டப்பட்ட அலகுகள் கொண்ட மாவட்டங்களை மொத்த எடுப்பின்படி வரிசைப்படுத்துங்கள்."]}),
    dict(id="units_above_state_low_recharge", difficulty="multi_hop", sampler="state_year", n=8, shape="scalar",
         sql=(f"SELECT COUNT(*) FROM {UJ} WHERE s.state_name = '{{s}}' AND ua.assessment_year = '{{y}}' "
              "AND ua.stage_of_extraction_pct > (SELECT sa.stage_of_extraction_pct FROM state_assessments sa JOIN states s2 "
              "ON s2.state_id = sa.state_id WHERE s2.state_name = '{s}' AND sa.assessment_year = '{y}') "
              f"AND ua.annual_recharge_ham < (SELECT AVG(ua2.annual_recharge_ham) FROM unit_assessments ua2 JOIN assessment_units u2 "
              "ON u2.unit_id = ua2.unit_id JOIN states s3 ON s3.state_id = u2.state_id WHERE s3.state_name = '{s}' AND ua2.assessment_year = '{y}')"),
         templates={
             "english": ["{year}, how many {utypes} in {state} had a stage of extraction above the state-level figure while their annual recharge was below the state's unit average?",
                         "Count {state} units {year} that are both more stressed than the state as a whole (stage of extraction) and below-average in annual recharge.",
                         "In {state} {year}, number of units with SoE above the state's SoE and recharge below the mean unit recharge?"],
             "hindi": ["{year} {state} के कितने {utypes} का दोहन स्तर राज्य-स्तरीय स्तर से अधिक था और साथ ही उनका वार्षिक पुनर्भरण राज्य की इकाइयों के औसत से कम था?",
                       "{year} {state} की उन इकाइयों की संख्या जिनका दोहन स्तर पूरे राज्य से अधिक और पुनर्भरण औसत से कम था?",
                       "{state} में {year} राज्य से ज़्यादा दोहन स्तर और औसत से कम रिचार्ज वाली इकाइयाँ कितनी?"],
             "hinglish": ["{year} {state} ke kitne {utypes} ka extraction stage state level se zyada tha aur recharge state ki units ke average se kam?",
                          "{state} ki units {year} jinka SoE state se upar aur recharge average se neeche ho, kitni hai?",
                          "{state} {year}: SoE > state SoE aur recharge < avg unit recharge wale units count"],
             "tamil": ["{year} {state} மாநிலத்தில் மாநில அளவைவிட அதிக எடுப்பு நிலையும், மாநில அலகுகளின் சராசரியைவிடக் குறைந்த ஆண்டு செறிவூட்டலும் கொண்ட {utypes} எத்தனை?",
                       "{year} {state} மாநிலத்தில் மாநிலத்தை விட அதிக எடுப்பு நிலையும் சராசரிக்குக் குறைவான செறிவூட்டலும் கொண்ட அலகுகளை எண்ணுங்கள்.",
                       "{state} {year}: மாநில எடுப்பு நிலையை விட அதிகமும் சராசரி செறிவூட்டலை விடக் குறைவும் உள்ள அலகுகள் எத்தனை?"]}),
    dict(id="units_oe_all_years", difficulty="multi_hop", sampler="state_stable_all_years", n=6, shape="scalar", caveat=True,
         sql=(f"SELECT COUNT(*) FROM (SELECT ua.unit_id FROM {UJ} WHERE s.state_name = '{{s}}' GROUP BY ua.unit_id "
              "HAVING COUNT(DISTINCT ua.assessment_year) = 5 AND SUM(ua.category = 'Over-Exploited') = 5)"),
         templates={
             "english": ["How many {utypes} in {state} were over-exploited in every one of the five assessment cycles?",
                         "Number of {state} units classified over-exploited in all five assessments.", "Count {state}'s {utypes} that stayed over-exploited in every cycle from 2020 to 2025."],
             "hindi": ["{state} के कितने {utypes} पाँचों आकलन चक्रों में अति-दोहित रहे?", "सभी पाँच आकलनों में अति-दोहित रहीं {state} की इकाइयों की संख्या?",
                       "2020 से 2025 तक हर आकलन में अति-दोहित रहे {state} के {utypes} कितने?"],
             "hinglish": ["{state} ke kitne {utypes} paanchon assessment cycles mein over-exploited rahe?", "{state} ki units jo har cycle mein OE rahi, count?",
                          "2020 se 2025 tak har assessment mein over-exploited {state} {utypes} kitne"],
             "tamil": ["ஐந்து மதிப்பீட்டு சுழற்சிகள் அனைத்திலும் அதிகப்படியாக சுரண்டப்பட்ட நிலையில் இருந்த {state} {utypes} எத்தனை?",
                       "அனைத்து ஐந்து மதிப்பீடுகளிலும் அதிகப்படியாக சுரண்டப்பட்டவை என வகைப்படுத்தப்பட்ட {state} அலகுகளின் எண்ணிக்கை?",
                       "2020 முதல் 2025 வரை ஒவ்வொரு மதிப்பீட்டிலும் அதிகப்படியாக சுரண்டப்பட்டிருந்த {state} {utypes} எத்தனை?"]}),
    dict(id="state_largest_oe_decrease_stable", difficulty="multi_hop", sampler="two_years_any", n=4, shape="scalar", caveat=True,
         sql=("WITH c AS (SELECT u.state_id, ua.assessment_year AS y, SUM(ua.category = 'Over-Exploited') AS oe "
              "FROM unit_assessments ua JOIN assessment_units u ON u.unit_id = ua.unit_id "
              "WHERE ua.assessment_year IN ('{ya}', '{yb}') GROUP BY u.state_id, ua.assessment_year), "
              "stable AS (SELECT g.state_id FROM state_unit_granularity g WHERE g.assessment_year IN ('{ya}', '{yb}') "
              "GROUP BY g.state_id HAVING COUNT(DISTINCT REPLACE(g.unit_type, 'MANDAL', 'BLOCK')) = 1 AND COUNT(DISTINCT g.assessment_year) = 2) "
              "SELECT s.state_name FROM c a JOIN c b ON b.state_id = a.state_id AND a.y = '{ya}' AND b.y = '{yb}' "
              "JOIN stable ON stable.state_id = a.state_id JOIN states s ON s.state_id = a.state_id "
              "ORDER BY b.oe - a.oe ASC, s.state_name LIMIT 1"),
         templates={
             "english": ["Among states whose assessment-unit type did not change, which saw the largest drop in the number of over-exploited units between {year_a} and {year_b}?",
                         "Considering only states with unchanged unit granularity, which state reduced its over-exploited unit count the most from {year_a} to {year_b}?",
                         "Largest decrease in over-exploited units from {year_a} to {year_b}, restricted to states assessed with the same unit type in both years: which state?"],
             "hindi": ["जिन राज्यों की आकलन इकाई का प्रकार नहीं बदला, उनमें से {year_a} और {year_b} के बीच किस राज्य में अति-दोहित इकाइयों की संख्या सबसे अधिक घटी?",
                       "समान इकाई-प्रकार वाले राज्यों में {year_a} से {year_b} तक अति-दोहित इकाइयाँ सबसे ज़्यादा किसने कम कीं?",
                       "{year_a} से {year_b} तक अति-दोहित इकाइयों में सबसे बड़ी गिरावट वाला राज्य (केवल वही राज्य जिनका इकाई प्रकार दोनों वर्षों में समान रहा)?"],
             "hinglish": ["jin states ka unit type nahi badla, unme se {year_a} aur {year_b} ke beech kis state mein over-exploited units sabse zyada ghati?",
                          "same unit type wale states mein {year_a} se {year_b} OE units sabse zyada kisne kam ki?",
                          "OE units ka biggest drop {year_a}->{year_b}, sirf stable unit type states: kaunsa state?"],
             "tamil": ["மதிப்பீட்டு அலகு வகை மாறாத மாநிலங்களில், {year_a} மற்றும் {year_b} இடையே அதிகப்படியாக சுரண்டப்பட்ட அலகுகளின் எண்ணிக்கை மிக அதிகமாகக் குறைந்த மாநிலம் எது?",
                       "அலகு வகை மாறாத மாநிலங்களை மட்டும் கருதினால், {year_a} முதல் {year_b} வரை அதிகப்படியாக சுரண்டப்பட்ட அலகுகளை அதிகம் குறைத்த மாநிலம் எது?",
                       "{year_a} முதல் {year_b} வரை அதிகப்படியாக சுரண்டப்பட்ட அலகுகளில் மிகப்பெரிய வீழ்ச்சி கண்ட மாநிலம் (இரு ஆண்டுகளிலும் ஒரே அலகு வகை கொண்டவை மட்டும்)?"]}),
    dict(id="worsened_extraction_rise", difficulty="multi_hop", sampler="state_two_years_comparable", n=8, shape="list", caveat=True,
         sql=(f"SELECT u.unit_name FROM unit_assessments a JOIN unit_assessments b ON b.unit_id = a.unit_id "
              f"JOIN assessment_units u ON u.unit_id = a.unit_id JOIN states s ON s.state_id = u.state_id "
              f"WHERE s.state_name = '{{s}}' AND a.assessment_year = '{{ya}}' AND b.assessment_year = '{{yb}}' "
              f"AND {RANK.format(x='b.category')} > {RANK.format(x='a.category')} "
              "AND b.extraction_total_ham > a.extraction_total_ham * 1.10"),
         templates={
             "english": ["Which {utypes} in {state} fell into a worse category between {year_a} and {year_b} while their total extraction also grew by more than 10%?",
                         "List {state} units whose category worsened from {year_a} to {year_b} and whose groundwater extraction rose over 10 percent.",
                         "{state}: units with a deteriorating category ({year_a} to {year_b}) and >10% higher extraction?"],
             "hindi": ["{year_a} और {year_b} के बीच {state} के किन {utypes} की श्रेणी बिगड़ी और साथ ही कुल दोहन 10% से अधिक बढ़ा?",
                       "{state} की वे इकाइयाँ बताइए जिनकी श्रेणी {year_a} से {year_b} तक खराब हुई और भूजल दोहन दस प्रतिशत से ज़्यादा बढ़ा।",
                       "{state}: श्रेणी बिगड़ने ({year_a}→{year_b}) और 10% से अधिक दोहन वृद्धि वाले {utypes}?"],
             "hinglish": ["{year_a} aur {year_b} ke beech {state} ke kaunse {utypes} ki category kharab hui aur extraction bhi 10% se zyada badha?",
                          "{state} units jinki category {year_a} se {year_b} worse hui aur extraction das percent se upar badha",
                          "{state}: category worse + extraction >10% up ({year_a}->{year_b}) wale units"],
             "tamil": ["{year_a} மற்றும் {year_b} இடையே {state} மாநிலத்தின் எந்த {utypes} மோசமான வகைக்குச் சென்றதுடன் மொத்த எடுப்பும் 10% க்கு மேல் அதிகரித்தது?",
                       "{year_a} முதல் {year_b} வரை வகை மோசமடைந்து நிலத்தடி நீர் எடுப்பு பத்து சதவீதத்திற்கு மேல் உயர்ந்த {state} அலகுகளைப் பட்டியலிடுங்கள்.",
                       "{state}: வகை மோசமடைந்த ({year_a}→{year_b}) மற்றும் 10% க்கு மேல் எடுப்பு உயர்ந்த {utypes}?"]}),
    dict(id="units_above_district_soe", difficulty="multi_hop", sampler="district_year", n=8, shape="list",
         sql=(f"SELECT u.unit_name FROM {UJ} WHERE d.district_name = '{{d}}' AND s.state_name = '{{s}}' AND ua.assessment_year = '{{y}}' "
              "AND ua.stage_of_extraction_pct > (SELECT da.stage_of_extraction_pct FROM district_assessments da "
              "WHERE da.district_id = d.district_id AND da.assessment_year = '{y}')"),
         templates={
             "english": ["Which {utypes} of {district} district, {state}, had a stage of extraction above the district's own figure {year}?",
                         "List units in {district} ({state}) more stressed than the district as a whole {year}.",
                         "{year}, {district} district ({state}): units whose stage of extraction exceeds the district-level value?"],
             "hindi": ["{year} {state} के {district} ज़िले के किन {utypes} का दोहन स्तर ज़िले के अपने स्तर से अधिक था?",
                       "{district} ({state}) की वे इकाइयाँ जिनका दोहन स्तर {year} पूरे ज़िले से ज़्यादा था?",
                       "{year} {district} ज़िला ({state}): ज़िला-स्तरीय मान से अधिक दोहन स्तर वाले {utypes}?"],
             "hinglish": ["{year} {state} ke {district} district ke kaunse {utypes} ka SoE district ke overall SoE se zyada tha?",
                          "{district} ({state}) ki units jo {year} district se zyada stressed thi", "{district} {year}: units with SoE > district SoE ({state})"],
             "tamil": ["{year} {state} மாநிலத்தின் {district} மாவட்டத்தில் மாவட்ட அளவைவிட அதிக எடுப்பு நிலை கொண்ட {utypes} எவை?",
                       "{year} முழு மாவட்டத்தைவிட அதிக அழுத்தத்தில் இருந்த {district} ({state}) அலகுகளைப் பட்டியலிடுங்கள்.",
                       "{year} {district} மாவட்டம் ({state}): மாவட்ட அளவிலான மதிப்பை மீறிய எடுப்பு நிலை கொண்ட {utypes}?"]}),
    dict(id="compare_two_states_stress", difficulty="multi_hop", sampler="two_states_year", n=8, shape="table_ordered",
         sql=(f"SELECT s.state_name, 100.0 * SUM(ua.category IN ('Critical', 'Over-Exploited')) / COUNT(*) AS pct FROM {UJ} "
              "WHERE s.state_name IN ('{s}', '{s2}') AND ua.assessment_year = '{y}' GROUP BY s.state_name ORDER BY pct DESC"),
         templates={
             "english": ["{year}, which had a higher share of critical or over-exploited units: {state} or {state2}? Give both percentages.",
                         "Compare {state} and {state2} {year}: percentage of units that were critical or over-exploited.",
                         "Between {state} and {state2}, whose assessment units were more often critical/over-exploited {year} (show %)?"],
             "hindi": ["{year} {state} और {state2} में से किसमें गंभीर या अति-दोहित इकाइयों का प्रतिशत अधिक था? दोनों प्रतिशत बताइए।",
                       "{year} {state} और {state2} की तुलना: गंभीर या अति-दोहित इकाइयों का प्रतिशत?",
                       "{state} बनाम {state2}, {year} गंभीर/अति-दोहित इकाइयों का हिस्सा (%)?"],
             "hinglish": ["{year} {state} aur {state2} mein kiska critical ya over-exploited units ka share zyada tha? dono % batao",
                          "{state} vs {state2} {year}: critical + OE units ka percentage", "{state} ya {state2}, kaun zyada stressed tha {year} (critical/OE %)?"],
             "tamil": ["{year} {state} மற்றும் {state2} இல் எதில் அபாயகரமான அல்லது அதிகப்படியாக சுரண்டப்பட்ட அலகுகளின் பங்கு அதிகம்? இரண்டு சதவீதங்களையும் கூறுங்கள்.",
                       "{year} {state} மற்றும் {state2} ஒப்பீடு: அபாயகரமான அல்லது அதிகப்படியாக சுரண்டப்பட்ட அலகுகளின் சதவீதம்.",
                       "{state} எதிர் {state2}, {year} அபாயகரமான/அதிகப்படியாக சுரண்டப்பட்ட அலகுகளின் பங்கு (%)?"]}),
    dict(id="top_oe_districts_irrigation", difficulty="multi_hop", sampler="state_year_oe_rich", n=6, shape="scalar",
         sql=("WITH top3 AS (SELECT u.district_id, COUNT(*) AS oe FROM unit_assessments ua JOIN assessment_units u ON u.unit_id = ua.unit_id "
              "JOIN states s ON s.state_id = u.state_id WHERE s.state_name = '{s}' AND ua.assessment_year = '{y}' "
              "AND ua.category = 'Over-Exploited' GROUP BY u.district_id ORDER BY oe DESC, u.district_id LIMIT 3) "
              "SELECT d.district_name FROM top3 JOIN district_assessments da ON da.district_id = top3.district_id AND da.assessment_year = '{y}' "
              "JOIN districts d ON d.district_id = top3.district_id "
              "ORDER BY da.extraction_irrigation_ham / da.extraction_total_ham DESC LIMIT 1"),
         templates={
             "english": ["Of the three {state} districts with the most over-exploited units {year}, which has the highest share of groundwater extraction going to irrigation?",
                         "{year}: take {state}'s top 3 districts by number of over-exploited units; which of them relies most on irrigation extraction (as a share of total extraction)?",
                         "Among the 3 districts of {state} with the largest over-exploited unit counts {year}, which has the greatest irrigation share of extraction?"],
             "hindi": ["{year} {state} के सबसे अधिक अति-दोहित इकाइयों वाले तीन ज़िलों में से किसमें कुल दोहन में सिंचाई का हिस्सा सबसे अधिक है?",
                       "{year}: अति-दोहित इकाइयों की संख्या के आधार पर {state} के शीर्ष 3 ज़िलों में से कौन सिंचाई दोहन पर सबसे अधिक निर्भर है?",
                       "{state} के सबसे ज़्यादा अति-दोहित इकाइयों वाले 3 ज़िलों ({year}) में सिंचाई का सबसे बड़ा हिस्सा किसका?"],
             "hinglish": ["{year} {state} ke sabse zyada over-exploited units wale teen districts mein se kiska irrigation share sabse zyada hai?",
                          "{state} ke top 3 OE districts {year} mein kaunsa irrigation pe sabse zyada depend karta hai?",
                          "{state} top-3 OE districts {year}, highest irrigation share wala district?"],
             "tamil": ["{year} அதிகப்படியாக சுரண்டப்பட்ட அலகுகள் அதிகமுள்ள {state} மாநிலத்தின் மூன்று மாவட்டங்களில், மொத்த எடுப்பில் பாசனத்தின் பங்கு அதிகமுள்ளது எது?",
                       "{year}: அதிகப்படியாக சுரண்டப்பட்ட அலகுகளின் எண்ணிக்கையில் {state} இன் முதல் 3 மாவட்டங்களில் பாசன எடுப்பை அதிகம் சார்ந்திருப்பது எது?",
                       "{state} இன் அதிக அதிகப்படியாக சுரண்டப்பட்ட அலகுகள் கொண்ட 3 மாவட்டங்களில் ({year}) பாசனப் பங்கு அதிகமுள்ள மாவட்டம்?"]}),
]
