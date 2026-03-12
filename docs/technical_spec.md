# Technical Specification: ACCA AA AI Marker

## Document Control

| Version | Date       | Author        | Changes               |
| ------- | ---------- | ------------- | --------------------- |
| 1.0     | March 2026 | AI Architects | Initial specification |

---

## 1. Executive Summary

### 1.1 Product Vision

An AI-powered marking assistant for ACCA AA (Audit and Assurance) exams that provides consistent, accurate, and explainable grading with 90%+ agreement with human markers. Students upload answers (PDF/Word), the system evaluates against official marking schemes, and returns marks with citations and feedback.

### 1.2 Target Users

- Primary: ACCA AA students (self-study practice)
- Secondary: Tutors (marking assistance, consistency checking)
- Tertiary: Tuition providers (batch marking)

### 1.3 Success Criteria

- 90% agreement with human markers on total scores
- Per-question mark accuracy >85%
- Feedback generation with specific citations
- Processing time <5 minutes per answer
- Cost <$1 per 100 answers (pilot phase)

---

## 2. System Architecture

### 2.1 High-Level Architecture

```text
Client Layer
- Web Upload Interface
- Results Dashboard
- Feedback View

API Gateway
- Auth
- Rate Limit
- Load Balancing

Core Services
- Document Service (PDF/Word parsing, text extraction, question detection, metadata tagging)
- Marking Service (question classifier, rubric loader, LLM evaluation, consistency check)
- Knowledge Service (vector storage, semantic search, RAG retrieval)
- Feedback Service (citation generator, explanation builder, improvement tips)

Data Layer
- PostgreSQL (metadata)
- ChromaDB (vectors)
- S3/MinIO (documents)
```

### 2.2 Technology Stack

| Layer               | Component     | Technology            | Justification                       |
| ------------------- | ------------- | --------------------- | ----------------------------------- |
| Frontend            | Web UI        | Streamlit             | Fast MVP, Python-native             |
| Backend             | API Framework | FastAPI               | Async support, automatic docs       |
| Document Processing | PDF           | PyPDF2                | Free, reliable extraction           |
| Document Processing | Word          | python-docx           | Standard .docx support              |
| Document Processing | OCR backup    | Tesseract             | Scanned documents (Phase 2)         |
| Vector DB           | Primary       | ChromaDB              | Local, free, simple                 |
| Vector DB           | Backup        | Qdrant                | Scaling fallback                    |
| Relational DB       | Metadata      | PostgreSQL            | ACID + JSON support                 |
| ORM                 | Data access   | SQLAlchemy            | Python ecosystem fit                |
| LLM                 | Primary       | DeepSeek R1           | Strong reasoning, cost-effective    |
| LLM                 | Secondary     | MiniMax-M2.5          | Price/performance, self-host option |
| Embeddings          | Primary       | text-embedding-004    | Retrieval-oriented                  |
| Prompting/Tracing   | Framework     | LangChain + LangSmith | Standard prompt + observability     |
| Infra               | Hosting       | Render/Railway        | Fast deployment                     |
| Infra               | Storage       | AWS S3/MinIO          | Scalable file storage               |
| Infra               | Monitoring    | Prometheus/Grafana    | Open-source observability           |

---

## 3. Data Models

### 3.1 Core Entities

```python
class Question:
    id: UUID
    paper_code: str        # e.g., "AA"
    paper_year: str        # e.g., "MJ25"
    question_number: str   # e.g., "1(b)"
    question_text: str
    max_marks: float
    question_type: str     # audit_risk, ethical_threats, substantive_procedures, controls_deficiency

class StudentAnswer:
    id: UUID
    user_id: UUID
    question_id: UUID
    original_filename: str
    file_path: str
    extracted_text: str
    answer_length: int
    status: str            # pending, processing, completed, failed

class MarkingRubric:
    id: UUID
    question_id: UUID
    source_file: str
    mark_breakdown: dict

class MarkingResult:
    id: UUID
    answer_id: UUID
    total_marks: float
    max_marks: float
    percentage_score: float
    question_marks: list
    professional_marks: dict
    feedback: str
    citations: list[str]
    confidence_score: float
    needs_human_review: bool
    llm_model_used: str
    processing_time_ms: int

class FeedbackDetail:
    id: UUID
    result_id: UUID
    category: str          # strength, weakness, improvement
    text: str
    references: list[str]
    priority: int

class KnowledgeDocument:
    id: UUID
    title: str
    document_type: str     # marking_scheme, examiner_report, technical_article, study_note
    file_path: str

class DocumentChunk:
    id: UUID
    document_id: UUID
    text: str
    embedding: list[float]
    chunk_index: int
    metadata: dict
```

