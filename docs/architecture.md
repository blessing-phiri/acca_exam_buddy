# Architecture Diagrams: ACCA AA AI Marker

This document contains 12 improved architecture diagrams for the platform.

## 1) System Context (C4)

```mermaid
C4Context
  title System Context Diagram for ACCA AA AI Marker

  Person(student, "ACCA Student", "Uploads answers and views marks/feedback")
  Person(tutor, "ACCA Tutor", "Validates markings and reviews flagged cases")

  System(aiMarker, "ACCA AA AI Marker", "Automatically marks ACCA AA exam answers with explainable feedback")

  System_Ext(llmAPI, "LLM Provider", "DeepSeek R1 / MiniMax API")
  System_Ext(embeddingAPI, "Embedding Service", "text-embedding-004 API")
  System_Ext(emailService, "Email Service", "SendGrid for notifications")

  Rel(student, aiMarker, "Uploads answers, views results", "HTTPS")
  Rel(tutor, aiMarker, "Reviews markings, validates", "HTTPS")

  Rel(aiMarker, llmAPI, "Sends marking prompts", "HTTPS/REST")
  Rel(aiMarker, embeddingAPI, "Generates embeddings for RAG", "HTTPS/REST")
  Rel(aiMarker, emailService, "Sends notifications", "HTTPS/API")

  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## 2) Container Diagram (C4)

```mermaid
C4Container
  title Container Diagram for ACCA AA AI Marker

  Person(student, "Student", "ACCA student")
  Person(tutor, "Tutor", "ACCA tutor/validator")

  System_Boundary(platform, "ACCA AI Marker Platform") {
    Container(webUI, "Web Application", "Streamlit", "Upload interface and result display")
    Container(api, "API Gateway", "FastAPI", "HTTP endpoints, orchestration, auth, status")

    Container(documentProc, "Document Processor", "Python Service", "Extracts and normalizes text from PDF/DOCX")
    Container(markingEngine, "Marking Engine", "Python Service", "Core marking logic and result assembly")
    Container(knowledgeBase, "Knowledge Base Service", "Python Service", "RAG retrieval of schemes and guidance")
    Container(consistencyChecker, "Consistency Checker", "Python Service", "Outlier detection across similar answers")
    Container(feedbackGen, "Feedback Generator", "Python Service", "Actionable feedback and citations")

    ContainerDb(metadataDB, "Metadata Database", "PostgreSQL", "Users, answers, marks, history")
    ContainerDb(vectorDB, "Vector Database", "ChromaDB", "Embeddings and semantic retrieval")
    ContainerDb(fileStorage, "File Storage", "MinIO/S3", "Uploaded files and source documents")
    Container(queue, "Task Queue", "Redis/Celery", "Background processing and retries")
  }

  System_Ext(llmAPI, "LLM Provider", "DeepSeek R1 / MiniMax")
  System_Ext(embeddingAPI, "Embedding Provider", "text-embedding-004")

  Rel(student, webUI, "Uses", "HTTPS")
  Rel(tutor, webUI, "Uses", "HTTPS")
  Rel(webUI, api, "Calls", "HTTPS/REST")

  Rel(api, queue, "Queues extraction/marking jobs", "Async")
  Rel(queue, documentProc, "Runs extraction jobs", "Async")
  Rel(queue, markingEngine, "Runs marking jobs", "Async")

  Rel(documentProc, fileStorage, "Stores/retrieves files", "S3 API")
  Rel(documentProc, metadataDB, "Stores extracted text and job status", "SQL")

  Rel(markingEngine, knowledgeBase, "Retrieves marking rules", "Internal API")
  Rel(markingEngine, consistencyChecker, "Checks score consistency", "Internal API")
  Rel(markingEngine, feedbackGen, "Builds feedback", "Internal API")
  Rel(markingEngine, llmAPI, "Scores answers", "HTTPS/REST")

  Rel(knowledgeBase, vectorDB, "Queries vectors", "Chroma API")
  Rel(knowledgeBase, embeddingAPI, "Generates embeddings", "HTTPS/REST")

  Rel(consistencyChecker, metadataDB, "Reads historical marks", "SQL")
  Rel(feedbackGen, metadataDB, "Stores feedback", "SQL")
  Rel(api, metadataDB, "Reads/writes request state", "SQL")

  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## 3) Marking Engine Components (C4)

