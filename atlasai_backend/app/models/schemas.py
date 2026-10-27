from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class OrchestratorRequest(BaseModel):
    query: str
    user_role: Optional[str] = "technician"   # technician | engineer | manager | auditor
    equipment_id: Optional[str] = None
    doc_ids: Optional[List[str]] = None
    agents: Optional[List[str]] = None        # force specific agents; None = auto-route
    target_language: Optional[str] = None     # English | Marathi | Hindi (None = auto-detect)


class PageCitation(BaseModel):
    fileName: str
    page: Optional[int] = None


class AgentResult(BaseModel):
    agent: str
    answer: str
    confidence: float
    sources: List[str] = []
    # New: structured (fileName, page) pairs alongside `sources` strings
    # — powers the Flutter CitationChips widget's clickable chips.
    citations: List[PageCitation] = []
    reasoning: str = ""
    detected_language: Optional[str] = "English"
    administrative_recommendations: List[str] = []
    suggested_circulars: List[str] = []


class OrchestratorResponse(BaseModel):
    query: str
    results: List[AgentResult]
    merged_answer: str
    overall_confidence: float
    detected_language: Optional[str] = "English"
    administrative_recommendations: List[str] = []
    suggested_circulars: List[str] = []
    # Day 4: filled in when request.equipment_id resolves to graph
    # neighbors — e.g. "Linked: 2 documents, 3 person/people." Empty
    # string if there's no equipment_id or no edges yet.
    graph_context: str = ""
    # New: document_relationships.py output for whatever's been
    # ingested this session, passed through so a Cross-Reference answer
    # can be paired with RelationshipTimelineCard on the same screen
    # without a second round-trip to /documents/graph.
    relationships: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    # New: document_relationships.build_timeline()'s dated, ordered
    # chain — separate from `relationships` (the raw graph edges)
    # because RelationshipTimelineCard on the Flutter side needs dates
    # attached to each entry, which only build_timeline() computes.
    timeline: List[Dict[str, Any]] = []


# --- Document Summarization & Detailed Comparison Schemas ---

class DocumentSummaryRequest(BaseModel):
    doc_id: str
    detail_level: Optional[str] = "short"  # short | detailed


class DocumentSummaryResponse(BaseModel):
    docId: str
    fileName: str
    summaryType: str
    summary: str
    keyPoints: List[str] = []
    effectiveDate: Optional[str] = None
    applicability: Optional[str] = None
    authority: Optional[str] = None


class DocumentCompareRow(BaseModel):
    field: str
    doc_a: Optional[Any] = None
    doc_b: Optional[Any] = None
    differs: bool = False


class DocumentCompareResponse(BaseModel):
    doc_a: str
    doc_b: str
    file_a: Optional[str] = None
    file_b: Optional[str] = None
    rows: List[DocumentCompareRow] = []
    added_clauses: List[str] = []
    removed_clauses: List[str] = []
    modified_clauses: List[str] = []
    policy_differences: List[str] = []



class GraphEdgeOut(BaseModel):
    edgeId: str
    fromType: str
    fromId: str
    toType: str
    toId: str
    relation: str


class SimilarIncidentOut(BaseModel):
    docId: str
    fileName: Optional[str] = None
    equipmentId: Optional[str] = None
    similarity: float
    snippet: str


class IngestResponse(BaseModel):
    docId: str
    fileName: str
    status: str
    pageCount: int
    chunkCount: int
    equipmentTags: List[str]
    graphEdges: List[GraphEdgeOut]
    # Day 4:
    personnel: List[str] = []
    dates: List[str] = []
    docType: str = "general_document"
    graphPersistedToFirestore: bool = False
    # Day 5:
    similarIncidents: List[SimilarIncidentOut] = []
    alertSent: bool = False


class GraphNeighborsResponse(BaseModel):
    """Day 4 shape — used by GET /graph/{entity_type}/{entity_id}."""
    entityType: str
    entityId: str
    edgeCount: int
    neighbors: Dict[str, List[str]]
    edges: List[Dict[str, Any]]


class GraphQueryResponse(BaseModel):
    """Day 5 shape — used by GET /graph/{equipment_id}. Kept alongside
    GraphNeighborsResponse rather than replacing it: the Day 5 Flutter
    screens/maintenance_agent.py expect this flatter {connected: [...]}
    form specifically."""
    equipmentId: str
    connected: List[Dict[str, Any]]
    graphEnabled: bool


# --- Day 5: Knowledge Capture Agent ---

class CaptureQuestionsResponse(BaseModel):
    equipmentId: Optional[str] = None
    questions: List[str]


class CaptureAnswer(BaseModel):
    question: str
    answer: str


class CaptureSubmitRequest(BaseModel):
    equipment_id: Optional[str] = None
    technician_id: Optional[str] = None
    answers: List[CaptureAnswer]


class CaptureSubmitResponse(BaseModel):
    cardId: str
    structuredSummary: str
    stored: bool


# --- Day 6: AI Action Engine ---

class ActionGenerateRequest(BaseModel):
    action_type: str   # rca_report | maintenance_checklist | inspection_schedule | preventive_maintenance | audit_report
    query: Optional[str] = None
    equipment_id: Optional[str] = None
    user_role: Optional[str] = "technician"


class ActionGenerateResponse(BaseModel):
    actionType: str
    title: str
    content: str
    sources: List[str] = []
    confidence: float


# =========================================================================
# WebRAG — Intelligent Website Mining & Question Answering System Schemas
# =========================================================================

class WebCrawlRequest(BaseModel):
    url: str
    max_pages: Optional[int] = 30
    max_depth: Optional[int] = 2


class WebCrawlResponse(BaseModel):
    jobId: str
    websiteId: str
    status: str
    message: str


class WebJobStatusResponse(BaseModel):
    jobId: str
    websiteId: str
    startUrl: str
    status: str
    progress: int
    crawledCount: int
    maxPages: int
    currentUrl: Optional[str] = None
    currentTitle: Optional[str] = None
    error: Optional[str] = None


class WebPageItem(BaseModel):
    url: str
    title: str
    wordCount: int
    chunkCount: int
    language: str
    timestamp: str


class WebCitationItem(BaseModel):
    index: int
    url: str
    title: str
    snippet: str
    distance: Optional[float] = None


class WebChatRequest(BaseModel):
    website_id: str
    query: str
    top_k: Optional[int] = 5


class WebChatResponse(BaseModel):
    websiteId: str
    query: str
    answer: str
    confidence: float
    citations: List[WebCitationItem]
    retrievalLatencyMs: float
    totalLatencyMs: float
    reasoning: str


class WebsiteSummaryItem(BaseModel):
    websiteId: str
    domain: str
    startUrl: str
    totalPages: int
    totalChunks: int
    totalWords: int
    createdAt: str
    status: str


class WebWordFrequencyItem(BaseModel):
    word: str
    count: int


class WebContentDistributionItem(BaseModel):
    url: str
    title: str
    word_count: int
    chunk_count: int


class WebStatsResponse(BaseModel):
    websiteId: str
    totalWebsites: int
    totalPages: int
    totalWords: int
    totalChunks: int
    averageWordsPerPage: float
    topWords: List[WebWordFrequencyItem]
    contentDistribution: List[WebContentDistributionItem]
    averageRetrievalLatencyMs: float
    averageConfidence: float
    totalQueriesLogged: int
    wordFrequencyChartBase64: Optional[str] = ""
    contentDistributionChartBase64: Optional[str] = ""