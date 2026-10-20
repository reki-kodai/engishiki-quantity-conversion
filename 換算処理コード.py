
from lxml import etree
from collections import defaultdict
import os
import math
import re
import sys

# =========================================
# XMLファイル入力
# =========================================

# コマンドライン引数で3つのパスを渡すと、入力を求めずに実行する
#   python 換算処理コード.py <XML> <taxonomy XML> <保存先フォルダ>
# 引数が無い場合は従来どおり入力を求める（何も入力せずEnterで、本コードと同じフォルダのファイルを使う）

script_dir = os.path.dirname(os.path.abspath(__file__))

default_paths = [
    os.path.join(script_dir, "engishiki_v24.xml"),
    os.path.join(script_dir, "engishiki_taxonomy_standoff_master.xml"),
    script_dir,
]


def ask_path(message, default):
    value = input(
        f"{message}（Enterで {default}）: "
    ).strip().strip('"').strip("'")
    return value or default


if len(sys.argv) == 4:
    xml_path, taxonomy_path, output_dir = sys.argv[1:4]
else:
    xml_path = ask_path(
        "XMLファイルのパスを入力してください", default_paths[0]
    )
    taxonomy_path = ask_path(
        "taxonomy XMLファイルのパスを入力してください", default_paths[1]
    )
    output_dir = ask_path(
        "結果の保存先フォルダのパスを入力してください", default_paths[2]
    )

os.makedirs(output_dir, exist_ok=True)

if not os.path.exists(xml_path):
    raise FileNotFoundError(
        f"ファイルが見つかりません: {xml_path}"
    )


# =========================================
# XML読み込み
# =========================================

tree = etree.parse(xml_path)
root = tree.getroot()

taxonomy_tree = etree.parse(taxonomy_path)
taxonomy_root = taxonomy_tree.getroot()

# TEI namespace
ns = {
    "tei": "http://www.tei-c.org/ns/1.0"
}

# =========================================
# 特殊単位対応
# =========================================
SPECIAL_EQUIVALENT_UNITS = {
    "#口": "#合_set",
    "#合_set": "#口"
}

# =========================================
# taxonomy取得
# =========================================

taxonomy_map = {}

taxonomies = taxonomy_root.xpath(
    './/tei:taxonomy',
    namespaces=ns
)

for tax in taxonomies:

    xml_id = tax.get(
        "{http://www.w3.org/XML/1998/namespace}id"
    )

    if not xml_id:
        continue

    name_el = tax.find(
        "./tei:desc/tei:name",
        namespaces=ns
    )

    if name_el is None:
        continue

    taxonomy_map[f"#{xml_id}"] = (
        "".join(name_el.itertext()).strip()
    )

# =========================================
# 国一覧取得
# =========================================

places = taxonomy_root.xpath(
    ".//tei:place",
    namespaces=ns
)

country_ids = set()
place_ids = set()

for place in places:

    xml_id = place.get(
        "{http://www.w3.org/XML/1998/namespace}id"
    )

    if not xml_id:
        continue

    token = f"#{xml_id}"

    # placeとして存在するID
    place_ids.add(token)

    # regionを持つplaceのみ令制国として登録
    if place.find("tei:region", namespaces=ns) is not None:
        country_ids.add(token)

def tokenize_corresp(corresp):

    if not corresp:
        return []

    return corresp.split()

# =========================================
# relation(active→passive)取得
# =========================================

relation_map = defaultdict(list)

relations = taxonomy_root.xpath(
    ".//tei:standOff//tei:relation",
    namespaces=ns
)

for rel in relations:

    active = rel.get("active")
    passive = rel.get("passive")

    if not (active and passive):
        continue

    for token in tokenize_corresp(passive):

        if token in place_ids:
            relation_map[active].append(token)
    
# =========================================
# unit conversion 抽出
# =========================================

conversion_map = defaultdict(list)

unit_defs = root.xpath(
    './/tei:unitDef',
    namespaces=ns
)

