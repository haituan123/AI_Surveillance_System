"""Generate the Draw.io ERD for the current SQLite schema (version 4)."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "docs" / "AI_Surveillance_System_ERD.drawio"


TABLES = {
    "people": {
        "section": "Identity",
        "position": (40, 180),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("", "name", "TEXT", "NOT NULL"),
            ("", "created_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
        ],
    },
    "face_embeddings": {
        "section": "Identity",
        "position": (40, 380),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("FK", "person_id", "INTEGER", "NOT NULL → people.id; ON DELETE CASCADE"),
            ("", "image_path", "TEXT", "NOT NULL"),
            ("", "embedding_path", "TEXT", "NULL"),
            ("", "created_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
        ],
    },
    "cameras": {
        "section": "Live surveillance",
        "position": (390, 180),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("", "name", "TEXT", "NOT NULL"),
            ("", "source", "TEXT", "NOT NULL"),
            ("", "location", "TEXT", "NULL"),
            ("", "is_active", "INTEGER", "NOT NULL, default 1; CHECK 0|1"),
            ("", "created_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
            ("", "updated_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
        ],
    },
    "zones": {
        "section": "Live surveillance",
        "position": (390, 500),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("FK", "camera_id", "INTEGER", "NOT NULL → cameras.id; ON DELETE CASCADE"),
            ("", "name", "TEXT", "NOT NULL"),
            ("", "polygon_json", "TEXT", "NOT NULL"),
            ("", "is_active", "INTEGER", "NOT NULL, default 1; CHECK 0|1"),
            ("", "created_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
            ("", "updated_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
            ("UQ", "camera_id + name", "", "unique together"),
        ],
    },
    "surveillance_sessions": {
        "section": "Live surveillance",
        "position": (750, 180),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("FK", "camera_id", "INTEGER", "NOT NULL → cameras.id"),
            ("", "status", "TEXT", "NOT NULL, default running; CHECK running | stopped | failed"),
            ("", "started_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
            ("", "ended_at", "TEXT", "NULL"),
            ("", "average_fps", "REAL", "NULL; CHECK >= 0"),
            ("", "frames_processed", "INTEGER", "NOT NULL, default 0; CHECK >= 0"),
            ("", "error_message", "TEXT", "NULL"),
        ],
    },
    "detection_logs": {
        "section": "Live surveillance",
        "position": (1110, 180),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("FK", "session_id", "INTEGER", "NOT NULL → surveillance_sessions.id; ON DELETE CASCADE"),
            ("FK", "camera_id", "INTEGER", "NOT NULL → cameras.id"),
            ("FK", "member_id", "INTEGER", "NULL → people.id; ON DELETE SET NULL"),
            ("", "track_id", "INTEGER", "NULL"),
            ("", "status", "TEXT", "known | unknown | low_quality"),
            ("", "confidence", "REAL", "NULL; CHECK -1.0..1.0"),
            ("", "snapshot_path", "TEXT", "NULL"),
            ("", "detected_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
        ],
    },
    "alerts": {
        "section": "Live surveillance",
        "position": (1490, 180),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("FK", "session_id", "INTEGER", "NOT NULL → surveillance_sessions.id; ON DELETE CASCADE"),
            ("FK", "camera_id", "INTEGER", "NOT NULL → cameras.id"),
            ("FK", "detection_log_id", "INTEGER", "NULL → detection_logs.id; ON DELETE SET NULL"),
            ("FK", "member_id", "INTEGER", "NULL → people.id; ON DELETE SET NULL"),
            ("", "alert_type", "TEXT", "unknown_person | restricted_area | loitering | knife_threat | weapon_drawn | fire_smoke | theft | violence"),
            ("", "message", "TEXT", "NOT NULL"),
            ("", "confidence", "REAL", "NULL; CHECK -1.0..1.0"),
            ("", "snapshot_path", "TEXT", "NULL"),
            ("", "is_read", "INTEGER", "NOT NULL, default 0; CHECK 0|1"),
            ("", "created_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
        ],
    },
    "video_frames": {
        "section": "Indexed video evidence",
        "position": (390, 900),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("FK", "camera_id", "INTEGER", "NULL → cameras.id; ON DELETE CASCADE"),
            ("", "session_or_video_id", "TEXT", "NOT NULL, logical video key"),
            ("", "timestamp_seconds", "REAL", "NOT NULL"),
            ("", "frame_number", "INTEGER", "NOT NULL"),
            ("", "frame_path", "TEXT", "NOT NULL"),
            ("", "person_count", "INTEGER", "NOT NULL, default 0"),
            ("", "scene_caption_en", "TEXT", "NULL"),
            ("", "visual_embedding", "TEXT", "NULL"),
            ("", "created_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
        ],
    },
    "detected_entities": {
        "section": "Indexed video evidence",
        "position": (790, 900),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("FK", "frame_id", "INTEGER", "NOT NULL → video_frames.id; ON DELETE CASCADE"),
            ("", "track_id", "INTEGER", "NULL"),
            ("FK", "member_id", "INTEGER", "NULL → people.id; ON DELETE SET NULL"),
            ("", "entity_type", "TEXT", "person | object | weapon"),
            ("", "label", "TEXT", "NOT NULL"),
            ("", "bbox_json", "TEXT", "NOT NULL"),
            ("", "confidence", "REAL", "NULL"),
            ("", "clothing_top_color", "TEXT", "NULL"),
            ("", "clothing_bottom_color", "TEXT", "NULL"),
            ("", "accessories_json", "TEXT", "NULL"),
            ("", "movement_direction", "TEXT", "NULL"),
            ("", "action_label", "TEXT", "NULL"),
            ("", "created_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
        ],
    },
    "danger_threats": {
        "section": "Indexed video evidence",
        "position": (1230, 900),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("FK", "frame_id", "INTEGER", "NOT NULL → video_frames.id; ON DELETE CASCADE"),
            ("", "threat_type", "TEXT", "knife_threat | weapon_drawn | fire_smoke | theft | violence"),
            ("", "confidence", "REAL", "NOT NULL"),
            ("", "snapshot_path", "TEXT", "NOT NULL"),
            ("", "description_en", "TEXT", "NULL"),
            ("", "is_resolved", "INTEGER", "NOT NULL, default 0; CHECK 0|1"),
            ("", "created_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
        ],
    },
    "qa_conversations": {
        "section": "Video Q&A",
        "position": (40, 1440),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("", "title", "TEXT", "NOT NULL, default 'Phiên hỏi đáp an ninh'"),
            ("", "created_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
        ],
    },
    "qa_uploaded_videos": {
        "section": "Video Q&A",
        "position": (390, 1440),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("FK", "conversation_id", "INTEGER", "NOT NULL → qa_conversations.id; ON DELETE CASCADE"),
            ("UQ", "video_id", "TEXT", "NOT NULL, unique"),
            ("", "filename", "TEXT", "NOT NULL"),
            ("", "file_path", "TEXT", "NOT NULL"),
            ("", "status", "TEXT", "NOT NULL, default queued; CHECK queued | processing | completed | failed"),
            ("", "processed_frames", "INTEGER", "NOT NULL, default 0"),
            ("", "total_frames", "INTEGER", "NULL"),
            ("", "error_message", "TEXT", "NULL"),
            ("", "created_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
            ("", "completed_at", "TEXT", "NULL"),
        ],
    },
    "qa_messages": {
        "section": "Video Q&A",
        "position": (790, 1440),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("FK", "conversation_id", "INTEGER", "NOT NULL → qa_conversations.id; ON DELETE CASCADE"),
            ("", "user_query_vi", "TEXT", "NOT NULL"),
            ("", "translated_query_en", "TEXT", "NOT NULL"),
            ("", "reasoning_en", "TEXT", "NULL"),
            ("", "response_vi", "TEXT", "NOT NULL"),
            ("", "question_type", "TEXT", "NOT NULL, default general; CHECK identity | attribute | threat | temporal | count | object_reasoning | general"),
            ("", "created_at", "TEXT", "NOT NULL, default CURRENT_TIMESTAMP"),
        ],
    },
    "qa_evidences": {
        "section": "Video Q&A",
        "position": (1230, 1440),
        "columns": [
            ("PK", "id", "INTEGER", "NOT NULL"),
            ("FK", "message_id", "INTEGER", "NOT NULL → qa_messages.id; ON DELETE CASCADE"),
            ("FK", "frame_id", "INTEGER", "NULL → video_frames.id; ON DELETE SET NULL"),
            ("", "start_timestamp", "REAL", "NOT NULL"),
            ("", "end_timestamp", "REAL", "NOT NULL"),
            ("", "snapshot_path", "TEXT", "NOT NULL"),
            ("", "highlight_bbox_json", "TEXT", "NULL"),
            ("", "explanation_vi", "TEXT", "NULL"),
        ],
    },
}


RELATIONSHIPS = [
    ("people", "face_embeddings", "parent 0..N; child 1", False),
    ("cameras", "zones", "parent 0..N; child 1", False),
    ("cameras", "surveillance_sessions", "parent 0..N; child 1", False),
    ("surveillance_sessions", "detection_logs", "parent 0..N; child 1", False),
    ("cameras", "detection_logs", "parent 0..N; child 1", False),
    ("people", "detection_logs", "parent 0..N; child 0..1", False),
    ("surveillance_sessions", "alerts", "parent 0..N; child 1", False),
    ("cameras", "alerts", "parent 0..N; child 1", False),
    ("detection_logs", "alerts", "parent 0..N; child 0..1", False),
    ("people", "alerts", "parent 0..N; child 0..1", False),
    ("cameras", "video_frames", "parent 0..N; child 0..1", False),
    ("video_frames", "detected_entities", "parent 0..N; child 1", False),
    ("people", "detected_entities", "parent 0..N; child 0..1", False),
    ("video_frames", "danger_threats", "parent 0..N; child 1", False),
    ("qa_conversations", "qa_uploaded_videos", "parent 0..N; child 1", False),
    ("qa_conversations", "qa_messages", "parent 0..N; child 1", False),
    ("qa_messages", "qa_evidences", "parent 0..N; child 1", False),
    ("video_frames", "qa_evidences", "parent 0..N; child 0..1", False),
    ("qa_uploaded_videos", "video_frames", "logical parent 0..N; frame 0..1", True),
]


SECTION_COLORS = {
    "Identity": ("#183526", "#83d39b"),
    "Live surveillance": ("#172b46", "#7eb6ff"),
    "Indexed video evidence": ("#3c3218", "#f2c94c"),
    "Video Q&A": ("#35223e", "#c99bdd"),
}


CONCEPTUAL_ENTITIES = {
    "people": (2020, 280),
    "face_embeddings": (2020, 580),
    "cameras": (2440, 200),
    "zones": (2440, 580),
    "surveillance_sessions": (2830, 200),
    "detection_logs": (3200, 300),
    "alerts": (3420, 650),
    "video_frames": (2400, 1020),
    "detected_entities": (2830, 1020),
    "danger_threats": (3260, 1020),
    "qa_conversations": (2040, 1570),
    "qa_uploaded_videos": (2460, 1450),
    "qa_messages": (2460, 1750),
    "qa_evidences": (2980, 1750),
}


CONCEPTUAL_RELATIONSHIPS = [
    ("people", "face_embeddings", "owns", (2100, 455), "(0,N)", "(1,1)"),
    ("cameras", "zones", "defines", (2490, 430), "(0,N)", "(1,1)"),
    ("cameras", "surveillance_sessions", "runs", (2680, 215), "(0,N)", "(1,1)"),
    ("surveillance_sessions", "detection_logs", "records", (3040, 260), "(0,N)", "(1,1)"),
    ("detection_logs", "alerts", "triggers", (3320, 505), "(0,N)", "(0,1)"),
    ("people", "detection_logs", "recognizes", (2690, 350), "(0,N)", "(0,1)"),
    ("video_frames", "detected_entities", "contains", (2650, 1035), "(0,N)", "(1,1)"),
    ("video_frames", "danger_threats", "reveals", (3040, 1150), "(0,N)", "(1,1)"),
    ("people", "detected_entities", "identifies", (2350, 820), "(0,N)", "(0,1)"),
    ("qa_conversations", "qa_uploaded_videos", "uploads", (2280, 1515), "(0,N)", "(1,1)"),
    ("qa_conversations", "qa_messages", "contains", (2280, 1745), "(0,N)", "(1,1)"),
    ("qa_messages", "qa_evidences", "cites", (2730, 1765), "(0,N)", "(1,1)"),
    ("qa_evidences", "video_frames", "references", (3160, 1450), "(0,1)", "(0,N)"),
    ("qa_uploaded_videos", "video_frames", "indexes", (2500, 1260), "(0,N)", "(0,1)"),
]


def add_cell(xml_parent: ET.Element, **attributes: str) -> ET.Element:
    return ET.SubElement(xml_parent, "mxCell", attributes)


def table_html(name: str, columns: list[tuple[str, str, str, str]], header: str) -> str:
    rows = []
    for key, column, data_type, note in columns:
        key_html = f'<b style="color:#ff9b92">{key}</b>' if key else ""
        type_html = f'<span style="color:#aab2bd">{data_type}</span>' if data_type else ""
        note_html = f' <span style="color:#c7cbd1">— {note}</span>' if note else ""
        rows.append(
            '<tr style="border-bottom:1px solid #4b4f55">'
            f'<td style="width:28px;padding:3px 6px;border-right:1px solid #666">{key_html}</td>'
            f'<td style="padding:3px 6px"><b>{column}</b> {type_html}{note_html}</td></tr>'
        )
    return (
        f'<div style="font-size:14px;text-align:center;font-weight:bold;background:{header};padding:7px;'
        f'margin:-6px -6px 0 -6px;border-bottom:1px solid #dddddd">{name}</div>'
        '<table style="width:100%;border-collapse:collapse;color:#ffffff;font-size:10px">'
        + "".join(rows)
        + "</table>"
    )


def generate() -> None:
    mxfile = ET.Element(
        "mxfile",
        {
            "host": "app.diagrams.net",
            "agent": "AI Surveillance System ERD generator",
            "version": "27.0.5",
        },
    )
    diagram = ET.SubElement(mxfile, "diagram", {"name": "Complete ERD", "id": "ais-schema-v4"})
    model = ET.SubElement(
        diagram,
        "mxGraphModel",
        {
            "dx": "3700",
            "dy": "2200",
            "grid": "1",
            "gridSize": "10",
            "guides": "1",
            "tooltips": "1",
            "connect": "1",
            "arrows": "1",
            "fold": "1",
            "page": "1",
            "pageScale": "1",
            "pageWidth": "3700",
            "pageHeight": "2200",
            "background": "#101214",
            "math": "0",
            "shadow": "0",
        },
    )
    root = ET.SubElement(model, "root")
    add_cell(root, id="0")
    add_cell(root, id="1", parent="0")

    title = add_cell(
        root,
        id="diagram-title",
        value="AI Surveillance System — Database Design (SQLite schema v4)",
        style="text;html=1;align=left;verticalAlign=middle;fontSize=24;fontStyle=1;fontColor=#ffffff;",
        parent="1",
        vertex="1",
    )
    ET.SubElement(title, "mxGeometry", {"x": "40", "y": "30", "width": "2500", "height": "40", "as": "geometry"})

    subtitle = add_cell(
        root,
        id="diagram-subtitle",
        value="Physical relational schema (left) and conceptual Chen-style ERD with relationship cardinalities (right)",
        style="text;html=1;align=left;verticalAlign=middle;fontSize=12;fontColor=#b6bdc8;",
        parent="1",
        vertex="1",
    )
    ET.SubElement(subtitle, "mxGeometry", {"x": "40", "y": "72", "width": "2500", "height": "30", "as": "geometry"})

    physical_heading = add_cell(
        root,
        id="physical-heading",
        value="PHYSICAL SCHEMA — TABLES, COLUMNS, KEYS AND FOREIGN-KEY LINKS",
        style="text;html=1;align=left;verticalAlign=middle;fontSize=15;fontStyle=1;fontColor=#ffffff;",
        parent="1",
        vertex="1",
    )
    ET.SubElement(physical_heading, "mxGeometry", {"x": "40", "y": "100", "width": "1550", "height": "30", "as": "geometry"})

    conceptual_heading = add_cell(
        root,
        id="conceptual-heading",
        value="CONCEPTUAL ERD — ENTITIES, RELATIONSHIPS AND CARDINALITIES",
        style="text;html=1;align=left;verticalAlign=middle;fontSize=15;fontStyle=1;fontColor=#ffffff;",
        parent="1",
        vertex="1",
    )
    ET.SubElement(conceptual_heading, "mxGeometry", {"x": "2000", "y": "100", "width": "1500", "height": "30", "as": "geometry"})

    divider = add_cell(
        root,
        id="main-divider",
        value="",
        style="shape=line;html=1;strokeColor=#59606b;dashed=1;dashPattern=8 8;",
        parent="1",
        vertex="1",
    )
    ET.SubElement(divider, "mxGeometry", {"x": "1910", "y": "110", "width": "1", "height": "1980", "as": "geometry"})

    section_y = {
        "Identity": 125,
        "Live surveillance": 125,
        "Indexed video evidence": 845,
        "Video Q&A": 1385,
    }
    section_x = {
        "Identity": 40,
        "Live surveillance": 390,
        "Indexed video evidence": 390,
        "Video Q&A": 40,
    }
    for index, section in enumerate(section_y):
        fill, stroke = SECTION_COLORS[section]
        label = add_cell(
            root,
            id=f"section-{index}",
            value=section,
            style=f"rounded=0;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};fontColor=#ffffff;fontStyle=1;fontSize=13;",
            parent="1",
            vertex="1",
        )
        width = "300" if section != "Live surveillance" else "1380"
        ET.SubElement(label, "mxGeometry", {"x": str(section_x[section]), "y": str(section_y[section]), "width": width, "height": "32", "as": "geometry"})

    for name, definition in TABLES.items():
        fill, stroke = SECTION_COLORS[definition["section"]]
        columns = definition["columns"]
        height = 44 + len(columns) * 23
        width = 320 if name not in {"detected_entities", "alerts"} else 350
        cell = add_cell(
            root,
            id=f"table-{name}",
            value=table_html(name, columns, fill),
            style=(
                "rounded=1;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacing=8;"
                f"fillColor=#151719;strokeColor={stroke};strokeWidth=1.5;fontColor=#ffffff;fontFamily=Consolas;"
                "fontSize=10;shadow=0;overflow=fill;"
            ),
            parent="1",
            vertex="1",
        )
        x, y = definition["position"]
        ET.SubElement(
            cell,
            "mxGeometry",
            {"x": str(x), "y": str(y), "width": str(width), "height": str(height), "as": "geometry"},
        )

    for index, (source, target, label, logical) in enumerate(RELATIONSHIPS):
        style = (
            "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;"
            "startArrow=ERone;startFill=0;endArrow=ERmany;endFill=0;strokeWidth=1.5;"
            "fontSize=10;labelBackgroundColor=#ffffff;"
        )
        if logical:
            style += "dashed=1;dashPattern=6 6;strokeColor=#c99bdd;fontColor=#ffffff;"
        else:
            style += "strokeColor=#c7cbd1;fontColor=#ffffff;"
        edge = add_cell(
            root,
            id=f"relationship-{index}",
            value=label,
            style=style,
            parent="1",
            source=f"table-{source}",
            target=f"table-{target}",
            edge="1",
        )
        ET.SubElement(edge, "mxGeometry", {"relative": "1", "as": "geometry"})

    # Conceptual Chen-style view: entities are rectangles and relationships are diamonds.
    for name, (x, y) in CONCEPTUAL_ENTITIES.items():
        section = TABLES[name]["section"]
        _, stroke = SECTION_COLORS[section]
        entity = add_cell(
            root,
            id=f"concept-{name}",
            value=name,
            style=(
                "rounded=0;whiteSpace=wrap;html=1;fillColor=#151719;"
                f"strokeColor={stroke};strokeWidth=1.5;fontColor=#ffffff;fontStyle=1;fontSize=12;"
            ),
            parent="1",
            vertex="1",
        )
        ET.SubElement(entity, "mxGeometry", {"x": str(x), "y": str(y), "width": "190", "height": "68", "as": "geometry"})

    for index, (source, target, relation_name, (x, y), source_card, target_card) in enumerate(CONCEPTUAL_RELATIONSHIPS):
        diamond_id = f"concept-relation-{index}"
        diamond = add_cell(
            root,
            id=diamond_id,
            value=relation_name,
            style="rhombus;whiteSpace=wrap;html=1;fillColor=#151719;strokeColor=#ffffff;fontColor=#ffffff;fontStyle=1;fontSize=10;",
            parent="1",
            vertex="1",
        )
        ET.SubElement(diamond, "mxGeometry", {"x": str(x), "y": str(y), "width": "105", "height": "70", "as": "geometry"})

        for suffix, edge_source, edge_target, cardinality in (
            ("source", f"concept-{source}", diamond_id, source_card),
            ("target", diamond_id, f"concept-{target}", target_card),
        ):
            edge = add_cell(
                root,
                id=f"concept-edge-{index}-{suffix}",
                value=cardinality,
                style=(
                    "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
                    "endArrow=none;startArrow=none;strokeColor=#ffffff;fontColor=#ffffff;"
                    "fontStyle=1;fontSize=10;labelBackgroundColor=#101214;"
                ),
                parent="1",
                source=edge_source,
                target=edge_target,
                edge="1",
            )
            ET.SubElement(edge, "mxGeometry", {"relative": "1", "as": "geometry"})

    legend = add_cell(
        root,
        id="legend",
        value=(
            "<b>Legend</b><br>PK = primary key &nbsp; FK = foreign key &nbsp; UQ = unique constraint"
            "<br>Solid physical links = declared SQLite foreign keys; dashed link = application-level video key."
        ),
        style="rounded=0;whiteSpace=wrap;html=1;align=left;verticalAlign=middle;spacing=10;fillColor=#151719;strokeColor=#ffffff;fontColor=#ffffff;fontSize=11;",
        parent="1",
        vertex="1",
    )
    ET.SubElement(legend, "mxGeometry", {"x": "40", "y": "2050", "width": "1500", "height": "70", "as": "geometry"})

    ET.indent(mxfile, space="  ")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(mxfile)
    tree.write(OUTPUT_PATH, encoding="utf-8", xml_declaration=True)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    try:
        from .generate_readable_erd import generate as generate_readable
    except ImportError:  # Direct execution: python scripts/generate_erd.py
        from generate_readable_erd import generate as generate_readable

    generate_readable()
