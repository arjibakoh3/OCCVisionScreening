from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from vision_logic import (
    FAR_COLOR_TOTAL,
    FAR_STEREO_KEY,
    FAR_VA_BE_KEY,
    FAR_VA_LE_KEY,
    FAR_VA_RE_KEY,
    JOB_GROUPS,
    NEAR_VA_BE_KEY,
    NEAR_VA_LE_KEY,
    NEAR_VA_RE_KEY,
    STEREO_MAP,
    VA_MAP,
    assess_screening,
    fmt_range,
    fmt_stereo,
    fmt_va,
    score_exam_step,
)


ANSWER_LABELS = {
    "T": "บน (Top)",
    "R": "ขวา (Right)",
    "L": "ซ้าย (Left)",
    "B": "ล่าง (Bottom)",
}

EXAM_MODES = {
    "far_va_be": ("Far VA - Both eyes", FAR_VA_BE_KEY, "va"),
    "far_va_re": ("Far VA - Right eye", FAR_VA_RE_KEY, "va"),
    "far_va_le": ("Far VA - Left eye", FAR_VA_LE_KEY, "va"),
    "near_va_be": ("Near VA - Both eyes", NEAR_VA_BE_KEY, "va"),
    "near_va_re": ("Near VA - Right eye", NEAR_VA_RE_KEY, "va"),
    "near_va_le": ("Near VA - Left eye", NEAR_VA_LE_KEY, "va"),
    "far_stereo": ("Far Stereo depth", FAR_STEREO_KEY, "stereo"),
}

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "office_clear": {
        "title": "สำนักงาน: ผ่านเกณฑ์แต่มี phoria ใกล้ขอบ",
        "job_key": "office",
        "include_intermediate": True,
        "inputs": {
            "far": {
                "binocular_cubes": 3,
                "va_be": 8,
                "va_re": 7,
                "va_le": 7,
                "stereo": None,
                "color_correct": 5,
                "vphoria": 5,
                "lphoria": 13,
            },
            "near": {
                "binocular_cubes": 3,
                "va_be": 9,
                "va_re": 8,
                "va_le": 8,
                "vphoria": 4,
                "lphoria": 10,
            },
            "intermediate": {"va_be": 9, "va_re": 8, "va_le": 8},
        },
        "teaching_point": "ค่าที่เท่ากับเกณฑ์ขั้นต่ำยังถือว่าผ่าน และ phoria ช่วงปลายขอบยังผ่านถ้าอยู่ใน range",
    },
    "driver_far_va": {
        "title": "Driver/Crane: Far VA ต่ำกว่าเกณฑ์",
        "job_key": "driver_mobile",
        "include_intermediate": True,
        "inputs": {
            "far": {
                "binocular_cubes": 3,
                "va_be": 8,
                "va_re": 7,
                "va_le": 8,
                "stereo": 6,
                "color_correct": 5,
                "vphoria": 4,
                "lphoria": 8,
            },
            "near": {
                "binocular_cubes": 3,
                "va_be": 8,
                "va_re": 7,
                "va_le": 7,
                "vphoria": 4,
                "lphoria": 8,
            },
            "intermediate": {"va_be": 7, "va_re": 6, "va_le": 6},
        },
        "teaching_point": "กลุ่มขับหรือควบคุมอุปกรณ์เคลื่อนที่ต้องการ Far VA สูงกว่า office และ operator",
    },
    "inspector_stereo": {
        "title": "Inspector: Stereo depth ไม่ถึงเกณฑ์",
        "job_key": "inspector",
        "include_intermediate": True,
        "inputs": {
            "far": {
                "binocular_cubes": 3,
                "va_be": 8,
                "va_re": 7,
                "va_le": 7,
                "stereo": 4,
                "color_correct": 6,
                "vphoria": 4,
                "lphoria": 9,
            },
            "near": {
                "binocular_cubes": 3,
                "va_be": 9,
                "va_re": 8,
                "va_le": 8,
                "vphoria": 4,
                "lphoria": 9,
            },
            "intermediate": {"va_be": 9, "va_re": 8, "va_le": 8},
        },
        "teaching_point": "งาน inspection ต้องดู stereo depth เพราะเกี่ยวกับการประเมินความลึกและงานละเอียด",
    },
    "labor_phoria": {
        "title": "Labor: เกณฑ์ phoria กว้างกว่า แต่ Near phoria เป็น N/A",
        "job_key": "labor",
        "include_intermediate": False,
        "inputs": {
            "far": {
                "binocular_cubes": 3,
                "va_be": 8,
                "va_re": 7,
                "va_le": 7,
                "stereo": None,
                "color_correct": 5,
                "vphoria": 6,
                "lphoria": 15,
            },
            "near": {
                "binocular_cubes": 3,
                "va_be": 7,
                "va_re": 6,
                "va_le": 6,
                "vphoria": None,
                "lphoria": None,
            },
        },
        "teaching_point": "บางหัวข้อเป็น N/A ตามกลุ่มงาน จึงบันทึกไว้ได้แต่ไม่ใช้ตัดเกณฑ์อัตโนมัติ",
    },
}