for ud in unit_defs:

    conversions = ud.xpath(
        './tei:conversion',
        namespaces=ns
    )

    for conv in conversions:

        from_unit = conv.get("fromUnit")
        to_unit = conv.get("toUnit")
        formula = conv.get("formula")

        if not (from_unit and to_unit and formula):
            continue

        m = re.search(
            r"\$fromUnit\s*\*\s*([0-9.]+)",
            formula
        )

        if not m:
            raise ValueError(
                f"未対応の conversion 式: {formula}"
            )

        factor = float(m.group(1))

        conversion_map[from_unit].append({
            "to": to_unit,
            "factor": factor
        })


# =========================================
# utility
# =========================================

def is_country(token):

    return token in country_ids


def apply_formula(quantity, formula):

    if formula is None:
        return None

    formula = formula.strip()

    formula = formula.replace("div", "/")

    if "x" not in formula:

        expr = f"{quantity} {formula}"

    else:

        expr = formula.replace(
            "x",
            str(quantity)
        )

    try:
        return eval(expr)

    except Exception as e:

        print("計算失敗")
        print(expr)
        print(e)

        return None


def convert_unit(
    value,
    from_unit,
    target_unit,
    conversion_map
):

    if from_unit == target_unit:
        return value                     

    queue = [(value, from_unit)]

    visited = set()

    while queue:

        current_value, current_unit = queue.pop(0)

        if current_unit in visited:
            continue

        visited.add(current_unit)

        # -----------------------------
        # 正方向探索
        # -----------------------------
        for conv in conversion_map.get(
            current_unit,
            []
        ):

            next_unit = conv["to"]

            next_value = (
                current_value
                * conv["factor"]
            )

            if next_unit == target_unit:
                return next_value

            queue.append(
                (
                    next_value,
                    next_unit
                )
            )

        # -----------------------------
        # 逆方向探索
        # -----------------------------
        for source_unit, conversions in conversion_map.items():

            for conv in conversions:

                if conv["to"] != current_unit:
                    continue

                next_value = (
                    current_value
                    / conv["factor"]
                )

                if source_unit == target_unit:
                    return next_value

                queue.append(
                    (
                        next_value,
                        source_unit
                    )
                )

    return None

def split_tei_result(value):

    if value is None:
        return (0, 0)
    
    # 0以上1未満は特例
    if 0 < value < 1:

        if abs(value - 0.5) < 0.000001:
            return (0, 1)

        return (1, 0)

    integer_part = math.floor(value)

    decimal = value - integer_part

    if abs(decimal - 0.5) < 0.000001:

        return (
            integer_part,
            1
        )

    return (
        integer_part,
        0
    )
def evaluate_rule(
    rule,
    rule_unit,
    country,
    measure_units,
    conversion_map
):
    

    # ---------------------------------
    # 国条件
    # ---------------------------------

    country_rejected = False

    if rule["countries"]:

        if country in rule["countries"]:
            country_result = "一致"

        else:
            country_result = "除外"
            country_rejected = True

    else:
        country_result = "適合"

    # ---------------------------------
    # 単位条件
    # ---------------------------------

    usable_units = []
    rejected_units = []

    has_exact = False
    has_conversion = False
    has_special = False

    for mu in measure_units:

        # 完全一致
        if mu == rule_unit:

            usable_units.append(mu)
            has_exact = True
            continue

        # conversion
        converted = convert_unit(
            1,
            mu,
            rule_unit,
            conversion_map
        )

        if converted is not None:

            usable_units.append(mu)
            has_conversion = True
            continue

        # 特殊同値
        if (
            SPECIAL_EQUIVALENT_UNITS.get(mu)
            == rule_unit
        ):

            usable_units.append(mu)
            has_special = True
            continue
        
        rejected_units.append(mu)


    # ---------------------------------
    # match_type決定
    # ---------------------------------

    if has_conversion:
        match_type = "conversion"

    elif has_special and not has_exact:
        match_type = "special"

    elif has_exact:
        match_type = "exact"

    else:
        match_type = None
    

    # 全部NG
    if len(usable_units) == 0:

        output_log(
            f"[RULE REJECT] "
            f"rule={rule['rule_id']} "
            f"unit mismatch "
            f"measure_units={measure_units} "
            f"rule_unit={rule_unit}"
        )

        return None

    output_log(
        f"[RULE PASS] "
        f"rule={rule['rule_id']} "
        f"usable={usable_units} "
        f"rejected={rejected_units}"
    )

    return {
        "usable_units": usable_units,
        "rejected_units": rejected_units,
        "match_type": match_type,

        "country_result": country_result,

        "unit_result":
            "完全一致"
            if match_type == "exact"
            else "変換可能"
            if match_type == "conversion"
            else "特殊同値",
        
        "rejected": country_rejected
    }

