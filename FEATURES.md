# SphereCast Features

## ✅ Implemented Features

### 1. Email Upload Interface
- **Simple .eml file upload** via drag-and-drop
- Automatic parsing of email metadata (From, Subject, Message-ID)
- Automatic extraction of attached documents (PDF/images)
- Real-time upload status and progress feedback
- Confidence score display after processing

**Location:** Upload page (default view)

### 2. Extractions Audit Trail
- **View all extractions** in a list with status indicators
- **Detailed extraction view** showing:
  - **Document Preview** - See the actual uploaded document
  - **Verification Report** - What the verifier LLM found
  - **Issues & Warnings** - Problems detected with severity levels (high/medium/low)
  - **Verification Statistics** - Fields checked, correct, incorrect, missing
  - **Confidence score** and verification status
  - **Full extracted JSON** output with copy button
  - **Processing status** and timestamps
- **Status indicators:**
  - 🟢 Green: Auto-processed (>90% confidence)
  - 🟡 Yellow: Pending review (75-90% confidence)
  - 🔴 Red: Manual review required (<75% confidence)
- **Copy JSON** functionality for easy data export
- **Complete transparency** into the LLM's work

**Location:** Extractions tab in sidebar

### 3. Backend API
- `POST /api/process-email` - Upload and process .eml files
- `GET /api/extractions` - Get all extraction records
- `GET /api/extraction/{id}` - Get specific extraction details
- `GET /api/document/{id}` - Get document file for preview
- `GET /api/review-queue` - Get items needing review
- `GET /api/statistics` - Processing statistics

### 4. LLM Integration
- **Two-phase extraction:**
  1. Extractor LLM reads and extracts data
  2. Verifier LLM validates against original document
- **Confidence-based routing:**
  - High confidence (>90%): Auto-process
  - Medium confidence (75-90%): Queue for review
  - Low confidence (<75%): Require manual review
- **Complete audit trail** stored in SQLite database

## 🎨 UI/UX Features

- **Dark theme** matching your design reference
- **Responsive layout** with fixed sidebar navigation
- **Real-time updates** with loading states
- **Status badges** and confidence indicators
- **Clean, professional** typography and spacing
- **Hover effects** and smooth transitions

## 📊 Data Flow

```
.eml file → FastAPI parses email
    ↓
Extracts attachment (PDF/image)
    ↓
LLM Vision extracts data
    ↓
Verifier validates extraction
    ↓
Stores in audit database
    ↓
Display in Extractions UI
```

## 🔄 Current Workflow

1. **Upload**: User drops .eml file
2. **Parse**: Backend extracts email body + attachment
3. **Extract**: LLM reads document and extracts structured data
4. **Verify**: Second LLM validates the extraction
5. **Store**: Save to audit database with confidence score
6. **Route**: Based on confidence:
   - High → Auto-process
   - Medium → Review queue
   - Low → Manual review
7. **View**: User can see all extractions in the Extractions tab

## 🚀 How to Use

### Start the Application

**Terminal 1 - Backend:**
```bash
cd /Users/suedagul/spherecast
export OPENAI_API_KEY="your-key"
uv run uvicorn api:app --reload
```

**Terminal 2 - Frontend:**
```bash
cd /Users/suedagul/spherecast/frontend
npm run dev
```

Open: http://localhost:5173

### Upload an Email

1. Export an email as `.eml` from your email client
2. Drag and drop it into the upload area
3. Wait for processing (typically 10-30 seconds)
4. View confidence score and status
5. Click "View in Extractions" to see full details

### View Extractions (Audit Trail)

1. Click "Extractions" in the sidebar
2. See list of all processed emails with status indicators
3. Click any extraction to view:
   - **Document preview** (see the actual uploaded file)
   - **Verification report** (LLM's assessment)
   - **Issues found** (color-coded by severity)
   - **Verification statistics** (accuracy metrics)
   - **Full JSON output** (complete extracted data)
   - **Timestamps** and processing status

This is your complete audit trail showing exactly what the LLM saw, extracted, and verified.

## 📁 File Structure

```
spherecast/
├── api.py                          # FastAPI backend
├── orchestrator.py                 # Extraction orchestrator
├── extraction/
│   ├── extract_and_verify.py     # Two-phase extraction
│   ├── audit.py                   # Audit trail database
│   └── prompts.py                 # LLM prompts
├── frontend/
│   └── src/
│       ├── App.tsx                # Main app with routing
│       ├── components/
│       │   ├── Sidebar.tsx        # Navigation
│       │   ├── UploadPage.tsx     # .eml upload interface
│       │   └── ExtractionsPage.tsx # Audit trail viewer
│       └── index.css              # Dark theme styles
├── database/
│   ├── models.py                  # SQLAlchemy models
│   ├── spherecast.db             # Main database
│   └── audit.db                   # Extraction audit trail
└── uploads/                       # Uploaded documents
```

## 🎯 Key Benefits

1. **No manual data entry** - Just upload the .eml file
2. **Full transparency** - See exactly what the LLM extracted
3. **Confidence-based routing** - High confidence items auto-process
4. **Complete audit trail** - Every extraction is logged
5. **Easy debugging** - View full JSON output for any extraction
6. **Professional UI** - Clean, modern interface

## 🔮 Future Enhancements

- [ ] Document preview/viewer in extraction details
- [ ] Batch .eml upload (multiple files at once)
- [ ] Review queue workflow (approve/reject)
- [ ] Statistics dashboard with charts
- [ ] Export extractions to CSV/Excel
- [ ] Search and filter extractions
- [ ] Email filtering (only process PO-related emails)
- [ ] Automatic database integration (create POs in main DB)

## 🐛 Troubleshooting

**Backend won't start:**
- Check OPENAI_API_KEY is set
- Run `uv sync` to install dependencies
- Check port 8000 is available

**Frontend can't connect:**
- Verify backend is running at http://127.0.0.1:8000
- Check browser console for errors
- Restart frontend dev server

**No extractions showing:**
- Upload an .eml file first
- Check backend logs for errors
- Verify audit.db exists in database/

Enjoy your SphereCast extraction system! 🎉

