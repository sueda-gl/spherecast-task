import { useState, useEffect, useRef, useCallback } from 'react'
import Sidebar from './components/Sidebar'
import UploadPage from './components/UploadPage'
import ExtractionsPage from './components/ExtractionsPage'
import DatabasePage from './components/DatabasePage'

type Page = 'upload' | 'extractions' | 'database'

export interface ProcessingState {
  type: 'idle' | 'uploading' | 'processing_db' | 'success' | 'error'
  message?: string
  result?: any
  processingStatus?: 'extracted' | 'processing' | 'completed' | 'failed'
  extractionId?: number
}

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('upload')
  
  // Lifted processing state - persists across page navigations
  const [processingState, setProcessingState] = useState<ProcessingState>({ type: 'idle' })
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Poll for processing status updates
  const pollForStatus = useCallback(async (extractionId: number) => {
    try {
      const response = await fetch(`/api/extraction/${extractionId}`)
      if (!response.ok) return

      const data = await response.json()
      const extraction = data.extraction
      const processingStatus = extraction?.processing_status

      if (processingStatus === 'processing') {
        setProcessingState(prev => ({
          ...prev,
          type: 'processing_db',
          message: 'Updating database...',
          processingStatus: 'processing'
        }))
      } else if (processingStatus === 'completed') {
        // Stop polling
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
        
        setProcessingState(prev => ({
          ...prev,
          type: 'success',
          message: 'Extraction complete! Database updated successfully.',
          processingStatus: 'completed'
        }))

        // Auto-reset after showing success
        setTimeout(() => {
          setProcessingState({ type: 'idle' })
        }, 5000)
      } else if (processingStatus === 'failed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
        
        setProcessingState(prev => ({
          ...prev,
          type: 'error',
          message: 'Database update failed. Please check the extraction details.',
          processingStatus: 'failed'
        }))
      }
    } catch (error) {
      console.error('Error polling status:', error)
    }
  }, [])

  // Start polling for a specific extraction
  const startPolling = useCallback((extractionId: number) => {
    // Clear any existing polling
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
    }
    
    pollingRef.current = setInterval(() => {
      pollForStatus(extractionId)
    }, 1500)
  }, [pollForStatus])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
      }
    }
  }, [])

  const handleNavigateToExtractions = useCallback(() => {
    setCurrentPage('extractions')
  }, [])

  return (
    <div className="flex min-h-screen bg-dark-bg">
      <Sidebar 
        currentPage={currentPage} 
        onNavigate={setCurrentPage}
        processingState={processingState}
      />
      <main className="flex-1 ml-64">
        {currentPage === 'upload' && (
          <UploadPage 
            onNavigateToExtractions={handleNavigateToExtractions}
            processingState={processingState}
            setProcessingState={setProcessingState}
            startPolling={startPolling}
          />
        )}
        {currentPage === 'extractions' && <ExtractionsPage />}
        {currentPage === 'database' && <DatabasePage />}
      </main>
      
      {/* Global Processing Indicator - visible on all pages */}
      {processingState.type === 'processing_db' && currentPage !== 'upload' && (
        <div className="fixed bottom-4 right-4 z-50">
          <div className="bg-dark-surface border border-amber-500/30 rounded-lg p-4 shadow-xl max-w-sm">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-amber-500/20 flex items-center justify-center">
                <svg className="w-4 h-4 text-amber-400 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              </div>
              <div>
                <p className="text-amber-400 font-medium text-sm">Database Update in Progress</p>
                <p className="text-gray-400 text-xs mt-0.5">
                  Extraction #{processingState.extractionId || processingState.result?.extraction_id}
                </p>
              </div>
            </div>
            <button 
              onClick={() => setCurrentPage('upload')}
              className="mt-3 w-full text-xs text-center py-1.5 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 rounded text-amber-300 transition-colors"
            >
              View Progress
            </button>
          </div>
        </div>
      )}
      
      {/* Success notification - visible on all pages */}
      {processingState.type === 'success' && processingState.processingStatus === 'completed' && currentPage !== 'upload' && (
        <div className="fixed bottom-4 right-4 z-50">
          <div className="bg-dark-surface border border-green-500/30 rounded-lg p-4 shadow-xl max-w-sm">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center">
                <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <div>
                <p className="text-green-400 font-medium text-sm">Database Updated!</p>
                <p className="text-gray-400 text-xs mt-0.5">
                  Extraction #{processingState.extractionId || processingState.result?.extraction_id} completed
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App

