import json
import logging
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import cv2

from backend.app.config import (
    ALLOWED_VIDEO_EXTENSIONS,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    SNAPSHOTS_DIR,
    TEMP_UPLOADS_DIR,
    VIDEO_UPLOAD_MAX_BYTES,
)
from backend.app.database import get_connection
from backend.app.models import QAQuestionType, QAUploadedVideoStatus
from backend.app.schemas import (
    QAAskRequest,
    QAConversation,
    QAConversationDetail,
    QAEvidence,
    QAMessage,
    QAUploadedVideo,
)

logger = logging.getLogger(__name__)


class QAService:
    """Service handling multi-lingual Video Surveillance Question Answering with Gemini reasoning."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        api_key: str = GEMINI_API_KEY,
        model_name: str = GEMINI_MODEL,
    ) -> None:
        self.connection = connection
        self.api_key = api_key
        self.model_name = model_name

    def create_conversation(self, title: str = "Phiên hỏi đáp an ninh") -> QAConversation:
        cursor = self.connection.execute(
            """
            INSERT INTO qa_conversations (title)
            VALUES (?)
            """,
            (title.strip() or "Phiên hỏi đáp an ninh",),
        )
        self.connection.commit()
        conv_id = int(cursor.lastrowid)
        return self.get_conversation(conv_id)

    def list_conversations(self) -> list[QAConversation]:
        rows = self.connection.execute(
            """
            SELECT 
                c.id, 
                c.title, 
                c.created_at, 
                COUNT(m.id) as message_count
            FROM qa_conversations c
            LEFT JOIN qa_messages m ON c.id = m.conversation_id
            GROUP BY c.id
            ORDER BY c.created_at DESC
            """
        ).fetchall()
        return [
            QAConversation(
                id=row["id"],
                title=row["title"],
                created_at=str(row["created_at"]),
                message_count=row["message_count"],
            )
            for row in rows
        ]

    def get_conversation(self, conversation_id: int) -> QAConversation:
        row = self.connection.execute(
            """
            SELECT 
                c.id, 
                c.title, 
                c.created_at, 
                COUNT(m.id) as message_count
            FROM qa_conversations c
            LEFT JOIN qa_messages m ON c.id = m.conversation_id
            WHERE c.id = ?
            GROUP BY c.id
            """,
            (conversation_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Conversation {conversation_id} not found")
        return QAConversation(
            id=row["id"],
            title=row["title"],
            created_at=str(row["created_at"]),
            message_count=row["message_count"],
        )

    def get_conversation_detail(self, conversation_id: int) -> QAConversationDetail:
        conversation = self.get_conversation(conversation_id)
        message_rows = self.connection.execute(
            """
            SELECT id, conversation_id, user_query_vi, translated_query_en,
                   reasoning_en, response_vi, question_type, created_at
            FROM qa_messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        ).fetchall()

        messages: list[QAMessage] = []
        for msg in message_rows:
            evidence_rows = self.connection.execute(
                """
                SELECT id, message_id, frame_id, start_timestamp, end_timestamp,
                       snapshot_path, highlight_bbox_json, explanation_vi
                FROM qa_evidences
                WHERE message_id = ?
                ORDER BY start_timestamp ASC
                """,
                (msg["id"],),
            ).fetchall()

            evidences = [
                QAEvidence(
                    id=e["id"],
                    message_id=e["message_id"],
                    frame_id=e["frame_id"],
                    start_timestamp=float(e["start_timestamp"]),
                    end_timestamp=float(e["end_timestamp"]),
                    snapshot_path=e["snapshot_path"],
                    highlight_bbox=json.loads(e["highlight_bbox_json"]) if e["highlight_bbox_json"] else None,
                    explanation=e["explanation_vi"],
                )
                for e in evidence_rows
            ]

            messages.append(
                QAMessage(
                    id=msg["id"],
                    conversation_id=msg["conversation_id"],
                    user_query_vi=msg["user_query_vi"],
                    translated_query_en=msg["translated_query_en"],
                    reasoning_en=msg["reasoning_en"],
                    response_vi=msg["response_vi"],
                    question_type=msg["question_type"],
                    created_at=str(msg["created_at"]),
                    evidences=evidences,
                )
            )

        uploaded_videos = self._list_uploaded_videos(conversation_id)

        return QAConversationDetail(
            conversation=conversation,
            messages=messages,
            uploaded_videos=uploaded_videos,
        )

    def delete_conversation(self, conversation_id: int) -> None:
        # First clean up uploaded video data (video_frames, snapshots, files)
        video_rows = self.connection.execute(
            "SELECT video_id, file_path FROM qa_uploaded_videos WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchall()
        for vrow in video_rows:
            self._cleanup_uploaded_video_data(vrow["video_id"], vrow["file_path"])

        # CASCADE will delete qa_messages, qa_evidences, qa_uploaded_videos
        self.connection.execute(
            "DELETE FROM qa_conversations WHERE id = ?",
            (conversation_id,),
        )
        self.connection.commit()

    def ask(self, request: QAAskRequest) -> QAMessage:
        """Process a Vietnamese query: translate to English, retrieve DB context, reason with Gemini, respond in Vietnamese."""
        conv_id = request.conversation_id
        if not conv_id:
            conv = self.create_conversation(title=request.question[:40] + ("..." if len(request.question) > 40 else ""))
            conv_id = conv.id

        # 1. Trích xuất ngữ cảnh video/camera từ Database
        context_data = self._gather_surveillance_context(
            camera_id=request.camera_id,
            session_or_video_id=request.session_or_video_id,
        )

        # 2. Suy luận bằng Gemini API (hoặc fallback nếu chưa cấu hình key)
        qa_result = self._reason_with_gemini(
            user_question=request.question,
            context_data=context_data,
        )

        # 3. Lưu vào Database
        cursor = self.connection.execute(
            """
            INSERT INTO qa_messages (
                conversation_id, user_query_vi, translated_query_en,
                reasoning_en, response_vi, question_type
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                conv_id,
                request.question,
                qa_result.get("translated_query_en", ""),
                qa_result.get("reasoning_en", ""),
                qa_result.get("response_vi", ""),
                qa_result.get("question_type", QAQuestionType.GENERAL),
            ),
        )
        message_id = int(cursor.lastrowid)

        # 4. Lưu Evidences
        saved_evidences: list[QAEvidence] = []
        for ev in qa_result.get("evidences", []):
            start_ts = float(ev.get("start_timestamp", 0.0))
            end_ts = float(ev.get("end_timestamp", start_ts))
            snapshot = ev.get("snapshot_path", "")
            bbox = ev.get("highlight_bbox")
            bbox_json = json.dumps(bbox) if bbox else None
            exp_vi = ev.get("explanation_vi") or ev.get("explanation", "")
            frame_id = ev.get("frame_id")

            ev_cur = self.connection.execute(
                """
                INSERT INTO qa_evidences (
                    message_id, frame_id, start_timestamp, end_timestamp,
                    snapshot_path, highlight_bbox_json, explanation_vi
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, frame_id, start_ts, end_ts, snapshot, bbox_json, exp_vi),
            )
            saved_evidences.append(
                QAEvidence(
                    id=int(ev_cur.lastrowid),
                    message_id=message_id,
                    frame_id=frame_id,
                    start_timestamp=start_ts,
                    end_timestamp=end_ts,
                    snapshot_path=snapshot,
                    highlight_bbox=bbox,
                    explanation=exp_vi,
                )
            )

        self.connection.commit()

        return QAMessage(
            id=message_id,
            conversation_id=conv_id,
            user_query_vi=request.question,
            translated_query_en=qa_result.get("translated_query_en", ""),
            reasoning_en=qa_result.get("reasoning_en", ""),
            response_vi=qa_result.get("response_vi", ""),
            question_type=qa_result.get("question_type", QAQuestionType.GENERAL),
            created_at="vừa xong",
            evidences=saved_evidences,
        )

    def _gather_surveillance_context(
        self,
        camera_id: int | None,
        session_or_video_id: str | None,
    ) -> dict[str, Any]:
        """Collect entities, threats, logs, and member names for the LLM prompt context."""
        query_parts = []
        params: list[Any] = []

        if camera_id is not None:
            query_parts.append("vf.camera_id = ?")
            params.append(camera_id)
        if session_or_video_id is not None:
            query_parts.append("vf.session_or_video_id = ?")
            params.append(session_or_video_id)

        where_clause = f"WHERE {' AND '.join(query_parts)}" if query_parts else ""

        # Lấy frames & entities
        entity_sql = f"""
            SELECT 
                vf.id as frame_id, vf.timestamp_seconds, vf.frame_number, vf.frame_path,
                vf.person_count, vf.scene_caption_en,
                de.label, de.entity_type, de.clothing_top_color, de.clothing_bottom_color,
                de.accessories_json, de.movement_direction, de.action_label, de.bbox_json,
                p.name as member_name
            FROM video_frames vf
            LEFT JOIN detected_entities de ON vf.id = de.frame_id
            LEFT JOIN people p ON de.member_id = p.id
            {where_clause}
            ORDER BY vf.timestamp_seconds ASC
            LIMIT 100
        """
        entities = self.connection.execute(entity_sql, params).fetchall()

        # Lấy danger threats
        threat_sql = f"""
            SELECT dt.threat_type, dt.confidence, dt.snapshot_path, dt.description_en,
                   vf.timestamp_seconds
            FROM danger_threats dt
            JOIN video_frames vf ON dt.frame_id = vf.id
            {where_clause}
            ORDER BY vf.timestamp_seconds ASC
            LIMIT 50
        """
        threats = self.connection.execute(threat_sql, params).fetchall()

        # Lấy alerts
        alerts = self.connection.execute(
            """
            SELECT a.alert_type, a.message, a.confidence, a.created_at, p.name as member_name
            FROM alerts a
            LEFT JOIN people p ON a.member_id = p.id
            ORDER BY a.created_at DESC
            LIMIT 20
            """
        ).fetchall()

        return {
            "entities": [dict(r) for r in entities],
            "threats": [dict(r) for r in threats],
            "alerts": [dict(r) for r in alerts],
        }

    def _reason_with_gemini(self, user_question: str, context_data: dict[str, Any]) -> dict[str, Any]:
        """Prompt Gemini 1.5 Flash with structured context or fallback to heuristic response."""
        if not self.api_key:
            return self._fallback_heuristic_qa(user_question, context_data)

        prompt = f"""
You are an expert AI Security & CCTV Surveillance Reasoning Assistant.
You receive a Vietnamese surveillance question and structured metadata from surveillance cameras/videos.

SURVEILLANCE DATABASE CONTEXT:
{json.dumps(context_data, ensure_ascii=False, indent=2)}

USER QUESTION (Vietnamese): "{user_question}"

TASKS:
1. Translate the user query into precise English ("translated_query_en").
2. Determine question category ("question_type"): one of ["identity", "attribute", "threat", "temporal", "count", "object_reasoning", "general"].
3. Perform step-by-step reasoning in English ("reasoning_en") based strictly on the provided CCTV evidence.
4. Synthesize the final answer in natural, polite Vietnamese ("response_vi").
5. Extract exact timestamps (in seconds), bounding boxes, snapshot paths, and explanations for evidence ("evidences").

OUTPUT FORMAT: You MUST return ONLY a valid JSON object with NO markdown ticks, following this exact schema:
{{
  "translated_query_en": "string",
  "question_type": "identity" | "attribute" | "threat" | "temporal" | "count" | "object_reasoning" | "general",
  "reasoning_en": "string",
  "response_vi": "string",
  "evidences": [
    {{
      "frame_id": integer or null,
      "start_timestamp": float,
      "end_timestamp": float,
      "snapshot_path": "string",
      "highlight_bbox": [x1, y1, x2, y2] or null,
      "explanation_vi": "string"
    }}
  ]
}}
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                text_content = res_body["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text_content)
        except Exception as exc:
            logger.warning("Gemini API call failed (%s). Falling back to heuristic reasoning.", exc)
            return self._fallback_heuristic_qa(user_question, context_data)

    def _fallback_heuristic_qa(self, user_question: str, context_data: dict[str, Any]) -> dict[str, Any]:
        """Local rule-based fallback when Gemini API is offline or not configured."""
        q_lower = user_question.lower()
        threats = context_data.get("threats", [])
        entities = context_data.get("entities", [])
        person_entities = [
            e for e in entities
            if e.get("entity_type") == "person" or e.get("label") == "person" or e.get("clothing_top_color")
        ]

        # 1. KIỂM TRA DAO / VŨ KHÍ / NGUY HIỂM (Threats)
        if any(w in q_lower for w in ["dao", "vũ khí", "súng", "cháy", "nổ", "nguy hiểm", "đe dọa", "đánh nhau", "bạo lực"]):
            matching_threat = next((t for t in threats if t["threat_type"] in ["knife_threat", "weapon_drawn", "fire_smoke", "violence"]), None)
            if matching_threat:
                ts = matching_threat.get("timestamp_seconds", 0.0)
                return {
                    "translated_query_en": f"Is there any weapon or dangerous threat in the video related to: {user_question}?",
                    "question_type": QAQuestionType.THREAT,
                    "reasoning_en": f"Found danger threat record ({matching_threat['threat_type']}) at timestamp {ts:.2f}s.",
                    "response_vi": f"Phát hiện cảnh báo nguy hiểm ({matching_threat['threat_type']}) tại mốc thời gian {ts:.2f}s.",
                    "evidences": [{
                        "frame_id": None,
                        "start_timestamp": ts,
                        "end_timestamp": ts + 3.0,
                        "snapshot_path": matching_threat.get("snapshot_path", ""),
                        "highlight_bbox": None,
                        "explanation_vi": f"Đối tượng cầm vũ khí/hành vi nguy hiểm ({matching_threat['threat_type']})",
                    }],
                }
            return {
                "translated_query_en": f"Check for weapons/threats: {user_question}",
                "question_type": QAQuestionType.THREAT,
                "reasoning_en": "No weapon or active danger threats recorded in context.",
                "response_vi": "Không phát hiện vũ khí hoặc hành vi nguy hiểm nào trong dữ liệu giám sát.",
                "evidences": [],
            }

        # 2. KIỂM TRA MÀU ÁO / TRANG PHỤC / MÀU SẮC (Clothing Color & Attributes)
        color_kw_map = {
            "xanh dương": "blue",
            "xanh lam": "blue",
            "xanh nước biển": "blue",
            "xanh da trời": "blue",
            "xanh lá": "green",
            "xanh lục": "green",
            "đỏ": "red",
            "đen": "black",
            "trắng": "white",
            "vàng": "yellow",
            "cam": "orange",
            "tím": "purple",
            "hồng": "pink",
            "nâu": "brown",
            "xám": "grey",
            "ghi": "grey",
        }
        color_vn_names = {
            "blue": "màu xanh dương",
            "green": "màu xanh lá",
            "red": "màu đỏ",
            "black": "màu đen",
            "white": "màu trắng",
            "yellow": "màu vàng",
            "orange": "màu cam",
            "purple": "màu tím",
            "pink": "màu hồng",
            "brown": "màu nâu",
            "grey": "màu xám",
        }

        is_asking_color = any(w in q_lower for w in ["áo", "màu", "quần", "mặc", "trang phục", "sắc"])
        if is_asking_color:
            target_color = None
            target_vn = None
            for kw, col in color_kw_map.items():
                if kw in q_lower:
                    target_color = col
                    target_vn = color_vn_names.get(col, kw)
                    break
            
            # Nếu người dùng chỉ nói "xanh" mà không rõ xanh lá hay xanh dương
            if not target_color and "xanh" in q_lower:
                # Kiểm tra xem trong video có màu xanh nào
                present_colors = {e.get("clothing_top_color") for e in person_entities}
                if "blue" in present_colors:
                    target_color = "blue"
                    target_vn = "màu xanh dương"
                elif "green" in present_colors:
                    target_color = "green"
                    target_vn = "màu xanh lá"
                else:
                    target_color = "blue"
                    target_vn = "màu xanh"

            if target_color:
                matching = [
                    e for e in person_entities
                    if e.get("clothing_top_color") == target_color or e.get("clothing_bottom_color") == target_color
                ]
                if matching:
                    first_match = matching[0]
                    ts_list = [e.get("timestamp_seconds", 0.0) for e in matching]
                    min_ts, max_ts = min(ts_list), max(ts_list)
                    member = first_match.get("member_name")
                    who = f"{member} " if member else ""

                    evidences = []
                    sample_step = max(1, len(matching) // 3)
                    for idx in range(0, len(matching), sample_step):
                        ent = matching[idx]
                        ts = ent.get("timestamp_seconds", 0.0)
                        bbox = None
                        if ent.get("bbox_json"):
                            try:
                                bbox = json.loads(ent["bbox_json"])
                            except Exception:
                                pass
                        evidences.append({
                            "frame_id": ent.get("frame_id"),
                            "start_timestamp": ts,
                            "end_timestamp": ts + 2.0,
                            "snapshot_path": ent.get("frame_path", ""),
                            "highlight_bbox": bbox,
                            "explanation_vi": f"Phát hiện {who}mặc áo {target_vn} tại mốc {ts:.2f}s",
                        })
                        if len(evidences) >= 3:
                            break

                    time_desc = f"tại mốc {min_ts:.2f}s" if abs(min_ts - max_ts) < 0.5 else f"từ mốc {min_ts:.2f}s đến {max_ts:.2f}s"
                    return {
                        "translated_query_en": f"Is someone wearing {target_color} clothing: {user_question}?",
                        "question_type": QAQuestionType.ATTRIBUTE,
                        "reasoning_en": f"Identified person {who}wearing {target_color} clothing across {len(matching)} frames ({time_desc}).",
                        "response_vi": f"Có. Trong video ghi nhận {who}mặc áo {target_vn} xuất hiện {time_desc}.",
                        "evidences": evidences,
                    }
                else:
                    present_colors = list(dict.fromkeys([
                        e.get("clothing_top_color") for e in person_entities
                        if e.get("clothing_top_color") and e.get("clothing_top_color") != "unknown"
                    ]))
                    present_vn = [color_vn_names.get(c, c) for c in present_colors]
                    color_summary = f"mặc áo {', '.join(present_vn)}" if present_vn else "chưa rõ màu áo"
                    return {
                        "translated_query_en": f"Check for person wearing {target_color}: {user_question}",
                        "question_type": QAQuestionType.ATTRIBUTE,
                        "reasoning_en": f"No person found wearing {target_color}. Recorded colors in context: {present_colors}.",
                        "response_vi": f"Không tìm thấy người nào mặc áo {target_vn} trong video. Dữ liệu video ghi nhận người xuất hiện {color_summary}.",
                        "evidences": [],
                    }
            else:
                # Hỏi màu áo chung
                if person_entities:
                    color_groups: dict[str, list[dict[str, Any]]] = {}
                    for e in person_entities:
                        c = e.get("clothing_top_color")
                        if c and c != "unknown":
                            color_groups.setdefault(c, []).append(e)

                    if color_groups:
                        desc_parts = []
                        evidences = []
                        for col, group in color_groups.items():
                            col_vn = color_vn_names.get(col, col)
                            min_t = min(e.get("timestamp_seconds", 0.0) for e in group)
                            max_t = max(e.get("timestamp_seconds", 0.0) for e in group)
                            member = group[0].get("member_name")
                            who = f"{member} " if member else ""
                            t_desc = f"tại {min_t:.2f}s" if abs(min_t - max_t) < 0.5 else f"từ {min_t:.2f}s đến {max_t:.2f}s"
                            desc_parts.append(f"{who}mặc áo {col_vn} ({t_desc})")

                            ent = group[0]
                            bbox = None
                            if ent.get("bbox_json"):
                                try:
                                    bbox = json.loads(ent["bbox_json"])
                                except Exception:
                                    pass
                            evidences.append({
                                "frame_id": ent.get("frame_id"),
                                "start_timestamp": min_t,
                                "end_timestamp": min_t + 2.0,
                                "snapshot_path": ent.get("frame_path", ""),
                                "highlight_bbox": bbox,
                                "explanation_vi": f"Người mặc áo {col_vn}",
                            })

                        return {
                            "translated_query_en": f"What colors are people wearing: {user_question}?",
                            "question_type": QAQuestionType.ATTRIBUTE,
                            "reasoning_en": f"Found clothing colors: {list(color_groups.keys())}.",
                            "response_vi": f"Trong video ghi nhận: {'; '.join(desc_parts)}.",
                            "evidences": evidences,
                        }

        # 3. KIỂM TRA LẤY TRỘM / BALO / ĐỒ VẬT / PHỤ KIỆN (Object & Theft Reasoning)
        if any(w in q_lower for w in ["balo", "lấy", "trộm", "điện thoại", "cầm", "túi", "nón", "mũ", "khẩu trang", "kính", "ăn", "uống", "đồ ăn", "chai", "ly"]):
            obj_entity = next((e for e in entities if e.get("action_label") in ["taking_object", "holding_weapon"] or e.get("label") in [
                "backpack", "phone", "cell phone", "knife", "bag", "handbag", "hat", "cap", "helmet", "food", "cup", "bottle", "pizza", "sandwich"
            ]), None)
            if obj_entity:
                ts = obj_entity.get("timestamp_seconds", 0.0)
                raw_label = str(obj_entity.get("label", "đồ vật"))
                label_map = {
                    "backpack": "chiếc balo",
                    "phone": "điện thoại",
                    "cell phone": "điện thoại",
                    "knife": "con dao",
                    "bag": "túi xách",
                    "handbag": "túi xách",
                    "hat": "nón/mũ",
                    "cap": "mũ lưỡi trai",
                    "helmet": "mũ bảo hiểm",
                    "food": "đồ ăn",
                    "cup": "ly nước",
                    "bottle": "chai nước",
                    "pizza": "bánh pizza",
                    "sandwich": "bánh mì",
                }
                vn_label = label_map.get(raw_label.lower(), raw_label)
                color = obj_entity.get("clothing_top_color")
                color_vn = color_vn_names.get(color, color) if color else ""
                person_desc = f"mặc áo {color_vn}" if color_vn else ""
                return {
                    "translated_query_en": f"Did someone take or interact with an object ({raw_label}): {user_question}?",
                    "question_type": QAQuestionType.OBJECT_REASONING,
                    "reasoning_en": f"Found entity interaction with object ({raw_label}) around {ts:.2f}s.",
                    "response_vi": f"Có. Phát hiện một người {person_desc} lấy/tương tác với {vn_label} vào khoảng {ts:.2f}s.",
                    "evidences": [{
                        "frame_id": obj_entity.get("frame_id"),
                        "start_timestamp": ts,
                        "end_timestamp": ts + 4.0,
                        "snapshot_path": obj_entity.get("frame_path", ""),
                        "highlight_bbox": json.loads(obj_entity["bbox_json"]) if obj_entity.get("bbox_json") else None,
                        "explanation_vi": f"Người tương tác với {vn_label}",
                    }],
                }
            else:
                return {
                    "translated_query_en": f"Did anyone have accessories or take objects: {user_question}?",
                    "question_type": QAQuestionType.OBJECT_REASONING,
                    "reasoning_en": "No special objects, accessories, or taking actions detected in context.",
                    "response_vi": "Không phát hiện hành vi lấy trộm hoặc phụ kiện đặc biệt nào trong video.",
                    "evidences": [],
                }

        # 4. KIỂM TRA SỐ LƯỢNG NGƯỜI (Count Query)
        if any(w in q_lower for w in ["bao nhiêu người", "mấy người", "số lượng người", "số người", "đếm người"]):
            if person_entities:
                max_people = max([e.get("person_count", 1) for e in person_entities] or [1])
                timestamps = [e.get("timestamp_seconds", 0.0) for e in person_entities]
                min_t, max_t = min(timestamps), max(timestamps)
                members = list(dict.fromkeys([e.get("member_name") for e in person_entities if e.get("member_name")]))
                member_desc = f" ({', '.join(members)})" if members else ""
                time_desc = f"tại {min_t:.2f}s" if abs(min_t - max_t) < 0.5 else f"từ {min_t:.2f}s đến {max_t:.2f}s"
                return {
                    "translated_query_en": f"How many people appear in the video: {user_question}?",
                    "question_type": QAQuestionType.COUNT,
                    "reasoning_en": f"Found up to {max_people} concurrent person(s) between {min_t:.2f}s and {max_t:.2f}s.",
                    "response_vi": f"Trong video ghi nhận có khoảng {max_people} người{member_desc} xuất hiện trong khoảng thời gian {time_desc}.",
                    "evidences": [{
                        "frame_id": person_entities[0].get("frame_id"),
                        "start_timestamp": min_t,
                        "end_timestamp": min_t + 2.0,
                        "snapshot_path": person_entities[0].get("frame_path", ""),
                        "highlight_bbox": json.loads(person_entities[0]["bbox_json"]) if person_entities[0].get("bbox_json") else None,
                        "explanation_vi": f"Khung hình ghi nhận người xuất hiện tại mốc {min_t:.2f}s",
                    }],
                }

        # 5. KIỂM TRA SỰ XUẤT HIỆN / DANH TÍNH (Identity & Presence)
        if any(w in q_lower for w in ["có ai", "ai xuất hiện", "có người nào", "người lạ", "nhận diện ai", "ai trong video", "có người không"]):
            if person_entities:
                timestamps = [e.get("timestamp_seconds", 0.0) for e in person_entities]
                min_t, max_t = min(timestamps), max(timestamps)
                members = list(dict.fromkeys([e.get("member_name") for e in person_entities if e.get("member_name")]))
                colors = list(dict.fromkeys([
                    color_vn_names.get(e.get("clothing_top_color"), e.get("clothing_top_color"))
                    for e in person_entities if e.get("clothing_top_color") and e.get("clothing_top_color") != "unknown"
                ]))
                color_desc = f", mặc áo {', '.join(colors)}" if colors else ""

                if members:
                    who_str = f"người quen là {', '.join(members)}"
                else:
                    who_str = "người xuất hiện (chưa đăng ký danh tính)"

                time_desc = f"tại {min_t:.2f}s" if abs(min_t - max_t) < 0.5 else f"từ mốc {min_t:.2f}s đến {max_t:.2f}s"
                return {
                    "translated_query_en": f"Who appears in the video: {user_question}?",
                    "question_type": QAQuestionType.IDENTITY,
                    "reasoning_en": f"Recorded person activity between {min_t:.2f}s and {max_t:.2f}s.",
                    "response_vi": f"Có. Trong video ghi nhận {who_str}{color_desc} xuất hiện {time_desc}.",
                    "evidences": [{
                        "frame_id": person_entities[0].get("frame_id"),
                        "start_timestamp": min_t,
                        "end_timestamp": min_t + 2.0,
                        "snapshot_path": person_entities[0].get("frame_path", ""),
                        "highlight_bbox": json.loads(person_entities[0]["bbox_json"]) if person_entities[0].get("bbox_json") else None,
                        "explanation_vi": f"Đối tượng xuất hiện tại mốc {min_t:.2f}s",
                    }],
                }

        # 6. TRẢ LỜI TỔNG QUÁT (General)
        if person_entities:
            timestamps = [e.get("timestamp_seconds", 0.0) for e in person_entities]
            min_t, max_t = min(timestamps), max(timestamps)
            colors = list(dict.fromkeys([
                color_vn_names.get(e.get("clothing_top_color"), e.get("clothing_top_color"))
                for e in person_entities if e.get("clothing_top_color") and e.get("clothing_top_color") != "unknown"
            ]))
            color_desc = f" (mặc áo {', '.join(colors)})" if colors else ""
            return {
                "translated_query_en": f"Surveillance query: {user_question}",
                "question_type": QAQuestionType.GENERAL,
                "reasoning_en": f"General surveillance query. Recorded person presence between {min_t:.2f}s and {max_t:.2f}s.",
                "response_vi": f"Hệ thống ghi nhận câu hỏi: '{user_question}'. Dữ liệu video cho thấy có người{color_desc} xuất hiện từ {min_t:.2f}s đến {max_t:.2f}s nhưng không ghi nhận hành vi nguy hiểm.",
                "evidences": [],
            }

        return {
            "translated_query_en": f"Surveillance query: {user_question}",
            "question_type": QAQuestionType.GENERAL,
            "reasoning_en": "Generic surveillance response synthesized from recorded logs.",
            "response_vi": f"Hệ thống đã ghi nhận câu hỏi: '{user_question}'. Dữ liệu hiện tại chưa ghi nhận sự việc liên quan.",
            "evidences": [],
        }

    # ==================== VIDEO UPLOAD METHODS ====================

    def upload_video(
        self,
        conversation_id: int,
        file_path: Path,
        filename: str,
    ) -> QAUploadedVideo:
        """Register an uploaded video and start background indexing."""
        # Validate conversation exists
        self.get_conversation(conversation_id)

        video_id = f"qa_upload_{uuid4().hex[:12]}"

        self.connection.execute(
            """
            INSERT INTO qa_uploaded_videos (
                conversation_id, video_id, filename, file_path, status
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                video_id,
                filename,
                str(file_path),
                QAUploadedVideoStatus.QUEUED,
            ),
        )
        self.connection.commit()

        # Start background indexing thread
        thread = threading.Thread(
            target=self._run_video_indexing,
            args=(video_id, file_path),
            name=f"qa-video-index-{video_id}",
            daemon=True,
        )
        thread.start()

        return self._get_uploaded_video(video_id)

    def _list_uploaded_videos(self, conversation_id: int) -> list[QAUploadedVideo]:
        rows = self.connection.execute(
            """
            SELECT id, conversation_id, video_id, filename, status,
                   processed_frames, total_frames, error_message,
                   created_at, completed_at
            FROM qa_uploaded_videos
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            """,
            (conversation_id,),
        ).fetchall()
        return [self._row_to_uploaded_video(r) for r in rows]

    def list_uploaded_videos(self, conversation_id: int) -> list[QAUploadedVideo]:
        self.get_conversation(conversation_id)
        return self._list_uploaded_videos(conversation_id)

    def _get_uploaded_video(self, video_id: str) -> QAUploadedVideo:
        row = self.connection.execute(
            """
            SELECT id, conversation_id, video_id, filename, status,
                   processed_frames, total_frames, error_message,
                   created_at, completed_at
            FROM qa_uploaded_videos
            WHERE video_id = ?
            """,
            (video_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Uploaded video '{video_id}' not found")
        return self._row_to_uploaded_video(row)

    def get_uploaded_video_status(self, video_id: str) -> QAUploadedVideo:
        return self._get_uploaded_video(video_id)

    def delete_uploaded_video(self, video_id: str) -> None:
        row = self.connection.execute(
            "SELECT video_id, file_path FROM qa_uploaded_videos WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Uploaded video '{video_id}' not found")

        self._cleanup_uploaded_video_data(row["video_id"], row["file_path"])
        self.connection.execute(
            "DELETE FROM qa_uploaded_videos WHERE video_id = ?",
            (video_id,),
        )
        self.connection.commit()

    def _cleanup_uploaded_video_data(self, video_id: str, file_path: str, delete_file: bool = True) -> None:
        """Remove video_frames (cascade deletes entities/threats), snapshot files, and optionally the video file."""
        # Get snapshot paths to delete files (both frame snapshots and threat snapshots)
        snapshot_rows = self.connection.execute(
            """
            SELECT frame_path FROM video_frames
            WHERE session_or_video_id = ? AND frame_path != ''
            """,
            (video_id,),
        ).fetchall()
        for srow in snapshot_rows:
            try:
                p = Path(srow["frame_path"])
                if not p.is_absolute():
                    from backend.app.config import BASE_DIR
                    p = BASE_DIR / p
                if p.exists() and p.is_file():
                    p.unlink()
            except OSError:
                pass

        threat_snapshot_rows = self.connection.execute(
            """
            SELECT dt.snapshot_path FROM danger_threats dt
            JOIN video_frames vf ON dt.frame_id = vf.id
            WHERE vf.session_or_video_id = ? AND dt.snapshot_path != ''
            """,
            (video_id,),
        ).fetchall()
        for trow in threat_snapshot_rows:
            try:
                p = Path(trow["snapshot_path"])
                if not p.is_absolute():
                    from backend.app.config import BASE_DIR
                    p = BASE_DIR / p
                if p.exists() and p.is_file():
                    p.unlink()
            except OSError:
                pass

        # Explicitly delete child rows (and rely on CASCADE)
        self.connection.execute(
            """
            DELETE FROM detected_entities
            WHERE frame_id IN (SELECT id FROM video_frames WHERE session_or_video_id = ?)
            """,
            (video_id,),
        )
        self.connection.execute(
            """
            DELETE FROM danger_threats
            WHERE frame_id IN (SELECT id FROM video_frames WHERE session_or_video_id = ?)
            """,
            (video_id,),
        )

        # Delete video_frames
        self.connection.execute(
            "DELETE FROM video_frames WHERE session_or_video_id = ?",
            (video_id,),
        )
        self.connection.commit()

        # Delete the video file if requested
        if delete_file:
            try:
                fp = Path(file_path)
                if fp.exists() and fp.is_file():
                    fp.unlink()
            except OSError:
                pass

    def retry_uploaded_video(self, video_id: str) -> QAUploadedVideo:
        """Retry indexing a previously failed video without re-uploading."""
        row = self.connection.execute(
            "SELECT video_id, file_path FROM qa_uploaded_videos WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Uploaded video '{video_id}' not found")

        fp = Path(row["file_path"])
        if not fp.exists():
            raise ValueError("Video file is no longer on disk. Please upload again.")

        # Clean up any partial frames/entities/threats but keep video file
        self._cleanup_uploaded_video_data(row["video_id"], row["file_path"], delete_file=False)

        # Reset status to queued
        self.connection.execute(
            """
            UPDATE qa_uploaded_videos
            SET status = ?, processed_frames = 0, error_message = NULL, completed_at = NULL
            WHERE video_id = ?
            """,
            (QAUploadedVideoStatus.QUEUED, video_id),
        )
        self.connection.commit()

        # Start background indexing thread
        thread = threading.Thread(
            target=self._run_video_indexing,
            args=(video_id, fp),
            name=f"qa-video-index-{video_id}",
            daemon=True,
        )
        thread.start()

        return self._get_uploaded_video(video_id)

    def _run_video_indexing(self, video_id: str, file_path: Path) -> None:
        """Background thread: process video frames and index into DB."""
        connection = None
        capture = None
        try:
            connection = get_connection()

            # Update status to processing
            connection.execute(
                "UPDATE qa_uploaded_videos SET status = ? WHERE video_id = ?",
                (QAUploadedVideoStatus.PROCESSING, video_id),
            )
            connection.commit()

            capture = cv2.VideoCapture(str(file_path))
            if not capture.isOpened():
                raise RuntimeError(f"Could not open video: {file_path}")

            input_fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if total_frames > 0:
                connection.execute(
                    "UPDATE qa_uploaded_videos SET total_frames = ? WHERE video_id = ?",
                    (total_frames, video_id),
                )
                connection.commit()

            # Use a virtual camera_id = 0 for uploaded QA videos
            # Sample every N frames to avoid indexing every single frame
            sample_interval = max(1, int(input_fps))  # ~1 frame per second

            from backend.services.frame_indexer_service import FrameIndexerService
            indexer = FrameIndexerService(connection)

            from backend.services.gallery_service import build_analysis_runtime
            runtime = build_analysis_runtime(connection)

            yolo_model = None
            try:
                if hasattr(runtime.engine, "person_tracker") and hasattr(runtime.engine.person_tracker, "_get_model"):
                    yolo_model = runtime.engine.person_tracker._get_model()
            except Exception:
                pass

            frame_index = 0
            indexed_count = 0
            while True:
                success, frame = capture.read()
                if not success or frame is None:
                    break

                if frame_index % sample_interval == 0:
                    timestamp_seconds = frame_index / input_fps if input_fps > 0 else 0.0

                    analysis = runtime.engine.analyze_frame(
                        frame,
                        frame_index=frame_index,
                        timestamp_seconds=timestamp_seconds,
                    )

                    # Get raw YOLO detections for threat/object detection
                    raw_detections = []
                    if yolo_model is not None:
                        try:
                            yolo_res = yolo_model(frame, conf=0.30, verbose=False)
                            if yolo_res and len(yolo_res) > 0 and yolo_res[0].boxes is not None:
                                for box in yolo_res[0].boxes:
                                    cls_id = int(box.cls.item())
                                    label_name = yolo_res[0].names.get(cls_id, "")
                                    conf_val = float(box.conf.item())
                                    coords = box.xyxy[0].cpu().numpy().astype(int)
                                    raw_detections.append({
                                        "label": label_name,
                                        "confidence": conf_val,
                                        "x1": int(coords[0]),
                                        "y1": int(coords[1]),
                                        "x2": int(coords[2]),
                                        "y2": int(coords[3]),
                                    })
                        except Exception:
                            pass
                    elif hasattr(runtime.engine, '_last_yolo_results'):
                        raw_detections = runtime.engine._last_yolo_results

                    indexer.index_frame(
                        frame,
                        camera_id=None,
                        session_or_video_id=video_id,
                        timestamp_seconds=timestamp_seconds,
                        frame_number=frame_index,
                        analysis=analysis,
                        raw_object_detections=raw_detections,
                    )
                    indexed_count += 1

                frame_index += 1

                # Update progress every 30 frames
                if frame_index % 30 == 0:
                    connection.execute(
                        "UPDATE qa_uploaded_videos SET processed_frames = ? WHERE video_id = ?",
                        (frame_index, video_id),
                    )
                    connection.commit()

            # Mark completed
            connection.execute(
                """
                UPDATE qa_uploaded_videos
                SET status = ?, processed_frames = ?, completed_at = ?
                WHERE video_id = ?
                """,
                (
                    QAUploadedVideoStatus.COMPLETED,
                    frame_index,
                    datetime.now(timezone.utc).isoformat(),
                    video_id,
                ),
            )
            connection.commit()
            logger.info("Video indexing completed: %s (%d frames, %d indexed)", video_id, frame_index, indexed_count)

        except Exception as exc:
            logger.exception("Video indexing failed for %s", video_id)
            if connection:
                try:
                    connection.execute(
                        """
                        UPDATE qa_uploaded_videos
                        SET status = ?, error_message = ?, completed_at = ?
                        WHERE video_id = ?
                        """,
                        (
                            QAUploadedVideoStatus.FAILED,
                            str(exc),
                            datetime.now(timezone.utc).isoformat(),
                            video_id,
                        ),
                    )
                    connection.commit()
                except Exception:
                    pass
        finally:
            if capture is not None:
                try:
                    capture.release()
                except Exception:
                    pass
            if connection is not None:
                connection.close()

    @staticmethod
    def _row_to_uploaded_video(row: sqlite3.Row) -> QAUploadedVideo:
        return QAUploadedVideo(
            id=row["id"],
            conversation_id=row["conversation_id"],
            video_id=row["video_id"],
            filename=row["filename"],
            status=row["status"],
            processed_frames=row["processed_frames"],
            total_frames=row["total_frames"],
            error_message=row["error_message"],
            created_at=str(row["created_at"]),
            completed_at=str(row["completed_at"]) if row["completed_at"] else None,
        )
