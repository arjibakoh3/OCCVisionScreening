import json
import base64
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import streamlit as st

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except Exception:
    FIREBASE_AVAILABLE = False

# ----------------------------
# Reference: V2a / Optec 5000 Job Standards (as per user's provided PDF)
# We keep thresholds as "minimum picture number achieved" (e.g., VA BE >= 8)
# and phoria ranges as inclusive min/max.
# Color: pass if correct_digits >= 5 out of 8.
# Stereo depth: pass if score >= threshold (when applicable).
# ----------------------------

@dataclass
class Range:
    lo: int
    hi: int

    def contains(self, x: int) -> bool:
        return self.lo <= x <= self.hi

@dataclass
class Standards:
    # Far
    far_binocular_required: bool = True  # "3 cubes" => we implement as pass/fail checkbox
    far_va_be_min: Optional[int] = None
    far_va_re_min: Optional[int] = None
    far_va_le_min: Optional[int] = None
    far_stereo_min: Optional[int] = None  # None = N/A
    far_color_min_correct: Optional[int] = None  # None = N/A
    far_vphoria_range: Optional[Range] = None
    far_lphoria_range: Optional[Range] = None  # None = N/A

    # Near
    near_binocular_required: bool = True
    near_va_be_min: Optional[int] = None
    near_va_re_min: Optional[int] = None
    near_va_le_min: Optional[int] = None
    near_vphoria_range: Optional[Range] = None
    near_lphoria_range: Optional[Range] = None

    # Intermediate (optional)
    inter_va_be_min: Optional[int] = None
    inter_va_re_min: Optional[int] = None
    inter_va_le_min: Optional[int] = None


JOB_GROUPS: Dict[str, Dict[str, Any]] = {
    # 0) Unspecified
    "unspecified": {
        "label_th": "0) ไม่ระบุ (Unspecified / Unknown job group)",
        # Use all N/A thresholds so we can still save and review the case.
        "std": Standards(
            far_binocular_required=False,
            far_va_be_min=None, far_va_re_min=None, far_va_le_min=None,
            far_stereo_min=None,
            far_color_min_correct=None,
            far_vphoria_range=None,
            far_lphoria_range=None,
            near_binocular_required=False,
            near_va_be_min=None, near_va_re_min=None, near_va_le_min=None,
            near_vphoria_range=None,
            near_lphoria_range=None,
            inter_va_be_min=None, inter_va_re_min=None, inter_va_le_min=None,
        ),
    },
    # 1) Office
    "office": {
        "label_th": "1) สำนักงาน (Office) — Clerical & Administrative",
        "std": Standards(
            far_va_be_min=8, far_va_re_min=7, far_va_le_min=7,
            far_stereo_min=None,
            far_color_min_correct=5,
            far_vphoria_range=Range(3, 5),
            far_lphoria_range=Range(4, 13),
            near_va_be_min=9, near_va_re_min=8, near_va_le_min=8,
            near_vphoria_range=Range(3, 5),
            near_lphoria_range=Range(4, 13),
            inter_va_be_min=9, inter_va_re_min=8, inter_va_le_min=8,
        )
    },
    # 2) Inspector / close machine
    "inspector": {
        "label_th": "2) ตรวจสอบ (Inspector) — Inspection & Close Machine Work",
        "std": Standards(
            far_va_be_min=7, far_va_re_min=6, far_va_le_min=6,
            far_stereo_min=5,
            far_color_min_correct=5,
            far_vphoria_range=Range(3, 5),
            far_lphoria_range=Range(4, 13),
            near_va_be_min=9, near_va_re_min=8, near_va_le_min=8,
            near_vphoria_range=Range(3, 5),
            near_lphoria_range=Range(4, 13),
            inter_va_be_min=9, inter_va_re_min=8, inter_va_le_min=8,
        )
    },
    # 3) Driver (mapped to mobile equipment)
    "driver_mobile": {
        "label_th": "3) ขับ/ควบคุมอุปกรณ์เคลื่อนที่ (Driver/Crane) — Operator of Mobile equipment",
        "std": Standards(
            far_va_be_min=9, far_va_re_min=8, far_va_le_min=8,
            far_stereo_min=6,
            far_color_min_correct=5,
            far_vphoria_range=Range(3, 5),
            far_lphoria_range=Range(4, 13),
            near_va_be_min=7, near_va_re_min=6, near_va_le_min=6,
            near_vphoria_range=Range(3, 5),
            near_lphoria_range=Range(4, 13),
            inter_va_be_min=7, inter_va_re_min=6, inter_va_le_min=6,
        )
    },
    # 4) Operator (machine operators)
    "operator": {
        "label_th": "4) ฝ่ายผลิต/ควบคุมเครื่องจักร (Operator) — Machine Operators",
        "std": Standards(
            far_va_be_min=8, far_va_re_min=7, far_va_le_min=7,
            far_stereo_min=5,
            far_color_min_correct=5,
            far_vphoria_range=Range(3, 5),
            far_lphoria_range=Range(4, 13),
            near_va_be_min=8, near_va_re_min=7, near_va_le_min=7,
            near_vphoria_range=Range(3, 5),
            near_lphoria_range=Range(4, 13),
            inter_va_be_min=8, inter_va_re_min=7, inter_va_le_min=7,
        )
    },
    # 5) Tradesman (skilled trades)
    "tradesman": {
        "label_th": "5) ช่าง (Tradesman) — Mechanics & Skilled Tradesmen",
        "std": Standards(
            far_va_be_min=8, far_va_re_min=7, far_va_le_min=7,
            far_stereo_min=5,
            far_color_min_correct=5,
            far_vphoria_range=Range(3, 5),
            far_lphoria_range=Range(4, 13),
            near_va_be_min=9, near_va_re_min=8, near_va_le_min=8,
            near_vphoria_range=Range(3, 5),
            near_lphoria_range=Range(4, 13),
            inter_va_be_min=9, inter_va_re_min=8, inter_va_le_min=8,
        )
    },
    # 6) General labor
    "labor": {
        "label_th": "6) แรงงานทั่วไป (Labor) — Unskilled Laborers",
        "std": Standards(
            far_va_be_min=8, far_va_re_min=7, far_va_le_min=7,
            far_stereo_min=None,
            far_color_min_correct=5,
            far_vphoria_range=Range(2, 6),
            far_lphoria_range=None,
            near_va_be_min=7, near_va_re_min=6, near_va_le_min=6,
            near_vphoria_range=None,
            near_lphoria_range=None,
            inter_va_be_min=None, inter_va_re_min=None, inter_va_le_min=None,
        )
    },
}


# ----------------------------
# Helpers
# ----------------------------

VA_MAP = {
    1: "20/200", 2: "20/100", 3: "20/70", 4: "20/50", 5: "20/40", 6: "20/35", 7: "20/30",
    8: "20/25", 9: "20/22", 10: "20/20", 11: "20/18", 12: "20/17", 13: "20/15", 14: "20/13"
}

STEREO_MAP = {1: "400\"", 2: "200\"", 3: "100\"", 4: "70\"", 5: "50\"", 6: "40\"", 7: "30\"", 8: "25\"", 9: "20\""}

FAR_VA_BE_KEY: List[str] = [
    "T", "R", "R", "L", "T", "B", "L", "R", "L", "B", "R", "B", "T", "R"
]

NEAR_VA_BE_KEY: List[str] = ["T","R","R","L","T","B","L","R","L","B","R","B","T","R"]

NEAR_VA_RE_KEY: List[str] = ["T","L","T","T","B","B","L","B","R","T","R","L","B","R"]
NEAR_VA_LE_KEY: List[str] = ["L","R","L","B","R","T","T","B","R","T","B","R","T","L"]

FAR_VA_RE_KEY: List[str] = [
    "T","L","T","T","B","B","L","B","R","T","R","L","B","R"
]
FAR_VA_LE_KEY: List[str] = [
    "L","R","L","B","R","T","T","B","R","T","B","R","T","L"
]
FAR_STEREO_KEY: List[str] = [
    "B","L","B","T","T","L","R","L","R"
]

FAR_COLOR_KEY: List[str] = ["12","5","26","6","16","x"]

def fmt_va(x: Optional[int]) -> str:
    if x is None:
        return "N/A"
    return f"{x} ({VA_MAP.get(x, '—')})"

def fmt_stereo(x: Optional[int]) -> str:
    if x is None:
        return "N/A"
    return f"{x} ({STEREO_MAP.get(x, '—')})"

def pass_fail_icon(ok: bool) -> str:
    return "✅ ผ่านเกณฑ์" if ok else "❌ ต่ำกว่าเกณฑ์"

def eval_min(name: str, val: Optional[int], min_required: Optional[int]) -> Tuple[bool, str]:
    if min_required is None:
        return True, f"{name}: N/A"
    if val is None:
        return False, f"{name}: ไม่ได้กรอกผล"
    ok = val >= min_required
    return ok, f"{name}: {fmt_va(val)} (เกณฑ์ ≥ {min_required} = {fmt_va(min_required)})"

def eval_stereo(val: Optional[int], min_required: Optional[int]) -> Tuple[bool, str]:
    if min_required is None:
        return True, "Stereo depth: N/A"
    if val is None:
        return False, "Stereo depth: ไม่ได้กรอกผล"
    ok = val >= min_required
    return ok, f"Stereo depth: {fmt_stereo(val)} (เกณฑ์ ≥ {min_required} = {fmt_stereo(min_required)})"

def eval_color(correct_digits: Optional[int], min_required: Optional[int]) -> Tuple[bool, str]:
    if min_required is None:
        return True, "Color: N/A"
    if correct_digits is None:
        return False, "Color: ไม่ได้กรอกผล"
    ok = correct_digits >= min_required
    return ok, f"Color correct: {correct_digits}/8 (เกณฑ์ ≥ {min_required}/8)"

def eval_range(name: str, val: Optional[int], r: Optional[Range], na_ok: bool = True) -> Tuple[bool, str]:
    if r is None:
        return (True, f"{name}: N/A") if na_ok else (False, f"{name}: N/A")
    if val is None:
        return False, f"{name}: ไม่ได้กรอกผล"
    ok = r.contains(val)
    return ok, f"{name}: {val} (เกณฑ์ {r.lo}–{r.hi})"

