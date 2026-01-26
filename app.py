import json
import io
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import streamlit as st

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
    GOOGLE_DRIVE_AVAILABLE = True
except Exception:
    GOOGLE_DRIVE_AVAILABLE = False

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
        r_nasal = "เห็นแสง" if vf.get("right_nasal_seen") else "ไม่เห็นแสง"
        l_nasal = "เห็นแสง" if vf.get("left_nasal_seen") else "ไม่เห็นแสง"
        vf_value = f"R Temporal:{r_temp_txt} / Nasal45:{r_nasal} | L Temporal:{l_temp_txt} / Nasal45:{l_nasal}"

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
        <div class="section-title">กลุ่มอาชีพ (Job groups)</div>
        <div class="small">{meta["job_group_label"]}</div>
        <div class="section-title">ทดสอบด้วยเครื่อง (Device)</div>
        <div class="small">{meta["device"]}</div>
      </div>
      <div class="box">
        <div class="section-title">ผลการตรวจ (ค่าที่ได้ + ค่าอ้างอิง)</div>
        <table>
          <tr>
            <th style="width:38%;">หัวข้อ</th>
            <th style="width:32%;">ค่าที่ได้</th>
            <th style="width:30%;">ค่าอ้างอิง (ตามกลุ่มอาชีพ)</th>
          </tr>
          <tr><td>Far: Binocular (3 cubes)</td><td>{"ผ่าน" if inputs["far"]["binocular_ok"] else "ไม่ผ่าน"}</td><td>ต้องผ่าน 3 cubes</td></tr>
          <tr><td>Far: VA Both eyes</td><td>{val_va(inputs["far"]["va_be"])}</td><td>{ref_min(std.far_va_be_min, fmt_va)}</td></tr>
          <tr><td>Far: VA Right</td><td>{val_va(inputs["far"]["va_re"])}</td><td>{ref_min(std.far_va_re_min, fmt_va)}</td></tr>
          <tr><td>Far: VA Left</td><td>{val_va(inputs["far"]["va_le"])}</td><td>{ref_min(std.far_va_le_min, fmt_va)}</td></tr>
          <tr><td>Far: Stereo depth</td><td>{fmt_stereo(inputs["far"]["stereo"]) if inputs["far"]["stereo"] is not None else "—"}</td><td>{ref_min(std.far_stereo_min, fmt_stereo)}</td></tr>
          <tr><td>Far: Color discrimination</td><td>{inputs["far"]["color_correct"]}/8</td><td>{ref_min(std.far_color_min_correct, lambda v: f"{v}/8")}</td></tr>
          <tr><td>Far: Vertical phoria</td><td>{val_num(inputs["far"]["vphoria"])}</td><td>{ref_range(std.far_vphoria_range)}</td></tr>
          <tr><td>Far: Lateral phoria</td><td>{val_num(inputs["far"]["lphoria"])}</td><td>{ref_range(std.far_lphoria_range)}</td></tr>
          <tr><td>Near: Binocular (3 cubes)</td><td>{"ผ่าน" if inputs["near"]["binocular_ok"] else "ไม่ผ่าน"}</td><td>ต้องผ่าน 3 cubes</td></tr>
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
          <tr><td>Visual field</td><td>{vf_value}</td><td>คัดกรอง/ตามดุลยพินิจแพทย์</td></tr>
        </table>
        <div class="row" style="margin-top:6px;">
          หมายเหตุแพทย์ <span class="line" style="min-width: 180px;">{review.get("physician_note","")}</span>
        </div>
      </div>
    </div>

    <div class="box">
      <div class="section-title">คำแนะนำ (Recommendation)</div>
      <div class="small">
        {"<br>".join(auto["recommendations"]) if auto["recommendations"] else "-"}
      </div>
      <div class="row" style="margin-top:6px;">
        ผู้ตรวจ (Technician) <span class="line" style="min-width: 160px;">{review.get("technician","")}</span>
        แพทย์ผู้แปลผล (Physician) <span class="line" style="min-width: 160px;">{review.get("physician","")}</span>
      </div>
    </div>
  </div>
