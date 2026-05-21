from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Range:
    lo: int
    hi: int

    def contains(self, x: int) -> bool:
        return self.lo <= x <= self.hi


@dataclass(frozen=True)
class Standards:
    far_binocular_required: bool = True
    far_va_be_min: Optional[int] = None
    far_va_re_min: Optional[int] = None
    far_va_le_min: Optional[int] = None
    far_stereo_min: Optional[int] = None
    far_color_min_correct: Optional[int] = None
    far_vphoria_range: Optional[Range] = None
    far_lphoria_range: Optional[Range] = None

    near_binocular_required: bool = True
    near_va_be_min: Optional[int] = None
    near_va_re_min: Optional[int] = None
    near_va_le_min: Optional[int] = None
    near_vphoria_range: Optional[Range] = None
    near_lphoria_range: Optional[Range] = None

    inter_va_be_min: Optional[int] = None
    inter_va_re_min: Optional[int] = None
    inter_va_le_min: Optional[int] = None


VA_MAP = {
    1: "20/200",
    2: "20/100",
    3: "20/70",
    4: "20/50",
    5: "20/40",
    6: "20/35",
    7: "20/30",
    8: "20/25",
    9: "20/22",
    10: "20/20",
    11: "20/18",
    12: "20/17",
    13: "20/15",
    14: "20/13",
}

STEREO_MAP = {
    1: '400"',
    2: '200"',
    3: '100"',
    4: '70"',
    5: '50"',
    6: '40"',
    7: '30"',
    8: '25"',
    9: '20"',
}

FAR_VA_BE_KEY: List[str] = ["T", "R", "R", "L", "T", "B", "L", "R", "L", "B", "R", "B", "T", "R"]
FAR_VA_RE_KEY: List[str] = ["T", "L", "T", "T", "B", "B", "L", "B", "R", "T", "R", "L", "B", "R"]
FAR_VA_LE_KEY: List[str] = ["L", "R", "L", "B", "R", "T", "T", "B", "R", "T", "B", "R", "T", "L"]
NEAR_VA_BE_KEY: List[str] = ["T", "R", "R", "L", "T", "B", "L", "R", "L", "B", "R", "B", "T", "R"]
NEAR_VA_RE_KEY: List[str] = ["T", "L", "T", "T", "B", "B", "L", "B", "R", "T", "R", "L", "B", "R"]
NEAR_VA_LE_KEY: List[str] = ["L", "R", "L", "B", "R", "T", "T", "B", "R", "T", "B", "R", "T", "L"]
FAR_STEREO_KEY: List[str] = ["B", "L", "B", "T", "T", "L", "R", "L", "R"]
FAR_COLOR_KEY: List[str] = ["12", "5", "26", "6", "16", "x"]
FAR_COLOR_TOTAL = len(FAR_COLOR_KEY)