```mermaid
C4Component
  title Component Diagram for Marking Engine Container

  Container_Boundary(markingEngine, "Marking Engine") {
    Component(classifier, "Question Classifier", "Python", "Determines question type")
    Component(rubricLoader, "Rubric Loader", "Python", "Loads rules and marking points")
    Component(promptBuilder, "Prompt Builder", "Python", "Builds type-specific prompts")
    Component(llmClient, "LLM Client", "Python", "Calls DeepSeek/MiniMax APIs")
    Component(parser, "Response Parser", "Python", "Parses JSON output")
    Component(validator, "Mark Validator", "Python", "Applies rule checks and bounds")
    Component(confidenceCalc, "Confidence Calculator", "Python", "Computes confidence and review flags")

    Component(auditRiskHandler, "Audit Risk Handler", "Python", "Risk identification, explanation, response logic")
    Component(ethicalHandler, "Ethical Threats Handler", "Python", "Threat type and safeguard logic")
    Component(proceduresHandler, "Substantive Procedures Handler", "Python", "Procedure specificity logic")
    Component(controlsHandler, "Controls Deficiency Handler", "Python", "Control issue and recommendation logic")
  }

  Container_Boundary(external, "External Services") {
    Component(kbService, "Knowledge Base Service", "Python", "Retrieves rules and examiner guidance")
    Component(consistencyService, "Consistency Checker", "Python", "Compares with similar historical answers")
    Component(feedbackService, "Feedback Generator", "Python", "Creates citations and tips")
  }

  Rel(classifier, auditRiskHandler, "Delegates when type is audit_risk")
  Rel(classifier, ethicalHandler, "Delegates when type is ethical_threats")
  Rel(classifier, proceduresHandler, "Delegates when type is substantive_procedures")
  Rel(classifier, controlsHandler, "Delegates when type is controls_deficiency")

  Rel(classifier, rubricLoader, "Provides question type")
  Rel(auditRiskHandler, promptBuilder, "Requests specialized prompt")
  Rel(ethicalHandler, promptBuilder, "Requests specialized prompt")
  Rel(proceduresHandler, promptBuilder, "Requests specialized prompt")
  Rel(controlsHandler, promptBuilder, "Requests specialized prompt")

  Rel(promptBuilder, rubricLoader, "Gets marking rules")
  Rel(promptBuilder, kbService, "Gets examiner guidance")
  Rel(promptBuilder, llmClient, "Sends composed prompt")

  Rel(llmClient, parser, "Returns raw model response")
  Rel(parser, validator, "Sends parsed marks")
  Rel(validator, consistencyService, "Requests consistency score")
  Rel(validator, feedbackService, "Requests feedback draft")
  Rel(validator, confidenceCalc, "Sends validated result")
  Rel(confidenceCalc, consistencyService, "Reads consistency impact")
```

## 4) Sequence Diagram (Upload to Result)