</body>
</html>"""
    return html


# ----------------------------
# State helpers + Cloud (Google Drive)
# ----------------------------

def _set_default_state() -> None:
    defaults = {
        "job_key": list(JOB_GROUPS.keys())[0],
        "test_device": "Titmus V2a / Optec 5000",
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
        "far_color_correct": 8,
        "far_va_be": 8,
        "far_va_re": None,
        "far_va_le": None,
        "far_vphoria": None,
        "far_lphoria": None,
        "near_binocular_ok": True,
        "near_va_be": 9,
        "near_va_re": None,
        "near_va_le": None,
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
        "gdrive_folder_id": "",
        "gdrive_refresh_sec": 10,
        "gdrive_autorefresh": True,
        "firebase_collection": "vision_records",
        "firebase_refresh_sec": 10,
        "firebase_autorefresh": True,
        "firebase_autosave": False,
        "firebase_doc_id": "",
        "firebase_last_hash": "",
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


def _drive_service_from_info(info: Dict[str, Any]):
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _drive_list_files(service, folder_id: str) -> List[Dict[str, Any]]:
    q = f"'{folder_id}' in parents and trashed=false"
    res = service.files().list(
        q=q,
        fields="files(id,name,modifiedTime,size,mimeType)",
        orderBy="modifiedTime desc",
        pageSize=50,
    ).execute()
    return res.get("files", [])


def _drive_download_json(service, file_id: str) -> Dict[str, Any]:
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return json.loads(fh.read().decode("utf-8"))


def _drive_upload_json(service, folder_id: str, name: str, payload: Dict[str, Any]) -> None:
    metadata = {"name": name, "parents": [folder_id]}
    data = io.BytesIO(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    media = MediaIoBaseUpload(data, mimetype="application/json")
    service.files().create(body=metadata, media_body=media, fields="id").execute()


def _firebase_client_from_info(info: Dict[str, Any]):
    if not firebase_admin._apps:
        cred = credentials.Certificate(info)
        firebase_admin.initialize_app(cred)
    return firestore.client()


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


def _match_keyword(doc, keyword: str) -> bool:
    if not keyword:
        return True
    data = doc.to_dict() or {}
    person = data.get("person", {})
    name = str(person.get("name", "")).lower()
    hn = str(person.get("hn", "")).lower()
    return keyword.lower() in name or keyword.lower() in hn


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

st.set_page_config(page_title="Vision Screening (Titmus V2a/Optec 5000)", layout="wide")

st.title("แบบฟอร์มบันทึกผลตรวจสมรรถภาพการมองเห็น (Electronic) — Titmus V2a / Optec 5000")
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

    st.markdown("### Far vision (20 ft.)")

    far_cols = st.columns([1, 1, 1])
    with far_cols[0]:
        far_binocular_ok = st.checkbox("1) Binocular vision (3 cubes) — ผ่าน", key="far_binocular_ok")
        far_stereo = st.selectbox(
            "5) Stereo depth (1–9)",
            options=[None] + list(range(1, 10)),
            index=_index_for(st.session_state["far_stereo"], [None] + list(range(1, 10)), 0),
            format_func=lambda x: "—" if x is None else fmt_stereo(x),
            key="far_stereo",
        )
        far_color_correct = st.number_input("6) Color correct (0–8)", min_value=0, max_value=8, value=st.session_state["far_color_correct"], key="far_color_correct")
    with far_cols[1]:
        far_va_be = st.selectbox(
            "2) Acuity Both eyes (1–14)",
            list(range(1, 15)),
            index=_index_for(st.session_state["far_va_be"], list(range(1, 15)), 7),
            format_func=lambda x: fmt_va(x),
            key="far_va_be",
        )
        far_va_re = st.selectbox(
            "3) Acuity Right eye (1–14)",
            [None] + list(range(1, 15)),
            index=_index_for(st.session_state["far_va_re"], [None] + list(range(1, 15)), 0),
            format_func=lambda x: "-" if x is None else fmt_va(x),
            key="far_va_re",
        )
        far_va_le = st.selectbox(
            "4) Acuity Left eye (1–14)",
            [None] + list(range(1, 15)),
            index=_index_for(st.session_state["far_va_le"], [None] + list(range(1, 15)), 0),
            format_func=lambda x: "-" if x is None else fmt_va(x),
            key="far_va_le",
        )
    with far_cols[2]:
        far_vphoria = st.selectbox(
            "7) Vertical phoria (1–7)",
            options=[None] + list(range(1, 8)),
            index=_index_for(st.session_state["far_vphoria"], [None] + list(range(1, 8)), 0),
            format_func=lambda x: "—" if x is None else str(x),
            key="far_vphoria",
        )
        far_lphoria = st.selectbox(
            "8) Lateral phoria (1–15)",
            options=[None] + list(range(1, 16)),
            index=_index_for(st.session_state["far_lphoria"], [None] + list(range(1, 16)), 0),
            format_func=lambda x: "—" if x is None else str(x),
            key="far_lphoria",
        )
        st.caption("หมายเหตุ: ถ้ากลุ่มอาชีพนั้น ๆ เป็น N/A ระบบจะไม่ตัดตก แต่ยังให้บันทึกได้")

    st.markdown("### Near vision (14 in.)")

    near_cols = st.columns([1, 1, 1])
    with near_cols[0]:
        near_binocular_ok = st.checkbox("1) Binocular vision (3 cubes) — ผ่าน (Near)", key="near_binocular_ok")
    with near_cols[1]:
        near_va_be = st.selectbox(
            "2) Near Acuity Both eyes (1–14)",
            list(range(1, 15)),
            index=_index_for(st.session_state["near_va_be"], list(range(1, 15)), 8),
            format_func=lambda x: fmt_va(x),
            key="near_va_be",
        )
        near_va_re = st.selectbox(
            "3) Near Acuity Right eye (1–14)",
            [None] + list(range(1, 15)),
            index=_index_for(st.session_state["near_va_re"], [None] + list(range(1, 15)), 0),
            format_func=lambda x: "-" if x is None else fmt_va(x),
            key="near_va_re",
        )
        near_va_le = st.selectbox(
            "4) Near Acuity Left eye (1–14)",
            [None] + list(range(1, 15)),
            index=_index_for(st.session_state["near_va_le"], [None] + list(range(1, 15)), 0),
            format_func=lambda x: "-" if x is None else fmt_va(x),
            key="near_va_le",
        )
    with near_cols[2]:
        near_vphoria = st.selectbox(
            "7) Near Vertical phoria (1–7)",
            options=[None] + list(range(1, 8)),
            index=_index_for(st.session_state["near_vphoria"], [None] + list(range(1, 8)), 0),
            format_func=lambda x: "—" if x is None else str(x),
            key="near_vphoria",
        )
        near_lphoria = st.selectbox(
            "8) Near Lateral phoria (1–15)",
            options=[None] + list(range(1, 16)),
            index=_index_for(st.session_state["near_lphoria"], [None] + list(range(1, 16)), 0),
            format_func=lambda x: "—" if x is None else str(x),
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
        vf_cols = st.columns([1, 1, 1])
        with vf_cols[0]:
            vf_status = st.radio("สรุป Visual field", ["ปกติ", "สงสัยผิดปกติ/ต้องประเมินเพิ่ม"], horizontal=False, key="vf_status")
        with vf_cols[1]:
            st.markdown("**Right Eye**")
            vf_right_temp = st.selectbox("Right Temporal (°)", options=[85, 70, 55, "ไม่เห็นแสง"], index=0, key="vf_right_temp")
            vf_right_nasal_seen = st.checkbox("Right Nasal 45° เห็นแสง", key="vf_right_nasal_seen")
        with vf_cols[2]:
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

    # Visual field (optional, not part of job standard comparison here)
    if include_visual_field and vf_status != "ปกติ":
        fails.append("Visual field")

    # Show results
    all_ok = (len(fails) == 0)

    st.markdown("### สรุป")
    st.write(f"**กลุ่มอาชีพ:** {JOB_GROUPS[job_key]['label_th']}")
    st.write(f"**การแก้ไขสายตาขณะตรวจ:** Far = {far_correction} | Near = {near_correction}")
    st.write(f"**ผลรวม:** {pass_fail_icon(all_ok)} (อิงเกณฑ์ V2a/Optec 5000 ของกลุ่มอาชีพนี้)")

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
    physician_name = st.text_input("ชื่อแพทย์ผู้แปลผล", value=st.session_state["physician_name"], key="physician_name")
    tech_name = st.text_input("ชื่อผู้ตรวจ (Technician)", value=st.session_state["tech_name"], key="tech_name")

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

            fb_file = st.file_uploader("Service account JSON (Firebase)", type=["json"])
            fb_text = st.text_area("หรือวาง JSON ของ Service account ที่นี่ (Firebase)", value="", height=120)
            fb_collection = st.text_input("Firestore collection", key="firebase_collection")
            fb_refresh = st.number_input("รีเฟรชรายการทุก (วินาที)", min_value=5, max_value=60, value=st.session_state["firebase_refresh_sec"], key="firebase_refresh_sec")
            fb_auto = st.checkbox("เปิด Auto refresh รายการเคส", value=st.session_state["firebase_autorefresh"], key="firebase_autorefresh")
            fb_autosave = st.checkbox("Auto update เมื่อแก้ฟอร์ม (ต้องโหลดเคสก่อน)", value=st.session_state["firebase_autosave"], key="firebase_autosave")
            fb_search = st.text_input("ค้นหา (HN/ชื่อ)", value="")

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
                    # Auto-update current case when form changes
                    if fb_autosave and st.session_state.get("firebase_doc_id"):
                        current_hash = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                        if current_hash != st.session_state.get("firebase_last_hash"):
                            _firebase_update_record(db, fb_collection, st.session_state["firebase_doc_id"], payload)
                            st.session_state["firebase_last_hash"] = current_hash
                    records = _firebase_list_records(db, fb_collection, limit=50)
                    records = [doc for doc in records if _match_keyword(doc, fb_search)]
                    if records:
                        labels = [_firebase_label(doc) for doc in records]
                        sel = st.selectbox("เลือกเคสเพื่อโหลดเข้าแอป", options=list(range(len(records))), format_func=lambda i: labels[i])
                    else:
                        sel = None
                        st.info("ยังไม่มีข้อมูลใน collection นี้")

                    col_a, col_b = st.columns(2)
                    with col_a:
                        if records and st.button("โหลดเคสที่เลือก"):
                            st.session_state["pending_payload"] = records[sel].to_dict() or {}
                            st.session_state["firebase_doc_id"] = records[sel].id
                            st.session_state["firebase_last_hash"] = ""
                            st.rerun()
                    with col_b:
                        if st.button("บันทึกเคสนี้ขึ้น Firebase"):
                            _firebase_save_record(db, fb_collection, payload)
                            st.success("บันทึกสำเร็จ")
                except Exception as e:
                    st.error(f"เชื่อมต่อ Firebase ไม่สำเร็จ: {e}")
            else:
                st.info("กรอก Service account และชื่อ collection เพื่อเริ่มใช้งาน")

    with st.expander("Cloud Sync (Google Drive)", expanded=False):
        st.caption("อัปโหลด/ดึงไฟล์จากโฟลเดอร์กลางเพื่อทำงานร่วมกันแบบใกล้เรียลไทม์")
        if not GOOGLE_DRIVE_AVAILABLE:
            st.warning("ยังไม่มีไลบรารี Google Drive API ในเครื่องนี้ (google-api-python-client).")
        else:
            secrets_gd = None
            if st.secrets and "gdrive" in st.secrets:
                try:
                    secrets_gd = json.loads(st.secrets["gdrive"]["service_account_json"])
                    if not st.session_state.get("gdrive_folder_id"):
                        st.session_state["gdrive_folder_id"] = st.secrets["gdrive"].get("folder_id", "")
                except Exception:
                    secrets_gd = None
            sa_file = st.file_uploader("Service account JSON", type=["json"])
            sa_text = st.text_area("หรือวาง JSON ของ Service account ที่นี่", value="", height=120)
            folder_id = st.text_input("Google Drive Folder ID", key="gdrive_folder_id")
            refresh_sec = st.number_input("รีเฟรชรายการทุก (วินาที)", min_value=5, max_value=60, value=st.session_state["gdrive_refresh_sec"], key="gdrive_refresh_sec")
            auto_refresh = st.checkbox("เปิด Auto refresh รายการไฟล์", value=st.session_state["gdrive_autorefresh"], key="gdrive_autorefresh")

            info = None
            if secrets_gd is not None:
                info = secrets_gd
            elif sa_file is not None:
                try:
                    info = json.load(sa_file)
                except Exception:
                    st.error("อ่านไฟล์ Service account ไม่ได้")
            elif sa_text.strip():
                try:
                    info = json.loads(sa_text)
                except Exception:
                    st.error("JSON ไม่ถูกต้อง")

            if info and folder_id:
                try:
                    service = _drive_service_from_info(info)
                    if auto_refresh and hasattr(st, "autorefresh"):
                        st.autorefresh(interval=int(refresh_sec * 1000), key="gdrive_autorefresh_tick")
                    files = _drive_list_files(service, folder_id)
                    if files:
                        file_labels = [f"{f['name']} | {f.get('modifiedTime','')}" for f in files]
                        sel = st.selectbox("เลือกไฟล์เพื่อโหลดเข้าแอป", options=list(range(len(files))), format_func=lambda i: file_labels[i])
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button("โหลดไฟล์ที่เลือก"):
                                payload_in = _drive_download_json(service, files[sel]["id"])
                                st.session_state["pending_payload"] = payload_in
                                st.rerun()
                        with col_b:
                            if st.button("อัปโหลดบันทึกนี้ขึ้นโฟลเดอร์"):
                                filename = f"vision_{hn or 'no_hn'}_{exam_date}.json"
                                _drive_upload_json(service, folder_id, filename, payload)
                                st.success("อัปโหลดสำเร็จ")
                    else:
                        st.info("ยังไม่มีไฟล์ในโฟลเดอร์นี้")
                except Exception as e:
                    st.error(f"เชื่อมต่อ Google Drive ไม่สำเร็จ: {e}")
            else:
                st.info("กรอก Service account และ Folder ID เพื่อเริ่มใช้งาน")

    txt_lines = []
    txt_lines.append("VISION SCREENING SUMMARY (Titmus V2a / Optec 5000)")
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
    txt_lines.append("")
    txt_lines.append(f"Technician: {tech_name}")
    txt_lines.append(f"Physician: {physician_name}")

    summary_txt = "\n".join(txt_lines)
    st.download_button("ดาวน์โหลดสรุป (TXT)", data=summary_txt.encode("utf-8"),
                       file_name=f"vision_screening_{hn or 'no_hn'}_{exam_date}.txt", mime="text/plain")
    st.download_button("ดาวน์โหลดข้อมูล (JSON)", data=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
                       file_name=f"vision_screening_{hn or 'no_hn'}_{exam_date}.json", mime="application/json")
    form_html = build_form_html(payload)
    st.download_button("ดาวน์โหลดฟอร์ม (HTML สำหรับพิมพ์)", data=form_html.encode("utf-8"),
                       file_name=f"vision_form_{hn or 'no_hn'}_{exam_date}.html", mime="text/html")

st.caption("หมายเหตุ: ระบบนี้เป็นแบบคัดกรอง + แนะนำเฉย ๆ เพื่อให้แพทย์ตรวจทานก่อนคืนข้อมูล (ไม่ตัดสินความเหมาะสมในการทำงาน)")