### 3.2 User Models (Phase 2)

```python
class User:
    id: UUID
    email: str
    name: str
    role: str              # student, tutor, admin
    subscription_tier: str # free, premium

class UserAnswerHistory:
    id: UUID
    user_id: UUID
    answer_id: UUID
    result_id: UUID
    saved_for_review: bool
    notes: str | None
```

---

## 4. API Specifications

### 4.1 Document Endpoints

```yaml
POST /api/v1/upload:
  description: Upload student answer
  request: [file (PDF/DOCX), paper_code, question_number?]
  response: [upload_id, status, estimated_time]

GET /api/v1/status/{upload_id}:
  response: [status, progress, result_id?]

GET /api/v1/result/{result_id}:
  response: [MarkingResult, FeedbackDetail[]]
```

### 4.2 Marking Endpoints

```yaml
POST /api/v1/mark:
  description: Direct marking for testing
  request: [question_text, student_answer, max_marks, question_type?]
  response: MarkingResult

POST /api/v1/mark/batch:
  description: Batch marking
  request: [answers[], callback_url?]
  response: [batch_id, status_url]
```

### 4.3 Knowledge Base Endpoints

```yaml
POST /api/v1/knowledge/ingest:
  description: Ingest marking scheme/examiner report
  request: [file, document_type, metadata]
  response: [document_id, chunks_created]

GET /api/v1/knowledge/search:
  query: q, type
  response: List[DocumentChunk + relevance score]
```

---

## 5. Core Service Specifications

### 5.1 Document Processing Service

- Accept PDF/DOCX
- Extract text (PyPDF2 / python-docx)
- Clean/normalize text
- Detect questions using patterns (e.g., "Requirement (a)-4 marks", "Question 1")
- Return processed document object

### 5.2 Marking Service Logic

1. Classify question type
2. Retrieve relevant marking rules (RAG)
3. Retrieve examiner guidance
4. Build type-specific prompt
5. Call LLM (`temperature=0` for consistency)
6. Parse/validate JSON response
7. Apply consistency check on similar answers
8. Compute confidence score
9. Flag low-confidence answers for review

### 5.3 Question-Type Specific Handlers

- `AuditRiskHandler`
  - Validate scenario-specific risk identification
  - Validate assertion + financial impact explanations
  - Validate practical and specific audit responses

- `EthicalThreatsHandler`
  - Detect threat type: self-interest, self-review, advocacy, familiarity, intimidation
  - Validate safeguards as concrete action statements

### 5.4 Consistency Checker

- Similarity threshold: 0.85
- Find similar answers for same question
- Compare score distribution
- Flag outliers (e.g., z-score > 2.0)
- Reduce confidence and set `needs_human_review=True`

---

## 6. LLM Integration Specifications

### 6.1 Primary LLM: DeepSeek R1

- Model: `deepseek-reasoner`
- JSON response mode required for structured marking outputs
- Default controls: `temperature=0.0`, bounded token budget

### 6.2 Fallback LLM: MiniMax-M2.5

- Used for resilience, pricing optimization, and optional self-host path

### 6.3 Self-Hosted Option

- Local/vended serving via Ollama or vLLM endpoint

### 6.4 Embedding Provider

- Default: `text-embedding-004` (dimension 768)
- Optional: `text-embedding-3-small` (dimension 1536)
- Support single and batch embedding

---

## 7. Knowledge Base Implementation

### 7.1 Vector DB Schema (ChromaDB)

- Collections:
  - `marking_schemes`
  - `examiner_guidance`
  - `student_answers` (consistency comparison)
- Cosine similarity index
- Metadata filters by question type/year/paper

### 7.2 Ingestion Pipeline

1. Process source document
2. Chunk by question/requirement
3. Attach metadata per chunk
4. Generate embeddings
5. Persist chunks + vectors

---

## 8. Testing Strategy

### 8.1 Unit Tests

- Half-mark logic for incomplete explanations
- Ethical threat type detection
- Safeguard specificity checks

### 8.2 Integration Tests

- Full async marking pipeline
- Result schema validation
- Confidence and citation output assertions

### 8.3 Validation Cases

- Generic vs tailored risks
- Half-mark vs full-mark explanations
- Generic vs specific auditor responses
- Threat identification with explicit type
- Objective wording vs action-based safeguards
- Terminology correctness (e.g., "unmodified" vs legacy terms)

---

## 9. Deployment Configuration

### 9.1 Docker Compose (Development)