JOB_GROUPS: Dict[str, Dict[str, Any]] = {
    "unspecified": {
        "label_th": "0) ไม่ระบุ (Unspecified / Unknown job group)",
        "std": Standards(
            far_binocular_required=False,
            far_vphoria_range=Range(3, 5),
            far_lphoria_range=Range(4, 13),
            near_binocular_required=False,
            near_vphoria_range=Range(3, 5),
            near_lphoria_range=Range(4, 13),
        ),
    },
    "office": {
        "label_th": "1) สำนักงาน (Office) - Clerical & Administrative",
        "std": Standards(
            far_va_be_min=8,
            far_va_re_min=7,
            far_va_le_min=7,
            far_color_min_correct=5,
            far_vphoria_range=Range(3, 5),
            far_lphoria_range=Range(4, 13),
            near_va_be_min=9,
            near_va_re_min=8,
            near_va_le_min=8,
            near_vphoria_range=Range(3, 5),
            near_lphoria_range=Range(4, 13),
            inter_va_be_min=9,
            inter_va_re_min=8,
            inter_va_le_min=8,
        ),
    },
    "inspector": {
        "label_th": "2) ตรวจสอบ (Inspector) - Inspection & Close Machine Work",
        "std": Standards(
            far_va_be_min=7,
            far_va_re_min=6,
            far_va_le_min=6,
            far_stereo_min=5,
            far_color_min_correct=5,
            far_vphoria_range=Range(3, 5),
            far_lphoria_range=Range(4, 13),
            near_va_be_min=9,
            near_va_re_min=8,
            near_va_le_min=8,
            near_vphoria_range=Range(3, 5),
            near_lphoria_range=Range(4, 13),
            inter_va_be_min=9,
            inter_va_re_min=8,
            inter_va_le_min=8,
        ),
    },
    "driver_mobile": {
        "label_th": "3) ขับ/ควบคุมอุปกรณ์เคลื่อนที่ (Driver/Crane) - Operator of Mobile equipment",
        "std": Standards(
            far_va_be_min=9,
            far_va_re_min=8,
            far_va_le_min=8,
            far_stereo_min=6,
            far_color_min_correct=5,
            far_vphoria_range=Range(3, 5),
            far_lphoria_range=Range(4, 13),
            near_va_be_min=7,
            near_va_re_min=6,
            near_va_le_min=6,
            near_vphoria_range=Range(3, 5),
            near_lphoria_range=Range(4, 13),
            inter_va_be_min=7,
            inter_va_re_min=6,
            inter_va_le_min=6,
        ),
    },
    "operator": {
        "label_th": "4) ฝ่ายผลิต/ควบคุมเครื่องจักร (Operator) - Machine Operators",
        "std": Standards(
            far_va_be_min=8,
            far_va_re_min=7,
            far_va_le_min=7,
            far_stereo_min=5,
            far_color_min_correct=5,
            far_vphoria_range=Range(3, 5),
            far_lphoria_range=Range(4, 13),
            near_va_be_min=8,
            near_va_re_min=7,
            near_va_le_min=7,
            near_vphoria_range=Range(3, 5),
            near_lphoria_range=Range(4, 13),
            inter_va_be_min=8,
            inter_va_re_min=7,
            inter_va_le_min=7,
        ),
    },
    "tradesman": {
        "label_th": "5) ช่าง (Tradesman) - Mechanics & Skilled Tradesmen",
        "std": Standards(
            far_va_be_min=8,
            far_va_re_min=7,
            far_va_le_min=7,
            far_stereo_min=5,
            far_color_min_correct=5,
            far_vphoria_range=Range(3, 5),
            far_lphoria_range=Range(4, 13),
            near_va_be_min=9,
            near_va_re_min=8,
            near_va_le_min=8,
            near_vphoria_range=Range(3, 5),
            near_lphoria_range=Range(4, 13),
            inter_va_be_min=9,
            inter_va_re_min=8,
            inter_va_le_min=8,
        ),
    },
    "labor": {
        "label_th": "6) แรงงานทั่วไป (Labor) - Unskilled Laborers",
        "std": Standards(
            far_va_be_min=8,
            far_va_re_min=7,
            far_va_le_min=7,
            far_color_min_correct=5,
            far_vphoria_range=Range(2, 6),
            far_lphoria_range=Range(1, 15),
            near_va_be_min=7,
            near_va_re_min=6,
            near_va_le_min=6,
        ),
    },
}


def fmt_va(x: Optional[int]) -> str:
    if x is None:
        return "N/A"
    return f"{x} ({VA_MAP.get(x, '-')})"


def fmt_stereo(x: Optional[int]) -> str:
    if x is None:
        return "N/A"
    return f"{x} ({STEREO_MAP.get(x, '-')})"


def fmt_range(r: Optional[Range]) -> str:
    if r is None:
        return "N/A"
    return f"{r.lo}-{r.hi}"


def pass_fail_icon(ok: bool) -> str:
    return "ผ่านเกณฑ์" if ok else "ต่ำกว่าเกณฑ์"


def fmt_bino_cubes(cubes: Optional[int]) -> str:
    if cubes is None:
        return "-"
    return f"{cubes} cubes"


def eval_min(name: str, val: Optional[int], min_required: Optional[int]) -> Tuple[bool, str]:
    if min_required is None:
        return True, f"{name}: N/A"
    if val is None:
        return True, f"{name}: ไม่ได้ตรวจ (ไม่นำมาตัดเกณฑ์)"
    ok = val >= min_required
    return ok, f"{name}: {fmt_va(val)} (เกณฑ์ >= {min_required} = {fmt_va(min_required)})"


