import json
import logging
import shutil
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    SNAPSHOTS_DIR,
    TEMP_UPLOADS_DIR,
    resolve_storage_path,
    serialize_storage_path,
)
from backend.app.models import QAQuestionType, QAUploadedVideoStatus
from backend.app.schemas import (
    QAAskRequest,
    QAConversation,
    QAConversationDetail,
    QAEvidence,
    QAMessage,
    QAUploadedVideo,
)
from backend.services.qa_video_index_manager import (
    QAVideoIndexManager,
    qa_video_index_manager,
)
from backend.services.qa_snapshot_storage import qa_video_snapshot_dir

logger = logging.getLogger(__name__)


class QAVideoCleanupError(RuntimeError):
    """Required Q&A filesystem cleanup failed; DB metadata is retained."""


class QAService:
    """Service handling multi-lingual Video Surveillance Question Answering with Gemini reasoning."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        api_key: str = GEMINI_API_KEY,
        model_name: str = GEMINI_MODEL,
        index_manager: QAVideoIndexManager = qa_video_index_manager,
        snapshots_dir: Path = SNAPSHOTS_DIR,
        uploads_dir: Path = TEMP_UPLOADS_DIR,
    ) -> None:
        self.connection = connection
        self.api_key = api_key
        self.model_name = model_name
        self.index_manager = index_manager
        try:
            self.snapshots_dir = Path(snapshots_dir).resolve()
            qa_root = Path(index_manager.qa_snapshots_dir)
            # Resolving must not hide an alias that the shared ownership helper
            # would reject when the manager uses the original configured path.
            if qa_root.is_symlink() or getattr(qa_root, "is_junction", lambda: False)():
                raise ValueError("Q&A snapshot root cannot be a filesystem alias")
            self.qa_snapshots_dir = qa_root.resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError("Invalid Q&A snapshot root configuration") from exc
        if self.qa_snapshots_dir == self.snapshots_dir or not self.qa_snapshots_dir.is_relative_to(self.snapshots_dir):
            raise ValueError("Manager Q&A snapshot root must be strictly inside snapshots_dir")
        self.uploads_dir = Path(uploads_dir)

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
        with self.index_manager.lifecycle_lock:
            video_rows = self.connection.execute(
                "SELECT video_id, file_path FROM qa_uploaded_videos WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
            # Signal ALL jobs before joining any; do not clean one video's files
            # while another worker from this conversation can still write.
            self.index_manager.cancel_many(row["video_id"] for row in video_rows)
            with self.connection:
                self._cleanup_uploaded_videos(video_rows)
                self.connection.execute(
                    "DELETE FROM qa_conversations WHERE id = ?", (conversation_id,)
                )

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

        returned_evidences = qa_result.get("evidences", [])
        provenance, threat_ids_by_path = self._context_snapshot_provenance(context_data) if returned_evidences else ({}, {})

        # Reasoning stays outside the lifecycle lock. Only final persistence is
        # serialized with deletion, and all inserts commit or roll back together.
        with self.index_manager.lifecycle_lock, self.connection:
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
            for ev in self._revalidate_evidences(returned_evidences, provenance, threat_ids_by_path, request):
                start_ts = float(ev.get("start_timestamp", 0.0))
                end_ts = float(ev.get("end_timestamp", start_ts))
                snapshot = ev.get("snapshot_path") or ""
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

    def _canonical_snapshot_path(self, stored_path: str) -> Path | None:
        """Resolve an untrusted snapshot reference without failing unrelated work."""
        if not stored_path or not isinstance(stored_path, str):
            return None
        try:
            path = resolve_storage_path(stored_path)
            root = self.snapshots_dir.resolve()
            if path != root and path.is_relative_to(root):
                return path
        except (OSError, ValueError, RuntimeError):
            pass
        return None

    def _context_snapshot_provenance(
        self, context: dict[str, Any],
    ) -> tuple[dict[Path, set[int]], dict[Path, set[int]]]:
        """Only the bounded context supplied to reasoning can identify images."""
        provenance: dict[Path, set[int]] = {}
        threat_ids_by_path: dict[Path, set[int]] = {}
        for source, path_key in (("entities", "frame_path"), ("threats", "snapshot_path")):
            for row in context.get(source, []):
                frame_id = row.get("frame_id")
                path = self._canonical_snapshot_path(row.get(path_key))
                if path is None or type(frame_id) is not int:
                    continue
                provenance.setdefault(path, set()).add(frame_id)
                threat_id = row.get("threat_id")
                if source == "threats" and type(threat_id) is int:
                    threat_ids_by_path.setdefault(path, set()).add(threat_id)
        return provenance, threat_ids_by_path

    def _revalidate_evidences(
        self, evidences: list[dict], provenance: dict[Path, set[int]],
        threat_ids_by_path: dict[Path, set[int]], request: QAAskRequest,
    ) -> list[dict]:
        """At most two keyed SELECTs, under the lifecycle lock/transaction.

        Frame IDs come from the current response or bounded context. Threat IDs
        come only from that context, keeping fetched data bounded as well.
        """
        candidates = []
        frame_ids: set[int] = set()
        threat_ids: set[int] = set()
        for evidence in evidences:
            frame_id = evidence.get("frame_id")
            if frame_id is not None and (type(frame_id) is not int or not 0 < frame_id < 2**63):
                continue
            snapshot = evidence.get("snapshot_path")
            path = self._canonical_snapshot_path(snapshot) if snapshot else None
            if snapshot and path is None:
                continue
            origins = {frame_id} if frame_id is not None else provenance.get(path, set())
            if snapshot and not origins:
                continue
            candidates.append((evidence, path, origins))
            frame_ids.update(origins)
            threat_ids.update(threat_ids_by_path.get(path, set()))

        current_frames: dict[int, set[Path]] = {}
        if frame_ids:
            parameters = list(frame_ids)
            conditions = [f"id IN ({','.join('?' for _ in parameters)})"]
            if request.session_or_video_id is not None:
                conditions.append("session_or_video_id = ?")
                parameters.append(request.session_or_video_id)
            if request.camera_id is not None:
                conditions.append("camera_id = ?")
                parameters.append(request.camera_id)
            rows = self.connection.execute(
                "SELECT id, frame_path FROM video_frames WHERE " + " AND ".join(conditions), parameters,
            ).fetchall()
            for row in rows:
                path = self._canonical_snapshot_path(row["frame_path"])
                current_frames[row["id"]] = {path} if path is not None else set()

        if threat_ids and current_frames:
            rows = self.connection.execute(
                "SELECT id, frame_id, snapshot_path FROM danger_threats WHERE id IN ("
                + ",".join("?" for _ in threat_ids) + ")", list(threat_ids),
            ).fetchall()
            for row in rows:
                if row["frame_id"] in current_frames:
                    path = self._canonical_snapshot_path(row["snapshot_path"])
                    if path is not None:
                        current_frames[row["frame_id"]].add(path)

        valid = []
        for evidence, path, origins in candidates:
            if origins and not any(frame_id in current_frames for frame_id in origins):
                continue
            if path is not None:
                owners = {frame_id for frame_id in origins if path in current_frames.get(frame_id, set())}
                if len(owners) != 1:
                    continue
                try:
                    if not path.is_file():
                        continue
                except (OSError, ValueError):
                    continue
                # Every new image card is owned by a surviving frame, including
                # snapshot-only Gemini evidence. Keep canonical storage spelling.
                evidence = {**evidence, "frame_id": owners.pop(), "snapshot_path": serialize_storage_path(path)}
            # Textual/time-range evidence without an image or frame is valid too.
            valid.append(evidence)
        return valid

    def _delete_snapshot_evidences(self, snapshot_paths: set[Path]) -> None:
        """Remove cards by canonical snapshot identity; never unlink their paths."""
        if not snapshot_paths:
            return
        rows = self.connection.execute(
            "SELECT id, snapshot_path FROM qa_evidences WHERE snapshot_path != ''"
        ).fetchall()
        self.connection.executemany(
            "DELETE FROM qa_evidences WHERE id = ?",
            [
                (row["id"],) for row in rows
                if self._canonical_snapshot_path(row["snapshot_path"]) in snapshot_paths
            ],
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
            SELECT dt.id AS threat_id, vf.id AS frame_id,
                   dt.threat_type, dt.confidence, dt.snapshot_path, dt.description_en,
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
                        "frame_id": matching_threat.get("frame_id"),
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
        with self.index_manager.lifecycle_lock:
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

            self.index_manager.start(video_id, file_path)

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
        with self.index_manager.lifecycle_lock:
            row = self.connection.execute(
                "SELECT video_id, file_path FROM qa_uploaded_videos WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Uploaded video '{video_id}' not found")
            self.index_manager.cancel(video_id)
            with self.connection:
                self._cleanup_uploaded_videos([row])
                self.connection.execute(
                    "DELETE FROM qa_uploaded_videos WHERE video_id = ?", (video_id,)
                )

    def _snapshot_paths(self, video_id: str) -> set[str]:
        rows = self.connection.execute(
            """
            SELECT frame_path AS path FROM video_frames WHERE session_or_video_id = ?
            UNION
            SELECT dt.snapshot_path AS path FROM danger_threats dt
            JOIN video_frames vf ON dt.frame_id = vf.id
            WHERE vf.session_or_video_id = ?
            """,
            (video_id, video_id),
        ).fetchall()
        return {row["path"] for row in rows if row["path"]}

    @staticmethod
    def _cleanup_path(stored_path: str, storage_root: Path) -> Path:
        path = resolve_storage_path(stored_path)
        root = storage_root.resolve()
        if path == root or not path.is_relative_to(root):
            logger.error("Refusing Q&A cleanup path %s outside storage root %s", path, root)
            raise QAVideoCleanupError("Q&A cleanup encountered an invalid storage path")
        return path

    def _cleanup_uploaded_videos(self, video_rows, *, delete_file: bool = True) -> None:
        """Stop workers before calling. No commits: callers own the transaction."""
        targets = {row["video_id"]: self._snapshot_paths(row["video_id"]) for row in video_rows}
        # Resolve and validate the entire batch before unlinking anything. Dedup
        # resolved paths too, since relative/absolute spellings can alias a file.
        path = None
        try:
            directories = {
                video_id: qa_video_snapshot_dir(video_id, qa_root=self.qa_snapshots_dir)
                for video_id in targets
            }
            qa_root = self._cleanup_path(str(self.qa_snapshots_dir), self.snapshots_dir)
            legacy_files: set[Path] = set()
            for video_id, snapshot_paths in targets.items():
                directory = directories[video_id]
                for stored_path in snapshot_paths:
                    path = self._cleanup_path(stored_path, self.snapshots_dir)
                    if path != directory and path.is_relative_to(directory):
                        continue
                    if path.is_relative_to(qa_root):
                        raise QAVideoCleanupError("Q&A snapshot path belongs to another video")
                    legacy_files.add(path)
            files = legacy_files.copy()
            if delete_file:
                files.update(
                    self._cleanup_path(row["file_path"], self.uploads_dir)
                    for row in video_rows if row["file_path"]
                )
            # All directories/files in the batch have been validated. Orphans
            # within each exact owned directory are removed with its snapshots.
            for video_id, path in directories.items():
                if path != qa_video_snapshot_dir(video_id, qa_root=self.qa_snapshots_dir):
                    raise QAVideoCleanupError("Q&A snapshot directory ownership changed")
                try:
                    shutil.rmtree(path)
                except FileNotFoundError:
                    if path.exists():
                        raise
            for path in sorted(files):
                path.unlink(missing_ok=True)
        except (OSError, ValueError, RuntimeError) as exc:
            logger.exception("Q&A filesystem cleanup failed for videos %s at %s", list(targets), path)
            raise QAVideoCleanupError(
                "Could not remove Q&A video files; please retry deletion"
            ) from exc

        # Only after every file was cleaned do we discard retry metadata.
        for video_id in targets:
            self.connection.execute(
                """
                DELETE FROM qa_evidences WHERE frame_id IN
                    (SELECT id FROM video_frames WHERE session_or_video_id = ?)
                """,
                (video_id,),
            )
        # Only legacy flat data needs the canonical scan for unowned/alias cards.
        # New image cards are removed by their indexed frame_id above.
        if legacy_files:
            self._delete_snapshot_evidences(legacy_files)
        for video_id in targets:
            for table in ("detected_entities", "danger_threats"):
                self.connection.execute(
                    f"DELETE FROM {table} WHERE frame_id IN "
                    "(SELECT id FROM video_frames WHERE session_or_video_id = ?)",
                    (video_id,),
                )
            self.connection.execute(
                "DELETE FROM video_frames WHERE session_or_video_id = ?", (video_id,)
            )

    def retry_uploaded_video(self, video_id: str) -> QAUploadedVideo:
        """Retry without allowing a previous worker to write into the new index."""
        with self.index_manager.lifecycle_lock:
            row = self.connection.execute(
                "SELECT video_id, file_path FROM qa_uploaded_videos WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Uploaded video '{video_id}' not found")
            self.index_manager.cancel(video_id)
            fp = self._cleanup_path(row["file_path"], self.uploads_dir)
            if not fp.exists():
                raise ValueError("Video file is no longer on disk. Please upload again.")
            with self.connection:
                self._cleanup_uploaded_videos([row], delete_file=False)
                self.connection.execute(
                    """
                    UPDATE qa_uploaded_videos
                    SET status = ?, processed_frames = 0, error_message = NULL, completed_at = NULL
                    WHERE video_id = ?
                    """,
                    (QAUploadedVideoStatus.QUEUED, video_id),
                )
            self.index_manager.start(video_id, fp)
            return self._get_uploaded_video(video_id)

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
