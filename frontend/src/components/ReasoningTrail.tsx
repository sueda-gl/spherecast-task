import { ChevronDown, ChevronRight, Brain, Database, CheckCircle, XCircle } from 'lucide-react'
import { useState } from 'react'

interface ToolCall {
  iteration: number
  tool: string
  arguments: Record<string, any>
  result: any
  type?: string
  content?: string
}

interface ReasoningTrailProps {
  reasoning?: ToolCall[]
  operations?: any[]
  summary?: string
  confidence?: number
}

export default function ReasoningTrail({ reasoning, operations, summary, confidence }: ReasoningTrailProps) {
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set([0]))

  const toggleStep = (index: number) => {
    const newExpanded = new Set(expandedSteps)
    if (newExpanded.has(index)) {
      newExpanded.delete(index)
    } else {
      newExpanded.add(index)
    }
    setExpandedSteps(newExpanded)
  }

  if (!reasoning || reasoning.length === 0) {
    return (
      <div className="bg-dark-surface border border-dark-border rounded-lg p-8 text-center">
        <Brain className="mx-auto mb-3 text-gray-600" size={48} />
        <p className="text-gray-400">No reasoning trail available</p>
        <p className="text-xs text-gray-500 mt-1">
          Processing may not have started yet
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Summary Card */}
      {summary && (
        <div className="bg-gradient-to-br from-blue-500/10 to-purple-500/10 border border-blue-500/20 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <CheckCircle className="text-blue-400 flex-shrink-0 mt-0.5" size={20} />
            <div className="flex-1">
              <div className="text-sm font-medium text-white mb-1">LLM Summary</div>
              <div className="text-sm text-gray-300">{summary}</div>
              {confidence && (
                <div className="mt-2 text-xs text-blue-400">
                  Confidence: {(confidence * 100).toFixed(0)}%
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Reasoning Steps */}
      <div className="bg-dark-surface border border-dark-border rounded-lg overflow-hidden">
        <div className="p-4 border-b border-dark-border bg-dark-bg/50">
          <div className="flex items-center gap-2">
            <Brain className="text-purple-400" size={20} />
            <h3 className="font-semibold text-white">LLM Reasoning Trail</h3>
            <span className="text-xs text-gray-500 ml-auto">
              {reasoning.length} steps
            </span>
          </div>
        </div>

        <div className="divide-y divide-dark-border">
          {reasoning.map((step, index) => {
            const isExpanded = expandedSteps.has(index)
            // Handle both formats: {tool: "...", type: "..."} or just {type: "..."}
            const toolName = step.tool || step.type || 'unknown'
            const isWrite = toolName === 'create_record' || toolName === 'update_record'
            const isRead = toolName === 'search_records' || toolName === 'get_record' || toolName === 'get_column_values'
            const isDiscovery = toolName === 'list_tables' || toolName === 'describe_table'
            const isFinalResponse = step.type === 'final_response'

            return (
              <div key={index} className="hover:bg-dark-hover/30 transition-colors">
                <button
                  onClick={() => toggleStep(index)}
                  className="w-full p-4 text-left"
                >
                  <div className="flex items-start gap-3">
                    {/* Step Number */}
                    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-dark-bg border border-dark-border flex items-center justify-center text-xs font-medium text-gray-400">
                      {index + 1}
                    </div>

                    {/* Tool Icon */}
                    <div className="flex-shrink-0">
                      {isFinalResponse && <CheckCircle className="text-green-400" size={18} />}
                      {!isFinalResponse && isWrite && <Database className="text-green-400" size={18} />}
                      {!isFinalResponse && isRead && <Database className="text-blue-400" size={18} />}
                      {!isFinalResponse && isDiscovery && <Database className="text-purple-400" size={18} />}
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-sm font-medium ${
                          isFinalResponse ? 'text-green-400' :
                          isWrite ? 'text-green-400' :
                          isRead ? 'text-blue-400' :
                          'text-purple-400'
                        }`}>
                          {isFinalResponse ? 'Final Response' : toolName}
                        </span>
                        {step.result?.success !== undefined && (
                          step.result.success ? (
                            <CheckCircle size={14} className="text-green-400" />
                          ) : (
                            <XCircle size={14} className="text-red-400" />
                          )
                        )}
                      </div>

                      {/* Arguments Preview */}
                      <div className="text-xs text-gray-400 truncate">
                        {step.arguments && Object.keys(step.arguments).length > 0 
                          ? JSON.stringify(step.arguments).substring(0, 80) + '...'
                          : 'No arguments'
                        }
                      </div>

                      {/* Result Preview */}
                      {step.result && (
                        <div className="text-xs text-gray-500 mt-1">
                          {step.result.error ? (
                            <span className="text-red-400">Error: {step.result.error}</span>
                          ) : step.result.found !== undefined ? (
                            <span>Found: {step.result.found} records</span>
                          ) : step.result.success ? (
                            <span className="text-green-400">✓ Success</span>
                          ) : (
                            <span>Completed</span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Expand/Collapse Icon */}
                    <div className="flex-shrink-0">
                      {isExpanded ? (
                        <ChevronDown size={18} className="text-gray-400" />
                      ) : (
                        <ChevronRight size={18} className="text-gray-400" />
                      )}
                    </div>
                  </div>
                </button>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="px-4 pb-4 pl-16 space-y-3">
                    {/* Arguments */}
                    {step.arguments && (
                      <div>
                        <div className="text-xs font-medium text-gray-400 mb-1">Arguments</div>
                        <pre className="text-xs text-gray-300 bg-dark-bg p-3 rounded border border-dark-border overflow-x-auto">
                          {JSON.stringify(step.arguments, null, 2)}
                        </pre>
                      </div>
                    )}

                    {/* Result or Content */}
                    {(step.result || step.content) && (
                      <div>
                        <div className="text-xs font-medium text-gray-400 mb-1">
                          {step.result ? 'Result' : 'Content'}
                        </div>
                        <pre className="text-xs text-gray-300 bg-dark-bg p-3 rounded border border-dark-border overflow-x-auto max-h-64 overflow-y-auto">
                          {JSON.stringify(step.result || step.content, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Operations Summary */}
      {operations && operations.length > 0 && (
        <div className="bg-dark-surface border border-dark-border rounded-lg">
          <div className="p-4 border-b border-dark-border">
            <h3 className="font-semibold text-white">Database Operations</h3>
          </div>
          <div className="p-4">
            <div className="space-y-2">
              {operations.map((op, idx) => (
                <div key={idx} className="flex items-start gap-3 p-3 bg-dark-bg rounded border border-dark-border">
                  <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-500/20 border border-blue-500/30 flex items-center justify-center text-xs text-blue-400">
                    {op.step || idx + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-white font-medium mb-1">
                      {op.action} → {op.table}
                    </div>
                    <div className="text-xs text-gray-400">
                      {op.result}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

