import os
from pathlib import Path
import uuid
from dotenv import load_dotenv

# Load .env file (GROQ_API_KEY, CHROMA_DB_PATH, etc.)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path, override=True)

# Force transformers/torch backend and disable TF conflict
os.environ["USE_TF"] = "0"
os.environ["USE_TORCH"] = "1"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware


from app.orchestrator import orchestrator
from app.models.schemas import (
    OrchestratorRequest,
    OrchestratorResponse,
    IngestResponse,
    GraphNeighborsResponse,
    GraphQueryResponse,
    CaptureQuestionsResponse,
    CaptureSubmitRequest,
    CaptureSubmitResponse,
    ActionGenerateRequest,
    ActionGenerateResponse,
    DocumentSummaryRequest,
    DocumentSummaryResponse,
    DocumentCompareResponse,
    DocumentCompareRow,
)

from app.services import ingestion
from app.services import embeddings
from app.services import entity_extraction
from app.services import graph_service
from app.services import lessons_learned_service
from app.services import notification_service
from app.services import capture_templates
from app.services import action_engine
from app.services import document_relationships
from app.services import document_store
from app.services.chroma_client import get_documents_collection
from app.routers import web_mining

app = FastAPI(title="WebRAG – Intelligent Website Mining and Question Answering System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(web_mining.router)



@app.get("/ping")
async def ping():
    return "pong"


@app.post("/query", response_model=OrchestratorResponse)
async def query(request: OrchestratorRequest):
    response = await orchestrator.handle(request)

    # Day 4: graph-enriched response — if the caller told us which
    # equipment this is about, attach what the Knowledge Graph knows
    # about it (linked SOPs, incidents, technicians, etc.) on top of
    # whatever the agent(s) answered.
    if request.equipment_id:
        try:
            response.graph_context = graph_service.graph_context_summary(
                request.equipment_id.upper()
            )
        except Exception as e:
            response.graph_context = ""
            print(f"[/query] graph_context lookup failed: {e}", flush=True)

    return response


@app.post("/ingest", response_model=IngestResponse)
async def ingest(
    file: UploadFile = File(...),
    equipment_id: str = Form(None),
    technician_id: str = Form(None),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF supported for ingestion.")

    file_bytes = await file.read()
    doc_id = str(uuid.uuid4())

    try:
        pages = ingestion.extract_pages(file_bytes)
    except Exception as e:
        raise HTTPException(422, f"Could not parse PDF: {e}")

    full_text = "\n".join(pages)

    # Day 4: full entity extraction (equipment tags + dates + personnel
    # + document type).
    entities = entity_extraction.extract_entities(full_text)
    equipment_tags = entities["equipment_tags"]
    if equipment_id and equipment_id.upper() not in equipment_tags:
        equipment_tags.append(equipment_id.upper())
        equipment_tags.sort()

    doc_type = entities["doc_type"]

    # New: keep the full text + primary reference number + earliest date
    # around for document_relationships.py (supersedes/amends/extends,
    # timeline ordering, conflict detection) — Chroma only holds chunks,
    # not a place to reconstruct "this document's" text on demand.
    primary_ref = equipment_tags[0] if equipment_tags else None
    primary_date = entities["dates"][0] if entities["dates"] else None
    document_store.add_document(
        doc_id=doc_id,
        file_name=file.filename,
        full_text=full_text,
        primary_ref=primary_ref,
        date=primary_date,
    )

    # Fold the uploader's technician_id (Day 5, passed by the Flutter
    # app on every upload) into the same personnel list entity_extraction
    # pulled from the document text, so both end up as graph edges
    # without two separate code paths for "people connected to this doc".
    personnel = list(entities["personnel"])
    if technician_id and technician_id not in personnel:
        personnel.append(technician_id)

    # Day 5: check against historical incidents BEFORE this document's
    # own chunks are added to the corpus, so it never matches itself.
    similar_incidents = []
    if doc_type == "incident":
        similar_incidents = await lessons_learned_service.find_similar_incidents(
            full_text, exclude_doc_id=doc_id, top_k=3,
        )

    # Day 4: full Knowledge Graph — equipment <-> SOPs <-> incidents <->
    # technicians <-> maintenance records, persisted to Firestore (falls
    # back to in-memory if Firebase Admin creds aren't set, so ingestion
    # never breaks the demo — see firebase_admin_client.py).
    graph_edges = graph_service.build_full_graph_edges(
        doc_id=doc_id,
        doc_type=doc_type,
        equipment_tags=equipment_tags,
        personnel=personnel,
    )
    graph_persisted = graph_service.persist_edges(graph_edges)

    collection = get_documents_collection()
    ids, docs, metadatas = [], [], []
    for page_num, page_text in enumerate(pages, start=1):
        for chunk in ingestion.chunk_text(page_text):
            chunk_id = f"{doc_id}_p{page_num}_{uuid.uuid4().hex[:8]}"
            ids.append(chunk_id)
            docs.append(chunk)
            metadatas.append({
                "doc_id": doc_id,
                "equipment_id": equipment_id or "",
                "page": page_num,
                "file_name": file.filename,
                # Day 5: lessons_learned_service filters on this field —
                # must be set on every chunk for incident matching to work.
                "doc_type": doc_type,
            })

    chunk_count = len(ids)
    if ids:
        vectors = await embeddings.embed_batch(docs)
        collection.add(ids=ids, documents=docs, metadatas=metadatas, embeddings=vectors)
        del ids, docs, metadatas, vectors
        import gc
        gc.collect()

    # Day 5: opt-in push alert if this incident matched historical patterns.
    alert_sent = False
    if similar_incidents:
        alert_sent = notification_service.send_lessons_learned_alert(
            equipment_id=equipment_id or "",
            doc_id=doc_id,
            file_name=file.filename,
            match_count=len(similar_incidents),
        )

    return IngestResponse(
        docId=doc_id,
        fileName=file.filename,
        status="ingested" if chunk_count > 0 else "failed",
        pageCount=len(pages),
        chunkCount=chunk_count,

        equipmentTags=equipment_tags,
        graphEdges=graph_edges,
        personnel=entities["personnel"],
        dates=entities["dates"],
        docType=doc_type,
        graphPersistedToFirestore=graph_persisted,
        similarIncidents=similar_incidents,
        alertSent=alert_sent,
    )


@app.get("/documents/graph")
async def documents_graph():
    """New — powers RelationshipTimelineCard on the Flutter side.
    Combines document_relationships.py's three outputs (graph, timeline,
    conflicts) into one payload built from everything ingested so far
    this session (see document_store.py)."""
    docs = document_store.all_documents()
    if not docs:
        return {
            "graph": {"nodes": [], "edges": []},
            "timeline": {"timeline": [], "undated": []},
            "conflicts": [],
        }
    return {
        "graph": document_relationships.build_relationship_graph(docs),
        "timeline": document_relationships.build_timeline(docs),
        "conflicts": document_relationships.detect_conflicts(docs),
    }


@app.get("/documents/list")
async def list_documents():
    """Returns a list of all ingested government documents for selection in summary/compare UIs."""
    docs = document_store.all_documents()
    return [
        {
            "docId": d["doc_id"],
            "fileName": d.get("file_name", "Untitled Document"),
            "primaryRef": d.get("primary_ref"),
            "date": d.get("date"),
        }
        for d in docs
    ]


@app.post("/documents/summarize", response_model=DocumentSummaryResponse)
async def summarize_doc(payload: DocumentSummaryRequest):
    """Generates a concise or detailed summary of an ingested government document."""
    docs_by_id = {d["doc_id"]: d for d in document_store.all_documents()}
    doc = docs_by_id.get(payload.doc_id)

    if not doc:
        collection = get_documents_collection()
        results = collection.get(where={"doc_id": payload.doc_id}, include=["documents", "metadatas"])
        if results and results.get("documents"):
            chunks = results["documents"]
            metas = results.get("metadatas", [{}])
            file_name = metas[0].get("file_name", "Government Document") if metas else "Government Document"
            doc = {
                "doc_id": payload.doc_id,
                "file_name": file_name,
                "full_text": "\n".join(chunks),
            }
        else:
            raise HTTPException(404, f"Document {payload.doc_id} not found in store or vector database.")

    result = await document_relationships.summarize_document(doc, detail_level=payload.detail_level or "short")
    return DocumentSummaryResponse(**result)



@app.get("/documents/compare", response_model=DocumentCompareResponse)
async def documents_compare(doc_a: str, doc_b: str):
    """Compares two ingested Government Resolutions or circulars, highlighting
    added, removed, and modified clauses as well as policy differences."""
    docs_by_id = {d["doc_id"]: d for d in document_store.all_documents()}

    missing = [d for d in (doc_a, doc_b) if d not in docs_by_id]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown doc_id(s): {missing}. Use a doc_id returned by /ingest.",
        )

    a, b = docs_by_id[doc_a], docs_by_id[doc_b]
    entities_a = entity_extraction.extract_entities(a["full_text"])
    entities_b = entity_extraction.extract_entities(b["full_text"])

    base_result = document_relationships.compare_documents(a, b, entities_a, entities_b)
    llm_diff = await document_relationships.compare_documents_llm(a, b)

    return DocumentCompareResponse(
        doc_a=doc_a,
        doc_b=doc_b,
        file_a=a.get("file_name", "Document A"),
        file_b=b.get("file_name", "Document B"),
        rows=[DocumentCompareRow(**r) for r in base_result["rows"]],
        added_clauses=llm_diff["added_clauses"],
        removed_clauses=llm_diff["removed_clauses"],
        modified_clauses=llm_diff["modified_clauses"],
        policy_differences=llm_diff["policy_differences"],
    )




@app.get("/graph/{entity_type}/{entity_id}", response_model=GraphNeighborsResponse)
async def graph_neighbors(entity_type: str, entity_id: str):
    """Day 4 — full graph traversal for any entity type. e.g.
    GET /graph/equipment/PUMP-04 -> every document/person/incident
    linked to Pump 4."""
    return graph_service.get_neighbors(entity_type, entity_id.upper())


@app.get("/graph/{equipment_id}", response_model=GraphQueryResponse)
async def graph_for_equipment(equipment_id: str):
    """Day 5 — flatter equipment-only shape ({connected: [...]})
    consumed by maintenance_agent.py's graph-context enrichment."""
    return graph_service.get_equipment_graph(equipment_id.upper())


# --- Day 5: Knowledge Capture Agent ---

@app.get("/capture/questions", response_model=CaptureQuestionsResponse)
async def capture_questions(equipment_id: str = None):
    """Returns the guided-interview question script for an equipment
    kind (inferred from the tag prefix, e.g. PUMP-04 -> PUMP), or a
    generic script if no equipment_id is given."""
    questions = capture_templates.get_questions_for_equipment(equipment_id)
    return CaptureQuestionsResponse(equipmentId=equipment_id, questions=questions)


@app.post("/capture/submit", response_model=CaptureSubmitResponse)
async def capture_submit(payload: CaptureSubmitRequest):
    """Stores a completed voice/text interview as a knowledge card —
    embedded and indexed immediately, so the Knowledge Agent can
    surface it the same day."""
    answered = [a for a in payload.answers if a.answer.strip()]
    if not answered:
        raise HTTPException(400, "No answers provided.")

    card_id = str(uuid.uuid4())
    structured_summary = "\n\n".join(f"Q: {a.question}\nA: {a.answer}" for a in answered)

    collection = get_documents_collection()
    vector = await embeddings.embed(structured_summary)
    collection.add(
        ids=[f"capture_{card_id}"],
        documents=[structured_summary],
        metadatas=[{
            "doc_id": card_id,
            "equipment_id": payload.equipment_id or "",
            "page": 1,
            "file_name": f"knowledge_capture_{card_id[:8]}",
            "doc_type": "knowledge_capture",
        }],
        embeddings=[vector],
    )

    return CaptureSubmitResponse(cardId=card_id, structuredSummary=structured_summary, stored=True)


# --- Day 6: AI Action Engine ---

@app.post("/actions/generate", response_model=ActionGenerateResponse)
async def generate_action(payload: ActionGenerateRequest):
    """Generates an RCA report, maintenance checklist, inspection
    schedule, or audit report — grounded in whatever's been ingested
    for the given equipment, same retrieval as the Knowledge Agent uses.
    This is the Action Generation step in the Demo Flow: triggered from
    the same context a query was just answered in, not a separate
    disconnected feature."""
    try:
        result = await action_engine.generate_action(
            action_type=payload.action_type,
            query=payload.query or "",
            equipment_id=payload.equipment_id,
            user_role=payload.user_role or "technician",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return ActionGenerateResponse(**result)