def eval_stereo(val: Optional[int], min_required: Optional[int]) -> Tuple[bool, str]:
    if min_required is None:
        return True, "Stereo depth: N/A"
    if val is None:
        return True, "Stereo depth: ไม่ได้ตรวจ (ไม่นำมาตัดเกณฑ์)"
    ok = val >= min_required
    return ok, f"Stereo depth: {fmt_stereo(val)} (เกณฑ์ >= {min_required} = {fmt_stereo(min_required)})"


def eval_color(correct_digits: Optional[int], min_required: Optional[int]) -> Tuple[bool, str]:
    if min_required is None:
        return True, "Color: N/A"
    if correct_digits is None:
        return True, "Color: ไม่ได้ตรวจ (ไม่นำมาตัดเกณฑ์)"
    ok = correct_digits >= min_required
    return ok, f"Color correct: {correct_digits}/{FAR_COLOR_TOTAL} (เกณฑ์ >= {min_required}/{FAR_COLOR_TOTAL})"


def eval_range(name: str, val: Optional[int], r: Optional[Range], na_ok: bool = True) -> Tuple[bool, str]:
    if r is None:
        return (True, f"{name}: N/A") if na_ok else (False, f"{name}: N/A")
    if val is None:
        return True, f"{name}: ไม่ได้ตรวจ (ไม่นำมาตัดเกณฑ์)"
    ok = r.contains(val)
    return ok, f"{name}: {val} (เกณฑ์ {r.lo}-{r.hi})"


def recommendation_from_failures(fails: List[str], symptoms: Dict[str, bool]) -> List[str]:
    recs: List[str] = []
    sym_flag = any(symptoms.values())

    if any("VA" in f for f in fails):
        recs.append("ตรวจซ้ำโดยยืนยันระยะ สภาพแสง การปิดตา และการใส่แว่นหรือคอนแทคเลนส์ที่ใช้งานจริง")
        recs.append("หากยังต่ำกว่าเกณฑ์ แนะนำประเมินค่าสายตาเพิ่มเติมเพื่อพิจารณาการแก้ไขด้วยแว่น")
    if any("Stereo" in f for f in fails):
        recs.append("ตรวจซ้ำ stereo depth โดยยืนยันการใส่แว่น การจัดท่าทาง และความเข้าใจคำสั่ง")
        recs.append("หากยังผิดปกติ แนะนำปรึกษาจักษุแพทย์หรือผู้เชี่ยวชาญสายตา")
    if any("Color" in f for f in fails):
        recs.append("ตรวจซ้ำการแยกสี หรือยืนยันด้วยแบบทดสอบมาตรฐานเพิ่มเติมตามหน่วยงาน")
    if any("Phoria" in f for f in fails):
        recs.append("ตรวจซ้ำ phoria โดยยืนยันคำสั่ง ความร่วมมือ และความล้าของผู้รับการตรวจ")
        if sym_flag:
            recs.append("หากมีอาการปวดตา ปวดศีรษะ หรือภาพซ้อนร่วม แนะนำส่งต่อจักษุแพทย์")
    if any("Binocular" in f for f in fails):
        recs.append("ตรวจซ้ำ binocular fusion และประเมินการเห็นภาพซ้อนหรือการกดภาพ")
    if any("Visual field" in f for f in fails):
        recs.append("หากสงสัยลานสายตาผิดปกติ แนะนำส่งต่อเพื่อทำ perimetry หรือประเมินจักษุเพิ่มเติม")
    if not recs and not fails:
        recs.append("ไม่พบข้อบ่งชี้ให้ตรวจเพิ่มเติมจากการคัดกรองครั้งนี้ แพทย์พิจารณาตามอาการและประวัติ")

    dedup: List[str] = []
    for rec in recs:
        if rec not in dedup:
            dedup.append(rec)
    return dedup


def score_exam_step(
    answer_key: List[str],
    slide: int,
    answer: str,
    wrong_streak: int = 0,
    last_passed: int = 0,
) -> Dict[str, Any]:
    expected = answer_key[slide - 1]
    correct = answer == expected
    next_wrong_streak = 0 if correct else wrong_streak + 1
    next_last_passed = slide if correct else last_passed
    stopped = next_wrong_streak >= 2 or slide >= len(answer_key)
    return {
        "correct": correct,
        "expected": expected,
        "slide": slide,
        "next_slide": min(slide + 1, len(answer_key)),
        "wrong_streak": next_wrong_streak,
        "last_passed": next_last_passed,
        "stopped": stopped,
        "score": next_last_passed,
    }


