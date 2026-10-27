# 🌐 WebRAG: Intelligent Website Mining and Question Answering System

> **A Complete Web Data Mining & Retrieval-Augmented Generation (RAG) Platform**  
> *"Autonomous Web Crawling → Data Extraction → Preprocessing → Mining Analytics → Visualizations → Grounded RAG Q&A"*

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI_0.115+-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![ChromaDB](https://img.shields.io/badge/Vector_Store-ChromaDB_1.5+-FF6F00)](https://www.trychroma.com)
[![Embeddings](https://img.shields.io/badge/Embeddings-SentenceTransformers_MiniLM-blue)](https://www.sbert.net)
[![LLM](https://img.shields.io/badge/LLM-Groq_Llama_3.3_70B-f50057)](https://groq.com)
[![Flutter](https://img.shields.io/badge/Frontend-Flutter_3.x-02569B?logo=flutter)](https://flutter.dev)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://python.org)

---

## 📌 1. Project Overview

**WebRAG** is an end-to-end Web Data Mining and Question Answering system that allows users to supply any publicly accessible website URL, autonomously crawl permitted pages, extract and preprocess clean textual content, construct semantic vector representations in ChromaDB, and interact with the crawled knowledge through a conversational AI grounded strictly in verifiable webpage citations.

The platform bridges the gap between raw web unstructured data and reliable knowledge retrieval by combining:
1. **Ethical & Secure Web Crawling** (robots.txt compliance, rate limiting, and strict SSRF prevention).
2. **Robust Web Preprocessing** (Unicode normalization, boilerplate removal, content hashing, and sentence-boundary sliding chunking).
3. **Statistical Web Data Mining** (Term Frequency mining, content distribution profiling, and retrieval latency analytics).
4. **Visual Analytics** (Dynamic Matplotlib charts rendered directly from crawled data).
5. **Grounded RAG Engine** (Multi-tenant ChromaDB partition by `website_id`, cosine similarity search, and Groq Llama 3.3 70B synthesis with strict zero-hallucination guardrails).

---

## 🏗️ 2. System Architecture

```
                             ┌─────────────────────────────────┐
                             │    Public Website (Target)      │
                             └────────────────┬────────────────┘
                                              │  HTTP / HTTPS
                                              ▼
                             ┌─────────────────────────────────┐
                             │       Secure Web Crawler        │
                             │  • SSRF Validation (IP Filter)  │
                             │  • robots.txt Compliance Parser │
                             │  • Politeness Delay & BFS Queue │
                             └────────────────┬────────────────┘
                                              │  Raw HTML Documents
                                              ▼
                             ┌─────────────────────────────────┐
                             │   Preprocessing & Data Mining   │
                             │  • BeautifulSoup Tag Cleaning   │
                             │  • Unicode NFKC Normalization   │
                             │  • SHA-256 Deduplication Hash   │
                             │  • 500-800 Token Chunk Window   │
                             └────────┬───────────────┬────────┘
                                      │               │
            ┌─────────────────────────┘               └────────────────────────┐
            ▼                                                                  ▼
┌───────────────────────────────┐                              ┌───────────────────────────────┐
│     Dense Vector Indexing     │                              │   Mining Analytics Engine     │
│ • Local SentenceTransformers  │                              │ • Term Frequency Analysis     │
│   (multi-qa-MiniLM-L6-cos-v1) │                              │ • Page Content Distribution   │
│ • ChromaDB HNSW (Cosine)      │                              │ • Query Latency Logs          │
│ • Metadata Filter (website_id)│                              │ • Dynamic Matplotlib Charts   │
└───────────────┬───────────────┘                              └───────────────┬───────────────┘
                │                                                              │
                │ Vector Embeddings                                            │ Base64 Charts & Stats
                ▼                                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                              FastAPI Asynchronous Gateway                                    │
│  /api/web/crawl  •  /api/web/status  •  /api/web/chat  •  /api/web/stats  •  /api/web/pages  │
└───────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                                │
                                                ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                               Flutter Modern WebRAG Client                                   │
│  [Web Mining Home]  •  [Website Dashboard]  •  [Grounded Chat]  •  [Visual Analytics]        │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ 3. Web Mining Pipeline

### Step 1: Web Crawling (`app/services/web_crawler.py`)
- **URL Validation & SSRF Guard:** Inspects protocol (`http`/`https`) and resolves target domain to IP addresses, strictly blocking loopback (`127.0.0.0/8`, `::1`), private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and cloud metadata IP endpoints (`169.254.169.254`).
- **Robots.txt Adherence:** Automatically queries `robots.txt` using `urllib.robotparser.RobotFileParser` and honors exclusion directives.
- **Domain Scoping & Breadth-First Traversal:** Restricts outbound link extraction to the approved root host, enforcing configurable `max_pages` (default: 30) and `max_depth` (default: 2).
- **Polite Crawling:** Applies configurable rate delays (0.25s–0.5s) to avoid server load.

### Step 2: Preprocessing & Data Extraction (`app/services/web_preprocessing.py`)
- **Boilerplate Elimination:** Strips `<nav>`, `<footer>`, `<header>`, `<aside>`, `<script>`, `<style>`, `<form>`, `<svg>`, and advertisement containers.
- **Structural Extraction:** Isolates page title, `<meta description>`, hierarchical headings (`h1`–`h3`), canonical URLs, and primary body text.
- **Normalization:** Executes Unicode NFKC normalization and trims whitespace.
- **Content Hashing:** Calculates SHA-256 digest on normalized strings to eliminate duplicate pages.
- **Sliding Window Chunking:** Splits text into 500–800 character windows with sentence-boundary preservation and 150-character overlaps.

### Step 3: Embeddings & Vector Storage (`app/services/web_retrieval.py`)
- **Embedding Model:** Local bi-encoder `sentence-transformers/multi-qa-MiniLM-L6-cos-v1` (384-dimensional dense vectors) pre-cached for zero network dependency.
- **ChromaDB Storage:** Persistent collection `web_documents` utilizing HNSW with cosine distance metric.
- **Website Isolation:** Chunks are indexed with `website_id`, ensuring queries on one domain never bleed into another.

### Step 4: Web Mining Analytics (`app/services/web_analytics.py`)
- **Token Frequency Mining:** Word tokenization with stopword filtering to isolate domain-specific keywords.
- **Content Distribution:** Word count histograms across crawled depths and pages.
- **Matplotlib Visualization:** Generates server-side high-resolution PNG charts encoded in base64 data URLs for immediate dashboard rendering.

### Step 5: Grounded RAG Q&A (`app/services/web_retrieval.py`)
- **Top-$k$ Semantic Search:** Cosine similarity nearest-neighbor lookup matching the user's question.
- **Groq LLM Generation:** Grounded synthesis using `llama-3.3-70b-versatile` under strict negative constraints.
- **Fallback Guarantee:** When facts are absent from the crawled site, responds with:
  > *"The requested information was not found in the indexed website content."*
- **Source Citations:** Every claim links to verifiable citation cards with full URL, page title, and matched excerpt.

---

## 💻 4. Technology Stack

| Layer | Technologies |
|---|---|
| **Backend API** | Python 3.12, FastAPI, Uvicorn, Pydantic v2 |
| **Crawling & Scraping** | Requests, BeautifulSoup4 (bs4), `urllib.robotparser` |
| **Vector Database** | ChromaDB (Persistent HNSW index, Cosine distance) |
| **Embeddings** | `sentence-transformers` (`multi-qa-MiniLM-L6-cos-v1`, PyTorch CPU) |
| **LLM Inference** | Groq API (`llama-3.3-70b-versatile`, temperature 0.2) |
| **Data Visualization** | Matplotlib (Agg headless backend) |
| **Frontend Client** | Flutter 3.x, Dart 3.12, Google Fonts, Material 3 Design |
| **Testing & Eval** | Pytest, TestClient, Custom Evaluation Benchmark |

---

## 🚀 5. Installation & Setup Instructions

### Prerequisites
- Python 3.10+ (tested on Python 3.12.4)
- Flutter SDK 3.22+ (tested on Flutter 3.44.6)
- Groq API Key (free tier available at [console.groq.com](https://console.groq.com))

---

### Step 1: Backend Setup

```bash
# Navigate to backend directory
cd atlasai_backend

# Create virtual environment (optional but recommended)
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
# Create a .env file inside atlasai_backend/:
GROQ_API_KEY=your_groq_api_key_here
CHROMA_DB_PATH=./chroma_db
USE_TF=0
USE_TORCH=1
```

### Step 2: Start the FastAPI Server

```bash
# From atlasai_backend directory:
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- Swagger UI will be available at: [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs)
- Health check: [`http://127.0.0.1:8000/ping`](http://127.0.0.1:8000/ping)

---

### Step 3: Frontend Setup

```bash
# Navigate to Flutter app directory
cd ../atlasai_app

# Fetch Flutter dependencies
flutter pub get

# Run on Chrome Web:
flutter run -d chrome

# Or run as a Windows Desktop application:
flutter run -d windows
```

---

## 🧪 6. Verification & Automated Testing

The backend includes a comprehensive unit and integration test suite covering URL validation, SSRF defense, robots.txt, HTML parsing, ChromaDB indexing, isolated retrieval, and FastAPI routes:

```bash
cd atlasai_backend
python tests/test_web_mining.py
```

### Test Suite Execution Output:
```
[RUNNING TEST SUITE DIRECTLY]
PASS: test_is_safe_url_blocks_localhost_and_private_ips
PASS: test_is_safe_url_allows_public_urls
PASS: test_normalize_url
PASS: test_robots_txt_disallow
PASS: test_html_data_extraction_and_boilerplate_stripping
PASS: test_web_preprocessing_and_deduplication
PASS: test_chunk_web_content_overlap
PASS: test_chromadb_website_indexing_and_isolation
PASS: test_unsupported_query_fallback
PASS: test_api_crawl_rejects_ssrf
PASS: test_api_crawl_and_status
PASS: test_api_stats
ALL 12 TESTS PASSED SUCCESSFULLY!
```

---

## 📊 7. Quantitative Evaluation Benchmark

The system features an automated, reproducible evaluation module located at `atlasai_backend/evaluation/evaluate_webrag.py`. It indexes a standardized evaluation benchmark corpus and measures standard Information Retrieval (IR) metrics against known ground truth questions:

```bash
cd atlasai_backend
python evaluation/evaluate_webrag.py
```

### Benchmark Results (from `evaluation_report.json`):

| Metric | Result | Target Benchmark | Analysis |
|---|---|---|---|
| **Mean Reciprocal Rank (MRR)** | **1.000** | $\ge 0.80$ | The relevant document was ranked #1 for 100% of queries. |
| **Precision @ 1** | **1.000** | $\ge 0.85$ | Top retrieved passage was relevant for every evaluation query. |
| **Precision @ 3** | **0.333** | Scaled | Reflects focused top-1 retrieval with padding for context. |
| **Precision @ 5** | **0.200** | Scaled | Correctly bounds precision when 1 gold document exists. |
| **Recall @ 1** | **1.000** | $\ge 0.80$ | Complete recall of gold documents within the first position. |
| **Recall @ 3** | **1.000** | $\ge 0.90$ | 100% gold document recovery in top-3 candidates. |
| **Recall @ 5** | **1.000** | $\ge 0.95$ | 100% gold document recovery in top-5 candidates. |
| **Avg Retrieval Latency** | **372.49 ms** | $\le 800$ ms | CPU-bound embedding + HNSW search completed in under 400ms. |
| **Answer Correctness** | **0.386** | Lexical overlap | Measured via strict non-hallucinatory keyword overlap. |

---

## ⚖️ 8. Ethical & Security Considerations

1. **SSRF Prevention:** All user-supplied URLs undergo multi-layer inspection before network resolution. Private subnets (RFC 1918), loopback interfaces, broadcast ranges, and cloud metadata services (`169.254.169.254`) are systematically rejected.
2. **Robots.txt Respect:** The crawler parses `robots.txt` at the domain root before requesting sub-paths and halts traversal if disallowed.
3. **Politeness & Rate Limiting:** A delay of 0.25s–0.5s is enforced between successive requests to prevent server denial of service.
4. **No CAPTCHA Bypassing:** The crawler never attempts to circumvent anti-bot protections, CAPTCHA mechanisms, or authentication gates.
5. **Multi-Tenant Vector Isolation:** ChromaDB queries enforce a strict `where={"website_id": website_id}` predicate, ensuring no cross-site information leakage.

---

## 📑 9. Suggested Outline for Academic Project Report (8–10 Pages)

For academic submission (Mini-Project on Web Data Mining), the following report structure is recommended:

- **1. Introduction (1 Page)**
  - Background: Information overload on the modern web.
  - Problem Statement: Traditional search engines return documents; users need grounded, synthesis-driven answers.
  - Objectives: Building an end-to-end Web Data Mining and RAG pipeline.
- **2. Literature Review & Theoretical Background (1.5 Pages)**
  - Web Data Mining Taxonomy: Content Mining vs. Structure Mining vs. Usage Mining.
  - Evolution of Retrieval-Augmented Generation (Dense Bi-encoders vs. BM25 Sparse Search).
  - Cosine Distance & Hierarchical Navigable Small World (HNSW) Graphs.
- **3. System Architecture & Methodology (2.5 Pages)**
  - Crawler Design: Politeness, BFS traversal, and SSRF security defense.
  - Preprocessing & Mining: Unicode normalization, HTML stripping, hashing deduplication, sliding window chunking.
  - Vector Representation: SentenceTransformers bi-encoder model and embedding space analysis.
  - Tenant Isolation: Isolated metadata partitioning in ChromaDB.
  - Grounded Synthesis: LLM prompt engineering with negative constraint prompting.
- **4. Web Data Mining & Analytics (1 Page)**
  - Word frequency mining and TF distribution.
  - Page-level content profiling and visual generation with Matplotlib.
- **5. Experimental Evaluation & Results (1.5 Pages)**
  - Experimental Setup: Dataset, query suite, test environments.
  - Metric Definitions: Precision@k, Recall@k, Mean Reciprocal Rank (MRR), Latency.
  - Quantitative Findings and Performance Tables.
  - Error Analysis & Boundary Conditions.
- **6. User Interface & Implementation Details (1 Page)**
  - Flutter Material 3 Responsive Architecture.
  - Interactive Citation Chips & Snippet Inspector.
- **7. Ethical Considerations, Security & Limitations (0.5 Pages)**
  - Fair use, robots.txt, rate limiting, and private network protection.
- **8. Conclusion & Future Work (0.5 Pages)**
  - Summary of achievements and future extensions (multimodal web mining, cross-lingual knowledge graphs).
- **References**

---

## 🏛️ 10. Preserved Legacy Functionality

In accordance with project requirements, existing **AskHTE** capabilities remain fully operational:
- Government PDF Ingestion (`/ingest`) with Tesseract OCR.
- Administrative Decision Support (`/query`).
- Cross-Circular Summarization and Side-by-Side Clause Comparison (`/documents/summarize`, `/documents/compare`).
- Administrative Knowledge Graph (`/documents/graph`).
- Trilingual English / Marathi / Hindi query handling.
- Accessible directly via the **Gov Docs** tab in the Flutter application!