# =========================================
# calculationRule 抽出
# =========================================

rules = []

notes = root.xpath(
    './/tei:note[@type="calculationRule"]',
    namespaces=ns
)

for note in notes:

    countries = []

    expanded = []

    for token in tokenize_corresp(note.get("corresp")):

        # token自身が国ならそのまま採用
        if is_country(token):
            expanded.append(token)

        # 国でなければrelationを利用して展開
        elif token in relation_map:
            expanded.extend([
                x for x in relation_map[token]
                if is_country(x)
            ])

    countries = [
        x for x in expanded
        if is_country(x)
    ]

    
    targets = tokenize_corresp(
        note.get("target")
    )

    unit_el = note.find(
        "tei:unit",
        namespaces=ns
    )

    rule_unit = None

    if unit_el is not None:
        rule_unit = unit_el.get("unitRef")


    formula_el = note.find(
        "tei:formula",
        namespaces=ns
    )

    formula = None

    if formula_el is not None:

        formula = "".join(
            formula_el.itertext()
        ).strip()

    rules.append({
        "rule_id": len(rules),
        "corresp": note.get("corresp"),
        "targets": targets,
        "countries": countries,
        "unit": rule_unit,
        "formula": formula
    })


# =========================================
# actual measure / measureGrp 抽出
# ana="#調" 限定
# =========================================

country_data = defaultdict(list)

targets = root.xpath(
    './/tei:measure[@type="actual"]'
    '[contains(concat(" ", normalize-space(@ana), " "), " #調 ")] | '
    './/tei:measureGrp[@type="actual"]'
    '[contains(concat(" ", normalize-space(@ana), " "), " #調 ")]',
    namespaces=ns
)

for target in targets:

    corresp = tokenize_corresp(
        target.get("corresp")
    )

    # correspには国だけ
    countries = corresp
    # commodityには物品IDだけ
    commodity = target.get("commodity")

    countries = [
        x for x in corresp
        if is_country(x)
    ]


    item_ids = tokenize_corresp(commodity)

    nested_measures = target.xpath(
        './/tei:measure[@quantity][not(@type="supplement")][not(ancestor::tei:measure[@type="supplement"])][not(ancestor::tei:measureGrp[@type="supplement"])]',
        namespaces=ns
    )
        

    measure_data = []

    for nm in nested_measures:

        quantity = nm.get("quantity")

        # -----------------------------
        # quantity欠落
        # -----------------------------

        if quantity is None:

            measure_data.append({
                "quantity": None,
                "unitRef": None,
                "status": "quantity_missing"
            })

            continue

        try:

            quantity = float(quantity)

        except:

            measure_data.append({
                "quantity": None,
                "unitRef": None,
                "status": "quantity_parse_failed"
            })

            continue

        unit_el = nm.find(
            ".//tei:unit",
            namespaces=ns
        )
                
        unit_ref = None

        if unit_el is not None:

            unit_ref = unit_el.get("unitRef")

        # -----------------------------
        # unit欠落
        # -----------------------------

        if unit_ref is None:

            measure_data.append({
                "quantity": quantity,
                "unitRef": None,
                "status": "unit_missing"
            })

            continue

        measure_data.append({
            "quantity": quantity,
            "unitRef": unit_ref,
            "status": "ok"
        })
                                                
    for country in countries:


        country_data[country].append({
            "item_ids": item_ids,
            "measures": measure_data
        })