def recommendation_from_failures(fails: List[str], symptoms: Dict[str, bool]) -> List[str]:
    recs: List[str] = []
    sym_flag = any(symptoms.values())

    # Visual acuity
    if any("VA" in f for f in fails):
        recs.append("แนะนำตรวจซ้ำโดยยืนยันระยะ/สภาพแสง/การปิดตาให้ถูกต้อง และทดสอบซ้ำขณะใส่แว่น/คอนแทคเลนส์ที่ใช้งานจริง (ถ้ามี)")
        recs.append("หากยังต่ำกว่าเกณฑ์: แนะนำประเมินสายตา/ค่าสายตาเพิ่มเติม (refraction) เพื่อพิจารณาการแก้ไขด้วยแว่น")

    # Stereo
    if any("Stereo" in f for f in fails):
        recs.append("แนะนำตรวจซ้ำ stereo depth (ยืนยันการใส่แว่น/การจัดท่าทาง/การเข้าใจคำสั่ง)")
        recs.append("หากยังผิดปกติ: แนะนำปรึกษาจักษุแพทย์/ผู้เชี่ยวชาญสายตาเพื่อตรวจ binocular vision เพิ่มเติม")

    # Color
    if any("Color" in f for f in fails):
        recs.append("แนะนำตรวจซ้ำการแยกสี และ/หรือยืนยันด้วยแบบทดสอบมาตรฐานเพิ่มเติมตามหน่วยงาน (เช่น PIP/Ishihara)")

    # Phoria
    if any("Phoria" in f for f in fails):
        recs.append("แนะนำตรวจซ้ำ phoria (ยืนยันคำสั่ง/ความร่วมมือ/ความล้า)")
        if sym_flag:
            recs.append("หากมีอาการปวดตา/ปวดศีรษะ/ภาพซ้อนร่วม: แนะนำส่งต่อจักษุแพทย์เพื่อตรวจเพิ่มเติม")

    # Binocular
    if any("Binocular" in f for f in fails):
        recs.append("แนะนำตรวจซ้ำ binocular fusion และประเมินการเห็นภาพซ้อน/การกดภาพ")

    # Visual field (if used)
    if any("Visual field" in f for f in fails):
        recs.append("หากสงสัยลานสายตาผิดปกติ: แนะนำส่งต่อเพื่อทำ perimetry/ประเมินจักษุเพิ่มเติม")

    if not recs and not fails:
        recs.append("ไม่พบข้อบ่งชี้ให้ตรวจเพิ่มเติมจากการคัดกรองครั้งนี้ (แพทย์พิจารณาตามอาการ/ประวัติ)")

    # Deduplicate while preserving order
    dedup = []
    for r in recs:
        if r not in dedup:
            dedup.append(r)
    return dedup


# ----------------------------
# Export: Form-like HTML
# ----------------------------

def _checked(flag: bool) -> str:
    return "checked" if flag else ""

