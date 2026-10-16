"""Generate a readable, multi-page Draw.io ERD for SQLite schema version 4."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from .generate_erd import RELATIONSHIPS, SECTION_COLORS, TABLES
except ImportError:  # Direct execution: python scripts/generate_readable_erd.py
    from generate_erd import RELATIONSHIPS, SECTION_COLORS, TABLES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "docs" / "AI_Surveillance_System_ERD.drawio"
BACKGROUND = "#101214"
PANEL = "#17191c"
TEXT = "#ffffff"
MUTED = "#aeb6c2"
LINE = "#d7dce2"

INDEXES_BY_TABLE = {
    "face_embeddings": ["idx_face_embeddings_person(person_id)"],
    "surveillance_sessions": ["idx_sessions_camera_started(camera_id, started_at DESC)"],
    "detection_logs": [
        "idx_detection_logs_session_time(session_id, detected_at DESC)",
        "idx_detection_logs_camera_time(camera_id, detected_at DESC)",
    ],
    "alerts": [
        "idx_alerts_created(created_at DESC)",
        "idx_alerts_camera_created(camera_id, created_at DESC)",
        "idx_alerts_unread(is_read, created_at DESC)",
    ],
    "zones": ["idx_zones_camera(camera_id, is_active)"],
    "video_frames": [
        "idx_video_frames_cam_time(camera_id, timestamp_seconds)",
        "idx_video_frames_session(session_or_video_id)",
    ],
    "detected_entities": [
        "idx_detected_entities_frame(frame_id)",
        "idx_detected_entities_attrs(clothing_top_color, label, action_label)",
    ],
    "danger_threats": ["idx_danger_threats_type(threat_type, created_at DESC)"],
    "qa_messages": ["idx_qa_messages_conv(conversation_id, created_at)"],
    "qa_uploaded_videos": ["idx_qa_uploaded_videos_conv(conversation_id)"],
}

COMPLETE_RELATIONSHIPS = [
    ("people", "face_embeddings", "owns", "(0,N)", "(1,1)", False),
    ("cameras", "zones", "defines", "(0,N)", "(1,1)", False),
    ("cameras", "surveillance_sessions", "runs", "(0,N)", "(1,1)", False),
    ("surveillance_sessions", "detection_logs", "records", "(0,N)", "(1,1)", False),
    ("cameras", "detection_logs", "captures", "(0,N)", "(1,1)", False),
    ("people", "detection_logs", "recognized in", "(0,N)", "(0,1)", False),
    ("surveillance_sessions", "alerts", "raises", "(0,N)", "(1,1)", False),
    ("cameras", "alerts", "reports", "(0,N)", "(1,1)", False),
    ("detection_logs", "alerts", "triggers", "(0,N)", "(0,1)", False),
    ("people", "alerts", "identified in", "(0,N)", "(0,1)", False),
    ("cameras", "video_frames", "sources", "(0,N)", "(0,1)", False),
    ("video_frames", "detected_entities", "contains", "(0,N)", "(1,1)", False),
    ("people", "detected_entities", "matches", "(0,N)", "(0,1)", False),
    ("video_frames", "danger_threats", "reveals", "(0,N)", "(1,1)", False),
    ("qa_conversations", "qa_uploaded_videos", "uploads", "(0,N)", "(1,1)", False),
    ("qa_conversations", "qa_messages", "contains", "(0,N)", "(1,1)", False),
    ("qa_messages", "qa_evidences", "cites", "(0,N)", "(1,1)", False),
    ("video_frames", "qa_evidences", "referenced by", "(0,N)", "(0,1)", False),
    ("qa_uploaded_videos", "video_frames", "indexes", "(0,N)", "(0,1)", True),
]


def cell(xml_parent: ET.Element, **attributes: str) -> ET.Element:
    return ET.SubElement(xml_parent, "mxCell", attributes)


def geometry(node: ET.Element, x: int, y: int, width: int, height: int, *, relative: bool = False) -> None:
    values = {
        "x": str(x),
        "y": str(y),
        "width": str(width),
        "height": str(height),
        "as": "geometry",
    }
    if relative:
        values = {"relative": "1", "as": "geometry"}
    ET.SubElement(node, "mxGeometry", values)


def create_page(mxfile: ET.Element, name: str, page_id: str, width: int, height: int) -> ET.Element:
    diagram = ET.SubElement(mxfile, "diagram", {"name": name, "id": page_id})
    model = ET.SubElement(
        diagram,
        "mxGraphModel",
        {
            "dx": str(width),
            "dy": str(height),
            "grid": "1",
            "gridSize": "20",
            "guides": "1",
            "tooltips": "1",
            "connect": "1",
            "arrows": "1",
            "fold": "1",
            "page": "1",
            "pageScale": "1",
            "pageWidth": str(width),
            "pageHeight": str(height),
            "background": BACKGROUND,
            "math": "0",
            "shadow": "0",
        },
    )
    root = ET.SubElement(model, "root")
    cell(root, id="0")
    cell(root, id="1", parent="0")

    backdrop = cell(
        root,
        id=f"{page_id}-background",
        value="",
        style=f"rounded=0;fillColor={BACKGROUND};strokeColor={BACKGROUND};movable=0;resizable=0;editable=0;selectable=0;",
        parent="1",
        vertex="1",
    )
    geometry(backdrop, 0, 0, width, height)
    return root


def add_heading(root: ET.Element, page_id: str, title: str, subtitle: str, width: int) -> None:
    heading = cell(
        root,
        id=f"{page_id}-title",
        value=title,
        style=f"text;html=1;align=left;verticalAlign=middle;fontSize=24;fontStyle=1;fontColor={TEXT};",
        parent="1",
        vertex="1",
    )
    geometry(heading, 40, 30, width - 80, 40)

    subheading = cell(
        root,
        id=f"{page_id}-subtitle",
        value=subtitle,
        style=f"text;html=1;align=left;verticalAlign=middle;fontSize=13;fontColor={MUTED};",
        parent="1",
        vertex="1",
    )
    geometry(subheading, 40, 75, width - 80, 30)


def table_html(name: str) -> str:
    definition = TABLES[name]
    header, _ = SECTION_COLORS[definition["section"]]
    rows = []
    for key, column, data_type, note in definition["columns"]:
        key_text = f'<b style="color:#ff9b92">{key}</b>' if key else ""
        type_text = f'<span style="color:#9ec5ff">{data_type}</span>' if data_type else ""
        note_text = f'<span style="color:#b8bec8"> — {note}</span>' if note else ""
        rows.append(
            '<tr style="border-bottom:1px solid #444a52">'
            f'<td style="width:34px;padding:4px 6px;border-right:1px solid #59606a">{key_text}</td>'
            f'<td style="padding:4px 7px"><b>{column}</b> {type_text}{note_text}</td>'
            "</tr>"
        )
    return (
        f'<div style="font-size:16px;text-align:center;font-weight:bold;background:{header};padding:9px;'
        f'margin:-7px -7px 0 -7px;border-bottom:1px solid #eeeeee">{name}</div>'
        '<table style="width:100%;border-collapse:collapse;color:#ffffff;font-size:11px">'
        + "".join(rows)
        + "</table>"
    )


def add_table(root: ET.Element, page_id: str, name: str, x: int, y: int, width: int = 370) -> None:
    _, stroke = SECTION_COLORS[TABLES[name]["section"]]
    line_capacity = max(42, (width - 75) // 7)
    row_heights = []
    for key, column, data_type, note in TABLES[name]["columns"]:
        content_length = len(key) + len(column) + len(data_type) + len(note) + 5
        lines = max(1, (content_length + line_capacity - 1) // line_capacity)
        row_heights.append(max(27, 11 + lines * 17))
    height = 52 + sum(row_heights)
    table = cell(
        root,
        id=f"{page_id}-table-{name}",
        value=table_html(name),
        style=(
            f"rounded=0;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacing=7;fillColor={PANEL};"
            f"strokeColor={stroke};strokeWidth=2;fontColor={TEXT};fontFamily=Consolas;fontSize=11;overflow=fill;"
        ),
        parent="1",
        vertex="1",
    )
    geometry(table, x, y, width, height)


def add_physical_edges(root: ET.Element, page_id: str, names: set[str], *, include_logical: bool = False) -> None:
    for index, (source, target, cardinality, logical) in enumerate(RELATIONSHIPS):
        if source not in names or target not in names or (logical and not include_logical):
            continue
        edge_style = (
            "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
            f"startArrow=ERone;startFill=0;endArrow=ERmany;endFill=0;strokeWidth=2;strokeColor={LINE};"
            f"fontColor={TEXT};fontStyle=1;fontSize=11;labelBackgroundColor={BACKGROUND};"
        )
        if logical:
            edge_style += "dashed=1;dashPattern=8 8;strokeColor=#c99bdd;"
        edge = cell(
            root,
            id=f"{page_id}-fk-{index}",
            value=cardinality,
            style=edge_style,
            parent="1",
            source=f"{page_id}-table-{source}",
            target=f"{page_id}-table-{target}",
            edge="1",
        )
        geometry(edge, 0, 0, 0, 0, relative=True)


def add_routed_edge(
    root: ET.Element,
    page_id: str,
    source: str,
    target: str,
    points: list[tuple[int, int]],
    *,
    exit_x: float,
    exit_y: float,
    entry_x: float,
    entry_y: float,
    logical: bool = False,
    source_optional: bool = False,
) -> None:
    """Add a label-free FK connector through explicit, table-free corridors."""
    source_marker = "ERzeroToOne" if source_optional else "ERone"
    style = (
        "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
        f"exitX={exit_x};exitY={exit_y};exitDx=0;exitDy=0;exitPerimeter=1;"
        f"entryX={entry_x};entryY={entry_y};entryDx=0;entryDy=0;entryPerimeter=1;"
        f"startArrow={source_marker};startFill=0;endArrow=ERzeroToMany;endFill=0;strokeWidth=2;strokeColor={LINE};"
    )
    if logical:
        style += "dashed=1;dashPattern=8 8;strokeColor=#c99bdd;"
    edge = cell(
        root,
        id=f"{page_id}-route-{source}-{target}",
        value="",
        style=style,
        parent="1",
        source=f"{page_id}-table-{source}",
        target=f"{page_id}-table-{target}",
        edge="1",
    )
    edge_geometry = ET.SubElement(edge, "mxGeometry", {"relative": "1", "as": "geometry"})
    point_array = ET.SubElement(edge_geometry, "Array", {"as": "points"})
    for x, y in points:
        ET.SubElement(point_array, "mxPoint", {"x": str(x), "y": str(y)})


def add_legend(root: ET.Element, page_id: str, y: int, width: int, table_names: set[str]) -> None:
    indexes = [index for name in sorted(table_names) for index in INDEXES_BY_TABLE.get(name, [])]
    index_text = "; ".join(indexes) if indexes else "none"
    legend = cell(
        root,
        id=f"{page_id}-legend",
        value=(
            "<b>Legend:</b> PK = primary key &nbsp;&nbsp; FK = foreign key &nbsp;&nbsp; UQ = unique constraint"
            " &nbsp;&nbsp; | = exactly one &nbsp;&nbsp; o| = zero or one &nbsp;&nbsp; o&lt; = zero or many"
            "<br><b>Line types:</b> solid = declared SQLite foreign key; dashed purple = logical application key only"
            f"<br><b>Indexes:</b> {index_text}"
        ),
        style=f"rounded=0;whiteSpace=wrap;html=1;align=left;verticalAlign=middle;spacing=10;fillColor={PANEL};strokeColor=#69717d;fontColor={TEXT};fontSize=12;",
        parent="1",
        vertex="1",
    )
    geometry(legend, 40, y, width - 80, 105)


def add_concept_entity(root: ET.Element, name: str, x: int, y: int) -> None:
    _, stroke = SECTION_COLORS[TABLES[name]["section"]]
    entity = cell(
        root,
        id=f"overview-entity-{name}",
        value=name,
        style=f"rounded=0;whiteSpace=wrap;html=1;fillColor={PANEL};strokeColor={stroke};strokeWidth=2;fontColor={TEXT};fontStyle=1;fontSize=13;",
        parent="1",
        vertex="1",
    )
    geometry(entity, x, y, 180, 64)


def add_concept_relation(
    root: ET.Element,
    index: int,
    source: str,
    target: str,
    name: str,
    x: int,
    y: int,
    source_cardinality: str = "(1,1)",
    target_cardinality: str = "(0,N)",
    *,
    dashed: bool = False,
) -> None:
    relation_id = f"overview-relation-{index}"
    relation = cell(
        root,
        id=relation_id,
        value=name,
        style=f"rhombus;whiteSpace=wrap;html=1;fillColor={PANEL};strokeColor={TEXT};strokeWidth=1.5;fontColor={TEXT};fontStyle=1;fontSize=11;",
        parent="1",
        vertex="1",
    )
    geometry(relation, x, y, 105, 72)

    for suffix, edge_source, edge_target, label in (
        ("source", f"overview-entity-{source}", relation_id, source_cardinality),
        ("target", relation_id, f"overview-entity-{target}", target_cardinality),
    ):
        edge_style = (
            "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
            f"endArrow=none;startArrow=none;strokeColor={TEXT};strokeWidth=1.5;fontColor={TEXT};"
            f"fontStyle=1;fontSize=11;labelBackgroundColor={BACKGROUND};"
        )
        if dashed:
            edge_style += "dashed=1;dashPattern=8 8;strokeColor=#c99bdd;"
        edge = cell(
            root,
            id=f"overview-edge-{index}-{suffix}",
            value=label,
            style=edge_style,
            parent="1",
            source=edge_source,
            target=edge_target,
            edge="1",
        )
        geometry(edge, 0, 0, 0, 0, relative=True)


def build_overview(mxfile: ET.Element) -> None:
    width, height = 1800, 1120
    root = create_page(mxfile, "1 - Conceptual Overview", "overview", width, height)
    add_heading(
        root,
        "overview",
        "AI Surveillance System — Conceptual ERD",
        "Primary business flows with correct min/max cardinalities. Page 2 lists every relationship; pages 3–6 show every column, constraint and foreign key.",
        width,
    )

    positions = {
        "people": (40, 170),
        "face_embeddings": (430, 170),
        "cameras": (40, 380),
        "surveillance_sessions": (430, 380),
        "detection_logs": (820, 380),
        "alerts": (1210, 380),
        "zones": (430, 540),
        "video_frames": (430, 720),
        "detected_entities": (820, 640),
        "danger_threats": (820, 800),
        "qa_conversations": (40, 930),
        "qa_uploaded_videos": (430, 900),
        "qa_messages": (820, 960),
        "qa_evidences": (1210, 960),
    }
    for name, (x, y) in positions.items():
        add_concept_entity(root, name, x, y)

    relations = [
        ("people", "face_embeddings", "owns", 275, 166, "(0,N)", "(1,1)", False),
        ("cameras", "surveillance_sessions", "runs", 275, 376, "(0,N)", "(1,1)", False),
        ("surveillance_sessions", "detection_logs", "records", 665, 376, "(0,N)", "(1,1)", False),
        ("detection_logs", "alerts", "triggers", 1055, 376, "(0,N)", "(0,1)", False),
        ("cameras", "zones", "defines", 275, 520, "(0,N)", "(1,1)", False),
        ("video_frames", "detected_entities", "contains", 665, 640, "(0,N)", "(1,1)", False),
        ("video_frames", "danger_threats", "reveals", 665, 800, "(0,N)", "(1,1)", False),
        ("qa_conversations", "qa_uploaded_videos", "uploads", 275, 906, "(0,N)", "(1,1)", False),
        ("qa_conversations", "qa_messages", "contains", 665, 1000, "(0,N)", "(1,1)", False),
        ("qa_messages", "qa_evidences", "cites", 1055, 956, "(0,N)", "(1,1)", False),
    ]
    for index, relationship in enumerate(relations):
        source, target, name, x, y, source_card, target_card, dashed = relationship
        add_concept_relation(root, index, source, target, name, x, y, source_card, target_card, dashed=dashed)


def build_relationship_catalog(mxfile: ET.Element) -> None:
    """Draw every declared and logical relationship as a separate, overlap-free mini diagram."""
    width, height = 2700, 1650
    page_id = "relationships"
    root = create_page(mxfile, "2 - Complete Relationship Map", page_id, width, height)
    add_heading(
        root,
        page_id,
        "Complete Relationship Map — All 18 Foreign Keys + 1 Logical Link",
        "Cardinality beside an entity states how many instances of that entity may participate. Dashed purple is not enforced by SQLite.",
        width,
    )

    column_x = (70, 1390)
    row_step = 142
    for index, (source, target, relation_name, source_card, target_card, logical) in enumerate(COMPLETE_RELATIONSHIPS):
        column = 0 if index < 10 else 1
        row = index if index < 10 else index - 10
        x = column_x[column]
        y = 145 + row * row_step
        source_id = f"{page_id}-{index}-source"
        target_id = f"{page_id}-{index}-target"
        relation_id = f"{page_id}-{index}-relation"
        for entity_id, entity_name, entity_x in (
            (source_id, source, x),
            (target_id, target, x + 780),
        ):
            _, stroke = SECTION_COLORS[TABLES[entity_name]["section"]]
            entity = cell(
                root,
                id=entity_id,
                value=entity_name,
                style=f"rounded=0;whiteSpace=wrap;html=1;fillColor={PANEL};strokeColor={stroke};strokeWidth=2;fontColor={TEXT};fontStyle=1;fontSize=13;",
                parent="1",
                vertex="1",
            )
            geometry(entity, entity_x, y, 310, 64)
        diamond = cell(
            root,
            id=relation_id,
            value=relation_name,
            style=(
                f"rhombus;whiteSpace=wrap;html=1;fillColor={PANEL};strokeColor={'#c99bdd' if logical else LINE};"
                f"strokeWidth=2;fontColor={TEXT};fontStyle=1;fontSize=12;"
            ),
            parent="1",
            vertex="1",
        )
        geometry(diamond, x + 485, y - 4, 120, 72)
        for suffix, edge_source, edge_target, label in (
            ("source", source_id, relation_id, source_card),
            ("target", relation_id, target_id, target_card),
        ):
            style = (
                "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=none;startArrow=none;"
                f"strokeColor={LINE};strokeWidth=1.5;fontColor={TEXT};fontStyle=1;fontSize=12;labelBackgroundColor={BACKGROUND};"
            )
            if logical:
                style += "dashed=1;dashPattern=8 8;strokeColor=#c99bdd;"
            edge = cell(
                root,
                id=f"{page_id}-{index}-{suffix}",
                value=label,
                style=style,
                parent="1",
                source=edge_source,
                target=edge_target,
                edge="1",
            )
            geometry(edge, 0, 0, 0, 0, relative=True)


def build_identity_page(mxfile: ET.Element) -> None:
    width, height = 2200, 1450
    page_id = "identity"
    root = create_page(mxfile, "3 - Identity & Camera Configuration", page_id, width, height)
    add_heading(root, page_id, "Identity & Camera Configuration — Physical Schema", "Registered faces, face embeddings, configured cameras and restricted zones.", width)
    layout = {
        "people": (100, 200),
        "face_embeddings": (100, 620),
        "cameras": (1250, 200),
        "zones": (1250, 700),
    }
    for name, (x, y) in layout.items():
        add_table(root, page_id, name, x, y, width=620)
    add_routed_edge(root, page_id, "people", "face_embeddings", [], exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=0)
    add_routed_edge(root, page_id, "cameras", "zones", [], exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=0)
    add_legend(root, page_id, 1310, width, set(layout))


def build_live_page(mxfile: ET.Element) -> None:
    width, height = 3200, 1850
    page_id = "live"
    root = create_page(mxfile, "4 - Live Monitoring & Alerts", page_id, width, height)
    add_heading(root, page_id, "Live Monitoring & Alerts — Physical Schema", "Persistent sessions, meaningful detection logs and security alerts. Connectors use dedicated outer corridors.", width)
    layout = {
        "people": (100, 220),
        "cameras": (760, 220),
        "surveillance_sessions": (1450, 220),
        "detection_logs": (1450, 900),
        "alerts": (2520, 550),
    }
    for name, (x, y) in layout.items():
        add_table(root, page_id, name, x, y, width=560)

    add_routed_edge(root, page_id, "cameras", "surveillance_sessions", [], exit_x=1, exit_y=0.35, entry_x=0, entry_y=0.35)
    add_routed_edge(root, page_id, "surveillance_sessions", "detection_logs", [], exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=0)
    add_routed_edge(
        root, page_id, "detection_logs", "alerts", [],
        exit_x=1, exit_y=0.55, entry_x=0, entry_y=0.75, source_optional=True,
    )
    add_routed_edge(
        root, page_id, "cameras", "detection_logs", [(1370, 520), (1370, 1040)],
        exit_x=1, exit_y=0.75, entry_x=0, entry_y=0.35,
    )
    add_routed_edge(
        root, page_id, "surveillance_sessions", "alerts", [(2250, 360), (2250, 680)],
        exit_x=1, exit_y=0.35, entry_x=0, entry_y=0.25,
    )
    add_routed_edge(
        root, page_id, "cameras", "alerts", [(1040, 150), (2800, 150)],
        exit_x=0.5, exit_y=0, entry_x=0.5, entry_y=0,
    )
    add_routed_edge(
        root, page_id, "people", "detection_logs", [(380, 1660), (1730, 1660)],
        exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=1,
        source_optional=True,
    )
    add_routed_edge(
        root, page_id, "people", "alerts", [(210, 120), (2800, 120), (2800, 550)],
        exit_x=0.25, exit_y=0, entry_x=0.75, entry_y=0,
        source_optional=True,
    )
    add_legend(root, page_id, 1710, width, set(layout))


def build_evidence_page(mxfile: ET.Element) -> None:
    width, height = 3050, 1600
    page_id = "evidence"
    root = create_page(mxfile, "5 - Indexed Video Evidence", page_id, width, height)
    add_heading(root, page_id, "Indexed Video Evidence — Physical Schema", "Frames, recognized entities, visual attributes and detected security threats.", width)
    layout = {
        "people": (100, 180),
        "cameras": (100, 760),
        "video_frames": (820, 430),
        "detected_entities": (1590, 180),
        "danger_threats": (2350, 800),
    }
    for name, (x, y) in layout.items():
        add_table(root, page_id, name, x, y, width=600)
    add_routed_edge(
        root, page_id, "people", "detected_entities", [(400, 130), (1890, 130)],
        exit_x=0.5, exit_y=0, entry_x=0.5, entry_y=0,
        source_optional=True,
    )
    add_routed_edge(
        root, page_id, "cameras", "video_frames", [],
        exit_x=1, exit_y=0.45, entry_x=0, entry_y=0.72, source_optional=True,
    )
    add_routed_edge(root, page_id, "video_frames", "detected_entities", [], exit_x=1, exit_y=0.35, entry_x=0, entry_y=0.65)
    add_routed_edge(
        root, page_id, "video_frames", "danger_threats", [(1120, 1370), (2650, 1370)],
        exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=1,
    )
    add_legend(root, page_id, 1450, width, set(layout))


def build_qa_page(mxfile: ET.Element) -> None:
    width, height = 3150, 1800
    page_id = "qa"
    root = create_page(mxfile, "6 - Video Q&A", page_id, width, height)
    add_heading(root, page_id, "Video Q&A — Physical Schema", "Conversations, uploaded videos, indexed frames, messages and timestamped evidence.", width)
    layout = {
        "qa_conversations": (100, 300),
        "qa_uploaded_videos": (760, 180),
        "video_frames": (1700, 180),
        "qa_messages": (760, 1050),
        "qa_evidences": (1700, 1050),
    }
    for name, (x, y) in layout.items():
        add_table(root, page_id, name, x, y, width=650)
    add_routed_edge(root, page_id, "qa_conversations", "qa_uploaded_videos", [], exit_x=1, exit_y=0.35, entry_x=0, entry_y=0.25)
    add_routed_edge(
        root, page_id, "qa_conversations", "qa_messages", [(425, 950), (1085, 950)],
        exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=0,
    )
    add_routed_edge(
        root, page_id, "qa_uploaded_videos", "video_frames", [],
        exit_x=1, exit_y=0.45, entry_x=0, entry_y=0.45, logical=True, source_optional=True,
    )
    add_routed_edge(root, page_id, "qa_messages", "qa_evidences", [], exit_x=1, exit_y=0.5, entry_x=0, entry_y=0.5)
    add_routed_edge(
        root, page_id, "video_frames", "qa_evidences", [],
        exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=0, source_optional=True,
    )
    add_legend(root, page_id, 1650, width, set(layout))


def generate() -> None:
    mxfile = ET.Element(
        "mxfile",
        {
            "host": "app.diagrams.net",
            "agent": "AI Surveillance System readable ERD generator",
            "version": "27.0.5",
            "pages": "6",
        },
    )
    build_overview(mxfile)
    build_relationship_catalog(mxfile)
    build_identity_page(mxfile)
    build_live_page(mxfile)
    build_evidence_page(mxfile)
    build_qa_page(mxfile)
    ET.indent(mxfile, space="  ")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(mxfile).write(OUTPUT_PATH, encoding="utf-8", xml_declaration=True)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    generate()