# =========================================
# 集計
# =========================================

country_total_sum = defaultdict(int)

country_next_count = defaultdict(int)

rule_usage = defaultdict(int)

rule_quantity_missing = defaultdict(int)

country_results = defaultdict(list)

summary_path = os.path.join(
    output_dir,
    "結果（国別集計）.txt"
)

rule_path = os.path.join(
    output_dir,
    "結果（rule確認）.txt"
)

log_path = os.path.join(
    output_dir,
    "結果（ログ）.txt"
)

summary_out = open(summary_path, "w", encoding="utf-8")
rule_out = open(rule_path, "w", encoding="utf-8")
log_out = open(log_path, "w", encoding="utf-8")

def output_summary(*args):
    text = " ".join(str(a) for a in args)
    summary_out.write(text + "\n")


def output_rule(*args):
    text = " ".join(str(a) for a in args)
    rule_out.write(text + "\n")

def output_log(*args):
    text = " ".join(str(a) for a in args)
    log_out.write(text + "\n")

# =========================================
# rule適用
# =========================================

for country, items in country_data.items():

    for item in items:

        item["rule_check"] = []

        measures = item["measures"]

        commodity_names = [
            taxonomy_map.get(cid, cid)
            for cid in item["item_ids"]
        ]

        commodity_name = ", ".join(commodity_names)

        raw_quantity = 0
        raw_units = set()

        for m in measures:

            if m["quantity"] is not None:
                raw_quantity += m["quantity"]

            if m["unitRef"] is not None:
                raw_units.add(m["unitRef"])

        raw_unit_text = ",".join(sorted(raw_units))

        for item_id in item["item_ids"]:
            
            # ---------------------------------
            # rule候補抽出
            # ---------------------------------

            id_rules = []

            for rule in rules:

                if item_id in rule["targets"]:
                    id_rules.append(rule)
            
            id_rule_count = len(id_rules)

            output_log("")
            output_log("==============================")
            output_log("[RULE SEARCH]")
            output_log(f"country={country}")

            output_log(f"hit rules={len(id_rules)}")

            for r in id_rules:

                output_log(
                    f"rule_id={r['rule_id']} "
                    f"corresp={r['corresp']} "
                    f"targets={' '.join(r['targets'])} "
                    f"unit={r['unit']} "
                    f"countries={r['countries']}"
                )

            # ---------------------------------
            # 数量欠落チェック
            # ---------------------------------

            if all(
                m["quantity"] is None
                for m in measures
            ):
                # -----------------------------
                # IDからrule候補あり
                # -----------------------------
                if len(id_rules) > 0:

                    candidate_rules = [
                        {
                            "rule_id": r["rule_id"],
                            "target_unit": r["unit"]
                        }
                        for r in id_rules
                    ]

                    #原則式数のない国を除く
                    EXCLUDED_COUNTRIES = {
                        "#志摩国",
                        "#若狭国",
                        "#隠伎国",
                        "#出羽国",
                        "#越後国",
                        "#佐渡国",
                        "#石見国",
                        "#長門国",
                        "#大隅国",
                        "#対馬島"  
                    }

                    for rc in candidate_rules:
                        if country not in EXCLUDED_COUNTRIES:
                            rule_quantity_missing[rc["rule_id"]] += 1

                    status = "quantity_missing"

                    message = (
                        "候補ruleはあるが、"
                        "数量・単位の記載がないためruleの採用は不可"
                    )

                # -----------------------------
                # IDからrule候補なし
                # -----------------------------
                else:

                    candidate_rules = []

                    status = "id_not_found"

                    message = (
                        f"{item_id} を含む calculationRule が存在しない"
                    )

                country_results[country].append({

                    "item_id": item_id,

                    "commodity": commodity_name,

                    "original_measures": [
                        {
                            "quantity": m["quantity"],
                            "unitRef": m["unitRef"]
                        }
                        for m in measures
                    ],

                    "id_rule_count": id_rule_count,

                    "candidate_rules": candidate_rules,

                    "quantity": None,

                    "unit": raw_unit_text,

                    "target_unit": None,

                    "formula": None,

                    "result": None,

                    "status": status,

                    "message": message,

                    "rule_check": item["rule_check"]

                })

                continue

            # ---------------------------------
            # ID不一致
            # ---------------------------------

            if len(id_rules) == 0:

                country_results[country].append({
                    "item_id": item_id,
                    "commodity": commodity_name,
                    "original_measures": [
                        {
                            "quantity": m["quantity"],
                            "unitRef": m["unitRef"]
                        }
                        for m in measures
                    ],
                    "id_rule_count": id_rule_count,
                    "quantity": raw_quantity,
                    "unit": raw_unit_text,
                    "formula": None,
                    "result": None,
                    "status": "id_not_found",
                    "message":
                        f"{item_id} を含む calculationRule が存在しない",
                    "rule_check": item["rule_check"]
                })

                continue

            # ---------------------------------
            # 単位候補取得
            # ---------------------------------

            unit_candidates = []

            for rule in id_rules:

                if rule["unit"] is not None:
                    unit_candidates.append(
                        (rule, rule["unit"])
                    )

            # ---------------------------------
            # 本文単位一覧
            # ---------------------------------

            measure_units = set()

            for m in measures:

                if m["unitRef"] is not None:
                    measure_units.add(
                        m["unitRef"]
                    )

            # ---------------------------------
            # 国別rule優先
            # ---------------------------------

            candidate_rules = []

            for rule, rule_unit in unit_candidates:

                result = evaluate_rule(
                    rule,
                    rule_unit,
                    country,
                    measure_units,
                    conversion_map
                )

                # 単位不一致
                if result is None:

                    rule_info = {
                        "rule_id": rule["rule_id"],
                        "target_unit": rule_unit,
                        "country_result": "適合",
                        "unit_result": "除外"
                    }

                    item["rule_check"].append(rule_info)

                    continue

                # 国指定あり ＆ 現在国が一致
                if result["country_result"] == "一致":

                    country_result = "一致"

                elif result["country_result"] == "除外":

                    country_result = "除外"

                else:

                    country_result = "適合"


                rule_info = {
                    "rule_id": rule["rule_id"],
                    "target_unit": rule_unit,
                    "country_result": country_result,
                    "unit_result": result["unit_result"]
                }

                item["rule_check"].append(rule_info)

                if result.get("rejected"):
                    continue

                candidate_rules.append({
                    "rule": rule,
                    "target_unit": rule_unit,
                    "usable_units": result["usable_units"],
                    "rejected_units": result["rejected_units"],
                    "match_type": result["match_type"]
                })

            output_log("")
            output_log("=== rule candidates ===")

            for c in candidate_rules:

                output_log(
                    f"rule={c['rule']['rule_id']}",
                    f"target={c['target_unit']}",
                    f"usable={c['usable_units']}",
                    f"rejected={c['rejected_units']}"
                )
            # ---------------------------------
            # 国一致ruleを優先
            # ---------------------------------

            country_rules = [

                c

                for c in candidate_rules

                if c["rule"]["countries"]
                and country in c["rule"]["countries"]

            ]

            if country_rules:

                candidate_rules = country_rules

            if len(candidate_rules) == 0:

                country_results[country].append({
                    "item_id": item_id,
                    "commodity": commodity_name,
                    "original_measures": [
                        {
                            "quantity": m["quantity"],
                            "unitRef": m["unitRef"]
                        }
                        for m in measures
                    ],
                    "id_rule_count": id_rule_count,
                    "quantity": raw_quantity,
                    "unit": raw_unit_text,
                    "formula": None,
                    "result": None,
                    "status": "rule_not_found",
                    "message": "適用可能なruleなし",
                    "rule_check": item["rule_check"]
                })

                continue 
            
            # ---------------------------------
            # 完全一致 > conversion > 特殊同値
            # ---------------------------------

            exact_rules = [
                c for c in candidate_rules
                if c["match_type"] == "exact"
            ]

            if exact_rules:
                candidate_rules = exact_rules

            else:

                conversion_rules = [
                    c for c in candidate_rules
                    if c["match_type"] == "conversion"
                ]

                if conversion_rules:
                    candidate_rules = conversion_rules

            # ---------------------------------
            # 候補数判定
            # ---------------------------------

            # 候補が複数ある場合
            if len(candidate_rules) > 1:

                candidate_rule_ids = [

                    x["rule"]["rule_id"]

                    for x in candidate_rules
                ]

                candidate_target_units = [

                    x["target_unit"]

                    for x in candidate_rules
                ]

                country_results[country].append({

                    "item_id": item_id,

                    "commodity": commodity_name,
                    "original_measures": [
                        {
                            "quantity": m["quantity"],
                            "unitRef": m["unitRef"]
                        }
                        for m in measures
                    ],
                    "id_rule_count": id_rule_count,
                    "quantity": raw_quantity,

                    "unit": raw_unit_text,

                    "formula": None,

                    "result": None,

                    "candidate_rule_ids": candidate_rule_ids,

                    "candidate_target_units": candidate_target_units,

                    "rule_candidate_count": len(candidate_rules),

                    "status": "rule_ambiguous",

                    "message": (
                        "適用可能な calculationRule が複数存在します"
                    ),
                    "rule_check": item["rule_check"]

                })

                output_log(

                    f"[RULE AMBIGUOUS] "

                    f"item={item_id} "

                    f"rules={candidate_rule_ids}"

                )

                continue


            # ---------------------------------
            # 候補1件
            # ---------------------------------

            selected = candidate_rules[0]

            matched_rule = selected["rule"]

            target_unit = selected["target_unit"]

            usable_units = selected["usable_units"]

            rejected_units = selected["rejected_units"]

            output_log(

                f"[RULE SELECT] "

                f"item={item_id} "

                f"rule={matched_rule['rule_id']} "

                f"target_unit={target_unit}"

            )
            

            # ---------------------------------
            # 単位統一
            # ---------------------------------
            processed_measures = []

            total_quantity = 0

            for m in measures:

                # measure自体の解析失敗
                if m["status"] != "ok":

                    processed_measures.append({
                        "measure": m,
                        "success": False,
                        "reason": m["status"]
                    })

                    continue

                q = m["quantity"]
                u = m["unitRef"]

                # -----------------------------
                # フィルター段階で除外された単位
                # -----------------------------
                if u in rejected_units:

                    processed_measures.append({
                        "measure": m,
                        "success": False,
                        "reason": "unit_conversion_failed"
                    })

                    continue

                # -----------------------------
                # 使用可能単位だけ変換
                # -----------------------------
                converted = convert_unit(
                    q,
                    u,
                    target_unit,
                    conversion_map
                )

                if converted is None:

                    # 特殊同値
                    if (
                        SPECIAL_EQUIVALENT_UNITS.get(u)
                        == target_unit
                    ):
                        converted = q
                    else:
                        processed_measures.append({
                            "measure": m,
                            "success": False,
                            "reason": "unit_conversion_failed"
                        })
                        

                        continue

                processed_measures.append({
                    "measure": m,
                    "success": True,
                    "converted": converted
                })

                total_quantity += converted


            success_count = sum(
                1
                for x in processed_measures
                if x["success"]
            )

            if success_count == len(processed_measures):

                conversion_status = "ok"

            elif success_count == 0:

                conversion_status = "unit_conversion_failed"

            else:

                conversion_status = "partial_conversion"

            if conversion_status == "unit_conversion_failed":

                for pm in processed_measures:

                    if pm["success"]:
                        continue

                    m = pm["measure"]

                    country_results[country].append({
                        "item_id": item_id,
                        "commodity": commodity_name,
                        "original_measures": [
                            {
                                "quantity": m["quantity"],
                                "unitRef": m["unitRef"]
                            }
                            for m in measures
                        ],
                        "id_rule_count": id_rule_count,
                        "quantity": m["quantity"],
                        "unit": m["unitRef"],
                        "formula": None,
                        "result": None,
                        "status": pm["reason"],
                        "message": (
                            "measure解析失敗"
                            if pm["reason"] != "unit_conversion_failed"
                            else f"{m['unitRef']} → {target_unit} に変換できません"
                        ),
                        "rule_check": item["rule_check"]
                    })

                continue

            # ---------------------------------
            # formula適用
            # ---------------------------------

            formula = matched_rule["formula"]

            calc_value = apply_formula(
                total_quantity,
                formula
            )

            if calc_value is None:

                country_results[country].append({
                    "item_id": item_id,
                    "commodity": commodity_name,
                    "original_measures": [
                        {
                            "quantity": m["quantity"],
                            "unitRef": m["unitRef"]
                        }
                        for m in measures
                    ],
                    "id_rule_count": id_rule_count,
                    "quantity": total_quantity,
                    "unit": target_unit,
                    "formula": formula,
                    "result": None,
                    "status": "formula_failed",
                    "message": "formula計算失敗",
                    "rule_check": item["rule_check"]
                    
                })

                continue

            # ---------------------------------
            # 正常処理
            # ---------------------------------

            main_count, next_count = (
                split_tei_result(calc_value)
            )

            country_total_sum[country] += (
                main_count
            )

            country_next_count[country] += (
                next_count
            )

            rule_usage[
                matched_rule["rule_id"]
            ] += 1

            result_text = f"正丁{main_count}"

            if next_count:
                result_text += (
                    f" + 次丁{next_count}"
                )

            country_results[country].append({
                "item_id": item_id,
                "commodity": commodity_name,
                "original_measures": [
                    {
                        "quantity": m["quantity"],
                        "unitRef": m["unitRef"]
                    }
                    for m in measures
                ],
                "id_rule_count": id_rule_count,
                "quantity": total_quantity,
                "unit": raw_unit_text,
                "target_unit": target_unit,
                "rule_id": matched_rule["rule_id"],
                "formula": formula,
                "result": calc_value,
                "formatted_result": result_text,
                "candidate_rule_ids": [matched_rule["rule_id"]],
                "status": conversion_status, 
                "message": "正常処理",
                "rule_check": item["rule_check"]
                
            })

            if conversion_status == "partial_conversion":

                for pm in processed_measures:

                    if pm["success"]:
                        continue

                    m = pm["measure"]

                    country_results[country].append({
                        "item_id": item_id,
                        "commodity": commodity_name,
                        "original_measures": [
                            {
                                "quantity": m["quantity"],
                                "unitRef": m["unitRef"]
                            }
                            for m in measures
                        ],
                        "id_rule_count": id_rule_count,
                        "quantity": m["quantity"],
                        "unit": m["unitRef"],
                        "formula": None,
                        "result": None,
                        "status": pm["reason"],
                        "message":
                            f"{m['unitRef']} → {target_unit} に変換できません"
                            if pm["reason"] == "unit_conversion_failed"
                            else "measure解析失敗",
                        "rule_check": item["rule_check"]
                    })

                    



