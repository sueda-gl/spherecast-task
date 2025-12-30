import { Database, Edit3, PlusCircle, Eye, Brain, AlertTriangle } from 'lucide-react'
import { useState } from 'react'

interface DatabaseUpdate {
  id: number
  table: string
  record_id: number
  operation: string
  field: string | null
  old_value: string | null
  new_value: string | null
  confidence: number
  llm_reasoning: string
  requires_approval?: boolean
  approved?: boolean
}

interface UpdateDetailsModalProps {
  update: DatabaseUpdate | null
  onClose: () => void
  documentPath?: string
}

function UpdateDetailsModal({ update, onClose, documentPath }: UpdateDetailsModalProps) {
  if (!update) return null

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="bg-dark-surface border border-dark-border rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-dark-border">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-xl font-bold text-white mb-1">Update Details</h2>
              <p className="text-sm text-gray-400">
                {update.operation === 'create' ? 'Record Created' : 'Record Updated'} in {update.table}
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Change Summary */}
          <div className="bg-dark-bg border border-dark-border rounded-lg p-4">
            <h3 className="text-sm font-semibold text-white mb-3">Change Summary</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-400">Table:</span>
                <span className="text-white font-mono">{update.table}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Record ID:</span>
                <span className="text-white font-mono">#{update.record_id}</span>
              </div>
              {update.field && (
                <div className="flex justify-between">
                  <span className="text-gray-400">Field:</span>
                  <span className="text-white font-mono">{update.field}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-gray-400">Operation:</span>
                <span className={`font-medium ${
                  update.operation === 'create' ? 'text-green-400' : 'text-blue-400'
                }`}>
                  {update.operation.toUpperCase()}
                </span>
              </div>
            </div>
          </div>

          {/* Value Changes */}
          {update.operation === 'update' && (
            <div className="bg-dark-bg border border-dark-border rounded-lg p-4">
              <h3 className="text-sm font-semibold text-white mb-3">Value Changes</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs text-gray-400 mb-2">Old Value</div>
                  <div className="bg-red-500/10 border border-red-500/20 rounded p-3">
                    <pre className="text-xs text-red-300 font-mono overflow-x-auto">
                      {update.old_value ? JSON.stringify(JSON.parse(update.old_value), null, 2) : 'null'}
                    </pre>
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-2">New Value</div>
                  <div className="bg-green-500/10 border border-green-500/20 rounded p-3">
                    <pre className="text-xs text-green-300 font-mono overflow-x-auto">
                      {update.new_value ? JSON.stringify(JSON.parse(update.new_value), null, 2) : 'null'}
                    </pre>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* LLM Reasoning */}
          <div className="bg-dark-bg border border-dark-border rounded-lg p-4">
            <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
              <Brain size={16} className="text-purple-400" />
              LLM Reasoning (Audit Trail)
            </h3>
            
            {/* Parse and format the reasoning */}
            <div className="space-y-3">
              {update.llm_reasoning?.split('\n\n').map((section, idx) => (
                <div key={idx} className="bg-dark-surface/50 rounded p-3 border border-dark-border/50">
                  {section.includes('Step ') ? (
                    <div className="text-xs">
                      <span className="text-purple-400 font-medium">{section.split(':')[0]}:</span>
                      <span className="text-gray-300">{section.split(':').slice(1).join(':')}</span>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
                      {section}
                    </p>
                  )}
                </div>
              ))}
            </div>

            {/* Confidence indicator */}
            <div className="mt-4 pt-3 border-t border-dark-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="text-xs text-gray-400">LLM Confidence:</div>
                <div className={`text-sm font-bold ${
                  update.confidence > 0.9 ? 'text-green-400' :
                  update.confidence > 0.75 ? 'text-yellow-400' :
                  'text-red-400'
                }`}>
                  {(update.confidence * 100).toFixed(0)}%
                </div>
              </div>
              {update.confidence < 0.9 && (
                <div className="flex items-center gap-1 text-xs text-yellow-400">
                  <AlertTriangle size={12} />
                  <span>May need review</span>
                </div>
              )}
            </div>
          </div>

          {/* Source Document */}
          {documentPath && (
            <div className="bg-dark-bg border border-dark-border rounded-lg overflow-hidden">
              <div className="p-4 border-b border-dark-border">
                <h3 className="text-sm font-semibold text-white">Source Document</h3>
                <p className="text-xs text-gray-400 mt-1">
                  This change originated from this section of the document
                </p>
              </div>
              <div className="p-4">
                <img
                  src={`/api/document/${update.id}`}
                  alt="Source document"
                  className="w-full rounded border border-dark-border"
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-4 border-t border-dark-border bg-dark-bg/50">
          <button
            onClick={onClose}
            className="w-full px-4 py-2 bg-dark-surface hover:bg-dark-hover border border-dark-border rounded text-white transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

interface DatabaseUpdatesProps {
  updates: DatabaseUpdate[]
  documentPath?: string
}

export default function DatabaseUpdates({ updates, documentPath }: DatabaseUpdatesProps) {
  const [selectedUpdate, setSelectedUpdate] = useState<DatabaseUpdate | null>(null)

  if (!updates || updates.length === 0) {
    return (
      <div className="bg-dark-surface border border-dark-border rounded-lg p-8 text-center">
        <Database className="mx-auto mb-3 text-gray-600" size={48} />
        <p className="text-gray-400">No database updates</p>
        <p className="text-xs text-gray-500 mt-1">
          No changes were made to the database
        </p>
      </div>
    )
  }

  return (
    <>
      <div className="bg-dark-surface border border-dark-border rounded-lg overflow-hidden">
        <div className="p-4 border-b border-dark-border bg-dark-bg/50">
          <div className="flex items-center gap-2">
            <Database className="text-blue-400" size={20} />
            <h3 className="font-semibold text-white">Database Changes</h3>
            <span className="text-xs text-gray-500 ml-auto">
              {updates.length} {updates.length === 1 ? 'change' : 'changes'}
            </span>
          </div>
        </div>

        <div className="divide-y divide-dark-border">
          {updates.map((update) => (
            <div
              key={update.id}
              className="p-4 hover:bg-dark-hover/30 transition-colors"
            >
              <div className="flex items-start gap-3">
                {/* Icon */}
                <div className="flex-shrink-0">
                  {update.operation === 'create' ? (
                    <PlusCircle className="text-green-400" size={18} />
                  ) : (
                    <Edit3 className="text-blue-400" size={18} />
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-white">
                      {update.operation === 'create' ? 'Created' : 'Updated'}: {update.table}
                    </span>
                    <span className="text-xs text-gray-500">
                      #{update.record_id}
                    </span>
                    {update.confidence && (
                      <span className={`text-xs font-medium ${
                        update.confidence > 0.9 ? 'text-green-400' :
                        update.confidence > 0.75 ? 'text-yellow-400' :
                        'text-red-400'
                      }`}>
                        {(update.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>

                  {update.field && (
                    <div className="text-xs text-gray-400 mb-2">
                      Field: <span className="text-gray-300 font-mono">{update.field}</span>
                    </div>
                  )}

                  {/* Show change preview for updates */}
                  {update.operation === 'update' && update.old_value && update.new_value && (
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-red-300 font-mono truncate max-w-[200px]">
                        {update.old_value.replace(/^"|"$/g, '')}
                      </span>
                      <span className="text-gray-500">→</span>
                      <span className="text-green-300 font-mono truncate max-w-[200px]">
                        {update.new_value.replace(/^"|"$/g, '')}
                      </span>
                    </div>
                  )}
                </div>

                {/* View Details Button */}
                <button
                  onClick={() => setSelectedUpdate(update)}
                  className="flex-shrink-0 p-2 hover:bg-dark-bg rounded transition-colors text-gray-400 hover:text-white"
                  title="View details and source"
                >
                  <Eye size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Update Details Modal */}
      {selectedUpdate && (
        <UpdateDetailsModal
          update={selectedUpdate}
          onClose={() => setSelectedUpdate(null)}
          documentPath={documentPath}
        />
      )}
    </>
  )
}

