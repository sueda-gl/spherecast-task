# SphereCast - Document Extraction & Database Automation System

An LLM-based system that extracts structured data from business documents (purchase orders, invoices, etc.) and automatically updates a relational database with full audit traceability.

## Architecture Overview

The system is designed for **accuracy and generalizability**—it handles any document type, adapts to unknown fields, and works with any relational schema.

```
📧 Email (.eml file)
        ↓
📄 Document Attachment (PDF/Image)
        ↓
┌─────────────────────────────────────┐
│  Stage 1: Extraction & Verification │
│  - Extractor LLM reads document     │
│  - Verifier LLM checks accuracy     │
└─────────────────────────────────────┘
        ↓
┌─────────────────────────────────────┐
│  Stage 2: Database Updates          │
│  - 5-step chain architecture        │
│  - Entity resolution → Execution    │
└─────────────────────────────────────┘
        ↓
🗃️ Database Updated + 📋 Audit Trail
```

---

## Stage 1: Document Extraction & Verification

### Extractor LLM

The system extracts from any document type without a rigid JSON schema. The LLM reads the document, identifies its type (PO, invoice, shipping notice), and constructs JSON dynamically based on what it sees—including reading actual column headers from tables.

This flexibility allows handling of invoices, purchase orders, or documents with unexpected fields without code changes.

### Verifier LLM

A second LLM acts as a judge. It sees both the original document and the extraction, then reports specific discrepancies. This separation makes debugging straightforward—you can see exactly where extraction went wrong.

The verifier focuses on business-critical accuracy (wrong quantity, wrong SKU) and ignores formatting differences (text concatenation, date formats).

---

## Stage 2: Database Updates (5-Stage Chain)

Instead of a single LLM call handling everything, the database update process is broken into 5 focused stages for reliability and debuggability.

### Stage 1 - Matching Document Data to Database Records

This stage identifies which database record each piece of text refers to (e.g., resolving "Item-X-Pro" to `product_id=842`). 

The LLM receives read-only database exploration tools—specifically `list_tables`, `describe_table`, `query_table`, and `search_value`. It proceeds through three phases:

First, it explores the database to understand the schema. It uses `list_tables` to see what tables exist, `describe_table` to inspect columns and foreign keys, and `query_table` to sample actual data.

Second, it learns patterns from this data. It discovers relationships—like how the `supplier_product` table maps vendor-specific codes to internal product IDs—and identifies formatting conventions.

Third, it resolves the specific entities from the document. It uses `search_value` to iteratively find terms across relevant tables until it locates a match, using its understanding of the schema to navigate relationships.

This allows the system to reason about formatting differences on its own—such as recognizing that "SKU13" maps to "SKU-1-3"—without requiring hard-coded transformation rules.

### Stage 2 - Deciding What Needs to Be Created vs Updated

After Stage 1 identifies what records the document refers to, Stage 2 decides the action—INSERT or UPDATE?