# =========================================
# 出力
# =========================================

output_summary("========================================")
output_summary("国別 集計結果")
output_summary("========================================")

for country, records in country_results.items():

    output_summary("\n")
    output_summary("=" * 60)
    output_summary(f"#{country}")
    output_summary("=" * 60)

    for r in records:

        output_summary(f"物品ID: {r['item_id']}")
        output_summary(f"物品名: {r.get('commodity')}")
        measure_text = " ".join(
            f"{m['quantity']} ({m['unitRef']})"
            for m in r.get("original_measures", [])
        )
        output_summary(f"数量: {measure_text}")
        output_summary(f"候補数: {r.get('id_rule_count')}")
        output_summary("候補rule") 

        # -----------------------------
        # 候補rule一覧表示
        # -----------------------------
        if "candidate_rules" in r:

            for rc in r.get("candidate_rules", []):

                output_summary(
                    f"  Rule{rc['rule_id']} "
                    f"({rc['target_unit']})"
                )

        # -----------------------------
        # 通常処理
        # -----------------------------
        else:

            for rc in r.get("rule_check", []):

                if rc["unit_result"] is None:

                    unit_text = ""

                elif rc["unit_result"] == "除外":

                    unit_text = "　単位：除外"

                else:

                    unit_text = (
                        f"　単位：適合（{rc['unit_result']}）"
                    )

                output_summary(
                    f"  Rule{rc['rule_id']} "
                    f"({rc['target_unit']})"
                    f"　国：{rc['country_result']}"
                    f"{unit_text}"
                )
        output_summary(f"採用rule: {r.get('rule_id')}")
        output_summary(f"formula: {r['formula']}")
        output_summary(
            f"計算結果(原値): "
            f"{r['result']}"
        )

        output_summary(
            f"丁換算: "
            f"{r.get('formatted_result')}"
        )
        output_summary(f"status: {r['status']}")
        output_summary(f"message: {r['message']}")

        output_summary("-" * 40)

    output_summary(
        f"正丁: "
        f"{country_total_sum[country]}"
    )

    output_summary(
        f"次丁: "
        f"{country_next_count[country]}"
    )

    output_summary("=" * 60)