```mermaid
sequenceDiagram
    actor Student
    participant WebUI as Streamlit UI
    participant API as FastAPI
    participant Queue as Task Queue
    participant DocProc as Document Processor
    participant Storage as File Storage
    participant Marking as Marking Engine
    participant KB as Knowledge Base
    participant VectorDB as ChromaDB
    participant Embedding as Embedding API
    participant LLM as DeepSeek API
    participant DB as PostgreSQL

    Student->>WebUI: Upload PDF/DOCX
    WebUI->>API: POST /api/v1/upload
    API->>Queue: Enqueue extraction job
    API-->>WebUI: Return upload_id

    Queue->>DocProc: Start extraction job
    DocProc->>Storage: Save source file
    DocProc->>DocProc: Extract and clean text
    DocProc->>DocProc: Detect question boundaries
    DocProc->>DB: Save extracted text + status
    DocProc->>Queue: Enqueue marking job

    Queue->>Marking: Start marking job
    Marking->>DB: Load answer + question metadata
    Marking->>Marking: Classify question type

    Marking->>KB: Retrieve rules and guidance
    KB->>Embedding: Generate query embedding
    Embedding-->>KB: Embedding vector
    KB->>VectorDB: Query relevant chunks
    VectorDB-->>KB: Top matching chunks
    KB-->>Marking: Rules + guidance

    Marking->>LLM: Send structured marking prompt
    LLM-->>Marking: Return JSON marks
    Marking->>Marking: Parse and validate scores
    Marking->>DB: Compare with similar results
    DB-->>Marking: Similar result stats
    Marking->>Marking: Compute confidence
    Marking->>DB: Store final result

    Student->>WebUI: Check progress
    WebUI->>API: GET /api/v1/status/{upload_id}
    API->>DB: Read job status
    DB-->>API: Status + progress
    API-->>WebUI: Progress response

    Student->>WebUI: Open result
    WebUI->>API: GET /api/v1/result/{result_id}
    API->>DB: Load result payload
    DB-->>API: Marks + feedback + citations
    API-->>WebUI: Render result
```

## 5) Data Flow Diagram

```mermaid
flowchart TD
    subgraph Input[Input Layer]
        A1[Student Upload PDF/DOCX]
        A2[Tutor Upload Marking Schemes]
    end

    subgraph Processing[Processing Layer]
        B1[Document Extractor]
        B2[Text Cleaner]
        B3[Question Detector]
        B4[Chunking Engine]
    end

    subgraph Storage[Storage Layer]
        C1[(Raw Files: MinIO/S3)]
        C2[(Extracted Text: PostgreSQL)]
        C3[(Vector Embeddings: ChromaDB)]
        C4[(Marking Results: PostgreSQL)]
    end

    subgraph Knowledge[Knowledge Layer]
        D1[Marking Scheme Index]
        D2[Examiner Guidance Index]
        D3[Technical References Index]
    end

    subgraph Marking[Marking Layer]
        E1[Question Classifier]
        E2[Prompt Builder]
        E3[LLM Orchestrator]
        E4[Response Parser]
        E5[Mark Validator]
    end

    subgraph Output[Output Layer]
        F1[Score Display]
        F2[Question Breakdown]
        F3[Feedback with Citations]
        F4[Report Export]
    end

    subgraph External[External Services]
        G1[DeepSeek or MiniMax API]
        G2[Embedding API]
    end

    A1 --> B1
    A2 --> B1
    B1 --> C1
    B1 --> B2
    B2 --> B3
    B3 --> B4
    B4 --> C2
    B4 --> D1
    B4 --> D2
    B4 --> D3

    D1 --> C3
    D2 --> C3
    D3 --> C3
    C3 <--> G2

    C2 --> E1
    C3 --> E2
    E1 --> E2
    E2 --> E3
    E3 --> G1
    G1 --> E4
    E4 --> E5
    E5 --> C4

    C4 --> F1
    C4 --> F2
    C4 --> F3
    C4 --> F4
```

## 6) Deployment Diagram (Runtime Topology)

```mermaid
flowchart TB
    User[User Browser]

    subgraph RenderCloud[Render Cloud]
        FE[Frontend Service: Streamlit]
        API[Backend Service: FastAPI]
        Worker[Worker Service: Celery]
        Redis[(Redis Queue)]
        PG[(Managed PostgreSQL)]
    end

    subgraph DataPlane[Data Plane]
        Minio[(MinIO or S3)]
        Chroma[(ChromaDB)]
    end

    subgraph ExternalAPIs[External APIs]
        DeepSeek[DeepSeek or MiniMax]
        EmbedAPI[Embedding API]
    end

    User -->|HTTPS| FE
    FE -->|HTTPS/REST| API
    API -->|Enqueue jobs| Redis
    Redis --> Worker

    API -->|SQL| PG
    Worker -->|SQL| PG
    API -->|S3 API| Minio
    Worker -->|Chroma API| Chroma

    Worker -->|HTTPS| DeepSeek
    Worker -->|HTTPS| EmbedAPI
```