Stage 1 finds the "nouns" (Product #5 exists, PO #1 exists). Stage 2 checks the links between them. For example: "Is Product #5 already linked to PO #1 in the `purchase_order_line` table?" If that combination exists, the decision is UPDATE. If not, INSERT.

*Note: In this implementation, I pass a data snapshot to the LLM because the trial database is small. For a production system, this would be optimized to use targeted SQL queries—once you have resolved IDs from Stage 1, existence checks are simple lookups, not LLM reasoning tasks.*

### Stage 3 - Checking Relationship Tables

When inserting new records, we often need to create corresponding entries in junction tables. This stage checks if new products need `supplier_product` mappings to link them to the supplier.

*Note: This stage is written specifically for this schema's junction table rather than being fully generic. A more generalizable approach would let the LLM discover junction tables dynamically using the same exploration tools from Stage 1.*

### Stage 4 - Generating the Final List of Operations

This stage synthesizes everything into a single, ordered list of database operations. The ordering respects foreign key dependencies—independent records first, dependent records last.

For records created in the same batch, placeholder syntax (`__NEW_product_id`) is used. This stage also applies email context instructions like "push back delivery to February".

### Stage 5 - Executing the Operations

Pure Python—no LLM. The executor runs each operation, captures generated IDs, and substitutes placeholders. Everything runs in a database transaction (rollback on any failure). Every change is logged to the audit trail with a link to the source document.

Planning (LLM) is separated from execution (Python) deliberately. LLMs reason well but execute unreliably. Deterministic code ensures the plan runs exactly as specified.

---

## Running the System

### Setup

```bash
# Install dependencies
uv sync

# Set API key
export OPENAI_API_KEY="your-api-key"
```

### Start the Application

```bash
# Backend
uv run uvicorn api:app --reload --port 8000

# Frontend (in another terminal)
cd frontend && npm run dev
```

Then open `http://localhost:5173` and upload `.eml` files.

---

## Project Structure

```
spherecast/
├── api.py                    # FastAPI backend
├── orchestrator.py           # Main coordinator (chain/hybrid/agent modes)
├── llm_client.py             # OpenAI API wrapper with vision support
│
├── extraction/               # Document extraction & verification
│   ├── extract_and_verify.py # Two-phase extraction
│   └── prompts.py            # Extractor & verifier prompts
│
├── reasoning/                # Database update chain
│   ├── chain_planner.py      # 5-stage chain architecture
│   ├── db_tools.py           # Read-only database exploration tools
│   ├── tool_agent.py         # LLM agent with tool calling
│   ├── schema_builder.py     # Database schema context builder
│   ├── executor.py           # Deterministic operation executor
│   └── planner.py            # Single-call planner (hybrid mode)
│
├── tools/                    # Full CRUD database tools (agent mode)
│   └── database_tools.py
│
├── audit/                    # Change tracking
│   └── update_tracker.py     # Audit trail with source traceability
│
├── database/                 # Database models & setup
│   ├── models.py             # SQLAlchemy ORM models
│   └── setup.py              # Database initialization
│
└── frontend/                 # React/TypeScript UI
    └── src/
        ├── App.tsx
        └── components/
```

---

## Database Schema

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
│  Supplier   │────<│ SupplierProduct │>────│   Product   │
│  (id, name) │     │ (supplier_sku)  │     │ (sku,title) │
└─────────────┘     └─────────────────┘     └─────────────┘
      │                                           │
      ↓                                           ↓
┌─────────────────┐     ┌────────────────────────┐
│ PurchaseOrder   │────<│   PurchaseOrderLine    │
│ (ref_num, date) │     │ (quantity, date)       │
└─────────────────┘     └────────────────────────┘
```

- **Product** - Internal product catalog (SKU, title)
- **Supplier** - Vendor information
- **SupplierProduct** - Maps supplier SKUs to internal products (junction table)
- **PurchaseOrder** - Order header (reference, dates, terms)
- **PurchaseOrderLine** - Line items (product, quantity, delivery date)

---

## Processing Modes

The orchestrator supports three modes:

| Mode | Description | Use Case |
|------|-------------|----------|
| `chain` | 5-stage focused LLM calls + deterministic executor | Production (default) |
| `hybrid` | Single-call planner + deterministic executor | Faster, less reliable |
| `agent` | LLM with direct database tool calling | Legacy/experimental |

---

## Key Design Decisions

### Adaptive Extraction
No rigid JSON schema. The LLM constructs output based on what it sees, enabling handling of any document type.

### LLM-as-Judge Verification
A second LLM verifies extraction accuracy, catching errors and providing clear feedback.

### Multi-Stage Chain
Breaking database operations into focused stages improves reliability and debuggability over a single monolithic LLM call.

### Tool-Based Entity Resolution
The LLM explores the database dynamically rather than relying on hard-coded matching rules, enabling fuzzy resolution of format variations.

### Separated Planning and Execution
LLMs plan, Python executes. This ensures reliable, transactional database operations.

### Full Audit Trail
Every database change links back to its source document, enabling complete traceability.

---

## Dependencies

- **OpenAI** - LLM API (GPT-5.2 with vision)
- **FastAPI** - Backend API framework
- **SQLAlchemy** - Database ORM
- **React/TypeScript** - Frontend UI
- **Pillow** - Image processing
- **python-dotenv** - Environment management
