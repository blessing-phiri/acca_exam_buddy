# ACCA AA AI Marker

AI-powered marking assistant for ACCA AA (Audit and Assurance) exam answers. The system grades uploaded student responses against official marking schemes and examiner guidance, returning marks, rationale, citations, and improvement feedback.

## 1. Executive Summary

### Product Vision

Deliver consistent, accurate, and explainable grading with target agreement of **90%+** against human markers.

### Target Users

- Primary: ACCA AA students (self-study and exam practice)
- Secondary: Tutors (marking support and consistency checking)
- Tertiary: Tuition providers (batch marking workflows)

### Success Criteria

- > =90% agreement with human markers on total scores
- > 85% per-question mark accuracy
- Feedback includes specific references/citations
- End-to-end processing time <5 minutes per answer
- Pilot operating cost target: <$1 per 100 answers

## 2. Core Features

- **Document upload and processing** for PDF/DOCX answers
- **AI-assisted marking engine** with question-aware rubric evaluation
- **Detailed mark breakdown** at point/sub-point level
- **Feedback and citations** for strengths, gaps, and next improvements
- **Professional marks evaluation** (structure, terminology, practicality)
- **Consistency checker** to flag outlier marks for review
- **Batch marking support** for tutor and provider workflows

## 3. High-Level Architecture

```text
Client Layer
  - Web upload UI
  - Results dashboard
  - Feedback view

API Gateway
  - Authentication
  - Rate limiting
  - Request routing

Core Services
  - Document Service (parse, extract, question detection)
  - Marking Service (classification, rubric retrieval, LLM scoring)
  - Knowledge Service (RAG retrieval, semantic search)
  - Feedback Service (explanations, citations, improvement actions)
  - Consistency Checker (similar-answer variance control)

Data Layer
  - PostgreSQL (metadata, results, operational records)
  - ChromaDB (vectors: schemes, guidance, answer similarity)
  - S3/MinIO (uploaded and source documents)
```

## 4. Project Structure

```text
backend/    FastAPI backend services
frontend/   Streamlit interface
data/       Local data assets and persisted artifacts
tests/      Unit and integration tests
docs/       Product and technical documentation
scripts/    Utility and ops scripts
```

## 5. Technology Stack

- **Frontend**: Streamlit
- **Backend**: FastAPI + SQLAlchemy
- **Document Processing**: PyPDF2, python-docx (Tesseract in Phase 2)
- **Vector Store**: ChromaDB (Qdrant considered for larger scale)
- **Relational DB**: PostgreSQL
- **Primary LLM**: DeepSeek R1
- **Fallback LLM**: MiniMax-M2.5
- **Embedding Models**: `text-embedding-004` (default), optional `text-embedding-3-small`
- **Infra/Hosting**: Render or Railway, S3/MinIO, Prometheus/Grafana

## 6. Marking Pipeline (End-to-End)

1. Upload answer file (PDF/DOCX)
2. Extract and normalize text
3. Detect question structure and classify question type
4. Retrieve marking scheme + examiner guidance using RAG
5. Build strict type-specific marking prompt
6. Evaluate with low-temperature LLM inference
7. Parse and validate JSON result schema
8. Run consistency/outlier check against similar answers
9. Compute confidence score and optional review flag
10. Return total marks, per-point evidence, feedback, and citations

## 7. API Overview

### Document Endpoints

- `POST /api/v1/upload` - upload answer file for processing
- `GET /api/v1/status/{upload_id}` - retrieve processing status/progress
- `GET /api/v1/result/{result_id}` - fetch final marking result + feedback

### Marking Endpoints

- `POST /api/v1/mark` - direct marking endpoint for testing/experiments
- `POST /api/v1/mark/batch` - submit bulk marking jobs

### Knowledge Base Endpoints

- `POST /api/v1/knowledge/ingest` - ingest marking scheme/guidance files
- `GET /api/v1/knowledge/search` - semantic retrieval over knowledge base

## 8. Data Model Overview

Primary entities:

- `Question`
- `StudentAnswer`
- `MarkingRubric`
- `MarkingResult`
- `FeedbackDetail`
- `KnowledgeDocument`
- `DocumentChunk`

Phase 2 user entities:

- `User`
- `UserAnswerHistory`

## 9. Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL (or local dev fallback)
- Optional: Docker Desktop

### Local Setup

```bash
python -m venv venv
.\venv\Scripts\Activate
pip install -r requirements.txt
```

Create `.env` with required secrets and connection values:

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

Run services:

```bash
uvicorn backend.main:app --reload
streamlit run frontend/app.py
```

## 10. Development Roadmap

### Phase 1: MVP (Weeks 1-4)

- Foundation setup (FastAPI, parsing, ChromaDB, upload UI)
- Audit-risk marking path with DeepSeek R1
- Add ethical threats and substantive procedures handlers
- Add feedback formatting, citation output, and tutor pilot deployment

### Phase 2: Validation (Weeks 5-6)

- Tutor benchmark testing
- Borderline/edge-case validation
- Prompt and scoring calibration
- Documentation and handoff hardening

### Phase 3: Expansion (Weeks 7-8)

- User accounts and answer history
- Batch upload UX and provider workflows
- Fine-tuning dataset preparation
- Self-hosted model option (institutional use)

## 11. Testing Strategy

- **Unit tests** for handlers, scoring rules, and validators
- **Integration tests** for full marking pipeline
- **Validation suites** based on examiner-report cases
- **Consistency tests** to detect outlier scoring behavior

Run tests:

```bash
pytest
```

## 12. Risks and Mitigations

- LLM marking drift -> strict prompting, schema validation, fallback model
- Partial-credit inconsistency -> hybrid rule checks + confidence scoring
- Hallucinated feedback -> required citation grounding + review flags
- Cost growth -> usage caps, batching, model routing by difficulty
- Future syllabus updates -> modular knowledge ingestion and rubric versioning

## 13. Cost Targets

- Pilot (500 answers): target around **$2 total** with DeepSeek-centric path
- Production (10,000 answers/month): target around **$100/month** baseline
- Self-hosted option available for higher-volume institutional deployments

## 14. Handoff Snapshot

### Key Decisions

- Start with ACCA AA
- Prioritize audit-risk question type first
- Primary model: DeepSeek R1
- Fallback model: MiniMax-M2.5
- Vector store: ChromaDB
- Frontend: Streamlit
- Backend: FastAPI

### Suggested Next Actions

1. Implement document processor (`backend`)
2. Implement first marking prompt flow (audit risk)
3. Ingest first marking scheme documents
4. Validate on 3-5 sample answers
5. Measure marker agreement and iterate

## 15. License

MIT
