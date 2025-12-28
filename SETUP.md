# SphereCast Frontend Setup Guide

## Overview

A modern web UI for your SphereCast document extraction system with:

- **Simple .eml upload** - Just drag and drop email files
- **Automatic parsing** - Extracts email body and attachments automatically  
- **Real-time confidence scoring** and extraction status
- **FastAPI backend** exposing your Python extraction system
- **React + TypeScript** frontend with dark UI

## Quick Start

### 1. Install Python Dependencies

```bash
pip install fastapi uvicorn python-multipart
```

### 2. Start the Backend

```bash
cd /Users/suedagul/spherecast
export OPENAI_API_KEY="your-key-here"
python -m uvicorn api:app --reload --port 8000
```

### 3. Start the Frontend

In a new terminal:

```bash
cd /Users/suedagul/spherecast/frontend
npm run dev
```

Open **http://localhost:5173**

## Usage

1. **Export an email as .eml** from your email client (Gmail, Outlook, etc.)
   - The email should have a purchase order document attached (PDF or image)
2. **Drop the .eml file** into the upload area
3. **The system automatically:**
   - Extracts the email body and metadata
   - Finds and extracts the attached document
   - Processes through LLM extraction pipeline
   - Shows confidence score and status

## How .eml Files Work

An `.eml` file is a standard email format that contains:
- Email headers (From, To, Subject, Date)
- Email body (plain text and/or HTML)
- Attachments (documents, images)

The backend automatically parses all this and processes the purchase order attachment.

## Confidence Routing

- **>90%**: Auto-processed ✓
- **75-90%**: Queued for review ⚠
- **<75%**: Requires manual review ✗

## Architecture

```
.eml file → FastAPI parses → Extracts attachment → LLM Vision → Database
              ↓
        Email body + metadata
```

## Tech Stack

**Backend:**
- FastAPI - Modern Python web framework
- Python `email` library - Parses .eml files
- Your extraction system (LLM + SQLAlchemy)

**Frontend:**
- React 18 + TypeScript
- Vite - Fast build tool
- TailwindCSS - Dark theme styling
- React Dropzone - File upload

## File Structure

```
spherecast/
├── api.py                    # FastAPI backend with .eml parsing
├── orchestrator.py           # Your extraction orchestrator
├── extraction/               # Extraction logic
├── frontend/                 # React application
│   └── src/
│       ├── components/
│       │   ├── Sidebar.tsx
│       │   └── UploadPage.tsx  # Single .eml upload
│       └── App.tsx
├── uploads/                  # Extracted documents (auto-created)
├── sample_email.eml         # Example email for testing
└── database/
    ├── spherecast.db        # Main database
    └── audit.db             # Audit trail
```

## Testing with Sample Email

A sample `.eml` file is included at `sample_email.eml`. You can drag and drop this to test the system (though it contains a minimal PDF, so extraction will be limited).

To create a real test email:
1. In Gmail/Outlook, open an email with a PO attachment
2. Use "Save as" or "Download" → Save as `.eml` format
3. Upload to the system

## API Endpoints

- `POST /api/process-email` - Upload .eml file (recommended)
- `POST /api/process` - Manual upload (legacy)
- `GET /api/review-queue` - Get items needing review
- `GET /api/statistics` - Processing statistics

## Example: Manual .eml Processing

```bash
curl -X POST http://localhost:8000/api/process-email \
  -F "email_file=@sample_email.eml"
```

Response:
```json
{
  "success": true,
  "result": {
    "extraction_id": 123,
    "status": "auto_processed",
    "confidence": 0.95,
    "verified": true
  },
  "email_info": {
    "from": "supplier@example.com",
    "subject": "Purchase Order #PO-2024-001",
    "message_id": "<abc123@example.com>"
  }
}
```

## Troubleshooting

**"No document attachment found":**
- Ensure the .eml file contains a PDF or image attachment
- Check the attachment is not inline/embedded

**Frontend upload fails:**
- Verify backend is running at http://localhost:8000
- Check browser console for errors

**Backend parsing error:**
- Some email clients export .eml differently
- Try a different email or client

## Next Steps

- Add batch .eml processing (upload multiple emails)
- Build review queue UI for medium-confidence items
- Add email filtering (only process PO-related emails)
- Database integration for automatic PO creation

Enjoy your simplified .eml upload workflow! 🚀