def _init_state() -> None:
    defaults = {
        "exam_mode": "far_va_be",
        "exam_slide": 1,
        "exam_wrong_streak": 0,
        "exam_last_passed": 0,
        "exam_stopped": False,
        "quiz_checked": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _reset_exam(mode: Optional[str] = None) -> None:
    if mode is not None:
        st.session_state["exam_mode"] = mode
    st.session_state["exam_slide"] = 1
    st.session_state["exam_wrong_streak"] = 0
    st.session_state["exam_last_passed"] = 0
    st.session_state["exam_stopped"] = False


def _score_text(score: int, score_type: str) -> str:
    if score <= 0:
        return "ยังไม่มี slide ที่ผ่าน"
    if score_type == "stereo":
        return fmt_stereo(score)
    return fmt_va(score)


def _status_badge(ok: bool) -> str:
    return "ผ่าน" if ok else "ไม่ผ่าน"


def _standard_rows(job_key: str) -> List[Dict[str, str]]:
    std = JOB_GROUPS[job_key]["std"]
    return [
        {"หัวข้อ": "Far binocular", "เกณฑ์": "3 cubes" if std.far_binocular_required else "N/A"},
        {"หัวข้อ": "Far VA Both eyes", "เกณฑ์": fmt_va(std.far_va_be_min)},
        {"หัวข้อ": "Far VA Right eye", "เกณฑ์": fmt_va(std.far_va_re_min)},
        {"หัวข้อ": "Far VA Left eye", "เกณฑ์": fmt_va(std.far_va_le_min)},
        {"หัวข้อ": "Far stereo", "เกณฑ์": fmt_stereo(std.far_stereo_min)},
        {"หัวข้อ": "Far color", "เกณฑ์": f"{std.far_color_min_correct}/{FAR_COLOR_TOTAL}" if std.far_color_min_correct else "N/A"},
        {"หัวข้อ": "Far vertical phoria", "เกณฑ์": fmt_range(std.far_vphoria_range)},
        {"หัวข้อ": "Far lateral phoria", "เกณฑ์": fmt_range(std.far_lphoria_range)},
        {"หัวข้อ": "Near binocular", "เกณฑ์": "3 cubes" if std.near_binocular_required else "N/A"},
        {"หัวข้อ": "Near VA Both eyes", "เกณฑ์": fmt_va(std.near_va_be_min)},
        {"หัวข้อ": "Near VA Right eye", "เกณฑ์": fmt_va(std.near_va_re_min)},
        {"หัวข้อ": "Near VA Left eye", "เกณฑ์": fmt_va(std.near_va_le_min)},
        {"หัวข้อ": "Near vertical phoria", "เกณฑ์": fmt_range(std.near_vphoria_range)},
        {"หัวข้อ": "Near lateral phoria", "เกณฑ์": fmt_range(std.near_lphoria_range)},
        {"หัวข้อ": "Intermediate VA BE/RE/LE", "เกณฑ์": f"{fmt_va(std.inter_va_be_min)} / {fmt_va(std.inter_va_re_min)} / {fmt_va(std.inter_va_le_min)}"},
    ]


def _render_assessment(result: Dict[str, Any]) -> None:
    st.metric("ผลรวม", _status_badge(result["all_ok"]), "อิงเกณฑ์กลุ่มงานที่เลือก")
    if result["fails"]:
        st.error("หัวข้อที่ต้องทบทวน: " + ", ".join(result["fails"]))
    else:
        st.success("ไม่พบหัวข้อที่ต่ำกว่าเกณฑ์")

    with st.expander("ดูรายละเอียดทีละหัวข้อ", expanded=True):
        for ok, message in result["details"]:
            st.write(f"{_status_badge(ok)} - {message}")

    with st.expander("แนวทางแนะนำ", expanded=False):
        for rec in result["recommendations"]:
            st.write(f"- {rec}")


def _render_standards_tab() -> None:
    left, right = st.columns([0.9, 1.1])
    with left:
        job_key = st.selectbox(
            "เลือกกลุ่มงาน",
            list(JOB_GROUPS.keys()),
            format_func=lambda key: JOB_GROUPS[key]["label_th"],
            key="standard_job",
        )
        st.caption("ตารางนี้ใช้ logic เดียวกับระบบแปลผลหลัก")
    with right:
        st.dataframe(_standard_rows(job_key), use_container_width=True, hide_index=True)


def _render_exam_tab() -> None:
    mode = st.selectbox(
        "ชุดฝึกอ่าน",
        list(EXAM_MODES.keys()),
        format_func=lambda key: EXAM_MODES[key][0],
        key="exam_mode_select",
    )
    if mode != st.session_state["exam_mode"]:
        _reset_exam(mode)
        st.rerun()

    title, answer_key, score_type = EXAM_MODES[st.session_state["exam_mode"]]
    slide = st.session_state["exam_slide"]
    expected = answer_key[slide - 1]
    progress = slide / len(answer_key)

    top_cols = st.columns([1, 1, 1])
    top_cols[0].metric("Slide", f"{slide}/{len(answer_key)}")
    top_cols[1].metric("ผิดติดกัน", f"{st.session_state['exam_wrong_streak']}/2")
    top_cols[2].metric("ผ่านล่าสุด", _score_text(st.session_state["exam_last_passed"], score_type))
    st.progress(progress)

    st.subheader(title)
    st.write("ให้นักศึกษากดตำแหน่งที่ผู้รับการตรวจตอบ แล้วดูว่า score จะหยุดเมื่อผิดติดกัน 2 ครั้งอย่างไร")

    answer_cols = st.columns(4)
    for answer_col, answer in zip(answer_cols, ["T", "R", "L", "B"]):
        if answer_col.button(ANSWER_LABELS[answer], disabled=st.session_state["exam_stopped"], use_container_width=True):
            result = score_exam_step(
                answer_key,
                slide,
                answer,
                st.session_state["exam_wrong_streak"],
                st.session_state["exam_last_passed"],
            )
            st.session_state["exam_wrong_streak"] = result["wrong_streak"]
            st.session_state["exam_last_passed"] = result["last_passed"]
            st.session_state["exam_slide"] = result["next_slide"]
            st.session_state["exam_stopped"] = result["stopped"]
            st.session_state["last_exam_feedback"] = result
            st.rerun()

    feedback = st.session_state.get("last_exam_feedback")
    if feedback:
        if feedback["correct"]:
            st.success(f"ตอบถูก เฉลย slide {feedback['slide']} คือ {ANSWER_LABELS[feedback['expected']]}")
        else:
            st.warning(f"ตอบผิด เฉลย slide {feedback['slide']} คือ {ANSWER_LABELS[feedback['expected']]}")

    if st.session_state["exam_stopped"]:
        st.info(f"สรุปผลที่อ่านได้: {_score_text(st.session_state['exam_last_passed'], score_type)}")

    with st.expander("เปิดเฉลยสำหรับผู้สอน", expanded=False):
        rows = []
        for index, answer in enumerate(answer_key, start=1):
            value = VA_MAP.get(index, STEREO_MAP.get(index, ""))
            rows.append({"slide": index, "answer": ANSWER_LABELS[answer], "value": value})
        st.dataframe(rows, use_container_width=True, hide_index=True)

    if st.button("เริ่มใหม่", use_container_width=True):
        _reset_exam(st.session_state["exam_mode"])
        st.session_state.pop("last_exam_feedback", None)
        st.rerun()


def _number_or_none(label: str, minimum: int, maximum: int, value: Optional[int], key: str) -> Optional[int]:
    enabled = st.checkbox(f"บันทึก {label}", value=value is not None, key=f"{key}_enabled")
    if not enabled:
        return None
    return int(st.slider(label, minimum, maximum, int(value or minimum), key=key))


def _render_case_lab_tab() -> None:
    job_key = st.selectbox(
        "กลุ่มงานสำหรับทดลอง",
        list(JOB_GROUPS.keys()),
        index=list(JOB_GROUPS.keys()).index("operator"),
        format_func=lambda key: JOB_GROUPS[key]["label_th"],
        key="lab_job",
    )
    include_intermediate = st.toggle("รวม Intermediate", value=True, key="lab_inter")

    far_col, near_col, inter_col = st.columns(3)
    with far_col:
        st.markdown("#### Far")
        far = {
            "binocular_cubes": st.radio("Binocular cubes", [2, 3, 4], index=1, horizontal=True, key="lab_far_bino"),
            "va_be": st.slider("VA BE", 1, 14, 8, key="lab_far_va_be"),
            "va_re": st.slider("VA RE", 1, 14, 7, key="lab_far_va_re"),
            "va_le": st.slider("VA LE", 1, 14, 7, key="lab_far_va_le"),
            "stereo": _number_or_none("Stereo", 1, 9, 5, "lab_far_stereo"),
            "color_correct": st.slider("Color correct", 0, FAR_COLOR_TOTAL, 5, key="lab_far_color"),
            "vphoria": _number_or_none("V Phoria Far", 1, 7, 4, "lab_far_vp"),
            "lphoria": _number_or_none("L Phoria Far", 1, 15, 8, "lab_far_lp"),
        }
    with near_col:
        st.markdown("#### Near")
        near = {
            "binocular_cubes": st.radio("Near binocular cubes", [2, 3, 4], index=1, horizontal=True, key="lab_near_bino"),
            "va_be": st.slider("Near VA BE", 1, 14, 8, key="lab_near_va_be"),
            "va_re": st.slider("Near VA RE", 1, 14, 7, key="lab_near_va_re"),
            "va_le": st.slider("Near VA LE", 1, 14, 7, key="lab_near_va_le"),
            "vphoria": _number_or_none("V Phoria Near", 1, 7, 4, "lab_near_vp"),
            "lphoria": _number_or_none("L Phoria Near", 1, 15, 8, "lab_near_lp"),
        }
    with inter_col:
        st.markdown("#### Intermediate")
        intermediate = {
            "va_be": st.slider("Inter VA BE", 1, 14, 8, key="lab_inter_va_be"),
            "va_re": st.slider("Inter VA RE", 1, 14, 7, key="lab_inter_va_re"),
            "va_le": st.slider("Inter VA LE", 1, 14, 7, key="lab_inter_va_le"),
        }

    result = assess_screening(
        job_key,
        {"far": far, "near": near, "intermediate": intermediate},
        include_intermediate=include_intermediate,
    )
    _render_assessment(result)


def _render_scenarios_tab() -> None:
    scenario_key = st.selectbox(
        "เลือกเคสสอน",
        list(SCENARIOS.keys()),
        format_func=lambda key: SCENARIOS[key]["title"],
        key="scenario_key",
    )
    scenario = SCENARIOS[scenario_key]
    result = assess_screening(
        scenario["job_key"],
        scenario["inputs"],
        include_intermediate=scenario["include_intermediate"],
    )

    st.subheader(scenario["title"])
    st.write(f"กลุ่มงาน: {JOB_GROUPS[scenario['job_key']]['label_th']}")
    st.info("Teaching point: " + scenario["teaching_point"])
    _render_assessment(result)


def _render_quiz_tab() -> None:
    quiz = [
        {
            "question": "ถ้าค่า VA เท่ากับเกณฑ์ขั้นต่ำพอดี ต้องประเมินอย่างไร",
            "options": ["ผ่าน", "ไม่ผ่าน", "ไม่นำมาตัดเกณฑ์"],
            "answer": "ผ่าน",
            "reason": "logic ใช้การเปรียบเทียบแบบมากกว่าหรือเท่ากับเกณฑ์ขั้นต่ำ",
        },
        {
            "question": "Labor มี near vertical/lateral phoria เป็น N/A ควรตัดตกอัตโนมัติหรือไม่",
            "options": ["ไม่ตัดตก", "ตัดตก", "ตัดตกเฉพาะ lateral"],
            "answer": "ไม่ตัดตก",
            "reason": "หัวข้อ N/A จะไม่ถูกนำมาตัดเกณฑ์ในระบบแปลผล",
        },
        {
            "question": "Exam mode จะหยุดอัตโนมัติเมื่อเกิดเงื่อนไขใด",
            "options": ["ผิดติดกัน 2 ครั้ง", "ผิดรวม 2 ครั้ง", "ถูกครบ 2 ครั้ง"],
            "answer": "ผิดติดกัน 2 ครั้ง",
            "reason": "logic เก็บ wrong streak และหยุดเมื่อ streak ถึง 2",
        },
        {
            "question": "Driver/Crane ต้องการ Far VA Both eyes อย่างน้อยเท่าไร",
            "options": ["9 (20/22)", "8 (20/25)", "7 (20/30)"],
            "answer": "9 (20/22)",
            "reason": "กลุ่ม driver_mobile ตั้งค่า far_va_be_min = 9",
        },
    ]

    answers: Dict[int, str] = {}
    for index, item in enumerate(quiz):
        answers[index] = st.radio(
            f"{index + 1}. {item['question']}",
            item["options"],
            index=None,
            key=f"quiz_{index}",
        )

    if st.button("ตรวจคำตอบ", use_container_width=True):
        st.session_state["quiz_checked"] = True

    if st.session_state["quiz_checked"]:
        correct_count = 0
        for index, item in enumerate(quiz):
            selected = answers[index]
            correct = selected == item["answer"]
            correct_count += int(correct)
            if correct:
                st.success(f"ข้อ {index + 1}: ถูก - {item['reason']}")
            else:
                st.warning(f"ข้อ {index + 1}: ยังไม่ถูก คำตอบคือ {item['answer']} - {item['reason']}")
        st.metric("คะแนน", f"{correct_count}/{len(quiz)}")


def render_teaching_media(show_home_link: bool = False) -> None:
    _init_state()

    if show_home_link:
        st.markdown("[กลับหน้าบันทึกผลตรวจ](./)")
    st.title("Interactive Teaching Media: Vision Screening")
    st.caption("โมดูล standalone สำหรับสอนนักศึกษาฝึกงาน โดยใช้ logic การแปลผลเดียวกับระบบตรวจสมรรถภาพการมองเห็น")

    tabs = st.tabs(["เกณฑ์กลุ่มงาน", "ฝึกอ่านสไลด์", "ทดลองเคสเอง", "เคสสอน", "Quiz"])
    with tabs[0]:
        _render_standards_tab()
    with tabs[1]:
        _render_exam_tab()
    with tabs[2]:
        _render_case_lab_tab()
    with tabs[3]:
        _render_scenarios_tab()
    with tabs[4]:
        _render_quiz_tab()


def main() -> None:
    st.set_page_config(page_title="Teaching Media - Vision Screening", layout="wide")
    render_teaching_media()


if __name__ == "__main__":
    main()