def assess_screening(
    job_key: str,
    inputs: Dict[str, Any],
    include_intermediate: bool = False,
    symptoms: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    std: Standards = JOB_GROUPS[job_key]["std"]
    far = inputs.get("far", {})
    near = inputs.get("near", {})
    inter = inputs.get("intermediate", {})

    fails: List[str] = []
    details: List[Tuple[bool, str]] = []

    if std.far_binocular_required:
        far_cubes = far.get("binocular_cubes")
        ok = far_cubes == 3
        details.append((ok, f"Binocular vision (Far): {fmt_bino_cubes(far_cubes)} (เกณฑ์ 3 cubes)"))
        if not ok:
            fails.append("Binocular (Far)")

    checks = [
        (eval_min, "VA (Far) Both eyes", far.get("va_be"), std.far_va_be_min, "VA (Far) BE"),
        (eval_min, "VA (Far) Right eye", far.get("va_re"), std.far_va_re_min, "VA (Far) RE"),
        (eval_min, "VA (Far) Left eye", far.get("va_le"), std.far_va_le_min, "VA (Far) LE"),
    ]
    for fn, name, val, rule, fail_name in checks:
        ok, msg = fn(name, val, rule)
        details.append((ok, msg))
        if not ok:
            fails.append(fail_name)

    ok, msg = eval_stereo(far.get("stereo"), std.far_stereo_min)
    details.append((ok, msg))
    if not ok:
        fails.append("Stereo (Far)")

    ok, msg = eval_color(far.get("color_correct"), std.far_color_min_correct)
    details.append((ok, msg))
    if not ok:
        fails.append("Color (Far)")

    for name, val, rule, fail_name in [
        ("Vertical Phoria (Far)", far.get("vphoria"), std.far_vphoria_range, "Vertical Phoria (Far)"),
        ("Lateral Phoria (Far)", far.get("lphoria"), std.far_lphoria_range, "Lateral Phoria (Far)"),
    ]:
        ok, msg = eval_range(name, val, rule, na_ok=True)
        details.append((ok, msg))
        if not ok:
            fails.append(fail_name)

    if std.near_binocular_required:
        near_cubes = near.get("binocular_cubes")
        ok = near_cubes == 3
        details.append((ok, f"Binocular vision (Near): {fmt_bino_cubes(near_cubes)} (เกณฑ์ 3 cubes)"))
        if not ok:
            fails.append("Binocular (Near)")

    checks = [
        (eval_min, "VA (Near) Both eyes", near.get("va_be"), std.near_va_be_min, "VA (Near) BE"),
        (eval_min, "VA (Near) Right eye", near.get("va_re"), std.near_va_re_min, "VA (Near) RE"),
        (eval_min, "VA (Near) Left eye", near.get("va_le"), std.near_va_le_min, "VA (Near) LE"),
    ]
    for fn, name, val, rule, fail_name in checks:
        ok, msg = fn(name, val, rule)
        details.append((ok, msg))
        if not ok:
            fails.append(fail_name)

    for name, val, rule, fail_name in [
        ("Vertical Phoria (Near)", near.get("vphoria"), std.near_vphoria_range, "Vertical Phoria (Near)"),
        ("Lateral Phoria (Near)", near.get("lphoria"), std.near_lphoria_range, "Lateral Phoria (Near)"),
    ]:
        ok, msg = eval_range(name, val, rule, na_ok=True)
        details.append((ok, msg))
        if not ok:
            fails.append(fail_name)

    if include_intermediate:
        if std.inter_va_be_min is None:
            details.append((True, "Intermediate: N/A (ตามตารางของกลุ่มอาชีพนี้)"))
        else:
            for name, val, rule, fail_name in [
                ("VA (Inter) Both eyes", inter.get("va_be"), std.inter_va_be_min, "VA (Inter) BE"),
                ("VA (Inter) Right eye", inter.get("va_re"), std.inter_va_re_min, "VA (Inter) RE"),
                ("VA (Inter) Left eye", inter.get("va_le"), std.inter_va_le_min, "VA (Inter) LE"),
            ]:
                ok, msg = eval_min(name, val, rule)
                details.append((ok, msg))
                if not ok:
                    fails.append(fail_name)

    return {
        "all_ok": len(fails) == 0,
        "fails": fails,
        "details": details,
        "recommendations": recommendation_from_failures(fails, symptoms or {}),
    }
