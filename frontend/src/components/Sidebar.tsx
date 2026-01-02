import { Upload, Database, Eye, Loader2 } from 'lucide-react'
import type { ProcessingState } from '../App'

interface SidebarProps {
  currentPage: string
  onNavigate: (page: 'upload' | 'extractions' | 'database') => void
  processingState?: ProcessingState
}

export default function Sidebar({ currentPage, onNavigate, processingState }: SidebarProps) {
  const isProcessing = processingState?.type === 'processing_db'
  
  const navItems = [
    { name: 'Upload', icon: <Upload size={18} />, page: 'upload' as const },
    { name: 'Extractions', icon: <Eye size={18} />, page: 'extractions' as const },
    { name: 'Database', icon: <Database size={18} />, page: 'database' as const },
  ]

  return (
    <aside className="fixed left-0 top-0 h-screen w-64 bg-dark-surface border-r border-dark-border flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-dark-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
            <span className="text-white font-bold text-sm">S</span>
          </div>
          <h1 className="text-xl font-semibold text-white">Spherecast</h1>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4">
        <ul className="space-y-1 px-3">
          {navItems.map((item) => {
            const isActive = item.page === currentPage
            const isDisabled = item.page === null
            const showProcessingIndicator = item.page === 'upload' && isProcessing
            
            return (
              <li key={item.name}>
                <button
                  onClick={() => item.page && onNavigate(item.page)}
                  disabled={isDisabled}
                  className={`
                    w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors text-left
                    ${
                      isActive
                        ? 'bg-dark-hover text-white font-medium'
                        : isDisabled
                        ? 'text-gray-600 cursor-not-allowed'
                        : 'text-gray-400 hover:text-white hover:bg-dark-hover'
                    }
                    ${showProcessingIndicator && !isActive ? 'bg-amber-500/10 border border-amber-500/30' : ''}
                  `}
                >
                  <span className={isActive ? 'text-blue-400' : showProcessingIndicator ? 'text-amber-400' : ''}>
                    {showProcessingIndicator ? <Loader2 size={18} className="animate-spin" /> : item.icon}
                  </span>
                  <span className="flex-1">{item.name}</span>
                  {showProcessingIndicator && (
                    <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      </nav>
      
      {/* Processing Status in Sidebar */}
      {isProcessing && (
        <div className="px-3 pb-4">
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3">
            <div className="flex items-center gap-2 text-amber-400 text-xs font-medium mb-1">
              <Loader2 size={12} className="animate-spin" />
              <span>Database Updating</span>
            </div>
            <p className="text-[10px] text-amber-300/70">
              Extraction #{processingState?.extractionId || processingState?.result?.extraction_id}
            </p>
          </div>
        </div>
      )}
    </aside>
  )
}