def build_form_html(payload: Dict[str, Any]) -> str:
    person = payload["person"]
    meta = payload["meta"]
    corr = payload["correction"]
    inputs = payload["inputs"]
    auto = payload["auto_interpretation"]
    review = payload["review"]
    std = JOB_GROUPS[meta["job_group_key"]]["std"]

    def ref_min(minv: Optional[int], fmt_func) -> str:
        if minv is None:
            return "N/A"
        return f">= {fmt_func(minv)}"

    def ref_range(r: Optional[Range]) -> str:
        if r is None:
            return "N/A"
        return f"{r.lo}-{r.hi}"

    def val_va(v: Optional[int]) -> str:
        return fmt_va(v) if v is not None else "—"

    def val_num(v: Optional[int]) -> str:
        return str(v) if v is not None else "—"

    vf = inputs.get("visual_field") or {}
    vf_value = "—"
    if vf:
        r_temp = vf.get("right_temp", "—")
        l_temp = vf.get("left_temp", "—")
        r_temp_txt = f"{r_temp}°" if isinstance(r_temp, int) else str(r_temp)
        l_temp_txt = f"{l_temp}°" if isinstance(l_temp, int) else str(l_temp)
        vf_value = f"R Temporal:{r_temp_txt} | L Temporal:{l_temp_txt}"

    inter = inputs.get("intermediate")

    html = f"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="utf-8">
  <title>Vision Screening Form</title>
  <style>
    @page {{ size: A4 landscape; margin: 8mm; }}
    body {{ font-family: "TH Sarabun New", "Sarabun", "Tahoma", sans-serif; font-size: 12.5pt; }}
    .page {{ width: 270mm; margin: 0 auto; }}
    .box {{ border: 1px solid #333; padding: 6px; }}
    .grid {{ display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 6px; }}
    .row {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
    .title {{ text-align: center; font-weight: 700; font-size: 16pt; }}
    .subtitle {{ text-align: center; font-size: 12pt; margin-top: 2px; }}
    .section-title {{ font-weight: 700; margin-top: 6px; }}
    .small {{ font-size: 11pt; }}
    .checkbox {{ display: inline-flex; align-items: center; gap: 4px; margin-right: 8px; }}
    .line {{ border-bottom: 1px dotted #333; min-width: 80px; display: inline-block; }}
    .right {{ text-align: right; }}
    table {{ width: 100%; border-collapse: collapse; }}
    td, th {{ border: 1px solid #333; padding: 4px; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
  </style>
</head>
<body>
  <div class="page">
    <div class="box">
      <div class="title">แบบบันทึกผลการตรวจสมรรถภาพการมองเห็นในงานอาชีวอนามัย</div>
      <div class="subtitle">(Record Form of Vision Screening Test in Occupational Health Setting)</div>
      <div class="grid">
        <div>
          ตรวจมองไกล (Far):
          <label class="checkbox"><input type="checkbox" {_checked(corr["far"]=="ไม่ใส่แว่น")}> ไม่ใส่แว่น</label>
          <label class="checkbox"><input type="checkbox" {_checked(corr["far"]=="ใส่แว่น")}> ใส่แว่น</label>
          <label class="checkbox"><input type="checkbox" {_checked(corr["far"]=="ใส่คอนแทคเลนส์")}> ใส่คอนแทคเลนส์</label>
          <br>
          ตรวจมองใกล้ (Near):
          <label class="checkbox"><input type="checkbox" {_checked(corr["near"]=="ไม่ใส่แว่น")}> ไม่ใส่แว่น</label>
          <label class="checkbox"><input type="checkbox" {_checked(corr["near"]=="ใส่แว่น")}> ใส่แว่น</label>
          <label class="checkbox"><input type="checkbox" {_checked(corr["near"]=="ใส่คอนแทคเลนส์")}> ใส่คอนแทคเลนส์</label>
        </div>
        <div>
          ชื่อ-นามสกุล (Name) <span class="line">{person["name"] or ""}</span>
          HN <span class="line">{person["hn"] or ""}</span><br>
          อายุ (Age) <span class="line">{person["age"]}</span>
          เพศ (Gender) <span class="line">{person["gender"]}</span><br>
          วันที่ตรวจ (Date of examination) <span class="line">{meta["exam_date"]}</span>
        </div>
      </div>
    </div>

    <div class="grid">
      <div class="box">
        <div class="section-title">Job groups</div>
        <div class="small">{meta["job_group_label"]}</div>
        <div class="section-title">Device</div>
        <div class="small">{meta["device"]}</div>
        <div class="section-title">Recommendation</div>
        <div class="small">
          {"<br>".join(auto["recommendations"]) if auto["recommendations"] else "-"}
        </div>
        <div class="section-title">Physician note</div>
        <div class="small">
          {review.get("physician_note","") or "&nbsp;"}
        </div>
        <div style="height: 1.2em;"></div>
        <div class="row" style="justify-content: flex-end; text-align: right;">
          Physician signature <span class="line" style="min-width: 220px;">&nbsp;</span>
        </div>
        <div class="small right">(นายแพทย์ แบงก์ชาติ จินตรัตน์ ว. 50587)</div>
      </div>
      <div class="box">
        <div class="section-title">Results (measured + reference)</div>
        <table>
          <tr>
            <th style="width:38%;">Item</th>
            <th style="width:32%;">Measured</th>
            <th style="width:30%;">Reference (by job group)</th>
          </tr>
          <tr><td>Far: Binocular (3 cubes)</td><td>{"PASS" if inputs["far"]["binocular_ok"] else "FAIL"}</td><td>Must pass 3 cubes</td></tr>
          <tr><td>Far: VA Both eyes</td><td>{val_va(inputs["far"]["va_be"])}</td><td>{ref_min(std.far_va_be_min, fmt_va)}</td></tr>
          <tr><td>Far: VA Right</td><td>{val_va(inputs["far"]["va_re"])}</td><td>{ref_min(std.far_va_re_min, fmt_va)}</td></tr>
          <tr><td>Far: VA Left</td><td>{val_va(inputs["far"]["va_le"])}</td><td>{ref_min(std.far_va_le_min, fmt_va)}</td></tr>
          <tr><td>Far: Stereo depth</td><td>{fmt_stereo(inputs["far"]["stereo"]) if inputs["far"]["stereo"] is not None else "-"}</td><td>{ref_min(std.far_stereo_min, fmt_stereo)}</td></tr>
          <tr><td>Far: Color discrimination</td><td>{inputs["far"]["color_correct"]}/8</td><td>{ref_min(std.far_color_min_correct, lambda v: f"{v}/8")}</td></tr>
          <tr><td>Far: Vertical phoria</td><td>{val_num(inputs["far"]["vphoria"])}</td><td>{ref_range(std.far_vphoria_range)}</td></tr>
          <tr><td>Far: Lateral phoria</td><td>{val_num(inputs["far"]["lphoria"])}</td><td>{ref_range(std.far_lphoria_range)}</td></tr>
          <tr><td>Near: Binocular (3 cubes)</td><td>{"PASS" if inputs["near"]["binocular_ok"] else "FAIL"}</td><td>Must pass 3 cubes</td></tr>
          <tr><td>Near: VA Both eyes</td><td>{val_va(inputs["near"]["va_be"])}</td><td>{ref_min(std.near_va_be_min, fmt_va)}</td></tr>
          <tr><td>Near: VA Right</td><td>{val_va(inputs["near"]["va_re"])}</td><td>{ref_min(std.near_va_re_min, fmt_va)}</td></tr>
          <tr><td>Near: VA Left</td><td>{val_va(inputs["near"]["va_le"])}</td><td>{ref_min(std.near_va_le_min, fmt_va)}</td></tr>
          <tr><td>Near: Vertical phoria</td><td>{val_num(inputs["near"]["vphoria"])}</td><td>{ref_range(std.near_vphoria_range)}</td></tr>
          <tr><td>Near: Lateral phoria</td><td>{val_num(inputs["near"]["lphoria"])}</td><td>{ref_range(std.near_lphoria_range)}</td></tr>
          {"".join([
              f'<tr><td>Inter: VA Both eyes</td><td>{val_va(inter.get("va_be"))}</td><td>{ref_min(std.inter_va_be_min, fmt_va)}</td></tr>',
              f'<tr><td>Inter: VA Right</td><td>{val_va(inter.get("va_re"))}</td><td>{ref_min(std.inter_va_re_min, fmt_va)}</td></tr>',
              f'<tr><td>Inter: VA Left</td><td>{val_va(inter.get("va_le"))}</td><td>{ref_min(std.inter_va_le_min, fmt_va)}</td></tr>',
          ]) if inter else ""}
          <tr><td>Visual field</td><td>{vf_value}</td><td>Screening / clinician judgment</td></tr>
        </table>
      </div>
    </div>

  </div>
</body>
</html>"""
    return html


# ----------------------------
# State helpers + Cloud (Firebase)
# ----------------------------

def _set_default_state() -> None:
    defaults = {
        "job_key": list(JOB_GROUPS.keys())[0],
        "test_device": "Titmus V2a",
        "far_correction": "ไม่ใส่แว่น",
        "near_correction": "ไม่ใส่แว่น",
        "include_intermediate": False,
        "include_visual_field": True,
        "name": "",
        "hn": "",
        "age": 30,
        "gender": "ชาย",
        "exam_date": datetime.today(),
        "far_binocular_ok": True,
        "far_stereo": None,
        "far_stereo_exam_enabled": False,
        "far_stereo_exam_slide": 1,
        "far_stereo_exam_wrong_streak": 0,
        "far_stereo_exam_last_passed": 0,
        "far_stereo_exam_stopped": False,
        "far_stereo_exam_apply_pending": None,

        "far_color_correct": 8,
        "far_color_exam_enabled": False,
        "far_color_exam_slide": 1,
        "far_color_exam_wrong_streak": 0,
        "far_color_exam_last_passed": 0,
        "far_color_exam_stopped": False,
        "far_color_exam_apply_pending": None,

        "far_va_be": 8,
        "far_va_be_exam_enabled": False,
        "far_va_be_exam_slide": 1,
        "far_va_be_exam_wrong_streak": 0,
        "far_va_be_exam_last_passed": 0,
        "far_va_be_exam_stopped": False,
        "far_va_be_exam_apply_pending": None,
        "far_va_re": None,
        "far_va_re_exam_enabled": False,
        "far_va_re_exam_slide": 1,
        "far_va_re_exam_wrong_streak": 0,
        "far_va_re_exam_last_passed": 0,
        "far_va_re_exam_stopped": False,
        "far_va_re_exam_apply_pending": None,

        "far_va_le": None,
        "far_va_le_exam_enabled": False,
        "far_va_le_exam_slide": 1,
        "far_va_le_exam_wrong_streak": 0,
        "far_va_le_exam_last_passed": 0,
        "far_va_le_exam_stopped": False,
        "far_va_le_exam_apply_pending": None,

        "far_vphoria": None,
        "far_lphoria": None,
        "near_binocular_ok": True,
        "near_va_be": 9,
        "near_va_be_exam_enabled": False,
        "near_va_be_exam_slide": 1,
        "near_va_be_exam_wrong_streak": 0,
        "near_va_be_exam_last_passed": 0,
        "near_va_be_exam_stopped": False,
        "near_va_be_exam_apply_pending": None,

        "near_va_re": None,
        "near_va_re_exam_enabled": False,
        "near_va_re_exam_slide": 1,
        "near_va_re_exam_wrong_streak": 0,
        "near_va_re_exam_last_passed": 0,
        "near_va_re_exam_stopped": False,
        "near_va_re_exam_apply_pending": None,

        "near_va_le": None,
        "near_va_le_exam_enabled": False,
        "near_va_le_exam_slide": 1,
        "near_va_le_exam_wrong_streak": 0,
        "near_va_le_exam_last_passed": 0,
        "near_va_le_exam_stopped": False,
        "near_va_le_exam_apply_pending": None,

        "near_vphoria": None,
        "near_lphoria": None,
        "inter_va_be": None,
        "inter_va_re": None,
        "inter_va_le": None,
        "vf_status": "ปกติ",
        "vf_right_temp": 85,
        "vf_left_temp": 85,
        "vf_right_nasal_seen": True,
        "vf_left_nasal_seen": True,
        "physician_note": "",
        "physician_name": "",
        "tech_name": "",
        "firebase_collection": "vision_records",
        "firebase_refresh_sec": 10,
        "firebase_autorefresh": True,
        "firebase_autosave": False,
        "firebase_doc_id": "",
        "firebase_last_hash": "",
        "firebase_save_request": False,
        "pending_payload": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _index_for(value, options: List[Any], default_index: int = 0) -> int:
    try:
        return options.index(value)
    except ValueError:
        return default_index


def apply_payload_to_state(payload: Dict[str, Any]) -> None:
    meta = payload.get("meta", {})
    person = payload.get("person", {})
    corr = payload.get("correction", {})
    inputs = payload.get("inputs", {})
    review = payload.get("review", {})

    st.session_state["job_key"] = meta.get("job_group_key", st.session_state.get("job_key"))
    st.session_state["test_device"] = meta.get("device", st.session_state.get("test_device"))
    if meta.get("exam_date"):
        try:
            st.session_state["exam_date"] = datetime.fromisoformat(meta["exam_date"]).date()
        except Exception:
            pass

    st.session_state["name"] = person.get("name", "")
    st.session_state["hn"] = person.get("hn", "")
    st.session_state["age"] = person.get("age", 30)
    st.session_state["gender"] = person.get("gender", "ชาย")

    st.session_state["far_correction"] = corr.get("far", st.session_state.get("far_correction"))
    st.session_state["near_correction"] = corr.get("near", st.session_state.get("near_correction"))

    far = inputs.get("far", {})
    near = inputs.get("near", {})
    inter = inputs.get("intermediate")
    vf = inputs.get("visual_field")

    st.session_state["far_binocular_ok"] = far.get("binocular_ok", True)
    st.session_state["far_va_be"] = far.get("va_be")
    st.session_state["far_va_re"] = far.get("va_re")
    st.session_state["far_va_le"] = far.get("va_le")
    st.session_state["far_stereo"] = far.get("stereo")
    st.session_state["far_color_correct"] = far.get("color_correct", 8)
    st.session_state["far_vphoria"] = far.get("vphoria")
    st.session_state["far_lphoria"] = far.get("lphoria")

    st.session_state["near_binocular_ok"] = near.get("binocular_ok", True)
    st.session_state["near_va_be"] = near.get("va_be")
    st.session_state["near_va_re"] = near.get("va_re")
    st.session_state["near_va_le"] = near.get("va_le")
    st.session_state["near_vphoria"] = near.get("vphoria")
    st.session_state["near_lphoria"] = near.get("lphoria")

    if inter is not None:
        st.session_state["include_intermediate"] = True
        st.session_state["inter_va_be"] = inter.get("va_be")
        st.session_state["inter_va_re"] = inter.get("va_re")
        st.session_state["inter_va_le"] = inter.get("va_le")
    else:
        st.session_state["include_intermediate"] = False

    if vf is not None:
        st.session_state["include_visual_field"] = True
        st.session_state["vf_status"] = vf.get("status", "ปกติ")
        st.session_state["vf_right_temp"] = vf.get("right_temp", 85)
        st.session_state["vf_left_temp"] = vf.get("left_temp", 85)
        st.session_state["vf_right_nasal_seen"] = bool(vf.get("right_nasal_seen", True))
        st.session_state["vf_left_nasal_seen"] = bool(vf.get("left_nasal_seen", True))
    else:
        st.session_state["include_visual_field"] = False

    st.session_state["physician_note"] = review.get("physician_note", "")
    st.session_state["physician_name"] = review.get("physician", "")
    st.session_state["tech_name"] = review.get("technician", "")


def _normalize_firebase_info(info: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize service account fields (notably private_key newlines)."""
    normalized = dict(info)
    pk = normalized.get("private_key")
    if isinstance(pk, str):
        # Common issues in TOML/env vars: newline characters are escaped as "\n" or "\r\n".
        pk_fixed = pk.strip()
        pk_fixed = pk_fixed.replace("\\r\\n", "\n").replace("\\n", "\n")
        pk_fixed = pk_fixed.replace("\r\n", "\n").replace("\r", "\n")
        # In some cases the key is wrapped in quotes.
        if (pk_fixed.startswith('"') and pk_fixed.endswith('"')) or (
            pk_fixed.startswith("'") and pk_fixed.endswith("'")
        ):
            pk_fixed = pk_fixed[1:-1]
        # Some setups store the private key as base64 to avoid newline issues.
        if "BEGIN PRIVATE KEY" not in pk_fixed and "END PRIVATE KEY" not in pk_fixed:
            try:
                decoded = base64.b64decode(pk_fixed).decode("utf-8", errors="ignore")
                if "BEGIN PRIVATE KEY" in decoded and "END PRIVATE KEY" in decoded:
                    pk_fixed = decoded
            except Exception:
                pass
        # Ensure proper PEM framing with line breaks after header/footer.
        header = "-----BEGIN PRIVATE KEY-----"
        footer = "-----END PRIVATE KEY-----"
        # If only one PEM boundary exists, add the missing one.
        if footer in pk_fixed and header not in pk_fixed:
            pk_fixed = f"{header}\n{pk_fixed}"
        if header in pk_fixed and footer not in pk_fixed:
            pk_fixed = f"{pk_fixed}\n{footer}"
        if header not in pk_fixed and footer not in pk_fixed:
            # If the content looks like key material but is missing framing, wrap it.
            # This is a best-effort fallback and won't fix truly invalid keys.
            if "PRIVATE KEY" not in pk_fixed and len(pk_fixed) > 200:
                pk_fixed = f"{header}\n{pk_fixed}\n{footer}"
        if header in pk_fixed and footer in pk_fixed:
            pk_fixed = pk_fixed.replace(header, header + "\n")
            pk_fixed = pk_fixed.replace(footer, "\n" + footer)
            # Collapse multiple blank lines that can appear after replacements.
            while "\n\n\n" in pk_fixed:
                pk_fixed = pk_fixed.replace("\n\n\n", "\n\n")
            # Remove blank lines immediately after header or before footer.
            lines = pk_fixed.split("\n")
            cleaned: List[str] = []
            for i, line in enumerate(lines):
                s = line.strip()
                if not s:
                    continue
                if s == header or s == footer:
                    cleaned.append(s)
                    continue
                # Drop any stray dashed lines inside the body.
                if s.startswith("-"):
                    continue
                cleaned.append(s)
            # Ensure the framing is preserved after cleanup.
            if not cleaned or cleaned[0] != header:
                cleaned.insert(0, header)
            if cleaned[-1] != footer:
                cleaned.append(footer)
            pk_fixed = "\n".join(cleaned)
        normalized["private_key"] = pk_fixed
    return normalized


def _firebase_client_from_info(info: Dict[str, Any]):
    normalized = _normalize_firebase_info(info)
    project_id = str(normalized.get("project_id", "") or "")
    if firebase_admin._apps:
        try:
            current_app = firebase_admin.get_app()
            current_pid = str(current_app.options.get("projectId", "") or "")
            # If the project changes between runs, reset the app to avoid sticky state.
            if project_id and current_pid and project_id != current_pid:
                firebase_admin.delete_app(current_app)
        except Exception:
            pass
    if not firebase_admin._apps:
        cred = credentials.Certificate(normalized)
        options = {"projectId": project_id} if project_id else None
        firebase_admin.initialize_app(cred, options)
    return firestore.client()


def _firebase_private_key_diagnostics(info: Dict[str, Any]) -> Dict[str, Any]:
    pk = info.get("private_key")
    if not isinstance(pk, str):
        return {"has_private_key": False}
    header = "-----BEGIN PRIVATE KEY-----"
    footer = "-----END PRIVATE KEY-----"
    return {
        "has_private_key": True,
        "has_header": header in pk,
        "has_footer": footer in pk,
        "newline_count": pk.count("\n"),
        "length": len(pk),
        "project_id": bool(info.get("project_id")),
        "client_email": bool(info.get("client_email")),
    }


def _firebase_save_record(db, collection: str, payload: Dict[str, Any]) -> None:
    payload_to_save = dict(payload)
    payload_to_save["_meta"] = {"created_at": firestore.SERVER_TIMESTAMP}
    db.collection(collection).add(payload_to_save)


def _firebase_update_record(db, collection: str, doc_id: str, payload: Dict[str, Any]) -> None:
    payload_to_save = dict(payload)
    payload_to_save["_meta"] = {"updated_at": firestore.SERVER_TIMESTAMP}
    db.collection(collection).document(doc_id).set(payload_to_save, merge=True)


def _firebase_list_records(db, collection: str, limit: int = 50):
    query = db.collection(collection).order_by("_meta.created_at", direction=firestore.Query.DESCENDING).limit(limit)
    return [doc for doc in query.stream()]


def _firebase_delete_record(db, collection: str, doc_id: str) -> None:
    db.collection(collection).document(doc_id).delete()


def _match_keyword(doc, keyword: str) -> bool:
    if not keyword:
        return True
    data = doc.to_dict() or {}
    person = data.get("person", {})
    name = str(person.get("name", "")).lower()
    hn = str(person.get("hn", "")).lower()
    return keyword.lower() in name or keyword.lower() in hn


def _match_exam_date(doc, exam_date_filter: Optional[Any]) -> bool:
    if exam_date_filter is None:
        return True
    data = doc.to_dict() or {}
    meta = data.get("meta", {})
    exam_date_str = str(meta.get("exam_date", "") or "")
    if not exam_date_str:
        return False
    # Stored as ISO date string (YYYY-MM-DD)
    return exam_date_str == str(exam_date_filter)


def _firebase_label(doc) -> str:
    data = doc.to_dict() or {}
    person = data.get("person", {})
    meta = data.get("meta", {})
    created = data.get("_meta", {}).get("created_at")
    created_txt = ""
    if created:
        try:
            created_txt = created.strftime("%Y-%m-%d %H:%M")
        except Exception:
            created_txt = str(created)
    return f"{person.get('name','')} | HN:{person.get('hn','')} | {meta.get('exam_date','')} | {created_txt}"
# ----------------------------
# UI
# ----------------------------

st.set_page_config(page_title="Vision Screening (Titmus V2a)", layout="wide")

st.title("แบบฟอร์มบันทึกผลตรวจสมรรถภาพการมองเห็น (Electronic) — Titmus V2a")
_set_default_state()
if st.session_state.get("pending_payload") is not None:
    apply_payload_to_state(st.session_state["pending_payload"])
    st.session_state["pending_payload"] = None

with st.expander("ตั้งค่าการใช้งาน", expanded=True):
    col_a, col_b, col_c = st.columns([1.1, 1.1, 1.2])
    with col_a:
        job_key = st.selectbox(
            "กลุ่มอาชีพ (Job group)",
            list(JOB_GROUPS.keys()),
            format_func=lambda k: JOB_GROUPS[k]["label_th"],
            key="job_key",
        )
        test_device = st.text_input("เครื่องตรวจ (Device)", key="test_device")
    with col_b:
        far_correction = st.radio(
            "ตรวจมองไกล (Far):",
            ["ไม่ใส่แว่น", "ใส่แว่น", "ใส่คอนแทคเลนส์"],
            horizontal=True,
            key="far_correction",
        )
        near_correction = st.radio(
            "ตรวจมองใกล้ (Near):",
            ["ไม่ใส่แว่น", "ใส่แว่น", "ใส่คอนแทคเลนส์"],
            horizontal=True,
            key="near_correction",
        )
    with col_c:
        include_intermediate = st.toggle("แสดงหัวข้อ Intermediate (ตามตารางมาตรฐาน)", key="include_intermediate")
        include_visual_field = st.toggle("บันทึก Visual field (แบบคัดกรอง/Perimeter score)", key="include_visual_field")

st.divider()

left, right = st.columns([1.05, 0.95])

with left:
    st.subheader("บันทึกผลโดยเจ้าหน้าที่ (Technician Input)")

    info1, info2, info3 = st.columns([1.2, 0.9, 0.9])
    with info1:
        name = st.text_input("ชื่อ-นามสกุล", key="name")
        hn = st.text_input("HN", key="hn")
    with info2:
        age = st.number_input("อายุ", min_value=0, max_value=120, value=st.session_state["age"], key="age")
        gender = st.selectbox("เพศ", ["ชาย", "หญิง", "อื่น ๆ / ไม่ระบุ"], key="gender")
    with info3:
        exam_date = st.date_input("วันที่ตรวจ", value=st.session_state["exam_date"], key="exam_date")

    far_col, near_col = st.columns(2)

    with far_col:
        st.markdown("### Far vision (20 ft.)")

        # Keep Far vision fields in a strict vertical order (important for mobile UI).
        far_binocular_ok = st.checkbox("1) Binocular vision (3 cubes) — ผ่าน", key="far_binocular_ok")
        # Apply exam-mode result before instantiating the VA widget.
        if st.session_state.get("far_va_be_exam_apply_pending"):
            st.session_state["far_va_be"] = int(st.session_state["far_va_be_exam_apply_pending"])
            st.session_state["far_va_be_exam_apply_pending"] = None

        st.markdown("2) Acuity Both eyes (1–14)")
        va_be_col, exam_col = st.columns([0.8, 1.6])
        with va_be_col:
            far_va_be = st.selectbox(
                "2) Acuity Both eyes (1–14)",
                list(range(1, 15)),
                index=_index_for(st.session_state["far_va_be"], list(range(1, 15)), 7),
                format_func=lambda x: fmt_va(x),
                key="far_va_be",
                label_visibility="collapsed",
            )

        with exam_col:
            with st.expander(
                "Exam mode (Far VA Both eyes)",
                expanded=st.session_state.get("far_va_be_exam_enabled", False),
            ):
                st.session_state["far_va_be_exam_enabled"] = True
                key = FAR_VA_BE_KEY
                max_slide = len(key)
                slide = int(st.session_state.get("far_va_be_exam_slide", 1) or 1)
                slide = min(max(slide, 1), max_slide)
                wrong_streak = int(st.session_state.get("far_va_be_exam_wrong_streak", 0) or 0)
                last_passed = int(st.session_state.get("far_va_be_exam_last_passed", 0) or 0)
                stopped = bool(st.session_state.get("far_va_be_exam_stopped", False))

                st.write(f"สไลด์ปัจจุบัน: **{slide} / {max_slide}**")
                st.write(f"เฉลย: **{key[slide-1]}**")
                st.caption(f"ผิดติดกัน: {wrong_streak}/2 | ผ่านล่าสุด: {last_passed}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    correct_click = st.button("✅ ถูก", key="far_va_be_exam_correct", disabled=stopped)
                with c2:
                    wrong_click = st.button("❌ ผิด", key="far_va_be_exam_wrong", disabled=stopped)
                with c3:
                    reset_click = st.button("↺ รีเซ็ต", key="far_va_be_exam_reset")

                if reset_click:
                    st.session_state["far_va_be_exam_slide"] = 1
                    st.session_state["far_va_be_exam_wrong_streak"] = 0
                    st.session_state["far_va_be_exam_last_passed"] = 0
                    st.session_state["far_va_be_exam_stopped"] = False
                    st.rerun()

                if correct_click and not stopped:
                    st.session_state["far_va_be_exam_last_passed"] = slide
                    st.session_state["far_va_be_exam_wrong_streak"] = 0
                    st.session_state["far_va_be_exam_slide"] = min(slide + 1, max_slide)
                    st.rerun()

                if wrong_click and not stopped:
                    wrong_streak += 1
                    st.session_state["far_va_be_exam_wrong_streak"] = wrong_streak
                    st.session_state["far_va_be_exam_slide"] = min(slide + 1, max_slide)
                    if wrong_streak >= 2:
                        st.session_state["far_va_be_exam_stopped"] = True
                    st.rerun()

                stopped = bool(st.session_state.get("far_va_be_exam_stopped", False))
                last_passed = int(st.session_state.get("far_va_be_exam_last_passed", 0) or 0)
                if stopped:
                    st.warning("หยุดการตรวจอัตโนมัติ (ผิดติดกัน 2 ครั้ง)")
                if last_passed > 0:
                    st.success(f"ผลที่อ่านได้: สไลด์ {last_passed} = {fmt_va(last_passed)}")
                    if st.button("ใช้ผลนี้เป็น VA Both eyes", key="far_va_be_exam_apply"):
                        st.session_state["far_va_be_exam_apply_pending"] = last_passed
                        st.rerun()

        # Apply exam-mode result before instantiating the widget.
        if st.session_state.get("far_va_re_exam_apply_pending"):
            st.session_state["far_va_re"] = int(st.session_state["far_va_re_exam_apply_pending"])
            st.session_state["far_va_re_exam_apply_pending"] = None

        st.markdown("3) Acuity Right eye (1–14)")
        va_re_col, exam_re_col = st.columns([0.8, 1.6])
        with va_re_col:
            far_va_re = st.selectbox(
                "3) Acuity Right eye (1–14)",
                [None] + list(range(1, 15)),
                index=_index_for(st.session_state["far_va_re"], [None] + list(range(1, 15)), 0),
                format_func=lambda x: "-" if x is None else fmt_va(x),
                key="far_va_re",
                label_visibility="collapsed",
            )
        with exam_re_col:
            with st.expander(
                "Exam mode (Far VA Right eye)",
                expanded=st.session_state.get("far_va_re_exam_enabled", False),
            ):
                st.session_state["far_va_re_exam_enabled"] = True
                key = FAR_VA_RE_KEY
                max_slide = len(key)
                slide = int(st.session_state.get("far_va_re_exam_slide", 1) or 1)
                slide = min(max(slide, 1), max_slide)
                wrong_streak = int(st.session_state.get("far_va_re_exam_wrong_streak", 0) or 0)
                last_passed = int(st.session_state.get("far_va_re_exam_last_passed", 0) or 0)
                stopped = bool(st.session_state.get("far_va_re_exam_stopped", False))

                st.write(f"สไลด์ปัจจุบัน: **{slide} / {max_slide}**")
                st.write(f"เฉลย: **{key[slide-1]}**")
                st.caption(f"ผิดติดกัน: {wrong_streak}/2 | ผ่านล่าสุด: {last_passed}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    correct_click = st.button("✅ ถูก", key="far_va_re_exam_correct", disabled=stopped)
                with c2:
                    wrong_click = st.button("❌ ผิด", key="far_va_re_exam_wrong", disabled=stopped)
                with c3:
                    reset_click = st.button("↺ รีเซ็ต", key="far_va_re_exam_reset")

                if reset_click:
                    st.session_state["far_va_re_exam_slide"] = 1
                    st.session_state["far_va_re_exam_wrong_streak"] = 0
                    st.session_state["far_va_re_exam_last_passed"] = 0
                    st.session_state["far_va_re_exam_stopped"] = False
                    st.rerun()

                if correct_click and not stopped:
                    st.session_state["far_va_re_exam_last_passed"] = slide
                    st.session_state["far_va_re_exam_wrong_streak"] = 0
                    st.session_state["far_va_re_exam_slide"] = min(slide + 1, max_slide)
                    st.rerun()

                if wrong_click and not stopped:
                    wrong_streak += 1
                    st.session_state["far_va_re_exam_wrong_streak"] = wrong_streak
                    st.session_state["far_va_re_exam_slide"] = min(slide + 1, max_slide)
                    if wrong_streak >= 2:
                        st.session_state["far_va_re_exam_stopped"] = True
                    st.rerun()

                stopped = bool(st.session_state.get("far_va_re_exam_stopped", False))
                last_passed = int(st.session_state.get("far_va_re_exam_last_passed", 0) or 0)
                if stopped:
                    st.warning("หยุดการตรวจอัตโนมัติ (ผิดติดกัน 2 ครั้ง)")
                if last_passed > 0:
                    st.success(f"ผลที่อ่านได้: สไลด์ {last_passed} = {fmt_va(last_passed)}")
                    if st.button("ใช้ผลนี้", key="far_va_re_exam_apply"):
                        st.session_state["far_va_re_exam_apply_pending"] = last_passed
                        st.rerun()

        # Apply exam-mode result before instantiating the widget.
        if st.session_state.get("far_va_le_exam_apply_pending"):
            st.session_state["far_va_le"] = int(st.session_state["far_va_le_exam_apply_pending"])
            st.session_state["far_va_le_exam_apply_pending"] = None

        st.markdown("4) Acuity Left eye (1–14)")
        va_le_col, exam_le_col = st.columns([0.8, 1.6])
        with va_le_col:
            far_va_le = st.selectbox(
                "4) Acuity Left eye (1–14)",
                [None] + list(range(1, 15)),
                index=_index_for(st.session_state["far_va_le"], [None] + list(range(1, 15)), 0),
                format_func=lambda x: "-" if x is None else fmt_va(x),
                key="far_va_le",
                label_visibility="collapsed",
            )
        with exam_le_col:
            with st.expander(
                "Exam mode (Far VA Left eye)",
                expanded=st.session_state.get("far_va_le_exam_enabled", False),
            ):
                st.session_state["far_va_le_exam_enabled"] = True
                key = FAR_VA_LE_KEY
                max_slide = len(key)
                slide = int(st.session_state.get("far_va_le_exam_slide", 1) or 1)
                slide = min(max(slide, 1), max_slide)
                wrong_streak = int(st.session_state.get("far_va_le_exam_wrong_streak", 0) or 0)
                last_passed = int(st.session_state.get("far_va_le_exam_last_passed", 0) or 0)
                stopped = bool(st.session_state.get("far_va_le_exam_stopped", False))

                st.write(f"สไลด์ปัจจุบัน: **{slide} / {max_slide}**")
                st.write(f"เฉลย: **{key[slide-1]}**")
                st.caption(f"ผิดติดกัน: {wrong_streak}/2 | ผ่านล่าสุด: {last_passed}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    correct_click = st.button("✅ ถูก", key="far_va_le_exam_correct", disabled=stopped)
                with c2:
                    wrong_click = st.button("❌ ผิด", key="far_va_le_exam_wrong", disabled=stopped)
                with c3:
                    reset_click = st.button("↺ รีเซ็ต", key="far_va_le_exam_reset")

                if reset_click:
                    st.session_state["far_va_le_exam_slide"] = 1
                    st.session_state["far_va_le_exam_wrong_streak"] = 0
                    st.session_state["far_va_le_exam_last_passed"] = 0
                    st.session_state["far_va_le_exam_stopped"] = False
                    st.rerun()

                if correct_click and not stopped:
                    st.session_state["far_va_le_exam_last_passed"] = slide
                    st.session_state["far_va_le_exam_wrong_streak"] = 0
                    st.session_state["far_va_le_exam_slide"] = min(slide + 1, max_slide)
                    st.rerun()

                if wrong_click and not stopped:
                    wrong_streak += 1
                    st.session_state["far_va_le_exam_wrong_streak"] = wrong_streak
                    st.session_state["far_va_le_exam_slide"] = min(slide + 1, max_slide)
                    if wrong_streak >= 2:
                        st.session_state["far_va_le_exam_stopped"] = True
                    st.rerun()

                stopped = bool(st.session_state.get("far_va_le_exam_stopped", False))
                last_passed = int(st.session_state.get("far_va_le_exam_last_passed", 0) or 0)
                if stopped:
                    st.warning("หยุดการตรวจอัตโนมัติ (ผิดติดกัน 2 ครั้ง)")
                if last_passed > 0:
                    st.success(f"ผลที่อ่านได้: สไลด์ {last_passed} = {fmt_va(last_passed)}")
                    if st.button("ใช้ผลนี้", key="far_va_le_exam_apply"):
                        st.session_state["far_va_le_exam_apply_pending"] = last_passed
                        st.rerun()

        # Apply exam-mode result before instantiating the widget.
        if st.session_state.get("far_stereo_exam_apply_pending"):
            st.session_state["far_stereo"] = int(st.session_state["far_stereo_exam_apply_pending"])
            st.session_state["far_stereo_exam_apply_pending"] = None

        st.markdown("5) Stereo depth (1–9)")
        stereo_col, stereo_exam_col = st.columns([0.8, 1.6])
        with stereo_col:
            far_stereo = st.selectbox(
                "5) Stereo depth (1–9)",
                options=[None] + list(range(1, 10)),
                index=_index_for(st.session_state["far_stereo"], [None] + list(range(1, 10)), 0),
                format_func=lambda x: "—" if x is None else fmt_stereo(x),
                key="far_stereo",
                label_visibility="collapsed",
            )
        with stereo_exam_col:
            with st.expander(
                "Exam mode (Far Stereo depth)",
                expanded=st.session_state.get("far_stereo_exam_enabled", False),
            ):
                st.session_state["far_stereo_exam_enabled"] = True
                key = FAR_STEREO_KEY
                max_slide = len(key)
                slide = int(st.session_state.get("far_stereo_exam_slide", 1) or 1)
                slide = min(max(slide, 1), max_slide)
                wrong_streak = int(st.session_state.get("far_stereo_exam_wrong_streak", 0) or 0)
                last_passed = int(st.session_state.get("far_stereo_exam_last_passed", 0) or 0)
                stopped = bool(st.session_state.get("far_stereo_exam_stopped", False))

                st.write(f"สไลด์ปัจจุบัน: **{slide} / {max_slide}**")
                st.write(f"เฉลย: **{key[slide-1]}**")
                st.caption(f"ผิดติดกัน: {wrong_streak}/2 | ผ่านล่าสุด: {last_passed}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    correct_click = st.button("✅ ถูก", key="far_stereo_exam_correct", disabled=stopped)
                with c2:
                    wrong_click = st.button("❌ ผิด", key="far_stereo_exam_wrong", disabled=stopped)
                with c3:
                    reset_click = st.button("↺ รีเซ็ต", key="far_stereo_exam_reset")

                if reset_click:
                    st.session_state["far_stereo_exam_slide"] = 1
                    st.session_state["far_stereo_exam_wrong_streak"] = 0
                    st.session_state["far_stereo_exam_last_passed"] = 0
                    st.session_state["far_stereo_exam_stopped"] = False
                    st.rerun()

                if correct_click and not stopped:
                    st.session_state["far_stereo_exam_last_passed"] = slide
                    st.session_state["far_stereo_exam_wrong_streak"] = 0
                    st.session_state["far_stereo_exam_slide"] = min(slide + 1, max_slide)
                    st.rerun()

                if wrong_click and not stopped:
                    wrong_streak += 1
                    st.session_state["far_stereo_exam_wrong_streak"] = wrong_streak
                    st.session_state["far_stereo_exam_slide"] = min(slide + 1, max_slide)
                    if wrong_streak >= 2:
                        st.session_state["far_stereo_exam_stopped"] = True
                    st.rerun()

                stopped = bool(st.session_state.get("far_stereo_exam_stopped", False))
                last_passed = int(st.session_state.get("far_stereo_exam_last_passed", 0) or 0)
                if stopped:
                    st.warning("หยุดการตรวจอัตโนมัติ (ผิดติดกัน 2 ครั้ง)")
                if last_passed > 0:
                    st.success(f"ผลที่อ่านได้: สไลด์ {last_passed} = {fmt_stereo(last_passed)}")
                    if st.button("ใช้ผลนี้", key="far_stereo_exam_apply"):
                        st.session_state["far_stereo_exam_apply_pending"] = last_passed
                        st.rerun()

        # Apply exam-mode result before instantiating the widget.
        if st.session_state.get("far_color_exam_apply_pending"):
            st.session_state["far_color_correct"] = int(st.session_state["far_color_exam_apply_pending"])
            st.session_state["far_color_exam_apply_pending"] = None

        st.markdown("6) Color correct (0–8)")
        color_col, color_exam_col = st.columns([0.8, 1.6])
        with color_col:
            far_color_correct = st.number_input(
                "6) Color correct (0–8)",
                min_value=0,
                max_value=8,
                value=st.session_state["far_color_correct"],
                key="far_color_correct",
                label_visibility="collapsed",
            )
        with color_exam_col:
            with st.expander(
                "Exam mode (Far Color)",
                expanded=st.session_state.get("far_color_exam_enabled", False),
            ):
                st.session_state["far_color_exam_enabled"] = True
                key = FAR_COLOR_KEY
                max_slide = len(key)
                slide = int(st.session_state.get("far_color_exam_slide", 1) or 1)
                slide = min(max(slide, 1), max_slide)
                wrong_streak = int(st.session_state.get("far_color_exam_wrong_streak", 0) or 0)
                last_passed = int(st.session_state.get("far_color_exam_last_passed", 0) or 0)
                stopped = bool(st.session_state.get("far_color_exam_stopped", False))

                st.write(f"สไลด์ปัจจุบัน: **{slide} / {max_slide}**")
                st.write(f"เฉลย: **{key[slide-1]}**")
                st.caption("หมายเหตุ: สไลด์ที่ 6 เฉลยเป็น x = คนตาปกติไม่ควรเห็นเลข")
                st.caption(f"ผิดติดกัน: {wrong_streak}/2 | ผ่านล่าสุด: {last_passed}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    correct_click = st.button("✅ ถูก", key="far_color_exam_correct", disabled=stopped)
                with c2:
                    wrong_click = st.button("❌ ผิด", key="far_color_exam_wrong", disabled=stopped)
                with c3:
                    reset_click = st.button("↺ รีเซ็ต", key="far_color_exam_reset")

                if reset_click:
                    st.session_state["far_color_exam_slide"] = 1
                    st.session_state["far_color_exam_wrong_streak"] = 0
                    st.session_state["far_color_exam_last_passed"] = 0
                    st.session_state["far_color_exam_stopped"] = False
                    st.rerun()

                if correct_click and not stopped:
                    st.session_state["far_color_exam_last_passed"] = slide
                    st.session_state["far_color_exam_wrong_streak"] = 0
                    st.session_state["far_color_exam_slide"] = min(slide + 1, max_slide)
                    st.rerun()

                if wrong_click and not stopped:
                    wrong_streak += 1
                    st.session_state["far_color_exam_wrong_streak"] = wrong_streak
                    st.session_state["far_color_exam_slide"] = min(slide + 1, max_slide)
                    if wrong_streak >= 2:
                        st.session_state["far_color_exam_stopped"] = True
                    st.rerun()

                stopped = bool(st.session_state.get("far_color_exam_stopped", False))
                last_passed = int(st.session_state.get("far_color_exam_last_passed", 0) or 0)
                if stopped:
                    st.warning("หยุดการตรวจอัตโนมัติ (ผิดติดกัน 2 ครั้ง)")
                if last_passed > 0:
                    st.success(f"ผลที่อ่านได้: สไลด์ {last_passed}")
                    if st.button("ใช้ผลนี้ (จำนวนที่ผ่าน)", key="far_color_exam_apply"):
                        st.session_state["far_color_exam_apply_pending"] = last_passed
                        st.rerun()

        far_vphoria = st.selectbox(
            "7) Vertical phoria (1–7)",
            options=[None] + list(range(1, 8)),
            index=_index_for(st.session_state["far_vphoria"], [None] + list(range(1, 8)), 0),
            format_func=lambda x: "?" if x is None else str(x),
            key="far_vphoria",
        )
        far_lphoria = st.selectbox(
            "8) Lateral phoria (1–15)",
            options=[None] + list(range(1, 16)),
            index=_index_for(st.session_state["far_lphoria"], [None] + list(range(1, 16)), 0),
            format_func=lambda x: "?" if x is None else str(x),
            key="far_lphoria",
        )
        st.caption("หมายเหตุ: ถ้ากลุ่มอาชีพนั้น ๆ เป็น N/A ระบบจะไม่ตัดตก แต่ยังให้บันทึกได้")

    with near_col:
        st.markdown("### Near vision (14 in.)")

        # Keep Near vision fields in a strict vertical order (important for mobile UI).
        near_binocular_ok = st.checkbox("1) Binocular vision (3 cubes) — ผ่าน (Near)", key="near_binocular_ok")

        # Apply exam-mode result before instantiating the VA widget.
        if st.session_state.get("near_va_be_exam_apply_pending"):
            st.session_state["near_va_be"] = int(st.session_state["near_va_be_exam_apply_pending"])
            st.session_state["near_va_be_exam_apply_pending"] = None

        st.markdown("2) Near Acuity Both eyes (1–14)")
        near_va_be_col, near_exam_col = st.columns([0.8, 1.6])
        with near_va_be_col:
            near_va_be = st.selectbox(
                "2) Near Acuity Both eyes (1–14)",
                list(range(1, 15)),
                index=_index_for(st.session_state["near_va_be"], list(range(1, 15)), 8),
                format_func=lambda x: fmt_va(x),
                key="near_va_be",
                label_visibility="collapsed",
            )
        with near_exam_col:
            with st.expander(
                "Exam mode (Near VA Both eyes)",
                expanded=st.session_state.get("near_va_be_exam_enabled", False),
            ):
                st.session_state["near_va_be_exam_enabled"] = True
                key = NEAR_VA_BE_KEY
                max_slide = len(key)
                slide = int(st.session_state.get("near_va_be_exam_slide", 1) or 1)
                slide = min(max(slide, 1), max_slide)
                wrong_streak = int(st.session_state.get("near_va_be_exam_wrong_streak", 0) or 0)
                last_passed = int(st.session_state.get("near_va_be_exam_last_passed", 0) or 0)
                stopped = bool(st.session_state.get("near_va_be_exam_stopped", False))

                st.write(f"สไลด์ปัจจุบัน: **{slide} / {max_slide}**")
                st.write(f"เฉลย: **{key[slide-1]}**")
                st.caption(f"ผิดติดกัน: {wrong_streak}/2 | ผ่านล่าสุด: {last_passed}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    correct_click = st.button("✅ ถูก", key="near_va_be_exam_correct", disabled=stopped)
                with c2:
                    wrong_click = st.button("❌ ผิด", key="near_va_be_exam_wrong", disabled=stopped)
                with c3:
                    reset_click = st.button("↺ รีเซ็ต", key="near_va_be_exam_reset")

                if reset_click:
                    st.session_state["near_va_be_exam_slide"] = 1
                    st.session_state["near_va_be_exam_wrong_streak"] = 0
                    st.session_state["near_va_be_exam_last_passed"] = 0
                    st.session_state["near_va_be_exam_stopped"] = False
                    st.rerun()

                if correct_click and not stopped:
                    st.session_state["near_va_be_exam_last_passed"] = slide
                    st.session_state["near_va_be_exam_wrong_streak"] = 0
                    st.session_state["near_va_be_exam_slide"] = min(slide + 1, max_slide)
                    st.rerun()

                if wrong_click and not stopped:
                    wrong_streak += 1
                    st.session_state["near_va_be_exam_wrong_streak"] = wrong_streak
                    st.session_state["near_va_be_exam_slide"] = min(slide + 1, max_slide)
                    if wrong_streak >= 2:
                        st.session_state["near_va_be_exam_stopped"] = True
                    st.rerun()

                stopped = bool(st.session_state.get("near_va_be_exam_stopped", False))
                last_passed = int(st.session_state.get("near_va_be_exam_last_passed", 0) or 0)
                if stopped:
                    st.warning("หยุดการตรวจอัตโนมัติ (ผิดติดกัน 2 ครั้ง)")
                if last_passed > 0:
                    st.success(f"ผลที่อ่านได้: สไลด์ {last_passed} = {fmt_va(last_passed)}")
                    if st.button("ใช้ผลนี้เป็น Near VA Both eyes", key="near_va_be_exam_apply"):
                        st.session_state["near_va_be_exam_apply_pending"] = last_passed
                        st.rerun()

        # Apply exam-mode result before instantiating the widget.
        if st.session_state.get("near_va_re_exam_apply_pending"):
            st.session_state["near_va_re"] = int(st.session_state["near_va_re_exam_apply_pending"])
            st.session_state["near_va_re_exam_apply_pending"] = None

        st.markdown("3) Near Acuity Right eye (1–14)")
        near_va_re_col, near_re_exam_col = st.columns([0.8, 1.6])
        with near_va_re_col:
            near_va_re = st.selectbox(
                "3) Near Acuity Right eye (1–14)",
                [None] + list(range(1, 15)),
                index=_index_for(st.session_state["near_va_re"], [None] + list(range(1, 15)), 0),
                format_func=lambda x: "-" if x is None else fmt_va(x),
                key="near_va_re",
                label_visibility="collapsed",
            )
        with near_re_exam_col:
            with st.expander(
                "Exam mode (Near VA Right eye)",
                expanded=st.session_state.get("near_va_re_exam_enabled", False),
            ):
                st.session_state["near_va_re_exam_enabled"] = True
                key = NEAR_VA_RE_KEY
                max_slide = len(key)
                slide = int(st.session_state.get("near_va_re_exam_slide", 1) or 1)
                slide = min(max(slide, 1), max_slide)
                wrong_streak = int(st.session_state.get("near_va_re_exam_wrong_streak", 0) or 0)
                last_passed = int(st.session_state.get("near_va_re_exam_last_passed", 0) or 0)
                stopped = bool(st.session_state.get("near_va_re_exam_stopped", False))

                st.write(f"สไลด์ปัจจุบัน: **{slide} / {max_slide}**")
                st.write(f"เฉลย: **{key[slide-1]}**")
                st.caption(f"ผิดติดกัน: {wrong_streak}/2 | ผ่านล่าสุด: {last_passed}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    correct_click = st.button("✅ ถูก", key="near_va_re_exam_correct", disabled=stopped)
                with c2:
                    wrong_click = st.button("❌ ผิด", key="near_va_re_exam_wrong", disabled=stopped)
                with c3:
                    reset_click = st.button("↺ รีเซ็ต", key="near_va_re_exam_reset")

                if reset_click:
                    st.session_state["near_va_re_exam_slide"] = 1
                    st.session_state["near_va_re_exam_wrong_streak"] = 0
                    st.session_state["near_va_re_exam_last_passed"] = 0
                    st.session_state["near_va_re_exam_stopped"] = False
                    st.rerun()

                if correct_click and not stopped:
                    st.session_state["near_va_re_exam_last_passed"] = slide
                    st.session_state["near_va_re_exam_wrong_streak"] = 0
                    st.session_state["near_va_re_exam_slide"] = min(slide + 1, max_slide)
                    st.rerun()

                if wrong_click and not stopped:
                    wrong_streak += 1
                    st.session_state["near_va_re_exam_wrong_streak"] = wrong_streak
                    st.session_state["near_va_re_exam_slide"] = min(slide + 1, max_slide)
                    if wrong_streak >= 2:
                        st.session_state["near_va_re_exam_stopped"] = True
                    st.rerun()

                stopped = bool(st.session_state.get("near_va_re_exam_stopped", False))
                last_passed = int(st.session_state.get("near_va_re_exam_last_passed", 0) or 0)
                if stopped:
                    st.warning("หยุดการตรวจอัตโนมัติ (ผิดติดกัน 2 ครั้ง)")
                if last_passed > 0:
                    st.success(f"ผลที่อ่านได้: สไลด์ {last_passed} = {fmt_va(last_passed)}")
                    if st.button("ใช้ผลนี้", key="near_va_re_exam_apply"):
                        st.session_state["near_va_re_exam_apply_pending"] = last_passed
                        st.rerun()

        # Apply exam-mode result before instantiating the widget.
        if st.session_state.get("near_va_le_exam_apply_pending"):
            st.session_state["near_va_le"] = int(st.session_state["near_va_le_exam_apply_pending"])
            st.session_state["near_va_le_exam_apply_pending"] = None

        st.markdown("4) Near Acuity Left eye (1–14)")
        near_va_le_col, near_le_exam_col = st.columns([0.8, 1.6])
        with near_va_le_col:
            near_va_le = st.selectbox(
                "4) Near Acuity Left eye (1–14)",
                [None] + list(range(1, 15)),
                index=_index_for(st.session_state["near_va_le"], [None] + list(range(1, 15)), 0),
                format_func=lambda x: "-" if x is None else fmt_va(x),
                key="near_va_le",
                label_visibility="collapsed",
            )
        with near_le_exam_col:
            with st.expander(
                "Exam mode (Near VA Left eye)",
                expanded=st.session_state.get("near_va_le_exam_enabled", False),
            ):
                st.session_state["near_va_le_exam_enabled"] = True
                key = NEAR_VA_LE_KEY
                max_slide = len(key)
                slide = int(st.session_state.get("near_va_le_exam_slide", 1) or 1)
                slide = min(max(slide, 1), max_slide)
                wrong_streak = int(st.session_state.get("near_va_le_exam_wrong_streak", 0) or 0)
                last_passed = int(st.session_state.get("near_va_le_exam_last_passed", 0) or 0)
                stopped = bool(st.session_state.get("near_va_le_exam_stopped", False))

                st.write(f"สไลด์ปัจจุบัน: **{slide} / {max_slide}**")
                st.write(f"เฉลย: **{key[slide-1]}**")
                st.caption(f"ผิดติดกัน: {wrong_streak}/2 | ผ่านล่าสุด: {last_passed}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    correct_click = st.button("✅ ถูก", key="near_va_le_exam_correct", disabled=stopped)
                with c2:
                    wrong_click = st.button("❌ ผิด", key="near_va_le_exam_wrong", disabled=stopped)
                with c3:
                    reset_click = st.button("↺ รีเซ็ต", key="near_va_le_exam_reset")

                if reset_click:
                    st.session_state["near_va_le_exam_slide"] = 1
                    st.session_state["near_va_le_exam_wrong_streak"] = 0
                    st.session_state["near_va_le_exam_last_passed"] = 0
                    st.session_state["near_va_le_exam_stopped"] = False
                    st.rerun()

                if correct_click and not stopped:
                    st.session_state["near_va_le_exam_last_passed"] = slide
                    st.session_state["near_va_le_exam_wrong_streak"] = 0
                    st.session_state["near_va_le_exam_slide"] = min(slide + 1, max_slide)
                    st.rerun()

                if wrong_click and not stopped:
                    wrong_streak += 1
                    st.session_state["near_va_le_exam_wrong_streak"] = wrong_streak
                    st.session_state["near_va_le_exam_slide"] = min(slide + 1, max_slide)
                    if wrong_streak >= 2:
                        st.session_state["near_va_le_exam_stopped"] = True
                    st.rerun()

                stopped = bool(st.session_state.get("near_va_le_exam_stopped", False))
                last_passed = int(st.session_state.get("near_va_le_exam_last_passed", 0) or 0)
                if stopped:
                    st.warning("หยุดการตรวจอัตโนมัติ (ผิดติดกัน 2 ครั้ง)")
                if last_passed > 0:
                    st.success(f"ผลที่อ่านได้: สไลด์ {last_passed} = {fmt_va(last_passed)}")
                    if st.button("ใช้ผลนี้", key="near_va_le_exam_apply"):
                        st.session_state["near_va_le_exam_apply_pending"] = last_passed
                        st.rerun()

        near_vphoria = st.selectbox(
            "7) Near Vertical phoria (1–7)",
            options=[None] + list(range(1, 8)),
            index=_index_for(st.session_state["near_vphoria"], [None] + list(range(1, 8)), 0),
            format_func=lambda x: "?" if x is None else str(x),
            key="near_vphoria",
        )
        near_lphoria = st.selectbox(
            "8) Near Lateral phoria (1–15)",
            options=[None] + list(range(1, 16)),
            index=_index_for(st.session_state["near_lphoria"], [None] + list(range(1, 16)), 0),
            format_func=lambda x: "?" if x is None else str(x),
            key="near_lphoria",
        )

    if include_intermediate:
        st.markdown("### Intermediate (ตามตารางมาตรฐาน)")
        inter_cols = st.columns([1, 1, 1])
        with inter_cols[0]:
            st.info("Intermediate ในตารางนี้เน้นเฉพาะ VA (BE/RE/LE)")
        with inter_cols[1]:
            inter_va_be = st.selectbox(
                "Inter Acuity Both eyes (1–14)",
                options=[None] + list(range(1, 15)),
                index=_index_for(st.session_state["inter_va_be"], [None] + list(range(1, 15)), 0),
                format_func=lambda x: "—" if x is None else fmt_va(x),
                key="inter_va_be",
            )
            inter_va_re = st.selectbox(
                "Inter Acuity Right eye (1–14)",
                options=[None] + list(range(1, 15)),
                index=_index_for(st.session_state["inter_va_re"], [None] + list(range(1, 15)), 0),
                format_func=lambda x: "—" if x is None else fmt_va(x),
                key="inter_va_re",
            )
            inter_va_le = st.selectbox(
                "Inter Acuity Left eye (1–14)",
                options=[None] + list(range(1, 15)),
                index=_index_for(st.session_state["inter_va_le"], [None] + list(range(1, 15)), 0),
                format_func=lambda x: "—" if x is None else fmt_va(x),
                key="inter_va_le",
            )
        with inter_cols[2]:
            st.caption("ถ้ากลุ่มอาชีพเป็น N/A ระบบจะไม่ประเมินหัวข้อนี้")
    else:
        inter_va_be = inter_va_re = inter_va_le = None

    if include_visual_field:
        st.markdown("### Visual field (คัดกรอง/Perimeter score)")
        vf_status = "ปกติ"
        vf_cols = st.columns([1, 1])
        with vf_cols[0]:
            st.markdown("**Right Eye**")
            vf_right_temp = st.selectbox("Right Temporal (°)", options=[85, 70, 55, "ไม่เห็นแสง"], index=0, key="vf_right_temp")
            vf_right_nasal_seen = st.checkbox("Right Nasal 45° เห็นแสง", key="vf_right_nasal_seen")
        with vf_cols[1]:
            st.markdown("**Left Eye**")
            vf_left_temp = st.selectbox("Left Temporal (°)", options=[85, 70, 55, "ไม่เห็นแสง"], index=0, key="vf_left_temp")
            vf_left_nasal_seen = st.checkbox("Left Nasal 45° เห็นแสง", key="vf_left_nasal_seen")
    else:
        vf_status = "ปกติ"
        vf_right_temp = vf_left_temp = None
        vf_right_nasal_seen = vf_left_nasal_seen = None

    # อาการร่วมถูกตัดออกตามที่ร้องขอ

with right:
    st.subheader("แปลผลอัตโนมัติ (Auto-interpretation) + คำแนะนำ")

    std: Standards = JOB_GROUPS[job_key]["std"]

    fails: List[str] = []
    details: List[Tuple[bool, str]] = []

    # FAR
    st.markdown("#### Far vision — เทียบเกณฑ์")
    if std.far_binocular_required:
        ok_bino = bool(far_binocular_ok)
        details.append((ok_bino, f"Binocular vision: {'ผ่าน' if ok_bino else 'ไม่ผ่าน'} (เกณฑ์: 3 cubes)"))
        if not ok_bino:
            fails.append("Binocular (Far)")

    ok, msg = eval_min("VA (Far) Both eyes", far_va_be, std.far_va_be_min)
    details.append((ok, msg))
    if not ok:
        fails.append("VA (Far) BE")

    ok, msg = eval_min("VA (Far) Right eye", far_va_re, std.far_va_re_min)
    details.append((ok, msg))
    if not ok:
        fails.append("VA (Far) RE")

    ok, msg = eval_min("VA (Far) Left eye", far_va_le, std.far_va_le_min)
    details.append((ok, msg))
    if not ok:
        fails.append("VA (Far) LE")

    ok, msg = eval_stereo(far_stereo, std.far_stereo_min)
    details.append((ok, msg))
    if not ok:
        fails.append("Stereo (Far)")

    ok, msg = eval_color(far_color_correct, std.far_color_min_correct)
    details.append((ok, msg))
    if not ok:
        fails.append("Color (Far)")

    ok, msg = eval_range("Vertical Phoria (Far)", far_vphoria, std.far_vphoria_range, na_ok=True)
    details.append((ok, msg))
    if not ok:
        fails.append("Vertical Phoria (Far)")

    ok, msg = eval_range("Lateral Phoria (Far)", far_lphoria, std.far_lphoria_range, na_ok=True)
    details.append((ok, msg))
    if not ok:
        fails.append("Lateral Phoria (Far)")

    # NEAR
    st.markdown("#### Near vision — เทียบเกณฑ์")
    if std.near_binocular_required:
        ok_bino_n = bool(near_binocular_ok)
        details.append((ok_bino_n, f"Binocular vision (Near): {'ผ่าน' if ok_bino_n else 'ไม่ผ่าน'} (เกณฑ์: 3 cubes)"))
        if not ok_bino_n:
            fails.append("Binocular (Near)")

    ok, msg = eval_min("VA (Near) Both eyes", near_va_be, std.near_va_be_min)
    details.append((ok, msg))
    if not ok:
        fails.append("VA (Near) BE")

    ok, msg = eval_min("VA (Near) Right eye", near_va_re, std.near_va_re_min)
    details.append((ok, msg))
    if not ok:
        fails.append("VA (Near) RE")

    ok, msg = eval_min("VA (Near) Left eye", near_va_le, std.near_va_le_min)
    details.append((ok, msg))
    if not ok:
        fails.append("VA (Near) LE")

    ok, msg = eval_range("Vertical Phoria (Near)", near_vphoria, std.near_vphoria_range, na_ok=True)
    details.append((ok, msg))
    if not ok:
        fails.append("Vertical Phoria (Near)")

    ok, msg = eval_range("Lateral Phoria (Near)", near_lphoria, std.near_lphoria_range, na_ok=True)
    details.append((ok, msg))
    if not ok:
        fails.append("Lateral Phoria (Near)")

    # Intermediate (optional)
    if include_intermediate:
        st.markdown("#### Intermediate — เทียบเกณฑ์")
        if std.inter_va_be_min is not None:
            ok, msg = eval_min("VA (Inter) Both eyes", inter_va_be, std.inter_va_be_min)
            details.append((ok, msg))
            if not ok:
                fails.append("VA (Inter) BE")
            ok, msg = eval_min("VA (Inter) Right eye", inter_va_re, std.inter_va_re_min)
            details.append((ok, msg))
            if not ok:
                fails.append("VA (Inter) RE")
            ok, msg = eval_min("VA (Inter) Left eye", inter_va_le, std.inter_va_le_min)
            details.append((ok, msg))
            if not ok:
                fails.append("VA (Inter) LE")
        else:
            details.append((True, "Intermediate: N/A (ตามตารางของกลุ่มอาชีพนี้)"))

    # Visual field is recorded for reference only (no automatic fail).

    # Show results
    all_ok = (len(fails) == 0)

    st.markdown("### สรุป")
    st.write(f"**กลุ่มอาชีพ:** {JOB_GROUPS[job_key]['label_th']}")
    st.write(f"**การแก้ไขสายตาขณะตรวจ:** Far = {far_correction} | Near = {near_correction}")
    st.write(f"**ผลรวม:** {pass_fail_icon(all_ok)} (อิงเกณฑ์ V2a ของกลุ่มอาชีพนี้)")

    # Quick save button directly under the summary.
    if st.button("บันทึกลง Firebase ตอนนี้"):
        st.session_state["firebase_save_request"] = True
        st.rerun()

    st.markdown("### รายละเอียดรายหัวข้อ")
    for ok, msg in details:
        st.write(f"{'✅' if ok else '❌'} {msg}")

    symptoms = {}
    recs = recommendation_from_failures(fails, symptoms)

    st.markdown("### คำแนะนำ (Recommendation) — *เป็นคำแนะนำ ไม่ใช่การตัดสินความเหมาะสม*")
    for r in recs:
        st.write(f"- {r}")

    st.markdown("### ส่วนแพทย์ตรวจทาน (Physician review)")
    physician_note = st.text_area("แพทย์ตรวจทาน/ข้อสังเกตเพิ่มเติม", value=st.session_state["physician_note"], height=100, key="physician_note")
    # Hide physician/technician name fields; keep payload shape stable.
    physician_name = ""
    tech_name = ""

    # Build export payload
    payload = {
        "meta": {
            "device": test_device,
            "job_group_key": job_key,
            "job_group_label": JOB_GROUPS[job_key]["label_th"],
            "exam_date": str(exam_date),
        },
        "person": {
            "name": name, "hn": hn, "age": age, "gender": gender
        },
        "correction": {
            "far": far_correction,
            "near": near_correction
        },
        "inputs": {
            "far": {
                "binocular_ok": far_binocular_ok,
                "va_be": far_va_be, "va_re": far_va_re, "va_le": far_va_le,
                "stereo": far_stereo, "color_correct": far_color_correct,
                "vphoria": far_vphoria, "lphoria": far_lphoria
            },
            "near": {
                "binocular_ok": near_binocular_ok,
                "va_be": near_va_be, "va_re": near_va_re, "va_le": near_va_le,
                "vphoria": near_vphoria, "lphoria": near_lphoria
            },
            "intermediate": {
                "va_be": inter_va_be, "va_re": inter_va_re, "va_le": inter_va_le
            } if include_intermediate else None,
            "visual_field": {
                "status": vf_status,
                "right_temp": vf_right_temp,
                "right_nasal_seen": vf_right_nasal_seen,
                "left_temp": vf_left_temp,
                "left_nasal_seen": vf_left_nasal_seen
            } if include_visual_field else None,
            "symptoms": symptoms
        },
        "auto_interpretation": {
            "overall_ok": all_ok,
            "fails": fails,
            "details": [{"ok": ok, "message": msg} for ok, msg in details],
            "recommendations": recs
        },
        "review": {
            "technician": tech_name,
            "physician": physician_name,
            "physician_note": physician_note
        }
    }

    with st.expander("Cloud Sync (Firebase)", expanded=False):
        st.caption("บันทึก/เปิดเคสแบบเรียลไทม์ด้วย Firestore")
        if not FIREBASE_AVAILABLE:
            st.warning("ยังไม่มีไลบรารี Firebase (firebase-admin).")
        else:
            secrets_fb = None
            secrets_fb_error = None
            if st.secrets and "firebase" in st.secrets:
                fb_section = st.secrets["firebase"]
                # Prefer explicit TOML keys if present
                required_keys = {
                    "type", "project_id", "private_key_id", "private_key", "client_email",
                    "client_id", "auth_uri", "token_uri", "auth_provider_x509_cert_url",
                    "client_x509_cert_url", "universe_domain",
                }
                if required_keys.issubset(set(fb_section.keys())):
                    secrets_fb = {k: fb_section[k] for k in required_keys}
                elif "service_account_json" in fb_section:
                    try:
                        secrets_fb = json.loads(fb_section["service_account_json"])
                    except Exception as e:
                        secrets_fb_error = f"อ่าน service_account_json ไม่ได้: {e}"
                else:
                    secrets_fb_error = "Secrets ไม่ครบ (ต้องมี service_account_json หรือคีย์แยกครบชุด)"

                if not st.session_state.get("firebase_collection"):
                    st.session_state["firebase_collection"] = fb_section.get("collection", "vision_records")

            if secrets_fb:
                st.success("อ่าน Firebase Secrets สำเร็จ (พร้อมใช้งาน)")
            elif secrets_fb_error:
                st.warning(f"อ่าน Firebase Secrets ไม่สำเร็จ: {secrets_fb_error}")
                st.caption("แนะนำใช้ TOML แบบแยกคีย์ (ไม่ใช้ service_account_json) หรือใส่ service_account_json ให้ถูกต้อง")

            # Hide local-only upload inputs when secrets are already configured (e.g., Streamlit Cloud).
            fb_file = None
            fb_text = ""
            if not secrets_fb:
                with st.expander("Advanced: Service account (local only)", expanded=False):
                    fb_file = st.file_uploader("Service account JSON (Firebase)", type=["json"])
                    fb_text = st.text_area(
                        "หรือวาง JSON ของ Service account ที่นี่ (Firebase)",
                        value="",
                        height=120,
                    )
            fb_collection = st.text_input("Firestore collection", key="firebase_collection")
            fb_refresh = st.number_input("รีเฟรชรายการทุก (วินาที)", min_value=5, max_value=60, value=st.session_state["firebase_refresh_sec"], key="firebase_refresh_sec")
            fb_auto = st.checkbox("เปิด Auto refresh รายการเคส", value=st.session_state["firebase_autorefresh"], key="firebase_autorefresh")
            fb_autosave = st.checkbox("Auto update เมื่อแก้ฟอร์ม (ต้องโหลดเคสก่อน)", value=st.session_state["firebase_autosave"], key="firebase_autosave")
            fb_search = st.text_input("ค้นหา (HN/ชื่อ)", value="")
            fb_use_date_filter = st.checkbox("กรองตามวันที่ตรวจ", value=False)
            fb_exam_date_filter = st.date_input("วันที่ตรวจ", value=datetime.today(), disabled=not fb_use_date_filter)

            fb_info = None
            if secrets_fb is not None:
                fb_info = secrets_fb
            elif fb_file is not None:
                try:
                    fb_info = json.load(fb_file)
                except Exception:
                    st.error("อ่านไฟล์ Service account ไม่ได้")
            elif fb_text.strip():
                try:
                    fb_info = json.loads(fb_text)
                except Exception:
                    st.error("JSON ไม่ถูกต้อง")

            if fb_info and fb_collection:
                try:
                    db = _firebase_client_from_info(fb_info)
                    if fb_auto and hasattr(st, "autorefresh"):
                        st.autorefresh(interval=int(fb_refresh * 1000), key="firebase_autorefresh_tick")
                    if st.session_state.get("firebase_save_request"):
                        _firebase_save_record(db, fb_collection, payload)
                        st.session_state["firebase_save_request"] = False
                        st.success("บันทึกสำเร็จ")
                    # Auto-update current case when form changes
                    if fb_autosave and st.session_state.get("firebase_doc_id"):
                        current_hash = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                        if current_hash != st.session_state.get("firebase_last_hash"):
                            _firebase_update_record(db, fb_collection, st.session_state["firebase_doc_id"], payload)
                            st.session_state["firebase_last_hash"] = current_hash
                    records = _firebase_list_records(db, fb_collection, limit=50)
                    exam_date_filter = fb_exam_date_filter if fb_use_date_filter else None
                    records = [
                        doc for doc in records
                        if _match_keyword(doc, fb_search) and _match_exam_date(doc, exam_date_filter)
                    ]
                    if records:
                        labels = [_firebase_label(doc) for doc in records]
                        sel = st.selectbox("เลือกเคสเพื่อโหลดเข้าแอป", options=list(range(len(records))), format_func=lambda i: labels[i])
                    else:
                        sel = None
                        st.info("ยังไม่มีข้อมูลใน collection นี้")

                    col_save, _ = st.columns([1, 1])
                    with col_save:
                        if st.button("บันทึกเคสนี้ขึ้น Firebase"):
                            _firebase_save_record(db, fb_collection, payload)
                            st.success("บันทึกสำเร็จ")

                    # Row-level actions: load/delete per record
                    if records:
                        st.caption("จัดการทีละเคส")
                        for doc in records:
                            data = doc.to_dict() or {}
                            person = data.get("person", {})
                            meta = data.get("meta", {})
                            label = f"{person.get('name','')} | HN:{person.get('hn','')} | {meta.get('exam_date','')}"
                            row_a, row_b, row_c = st.columns([6, 2, 2])
                            with row_a:
                                st.write(label)
                            with row_b:
                                if st.button("โหลด", key=f"fb_load_{doc.id}"):
                                    st.session_state["pending_payload"] = data
                                    st.session_state["firebase_doc_id"] = doc.id
                                    st.session_state["firebase_last_hash"] = ""
                                    st.rerun()
                            with row_c:
                                if st.button("ลบ", key=f"fb_del_{doc.id}"):
                                    _firebase_delete_record(db, fb_collection, doc.id)
                                    if st.session_state.get("firebase_doc_id") == doc.id:
                                        st.session_state["firebase_doc_id"] = ""
                                        st.session_state["firebase_last_hash"] = ""
                                    st.success("ลบเคสแล้ว")
                                    st.rerun()
                except Exception as e:
                    st.error(f"เชื่อมต่อ Firebase ไม่สำเร็จ: {e}")
                    try:
                        diag_info = _normalize_firebase_info(fb_info)
                        diag = _firebase_private_key_diagnostics(diag_info)
                        if diag.get("has_private_key"):
                            st.caption(
                                "Firebase key check: "
                                f"header={diag.get('has_header')} | "
                                f"footer={diag.get('has_footer')} | "
                                f"newlines={diag.get('newline_count')} | "
                                f"len={diag.get('length')} | "
                                f"project_id={diag.get('project_id')} | "
                                f"client_email={diag.get('client_email')}"
                            )
                        else:
                            st.caption("Firebase key check: ไม่พบ private_key ในข้อมูลที่โหลด")
                    except Exception:
                        pass
            else:
                st.info("กรอก Service account และชื่อ collection เพื่อเริ่มใช้งาน")

    txt_lines = []
    txt_lines.append("VISION SCREENING SUMMARY (Titmus V2a)")
    txt_lines.append(f"Date: {exam_date}")
    txt_lines.append(f"Name: {name} | HN: {hn} | Age: {age} | Gender: {gender}")
    txt_lines.append(f"Job group: {JOB_GROUPS[job_key]['label_th']}")
    txt_lines.append(f"Correction: Far={far_correction}, Near={near_correction}")
    txt_lines.append(f"Overall: {'PASS (meets reference)' if all_ok else 'BELOW REFERENCE in some items'}")
    if fails:
        txt_lines.append("Items below reference:")
        for f in fails:
            txt_lines.append(f"- {f}")
    txt_lines.append("")
    txt_lines.append("Details:")
    for ok, msg in details:
        txt_lines.append(f"- {'PASS' if ok else 'FAIL'}: {msg}")
    txt_lines.append("")
    txt_lines.append("Recommendations (advisory only):")
    for r in recs:
        txt_lines.append(f"- {r}")
    if physician_note.strip():
        txt_lines.append("")
        txt_lines.append("Physician review note:")
        txt_lines.append(physician_note.strip())

    summary_txt = "\n".join(txt_lines)
    st.download_button("ดาวน์โหลดสรุป (TXT)", data=summary_txt.encode("utf-8"),
                       file_name=f"vision_screening_{hn or 'no_hn'}_{exam_date}.txt", mime="text/plain")
    st.download_button("ดาวน์โหลดข้อมูล (JSON)", data=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
                       file_name=f"vision_screening_{hn or 'no_hn'}_{exam_date}.json", mime="application/json")
    form_html = build_form_html(payload)
    st.download_button("ดาวน์โหลดฟอร์ม (HTML สำหรับพิมพ์)", data=form_html.encode("utf-8"),
                       file_name=f"vision_form_{hn or 'no_hn'}_{exam_date}.html", mime="text/html")

st.caption("หมายเหตุ: ระบบนี้เป็นแบบคัดกรอง + แนะนำเฉย ๆ เพื่อให้แพทย์ตรวจทานก่อนคืนข้อมูล (ไม่ตัดสินความเหมาะสมในการทำงาน)")
