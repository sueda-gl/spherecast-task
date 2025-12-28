import { useState, useEffect } from 'react'
import { 
  X, 
  FileText, 
  ArrowRight, 
  Brain, 
  Calendar,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Minimize2
} from 'lucide-react'

interface Change {
  id: number
  extraction_id: number | null
  timestamp: string | null
  operation: string
  field: string | null
  old_value: string | null
  new_value: string | null
  source_document: string | null
  source_field: string | null
  source_value: string | null
  llm_reasoning: string | null
  confidence: number | null
  requires_approval: boolean
  approved: boolean | null
  extraction?: {
    id: number
    document_path: string
    confidence: number
    verified: boolean
    extraction_result: any
  } | null
}

interface SourceDocumentViewerProps {
  isOpen: boolean
  onClose: () => void
  tableName: string
  recordId: number | string
  changes: Change[]
}

export default function SourceDocumentViewer({
  isOpen,
  onClose,
  tableName,
  recordId,
  changes
}: SourceDocumentViewerProps) {
  const [currentChangeIndex, setCurrentChangeIndex] = useState(0)
  const [documentUrl, setDocumentUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [imageError, setImageError] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)

  const currentChange = changes[currentChangeIndex]

  // Load document when change changes
  useEffect(() => {
    if (!currentChange) return
    
    setLoading(true)
    setImageError(false)
    
    // Get document URL
    const docPath = currentChange.source_document || 
                    currentChange.extraction?.document_path
    
    if (docPath) {
      // Use the document-by-path endpoint
      setDocumentUrl(`/api/document-by-path?path=${encodeURIComponent(docPath)}`)
    } else if (currentChange.extraction_id) {
      // Fallback to extraction document
      setDocumentUrl(`/api/document/${currentChange.extraction_id}`)
    } else {
      setDocumentUrl(null)
    }
    
    setLoading(false)
  }, [currentChange])

  // Reset index when changes change
  useEffect(() => {
    setCurrentChangeIndex(0)
  }, [changes])

  if (!isOpen) return null

  const formatValue = (value: string | null): string => {
    if (!value) return '(empty)'
    try {
      // Try to parse JSON and format nicely
      const parsed = JSON.parse(value)
      if (typeof parsed === 'object') {
        return JSON.stringify(parsed, null, 2)
      }
      return String(parsed)
    } catch {
      return value
    }
  }

  const formatDate = (timestamp: string | null): string => {
    if (!timestamp) return 'Unknown'
    return new Date(timestamp).toLocaleString()
  }

  const getOperationBadge = (operation: string) => {
    switch (operation) {
      case 'create':
        return (
          <span className="px-2 py-1 text-xs font-medium rounded bg-green-500/20 text-green-400 border border-green-500/30">
            CREATED
          </span>
        )
      case 'update':
        return (
          <span className="px-2 py-1 text-xs font-medium rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">
            UPDATED
          </span>
        )
      case 'delete':
        return (
          <span className="px-2 py-1 text-xs font-medium rounded bg-red-500/20 text-red-400 border border-red-500/30">
            DELETED
          </span>
        )
      default:
        return (
          <span className="px-2 py-1 text-xs font-medium rounded bg-gray-500/20 text-gray-400 border border-gray-500/30">
            {operation.toUpperCase()}
          </span>
        )
    }
  }

  // Side panel width classes
  const panelWidth = isExpanded ? 'w-[900px]' : 'w-[480px]'

  return (
    <>
      {/* Backdrop - click to close */}
      <div 
        className="fixed inset-0 bg-black/40 z-40 transition-opacity"
        onClick={onClose}
      />
      
      {/* Side Panel */}
      <div className={`fixed right-0 top-0 h-full ${panelWidth} bg-[#0d0d0d] border-l border-[#1a1a1a] z-50 flex flex-col shadow-2xl transition-all duration-300`}>
        {/* Header */}
        <div className="px-4 py-3 border-b border-[#1a1a1a] bg-[#111] flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <div className="p-1.5 bg-blue-500/10 rounded-lg flex-shrink-0">
                <FileText className="text-blue-400" size={18} />
              </div>
              <div className="min-w-0">
                <h2 className="text-sm font-bold text-white truncate">
                  Source Document
                </h2>
                <p className="text-xs text-gray-400 truncate">
                  <span className="font-mono text-blue-400">{tableName}</span>
                  <span className="mx-1.5">→</span>
                  <span className="font-mono">#{recordId}</span>
                  <span className="mx-1.5">•</span>
                  <span>{changes.length} change{changes.length !== 1 ? 's' : ''}</span>
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="p-1.5 hover:bg-[#1a1a1a] rounded transition-colors text-gray-400 hover:text-white"
                title={isExpanded ? 'Collapse' : 'Expand'}
              >
                {isExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
              </button>
              <button
                onClick={onClose}
                className="p-1.5 hover:bg-[#1a1a1a] rounded transition-colors text-gray-400 hover:text-white"
              >
                <X size={18} />
              </button>
            </div>
          </div>
        </div>

        {/* Navigation (if multiple changes) */}
        {changes.length > 1 && (
          <div className="px-4 py-2 border-b border-[#1a1a1a] bg-[#0a0a0a] flex items-center justify-between flex-shrink-0">
            <button
              onClick={() => setCurrentChangeIndex(Math.max(0, currentChangeIndex - 1))}
              disabled={currentChangeIndex === 0}
              className="flex items-center gap-1 px-2 py-1 rounded bg-[#1a1a1a] hover:bg-[#222] disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-xs"
            >
              <ChevronLeft size={14} />
              Prev
            </button>
            <div className="flex items-center gap-1.5">
              {changes.map((_, idx) => (
                <button
                  key={idx}
                  onClick={() => setCurrentChangeIndex(idx)}
                  className={`w-1.5 h-1.5 rounded-full transition-colors ${
                    idx === currentChangeIndex 
                      ? 'bg-blue-500' 
                      : 'bg-[#333] hover:bg-[#444]'
                  }`}
                />
              ))}
            </div>
            <button
              onClick={() => setCurrentChangeIndex(Math.min(changes.length - 1, currentChangeIndex + 1))}
              disabled={currentChangeIndex === changes.length - 1}
              className="flex items-center gap-1 px-2 py-1 rounded bg-[#1a1a1a] hover:bg-[#222] disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-xs"
            >
              Next
              <ChevronRight size={14} />
            </button>
          </div>
        )}

        {/* Main Content - Scrollable */}
        <div className="flex-1 overflow-y-auto">
          {isExpanded ? (
            // Expanded: Two column layout
            <div className="flex h-full">
              {/* Left: Document */}
              <div className="w-1/2 border-r border-[#1a1a1a] flex flex-col">
                <div className="px-3 py-2 border-b border-[#1a1a1a] bg-[#0a0a0a] flex-shrink-0">
                  <h3 className="text-xs font-semibold text-white flex items-center gap-2">
                    <FileText size={12} className="text-gray-400" />
                    Document
                  </h3>
                </div>
                <div className="flex-1 overflow-auto p-3 bg-[#080808]">
                  {loading ? (
                    <div className="h-full flex items-center justify-center">
                      <div className="text-gray-400 flex flex-col items-center gap-2">
                        <div className="animate-spin w-6 h-6 border-2 border-gray-600 border-t-blue-500 rounded-full" />
                        <span className="text-xs">Loading...</span>
                      </div>
                    </div>
                  ) : documentUrl && !imageError ? (
                    <img
                      src={documentUrl}
                      alt="Source document"
                      className="max-w-full h-auto rounded border border-[#1a1a1a]"
                      onError={() => setImageError(true)}
                    />
                  ) : (
                    <div className="h-full flex items-center justify-center">
                      <div className="text-center text-gray-500">
                        <FileText className="mx-auto mb-2 opacity-50" size={32} />
                        <p className="text-xs">No document</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
              
              {/* Right: Change Details */}
              <div className="w-1/2 overflow-y-auto p-3 space-y-3">
                {renderChangeDetails()}
              </div>
            </div>
          ) : (
            // Collapsed: Single column
            <div className="p-3 space-y-3">
              {renderChangeDetails()}
              
              {/* Document Preview (collapsed) */}
              {documentUrl && !imageError && (
                <div className="bg-[#111] border border-[#1a1a1a] rounded-lg overflow-hidden">
                  <div className="px-3 py-2 border-b border-[#1a1a1a] flex items-center justify-between">
                    <h3 className="text-xs font-semibold text-white flex items-center gap-2">
                      <FileText size={12} className="text-gray-400" />
                      Source Document
                    </h3>
                    <button
                      onClick={() => setIsExpanded(true)}
                      className="text-xs text-blue-400 hover:text-blue-300"
                    >
                      Expand
                    </button>
                  </div>
                  <div className="p-2 bg-[#080808]">
                    <img
                      src={documentUrl}
                      alt="Source document"
                      className="w-full h-auto rounded border border-[#1a1a1a] max-h-48 object-cover object-top"
                      onError={() => setImageError(true)}
                    />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-[#1a1a1a] bg-[#0a0a0a] flex-shrink-0">
          <button
            onClick={onClose}
            className="w-full px-3 py-2 bg-[#1a1a1a] hover:bg-[#222] border border-[#2a2a2a] rounded text-white transition-colors text-sm font-medium"
          >
            Close
          </button>
        </div>
      </div>
    </>
  )

  function renderChangeDetails() {
    if (!currentChange) {
      return (
        <div className="h-full flex items-center justify-center text-gray-500 text-sm">
          No change selected
        </div>
      )
    }

    return (
      <>
        {/* Operation & Timestamp */}
        <div className="flex items-center justify-between">
          {getOperationBadge(currentChange.operation)}
          <span className="text-xs text-gray-500 flex items-center gap-1">
            <Calendar size={10} />
            {formatDate(currentChange.timestamp)}
          </span>
        </div>

        {/* Field Changed */}
        {currentChange.field && (
          <div className="bg-[#111] border border-[#1a1a1a] rounded-lg p-3">
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">
              Field Changed
            </div>
            <div className="font-mono text-blue-400 text-sm">
              {currentChange.field}
            </div>
          </div>
        )}

        {/* Value Change */}
        {currentChange.operation === 'update' && (
          <div className="bg-[#111] border border-[#1a1a1a] rounded-lg p-3">
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-2">
              Value Change
            </div>
            <div className="space-y-2">
              {/* Old Value */}
              <div>
                <div className="text-xs text-red-400 mb-1 flex items-center gap-1">
                  <X size={10} />
                  Old Value
                </div>
                <div className="bg-red-500/10 border border-red-500/20 rounded p-2">
                  <pre className="text-xs text-red-300 font-mono whitespace-pre-wrap break-all">
                    {formatValue(currentChange.old_value)}
                  </pre>
                </div>
              </div>

              {/* Arrow */}
              <div className="flex justify-center">
                <ArrowRight className="text-gray-600" size={16} />
              </div>

              {/* New Value */}
              <div>
                <div className="text-xs text-green-400 mb-1 flex items-center gap-1">
                  <CheckCircle size={10} />
                  New Value
                </div>
                <div className="bg-green-500/10 border border-green-500/20 rounded p-2">
                  <pre className="text-xs text-green-300 font-mono whitespace-pre-wrap break-all">
                    {formatValue(currentChange.new_value)}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* For CREATE operations */}
        {currentChange.operation === 'create' && currentChange.new_value && (
          <div className="bg-[#111] border border-[#1a1a1a] rounded-lg p-3">
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-2">
              Created Record
            </div>
            <div className="bg-green-500/10 border border-green-500/20 rounded p-2">
              <pre className="text-xs text-green-300 font-mono whitespace-pre-wrap break-all max-h-32 overflow-y-auto">
                {formatValue(currentChange.new_value)}
              </pre>
            </div>
          </div>
        )}

        {/* LLM Reasoning */}
        {currentChange.llm_reasoning && (
          <div className="bg-[#111] border border-[#1a1a1a] rounded-lg p-3">
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1">
              <Brain size={12} className="text-purple-400" />
              LLM Reasoning
            </div>
            <p className="text-xs text-gray-300 leading-relaxed whitespace-pre-wrap">
              {currentChange.llm_reasoning}
            </p>
          </div>
        )}

        {/* Source Value */}
        {currentChange.source_value && (
          <div className="bg-[#111] border border-[#1a1a1a] rounded-lg p-3">
            <div className="text-xs text-gray-400 uppercase tracking-wider mb-2">
              Extracted From Document
            </div>
            <div className="bg-blue-500/10 border border-blue-500/20 rounded p-2">
              <pre className="text-xs text-blue-300 font-mono whitespace-pre-wrap break-all">
                {currentChange.source_value}
              </pre>
            </div>
          </div>
        )}

      </>
    )
  }
}