## 7) Component Interaction Diagram

```mermaid
graph TD
    UI[Streamlit UI]
    API[FastAPI Gateway]
    Doc[Document Processor]
    Queue[(Redis/Celery Queue)]
    Worker[Marking Worker]
    KB[Knowledge Base Service]
    Chroma[(ChromaDB)]
    PG[(PostgreSQL)]
    Minio[(MinIO/S3)]
    LLMClient[LLM Client]
    Deep[DeepSeek API]
    Embed[Embedding API]

    UI -->|HTTPS| API
    API -->|HTTP/REST| Doc
    API -->|Async enqueue| Queue
    Queue -->|Async consume| Worker

    Doc -->|S3 API| Minio
    Doc -->|SQL| PG

    Worker -->|Internal API| KB
    KB -->|HTTPS| Embed
    KB -->|Chroma API| Chroma

    Worker -->|SQL| PG
    Worker -->|HTTP| LLMClient
    LLMClient -->|HTTPS| Deep
```

## 8) Processing State Machine

```mermaid
stateDiagram-v2
    [*] --> UPLOADED: Student uploads file
    UPLOADED --> QUEUED: Added to processing queue
    QUEUED --> EXTRACTING: Worker starts extraction

    EXTRACTING --> EXTRACTED: Parsing succeeded
    EXTRACTING --> EXTRACTION_FAILED: Parsing error

    EXTRACTED --> CLEANING
    CLEANING --> CLEANED

    CLEANED --> DETECTING_QUESTIONS
    DETECTING_QUESTIONS --> QUESTIONS_DETECTED

    QUESTIONS_DETECTED --> MARKING_QUEUED
    MARKING_QUEUED --> RETRIEVING_RULES

    RETRIEVING_RULES --> RULES_RETRIEVED
    RETRIEVING_RULES --> RULES_MISSING

    RULES_RETRIEVED --> CALLING_LLM
    CALLING_LLM --> LLM_RESPONSE_RECEIVED
    CALLING_LLM --> LLM_FAILED

    LLM_RESPONSE_RECEIVED --> PARSING_RESPONSE
    PARSING_RESPONSE --> PARSED
    PARSING_RESPONSE --> PARSE_FAILED

    PARSED --> VALIDATING_MARKS
    VALIDATING_MARKS --> VALIDATED

    VALIDATED --> CHECKING_CONSISTENCY
    CHECKING_CONSISTENCY --> CONSISTENCY_CHECKED

    CONSISTENCY_CHECKED --> CALCULATING_CONFIDENCE
    CALCULATING_CONFIDENCE --> CONFIDENCE_CALCULATED

    CONFIDENCE_CALCULATED --> STORING_RESULT
    STORING_RESULT --> COMPLETED
    COMPLETED --> [*]

    EXTRACTION_FAILED --> MANUAL_REVIEW
    RULES_MISSING --> MANUAL_REVIEW
    LLM_FAILED --> RETRY
    PARSE_FAILED --> RETRY
    RETRY --> CALLING_LLM: Max 3 attempts

    MANUAL_REVIEW --> COMPLETED: Tutor finalizes

    state MANUAL_REVIEW {
        [*] --> WAITING_FOR_TUTOR
        WAITING_FOR_TUTOR --> TUTOR_REVIEWING
        TUTOR_REVIEWING --> TUTOR_COMPLETED
        TUTOR_COMPLETED --> [*]
    }
```

## 9) Database Schema (ER)