# =========================================
# calculationRule 使用頻度
# =========================================

output_rule("========================================")
output_rule("calculationRule 使用頻度")
output_rule("========================================")

for rule in rules:

    rule_id = rule["rule_id"]

    # noun系ID取得
    item_names = []

    for token in rule["targets"]:

        if token.startswith("#noun"):

            item_names.append(
                taxonomy_map.get(token, token)
            )

    output_rule("\n")
    output_rule(f"Rule ID: {rule_id}")

    output_rule(
            f"countries: {' '.join(rule['countries'])}  "
            f"targets: {' '.join(rule['targets'])}  "
            f"unit: {rule['unit']}  "

    )

    if item_names:

        output_rule(
            f"物品名: "
            f"{', '.join(item_names)}"
        )

    output_rule(f"formula: {rule['formula']}")

    output_rule(
        f"実際の使用回数: "
        f"{rule_usage[rule_id]}"
    )

    output_rule(
        "数量・単位欠落で未使用: "
        f"{rule_quantity_missing[rule_id]}"
    )

    output_rule(
        "潜在的使用回数: "
        f"{rule_usage[rule_id] + rule_quantity_missing[rule_id]}"
    )

unused_rule_count = 0

for rule in rules:

    rule_id = rule["rule_id"]

    if (
        rule_usage[rule_id]
        + rule_quantity_missing[rule_id]
    ) == 0:
        unused_rule_count += 1

output_rule("\n")
output_rule("========================================")
output_rule("未使用 calculationRule")
output_rule("========================================")
output_rule(
    f"潜在的にも使用の可能性が0だったrule数: "
    f"{unused_rule_count}"
)

summary_out.close()
rule_out.close()
log_out.close()

print(f"\n結果を保存しました：{summary_path}")
print(f"結果を保存しました：{rule_path}")
print(f"結果を保存しました：{log_path}")