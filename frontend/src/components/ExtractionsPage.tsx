import { useState, useEffect, useRef } from 'react'
import { ChevronRight, CheckCircle, AlertCircle, Clock, FileText, Download, Code, Brain, Database } from 'lucide-react'
import ReasoningTrail from './ReasoningTrail'
import DatabaseUpdates from './DatabaseUpdates'

interface Extraction {
  id: number
  email_id: string
  status: string
  processing_status?: string  // 'extracted', 'processing', 'completed', 'failed'
  confidence: number
  verified: boolean
  created_at: string
  document_path: string
  extraction_result?: any
  verification_report?: any
  processing_result?: any
  document_hash?: string
  issues_count?: number
  review_priority?: string
  reviewed_by?: string
  reviewed_at?: string
}

type TabType = 'json' | 'reasoning' | 'updates'

function ExtractionTabs({ extraction }: { extraction: Extraction }) {
  const [activeTab, setActiveTab] = useState<TabType>('reasoning')

  const tabs = [
    { id: 'reasoning' as TabType, label: 'LLM Reasoning', icon: Brain },
    { id: 'updates' as TabType, label: 'DB Changes', icon: Database },
    { id: 'json' as TabType, label: 'Raw JSON', icon: Code },
  ]

  // Extract reasoning trail and database updates from processing result
  // Data is nested under processing_result.result due to API structure
  const processingData = extraction.processing_result?.result || extraction.processing_result || {}
  const reasoningTrail = processingData.reasoning_trail || []
  const operations = processingData.operations || []
  const summary = processingData.summary
  const confidence = processingData.confidence
  const databaseUpdates = extraction.database_updates || []

  return (
    <div className="bg-dark-surface border border-dark-border rounded-lg h-full flex flex-col">
      {/* Tab Header */}
      <div className="border-b border-dark-border">
        <div className="flex">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors border-b-2 ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-white bg-dark-hover/50'
                    : 'border-transparent text-gray-400 hover:text-white hover:bg-dark-hover/30'
                }`}
              >
                <div className="flex items-center justify-center gap-2">
                  <Icon size={16} />
                  <span>{tab.label}</span>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-auto p-4">
        {activeTab === 'reasoning' && (
          <ReasoningTrail
            reasoning={reasoningTrail}
            operations={operations}
            summary={summary}
            confidence={confidence}
          />
        )}

        {activeTab === 'updates' && (
          <DatabaseUpdates
            updates={databaseUpdates}
            documentPath={extraction.document_path}
          />
        )}

        {activeTab === 'json' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-white">Extracted Data (JSON)</h3>
              <button
                onClick={() => {
                  const json = JSON.stringify(extraction.extraction_result, null, 2)
                  navigator.clipboard.writeText(json)
                }}
                className="text-xs px-3 py-1.5 bg-dark-bg hover:bg-dark-hover border border-dark-border rounded text-gray-300 transition-colors"
              >
                Copy JSON
              </button>
            </div>
            <pre className="text-xs text-gray-300 font-mono bg-dark-bg p-4 rounded border border-dark-border overflow-x-auto">
              {JSON.stringify(extraction.extraction_result, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}

export default function ExtractionsPage() {
  const [extractions, setExtractions] = useState<Extraction[]>([])
  const [selectedExtraction, setSelectedExtraction] = useState<Extraction | null>(null)
  const [loading, setLoading] = useState(true)
  const extractionsRef = useRef<Extraction[]>([])
  
  // Keep ref in sync with state
  useEffect(() => {
    extractionsRef.current = extractions
  }, [extractions])

  useEffect(() => {
    fetchExtractions()
    
    // Set up polling interval - checks every 5 seconds
    const interval = setInterval(() => {
      // Check if any extraction is processing (using ref to avoid stale closure)
      const hasProcessing = extractionsRef.current.some(e => e.processing_status === 'processing')
      if (hasProcessing) {
        fetchExtractions()
      }
    }, 5000)
    
    return () => clearInterval(interval)
  }, [])

  const fetchExtractions = async () => {
    try {
      const response = await fetch('/api/extractions')
      const data = await response.json()
      setExtractions(data.extractions || [])
    } catch (error) {
      console.error('Failed to fetch extractions:', error)
    } finally {
      setLoading(false)
    }
  }

  const getStatusIcon = (extraction: Extraction) => {
    // Show processing status if available
    if (extraction.processing_status === 'processing') {
      return (
        <div className="relative">
          <Clock className="text-blue-400 animate-pulse" size={20} />
        </div>
      )
    }
    
    if (extraction.status === 'auto_processed' || extraction.confidence > 0.9) {
      return <CheckCircle className="text-green-400" size={20} />
    } else if (extraction.confidence > 0.75) {
      return <AlertCircle className="text-yellow-400" size={20} />
    } else {
      return <AlertCircle className="text-red-400" size={20} />
    }
  }

  const getStatusText = (status: string) => {
    const statusMap: Record<string, string> = {
      auto_processed: 'Auto Processed',
      pending_review: 'Pending Review',
      requires_manual: 'Manual Review',
    }
    return statusMap[status] || status
  }

  if (loading) {
    return (
      <div className="min-h-screen p-8 flex items-center justify-center">
        <div className="text-gray-400">Loading extractions...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Extractions</h1>
          <p className="text-gray-400">View all document extraction results and LLM outputs</p>
        </div>

        {/* Extractions List */}
        <div className="mb-6">
          <div className="bg-dark-surface border border-dark-border rounded-lg">
            <div className="p-4 border-b border-dark-border">
              <h2 className="font-semibold text-white">
                All Extractions ({extractions.length})
              </h2>
            </div>
            <div className="overflow-x-auto">
              {extractions.length === 0 ? (
                <div className="p-8 text-center text-gray-500">
                  <FileText className="mx-auto mb-3" size={48} />
                  <p>No extractions yet</p>
                  <p className="text-sm mt-1">Upload an email to get started</p>
                </div>
              ) : (
                <div className="flex gap-2 p-4">
                  {extractions.map((extraction) => (
                    <button
                      key={extraction.id}
                      onClick={() => setSelectedExtraction(extraction)}
                      className={`
                        flex-shrink-0 px-4 py-3 rounded-lg border transition-colors
                        ${
                          selectedExtraction?.id === extraction.id
                            ? 'bg-dark-hover border-blue-500'
                            : 'bg-dark-bg border-dark-border hover:border-gray-600'
                        }
                      `}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        {getStatusIcon(extraction)}
                        <span className="font-medium text-white text-sm">
                          #{extraction.id}
                        </span>
                        <span className="text-xs font-medium text-blue-400">
                          {(extraction.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                      {extraction.processing_status === 'processing' && (
                        <div className="text-xs text-blue-400">Processing...</div>
                      )}
                      <div className="text-xs text-gray-500">
                        {new Date(extraction.created_at).toLocaleDateString()}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-6">
          {/* Left: Document Preview & Details */}
          <div>
            {selectedExtraction ? (
              <div className="space-y-6">
                {/* Header Info */}
                <div className="bg-dark-surface border border-dark-border rounded-lg p-6">
                  <div className="mb-4">
                    <h2 className="text-xl font-bold text-white mb-1">
                      Extraction #{selectedExtraction.id}
                    </h2>
                    <p className="text-gray-400 text-sm truncate">{selectedExtraction.email_id}</p>
                  </div>
                  <div className="grid grid-cols-4 gap-4 text-sm">
                    <div>
                      <div className="text-gray-400 mb-1">Status</div>
                      <div className="flex items-center gap-2">
                        <div className="text-white font-medium">
                          {getStatusText(selectedExtraction.status)}
                        </div>
                        {selectedExtraction.processing_status === 'processing' && (
                          <div className="flex items-center gap-1 text-xs text-blue-400">
                            <Clock size={12} className="animate-pulse" />
                            <span>Processing...</span>
                          </div>
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-400 mb-1">Verified</div>
                      <div className="text-white font-medium">
                        {selectedExtraction.verified ? 'Yes' : 'No'}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-400 mb-1">Confidence</div>
                      <div className="text-green-400 font-bold text-lg">
                        {(selectedExtraction.confidence * 100).toFixed(0)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-400 mb-1">Date</div>
                      <div className="text-white font-medium text-xs">
                        {new Date(selectedExtraction.created_at).toLocaleString()}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Document Preview */}
                <div className="bg-dark-surface border border-dark-border rounded-lg">
                  <div className="p-4 border-b border-dark-border">
                    <h3 className="font-semibold text-white">Document Preview</h3>
                  </div>
                  <div className="p-4">
                    <div className="bg-dark-bg rounded-lg border border-dark-border overflow-hidden">
                      <img
                        src={`/api/document/${selectedExtraction.id}`}
                        alt="Document"
                        className="w-full h-auto"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none'
                          e.currentTarget.nextElementSibling!.classList.remove('hidden')
                        }}
                      />
                      <div className="hidden p-8 text-center text-gray-500">
                        <FileText className="mx-auto mb-2" size={48} />
                        <p>Document preview not available</p>
                        <p className="text-xs mt-1">{selectedExtraction.document_path}</p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Verification Report & Issues */}
                {selectedExtraction.verification_report && Object.keys(selectedExtraction.verification_report).length > 0 && (
                  <div className="bg-dark-surface border border-dark-border rounded-lg">
                    <div className="p-4 border-b border-dark-border">
                      <h3 className="font-semibold text-white">Verification Report (Audit Trail)</h3>
                    </div>
                    <div className="p-4 space-y-4">
                      {/* Overall Assessment */}
                      {selectedExtraction.verification_report.overall_assessment && (
                        <div>
                          <div className="text-xs text-gray-400 mb-1">Assessment</div>
                          <div className="text-sm text-gray-300">
                            {selectedExtraction.verification_report.overall_assessment}
                          </div>
                        </div>
                      )}

                      {/* Issues */}
                      {selectedExtraction.verification_report.issues?.length > 0 && (
                        <div>
                          <div className="text-xs text-gray-400 mb-2">Issues Found</div>
                          <div className="space-y-2">
                            {selectedExtraction.verification_report.issues.map((issue: any, idx: number) => (
                              <div
                                key={idx}
                                className={`p-3 rounded border text-sm ${
                                  issue.severity === 'high'
                                    ? 'bg-red-500/10 border-red-500/20 text-red-300'
                                    : issue.severity === 'medium'
                                    ? 'bg-yellow-500/10 border-yellow-500/20 text-yellow-300'
                                    : 'bg-blue-500/10 border-blue-500/20 text-blue-300'
                                }`}
                              >
                                <div className="font-medium mb-1">
                                  [{issue.severity?.toUpperCase()}] {issue.field}
                                </div>
                                <div className="text-xs opacity-80">{issue.description}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Statistics */}
                      {selectedExtraction.verification_report.statistics && (
                        <div>
                          <div className="text-xs text-gray-400 mb-2">Verification Stats</div>
                          <div className="grid grid-cols-4 gap-3 text-xs">
                            <div className="bg-dark-bg p-2 rounded">
                              <div className="text-gray-400">Checked</div>
                              <div className="text-white font-medium">
                                {selectedExtraction.verification_report.statistics.total_fields_checked || 0}
                              </div>
                            </div>
                            <div className="bg-dark-bg p-2 rounded">
                              <div className="text-green-400">Correct</div>
                              <div className="text-white font-medium">
                                {selectedExtraction.verification_report.statistics.correct_fields || 0}
                              </div>
                            </div>
                            <div className="bg-dark-bg p-2 rounded">
                              <div className="text-red-400">Incorrect</div>
                              <div className="text-white font-medium">
                                {selectedExtraction.verification_report.statistics.incorrect_fields || 0}
                              </div>
                            </div>
                            <div className="bg-dark-bg p-2 rounded">
                              <div className="text-yellow-400">Missing</div>
                              <div className="text-white font-medium">
                                {selectedExtraction.verification_report.statistics.missing_fields || 0}
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Audit Trail Info */}
                      <div className="pt-4 border-t border-dark-border">
                        <div className="text-xs text-gray-400 mb-2">Audit Information</div>
                        <div className="grid grid-cols-2 gap-3 text-xs">
                          {selectedExtraction.document_hash && (
                            <div>
                              <span className="text-gray-500">Document Hash:</span>{' '}
                              <span className="text-gray-300 font-mono">{selectedExtraction.document_hash.substring(0, 16)}...</span>
                            </div>
                          )}
                          {selectedExtraction.issues_count !== undefined && (
                            <div>
                              <span className="text-gray-500">Issues Count:</span>{' '}
                              <span className="text-white font-medium">{selectedExtraction.issues_count}</span>
                            </div>
                          )}
                          {selectedExtraction.review_priority && (
                            <div>
                              <span className="text-gray-500">Review Priority:</span>{' '}
                              <span className={`font-medium ${
                                selectedExtraction.review_priority === 'high' ? 'text-red-400' :
                                selectedExtraction.review_priority === 'medium' ? 'text-yellow-400' :
                                'text-green-400'
                              }`}>{selectedExtraction.review_priority.toUpperCase()}</span>
                            </div>
                          )}
                          {selectedExtraction.reviewed_by && (
                            <div>
                              <span className="text-gray-500">Reviewed By:</span>{' '}
                              <span className="text-white font-medium">{selectedExtraction.reviewed_by}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

              </div>
            ) : (
              <div className="bg-dark-surface border border-dark-border rounded-lg p-12 text-center">
                <ChevronRight className="mx-auto mb-4 text-gray-600" size={48} />
                <p className="text-gray-400">Select an extraction to view details</p>
              </div>
            )}
          </div>

          {/* Right: Tabs for different views */}
          <div>
            {selectedExtraction ? (
              <ExtractionTabs extraction={selectedExtraction} />
            ) : (
              <div className="bg-dark-surface border border-dark-border rounded-lg p-12 text-center h-full flex items-center justify-center">
                <div>
                  <Code className="mx-auto mb-4 text-gray-600" size={48} />
                  <p className="text-gray-400">Select an extraction to view details</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

