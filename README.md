# SphereCast — Document-to-Database Processing System

This system extracts structured data from business documents (purchase orders, invoices) and updates a relational database. Below I explain the architecture and the reasoning behind each design choice.

---

## The Problem

Given an email with an attached document (PDF/image of a purchase order), the system needs to:
1. Extract structured data from the document
2. Resolve entities to existing database records (e.g., "SKU-13" → product ID 5)
3. Generate and execute the correct database operations (INSERT/UPDATE)

This is harder than it looks because:
- Documents come in different formats from different suppliers
- SKUs in documents may not match internal SKUs (vendors use their own codes)
- The system needs to know whether to INSERT a new record or UPDATE an existing one
- Foreign key relationships must be respected (can't create a PO line without a valid product_id)

---

## Overall Architecture

```
Document → [Extraction] → [Verification] → [Chain Planner] → [Executor] → Database
                ↓              ↓                  ↓
           Extractor LLM   Verifier LLM    Tool-calling LLM
```

I split the system into distinct phases because a single LLM call trying to do everything at once performed poorly in my testing—it would conflate extraction with database logic, hallucinate entity matches, and generate invalid SQL.

---

## Part 1: Document Extraction

### Two-LLM Pattern (Extractor + Verifier)

I use two separate LLM calls for extraction:

```
Document → [Extractor LLM] → JSON → [Verifier LLM] → Confidence Score
```

**The reasoning:**

When I initially used a single LLM to extract and self-verify, it would often "confirm" its own mistakes—if it misread "50" as "500", it would also verify "500" as correct because it had the same misreading both times.

By using a second, independent LLM call that sees the original document alongside the claimed extraction, errors get caught. The verifier doesn't know what the extractor "intended"—it just checks if the JSON matches what's actually in the document.

The tradeoff is 2x the LLM calls, but the accuracy improvement justified it for this use case where database corruption is costly.

### Flexible JSON Schema

Instead of defining a fixed schema like:
```python
{"po_number": str, "line_items": [{"sku": str, "quantity": int}]}
```

I instruct the LLM to read the actual column headers from the document and use those as field names:

```
Document table: [sku | title | quantity | date | total price]
→ JSON: {"sku": "...", "title": "...", "quantity": ..., "date": "...", "total_price": ...}
```

**The reasoning:**

Different suppliers use different document formats. One might have columns `[SKU, Description, Qty, Price]`, another might have `[Item Code, Product Name, Units, Amount]`. A fixed schema would require:
- Knowing all possible formats upfront
- Mapping logic for each format variation
- Code changes when a new supplier uses different column names

With flexible extraction, the LLM adapts to whatever columns exist. The downstream processing (chain planner) then handles mapping these fields to database columns.

The tradeoff is that the extracted JSON structure isn't guaranteed—downstream code needs to handle field variations. But this was preferable to maintaining brittle format-specific extraction logic.

### Verification Prompt Design

The verifier is specifically instructed to focus on **business-critical accuracy only**:

- Flag: Wrong quantities, wrong SKUs, wrong prices, wrong reference numbers
- Ignore: Formatting differences, text concatenation, whitespace

Early versions of the verifier were too pedantic—flagging issues like "title spans two lines in document but is one string in JSON". This created noise and reduced confidence scores for valid extractions. The prompt now explicitly tells the verifier what constitutes a real error versus a formatting difference.

---

## Part 2: Chain Planner (Database Operations)

### The Problem with Single-Call Planning

My first approach was a single LLM call: "Here's the extracted data and the database schema. Generate the SQL operations."

This failed in several ways:
- The LLM would assume entities existed when they didn't (hallucinating product IDs)
- It would miss junction table requirements (supplier_product mappings)
- It couldn't reliably determine INSERT vs UPDATE
- Foreign key ordering was often wrong

### Multi-Step Chain Architecture

I broke the planning into four sequential steps, each with a focused task:

**Step 1: Entity Resolution**
```
Input: Extracted data + email context
Output: Mapping of document entities to database IDs (or "new" if not found)
```
The LLM uses database exploration tools to actually query the database and find matches. It's not guessing from a static schema dump—it's searching.

**Step 2: Existence Analysis**
```
Input: Resolved entities
Output: For each entity, does it exist? What operation is needed?
```

**Step 3: Relationship Check**
```
Input: Existence analysis
Output: What junction table records are needed? What's the dependency order?
```

**Step 4: Operation Generation**
```
Input: All previous steps
Output: Concrete INSERT/UPDATE operations with resolved IDs
```

**The reasoning:**

Each step validates the previous step's output before proceeding. If entity resolution fails, we don't proceed to operation generation with bad data. Each step has a narrower task, which LLMs handle more reliably than broad multi-concern tasks.

The tradeoff is more LLM calls and more complex orchestration code. But the reliability improvement was significant—the single-call approach had maybe 60% success rate on complex documents, the chain approach is closer to 90%.

---

## Part 3: Entity Resolution (Schema Context + Tool-Calling)

### Combining Static Schema with Dynamic Tools

The entity resolution step uses both approaches:

1. **Static schema context** (`schema_builder.py`): Provides the LLM with table structure, foreign key relationships, business rules (e.g., "check supplier_product for vendor SKU mappings"), and a snapshot of current data
2. **Dynamic tools**: Let the LLM query the database for specific lookups

The schema builder generates a formatted representation that includes:
- Table purposes ("supplier_product is a junction table mapping vendor SKUs to internal products")
- Identity rules ("for products, check by SKU column")
- Foreign key dependency order
- Sample data from each table

This gives the LLM context about what tables exist and how they relate, without it needing to discover everything from scratch.

### Database Exploration Tools

On top of the schema context, the LLM has tools for specific queries:

| Tool | What it does |
|------|--------------|
| `list_tables()` | Returns all table names |
| `describe_table(name)` | Returns columns, types, constraints, foreign keys |
| `get_relationships(name)` | Returns incoming/outgoing foreign keys |
| `query_table(name, conditions)` | Queries with filters, returns rows |
| `search_value(value)` | Searches for a value across all text columns |
| `get_sample_data(name)` | Returns sample rows |

**The reasoning for this hybrid approach:**

Pure static context has a limitation: it's a snapshot. When the LLM needs to answer "does SKU-13 exist?" or "what's the product_id for vendor SKU 'VENDOR-99' from supplier 3?", a static dump can't help—it needs to actually query the database.

Pure tool-calling has a different problem: the LLM spends many tool calls just understanding the schema before it can do useful work.

By providing schema context upfront AND giving tools for specific queries, the LLM starts with understanding and can immediately do targeted lookups. The schema context handles "what tables exist and how do they relate", while tools handle "does this specific value exist".

The tradeoff is some redundancy—the schema context includes information the tools could also provide. But this redundancy reduces tool calls and speeds up resolution.

---

## Part 4: Operation Executor

### Deterministic Execution

The final step is pure Python code—no LLM. It takes the operation plan:

```json
{
  "operations": [
    {"operation": "INSERT", "table": "product", "values": {"sku": "NEW-1", "title": "New Product"}},
    {"operation": "INSERT", "table": "purchase_order_line", "values": {"product_id": "@product:NEW-1", "quantity": 100}}
  ]
}
```

And executes it:
1. Parses operations
2. Resolves placeholders (`@product:NEW-1` → actual ID from previous INSERT)
3. Executes SQL in dependency order
4. Logs what was created/updated

**The reasoning:**

LLMs shouldn't execute SQL directly. They hallucinate, they make syntax errors, they don't handle edge cases. By having the LLM generate a structured plan and Python code execute it, I get:
- Validation before execution
- Proper transaction handling
- Placeholder resolution (the LLM doesn't know what ID a new record will get)
- Audit logging

---

## Confidence-Based Routing

The orchestrator routes extractions based on verification confidence:

| Confidence | Action |
|------------|--------|
| ≥ 90% and verified | Auto-process |
| 75% - 90% | Queue for human review |
| < 75% | Require manual handling |

**The reasoning:**

Not all extractions should be trusted equally. A blurry scan with ambiguous characters should not automatically update the database. By having confidence thresholds, high-quality extractions flow through automatically while questionable ones get human oversight.

---

## Database Schema

The schema handles purchase orders with supplier-specific SKU mappings:

```
supplier ──────┐
               │
               ▼
         supplier_product ◀──── product
          (junction table:
           maps vendor SKUs
           to internal SKUs)
               │
               │
purchase_order ◀────────────── purchase_order_line
```

The `supplier_product` table is key: it maps external vendor SKUs to internal product IDs. When a document says "VENDOR-99", the system can look up that this supplier's "VENDOR-99" maps to internal product ID 5.

---

## File Structure

```
spherecast/
├── orchestrator.py           # Main entry point, routes by confidence
├── llm_client.py             # LLM API wrapper
│
├── extraction/
│   ├── extract_and_verify.py # Two-LLM extraction pattern
│   ├── prompts.py            # Extraction and verification prompts
│   └── audit.py              # Logs extractions
│
├── reasoning/
│   ├── chain_planner.py      # Multi-step planning
│   ├── tool_agent.py         # LLM with tool-calling loop
│   ├── db_tools.py           # Database exploration tools
│   ├── schema_builder.py     # Static schema representation (partially used)
│   └── executor.py           # Executes INSERT/UPDATE operations
│
├── database/
│   └── models.py             # SQLAlchemy models
│
├── audit/
│   └── update_tracker.py     # Tracks database changes
│
├── frontend/                 # React UI for uploading and viewing
└── api.py                    # FastAPI backend
```

---

## Running the System

```bash
# Install dependencies
uv sync

# Set API key
export OPENAI_API_KEY="your-key"

# Start backend
python -m uvicorn api:app --reload --port 8000

# Start frontend
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173`, upload an `.eml` file with a PDF attachment.

---

## Tradeoffs and Limitations

**Multiple LLM calls**: The system makes 5-10 LLM calls per document (extraction, verification, 4 chain steps with potential tool loops). This adds latency and cost. For high-volume processing, batching or caching would be needed.

**Flexible schema complexity**: Because extraction doesn't enforce a fixed schema, downstream processing has to handle field variations. This adds complexity to the chain planner prompts.

**Tool-calling latency**: The entity resolution step may make 5-15 tool calls as it explores the database. Each is a round-trip. For real-time requirements, this would need optimization.

**SQLite for demo**: The current implementation uses SQLite. For production, this would need PostgreSQL or similar, but the architecture (SQLAlchemy-based) supports that.

---

## Adapting to Different Use Cases

**Different database schema**: The tool-calling approach means the system discovers the schema at runtime. Point it at a different database and it will explore and adapt. Business rules specific to tables can be added to `schema_builder.py`.

**Different document types**: The extraction prompt already handles multiple types (purchase orders, invoices, shipping notices). The flexible JSON approach means new column formats don't require code changes.

**Different LLM providers**: `llm_client.py` wraps the OpenAI API but could be swapped for Anthropic, local models, etc.
# spherecast-task