- Services:
  - `api` (FastAPI)
  - `frontend` (Streamlit)
  - `db` (PostgreSQL)
  - `chroma` (ChromaDB)
  - `minio` (object storage)

### 9.2 Environment Variables

```bash
DEEPSEEK_API_KEY=sk-xxx
MINIMAX_API_KEY=mmsk-xxx
MINIMAX_GROUP_ID=123456
DATABASE_URL=postgresql://postgres:password@localhost:5432/accamarker
CHROMA_DB_PATH=./chroma_db
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
LOG_LEVEL=INFO
ENVIRONMENT=development
```

### 9.3 Production Deployment

- Render blueprint with separate API/frontend services
- Managed PostgreSQL
- Persistent volume path for vector storage (or managed vector DB)

---

## 10. Development Roadmap

### Phase 1: MVP (Weeks 1-4)

- Foundation setup
- Audit risk flow
- Add additional question handlers
- Tutor-facing pilot quality loop

### Phase 2: Validation (Weeks 5-6)

- Tutor benchmark marking
- Edge-case confidence calibration
- Prompt tuning and documentation completion

### Phase 3: Expansion (Weeks 7-8)

- User accounts
- Answer history and review
- Batch upload for providers
- Fine-tuning dataset prep
- Self-hosting option evaluation

---

## 11. Risk Register

| Risk                    | Probability | Impact | Mitigation                             |
| ----------------------- | ----------- | ------ | -------------------------------------- |
| LLM accuracy <90%       | Medium      | High   | Fallback model + iterative calibration |
| Partial-credit errors   | Medium      | High   | Rule-based checks + structured prompts |
| Cost overrun            | Low         | Medium | Usage caps + routing strategies        |
| Data residency concerns | Low/High    | Medium | Self-hosted deployment option          |
| API rate limits         | Low         | Medium | Queueing + batch processing            |
| Hallucinations          | Medium      | Medium | Citation grounding + review flags      |
| Competitor entry        | Medium      | Low    | ACCA specialization focus              |
| Syllabus changes        | Low         | Medium | Modular knowledge updates              |

---

## 12. Cost Analysis

### Pilot (500 answers)

- LLM API (DeepSeek): ~$2.00
- Embeddings: ~$0 (free tier assumptions)
- Vector DB: $0 local
- Hosting/storage: minimal local/free-tier

### Production (10,000 answers/month)

- Estimated baseline: ~$100/month across LLM, embeddings, vector DB, hosting, storage

### Self-Hosted Option

- Approximate range: $1,200-$2,500/month depending on hardware and provider

---

## 13. Handoff Checklist

### Current Status

- Phase 1 completed
- Phase 2 in progress
- Blockers identified
- Next steps defined

### Key Decisions Made

- Start with AA
- Target 90% human-level agreement
- Primary LLM: DeepSeek R1
- Fallback: MiniMax-M2.5
- Vector DB: ChromaDB
- Frontend: Streamlit
- Backend: FastAPI

### Pending Decisions

- Self-host vs API in production
- Authentication approach
- Pricing model
- Data retention policy

### Next Actions

1. Set up repository and project scaffolding
2. Implement document processor
3. Implement audit risk prompt flow
4. Validate against sample answers
5. Iterate based on agreement metrics

### Critical Files

- `docs/technical_spec.md`
- `sample_answers/`
- `marking_schemes/`
- `prompts/audit_risk_prompt.txt`
- `src/document_processor.py`
- `src/marking_service.py`

---

## 14. Quick Reference: Key Decisions

| Decision            | Choice           | Rationale                          |
| ------------------- | ---------------- | ---------------------------------- |
| First paper         | AA               | Easier initial scope               |
| First question type | Audit risk       | Most complex proof point           |
| Primary LLM         | DeepSeek R1      | Reasoning + cost                   |
| Fallback LLM        | MiniMax-M2.5     | Price/performance + self-host path |
| Vector DB           | ChromaDB         | Free + local simplicity            |
| Frontend            | Streamlit        | Fast MVP                           |
| Backend             | FastAPI          | Async + auto-docs                  |
| Hosting             | Render           | Easy deployment                    |
| Early testing       | 3 sample answers | Fast validation loop               |
| Success criterion   | 90% agreement    | Human marker parity target         |

---

## 15. Next Chat Starter

```text
Continuing from previous chat. We are building an ACCA AA AI marker.

Current status: [e.g., "Completed Phase 1, starting Phase 2"]

Key decisions made:
- DeepSeek R1 as primary LLM
- Audit risk questions first
- ChromaDB for vector storage
- Streamlit frontend

We are at: [describe current state]

Next task: [describe immediate task]

Reference docs/technical_spec.md for full details.
```