```mermaid
erDiagram
    USERS ||--o{ ANSWERS : submits
    QUESTIONS ||--o{ ANSWERS : answered_by
    ANSWERS ||--o{ MARKING_RESULTS : produces
    MARKING_RESULTS ||--o{ FEEDBACK : contains
    QUESTIONS ||--o{ MARKING_SCHEMES : uses
    KNOWLEDGE_DOCUMENTS ||--o{ DOCUMENT_CHUNKS : chunked_into

    USERS {
        uuid id PK
        string email
        string name
        string role
        timestamp created_at
    }

    QUESTIONS {
        uuid id PK
        string paper_code
        string paper_year
        string question_number
        text question_text
        float max_marks
        string question_type
    }

    ANSWERS {
        uuid id PK
        uuid user_id FK
        uuid question_id FK
        string file_path
        text extracted_text
        string status
        timestamp submitted_at
    }

    MARKING_SCHEMES {
        uuid id PK
        uuid question_id FK
        string source_file
        json mark_breakdown
        timestamp created_at
    }

    MARKING_RESULTS {
        uuid id PK
        uuid answer_id FK
        float total_marks
        float max_marks
        json question_marks
        json professional_marks
        float confidence_score
        boolean needs_human_review
        string llm_model_used
        timestamp created_at
    }

    FEEDBACK {
        uuid id PK
        uuid result_id FK
        string category
        text text
        json references
        int priority
    }

    KNOWLEDGE_DOCUMENTS {
        uuid id PK
        string title
        string document_type
        string paper_code
        string year
        string file_path
        json metadata
    }

    DOCUMENT_CHUNKS {
        uuid id PK
        uuid document_id FK
        text text
        string embedding_ref
        int chunk_index
        json metadata
    }
```

## 10) Tech Stack Diagram

```mermaid
mindmap
  root((ACCA AA AI Marker))
    Frontend
      Streamlit
      Session State
      Charts and Reports
    Backend
      FastAPI
      Celery Workers
      Redis Queue
    Data Storage
      PostgreSQL
      ChromaDB
      MinIO or S3
    Document Processing
      PyPDF2
      python-docx
      Question Parser
    AI and Retrieval
      DeepSeek R1
      MiniMax M2.5
      text-embedding-004
      RAG Retrieval
    DevOps
      Docker
      Render
      GitHub Actions
      Monitoring
```

## 11) Security Architecture

```mermaid
flowchart TD
    subgraph Perimeter[Perimeter Security]
        FW[Web Application Firewall]
        TLS[TLS Termination]
        RL[Rate Limiting]
    end

    subgraph Identity[Authentication and Access]
        JWT[JWT Tokens]
        APIKey[API Key Vault]
        RBAC[Role-Based Access Control]
    end

    subgraph Validation[Input Validation]
        FV[File Validation]
        SV[Size Validation]
        TV[Type Validation]
        CV[Content Validation]
    end

    subgraph DataSec[Data Protection]
        EAR[Encryption at Rest]
        TIT[Encryption in Transit]
        PII[PII Masking]
        ANON[Anonymization]
    end

    subgraph Audit[Audit and Compliance]
        AL[Audit Logs]
        ACL[Access Logs]
        CT[Change Tracking]
    end

    User[User] --> Perimeter
    Perimeter --> Identity
    Identity --> Validation
    Validation --> DataSec
    DataSec --> Audit
```

## 12) Monitoring and Observability

```mermaid
flowchart LR
    subgraph Sources[Telemetry Sources]
        API[API Logs]
        LLM[LLM Call Metrics]
        APP[Application Metrics]
        DB[Database Metrics]
    end

    subgraph Collection[Collection Layer]
        PROM[Prometheus]
        LOKI[Loki]
        OTEL[OpenTelemetry]
    end

    subgraph Storage[Storage Layer]
        TSDB[Time-Series Store]
        LOGS[Log Store]
        TRACES[Trace Store]
    end

    subgraph Viz[Visualization]
        GRAF[Grafana]
        DASH[Dashboards]
        ALERT[Alertmanager]
    end

    subgraph Notify[Alert Destinations]
        EMAIL[Email]
        SLACK[Slack]
        PAGER[PagerDuty]
    end

    Sources --> Collection
    Collection --> Storage
    Storage --> Viz
    Viz --> Notify
```
