import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, Mail, CheckCircle, AlertCircle, Loader2, FileText, Database } from 'lucide-react'
import type { ProcessingState } from '../App'

interface UploadPageProps {
  onNavigateToExtractions?: () => void
  processingState: ProcessingState
  setProcessingState: React.Dispatch<React.SetStateAction<ProcessingState>>
  startPolling: (extractionId: number) => void
}

export default function UploadPage({ 
  onNavigateToExtractions, 
  processingState,
  setProcessingState,
  startPolling 
}: UploadPageProps) {
  const [emailFile, setEmailFile] = useState<File | null>(null)

  // Use the processing state from App.tsx
  const status = processingState

  const handleUpload = useCallback(async (file: File) => {
    setProcessingState({ type: 'uploading', message: 'Extracting data from document...' })

    try {
      const formData = new FormData()
      formData.append('email_file', file)

      const response = await fetch('/api/process-email', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Processing failed')
      }

      const data = await response.json()

      // If status is 'processing', the database is being updated in background
      if (data.status === 'processing') {
        setProcessingState({
          type: 'processing_db',
          message: 'Extraction complete! Updating database...',
          result: data,
          processingStatus: 'processing',
          extractionId: data.extraction_id
        })

        // Start polling for status updates (handled at App level, persists across pages)
        startPolling(data.extraction_id)

      } else {
        // Not auto-processing (pending review)
        setProcessingState({
          type: 'success',
          message: `Extraction complete! ${data.message || ''}`,
          result: data,
          processingStatus: 'extracted',
          extractionId: data.extraction_id
        })

        // Navigate to extractions page after 2 seconds
        setTimeout(() => {
          if (onNavigateToExtractions) {
            onNavigateToExtractions()
          }
        }, 2000)
      }
    } catch (error) {
      setProcessingState({
        type: 'error',
        message: error instanceof Error ? error.message : 'Processing failed',
      })
    }
  }, [setProcessingState, startPolling, onNavigateToExtractions])

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      const file = acceptedFiles[0]
      setEmailFile(file)
      // Auto-submit when file is dropped
      handleUpload(file)
    }
  }, [handleUpload])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'message/rfc822': ['.eml'],
      'application/octet-stream': ['.eml'],
    },
    maxFiles: 1,
  })

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (emailFile) {
      handleUpload(emailFile)
    }
  }

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Upload Purchase Order Email</h1>
          <p className="text-gray-400">
            Drop your .eml file here - we'll automatically extract the email body and attached document
          </p>
        </div>

        {/* Main Upload Area */}
        <form onSubmit={handleManualSubmit} className="space-y-6">
          <div className="bg-dark-surface border border-dark-border rounded-lg p-8">
            <div
              {...getRootProps()}
              className={`
                border-2 border-dashed rounded-lg p-16 text-center cursor-pointer transition-all
                ${
                  isDragActive
                    ? 'border-blue-500 bg-blue-500/10'
                    : emailFile
                    ? 'border-green-500/50 bg-green-500/5'
                    : 'border-dark-border hover:border-gray-600 bg-dark-bg'
                }
              `}
            >
              <input {...getInputProps()} />
              <div className="flex flex-col items-center gap-6">
                <div className={`w-20 h-20 rounded-full flex items-center justify-center ${
                  emailFile ? 'bg-green-500/20' : 'bg-dark-border'
                }`}>
                  {emailFile ? (
                    <Mail className="text-green-400" size={40} />
                  ) : (
                    <Upload className="text-gray-400" size={40} />
                  )}
                </div>
                
                {emailFile ? (
                  <>
                    <div className="text-center">
                      <div className="text-green-400 flex items-center justify-center gap-2 mb-2">
                        <CheckCircle size={24} />
                        <span className="font-semibold text-lg">{emailFile.name}</span>
                      </div>
                      <p className="text-sm text-gray-400">
                        {(emailFile.size / 1024).toFixed(1)} KB
                      </p>
                    </div>
                    <p className="text-sm text-gray-500">Click or drag to replace</p>
                  </>
                ) : (
                  <>
                    <div className="text-center">
                      <p className="text-white font-semibold text-xl mb-2">
                        Drop your .eml file here
                      </p>
                      <p className="text-gray-400 mb-1">
                        or click to browse
                      </p>
                      <p className="text-sm text-gray-500">
                        Email files containing purchase order attachments
                      </p>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Info */}
            <div className="mt-6 flex items-start gap-3 text-sm text-gray-400">
              <FileText className="flex-shrink-0 mt-0.5" size={16} />
              <p>
                The system will automatically extract the email body and any attached documents (PDF, images), 
                then process them through the LLM extraction pipeline.
              </p>
            </div>
          </div>

          {/* Status Message */}
          {status.type !== 'idle' && (
            <div
              className={`
                rounded-lg p-4 flex items-start gap-3
                ${status.type === 'success' ? 'bg-green-500/10 border border-green-500/20' : ''}
                ${status.type === 'error' ? 'bg-red-500/10 border border-red-500/20' : ''}
                ${status.type === 'uploading' ? 'bg-blue-500/10 border border-blue-500/20' : ''}
                ${status.type === 'processing_db' ? 'bg-amber-500/10 border border-amber-500/20' : ''}
              `}
            >
              {status.type === 'uploading' && (
                <Loader2 className="text-blue-400 animate-spin flex-shrink-0" size={20} />
              )}
              {status.type === 'processing_db' && (
                <Database className="text-amber-400 animate-pulse flex-shrink-0" size={20} />
              )}
              {status.type === 'success' && (
                <CheckCircle className="text-green-400 flex-shrink-0" size={20} />
              )}
              {status.type === 'error' && (
                <AlertCircle className="text-red-400 flex-shrink-0" size={20} />
              )}
              <div className="flex-1">
                <p
                  className={`
                  font-medium
                  ${status.type === 'success' ? 'text-green-400' : ''}
                  ${status.type === 'error' ? 'text-red-400' : ''}
                  ${status.type === 'uploading' ? 'text-blue-400' : ''}
                  ${status.type === 'processing_db' ? 'text-amber-400' : ''}
                `}
                >
                  {status.message}
                </p>
                {status.result && (
                  <>
                    <div className="mt-3 text-sm text-gray-300 space-y-1">
                      <p>Confidence: <span className="text-white font-medium">{(status.result.confidence * 100).toFixed(1)}%</span></p>
                      <p>Verified: <span className="text-white font-medium">{status.result.verified ? 'Yes ✓' : 'No'}</span></p>
                      <p>Extraction ID: <span className="text-white font-medium">#{status.result.extraction_id}</span></p>
                    </div>
                    
                    {/* Database Update Progress */}
                    {status.type === 'processing_db' && (
                      <div className="mt-4 space-y-3">
                        <div className="flex items-center gap-3 text-sm text-amber-300 bg-amber-500/10 p-3 rounded border border-amber-500/20">
                          <Loader2 size={16} className="animate-spin flex-shrink-0" />
                          <div>
                            <p className="font-medium">Updating Database</p>
                            <p className="text-xs text-amber-200/70 mt-0.5">
                              Master LLM is analyzing extraction and updating records...
                            </p>
                          </div>
                        </div>
                        
                        {/* Progress Steps */}
                        <div className="flex items-center gap-2 text-xs text-gray-400">
                          <div className="flex items-center gap-1.5">
                            <CheckCircle size={12} className="text-green-400" />
                            <span>Extracted</span>
                          </div>
                          <div className="w-4 h-px bg-gray-600" />
                          <div className="flex items-center gap-1.5">
                            <CheckCircle size={12} className="text-green-400" />
                            <span>Verified</span>
                          </div>
                          <div className="w-4 h-px bg-gray-600" />
                          <div className="flex items-center gap-1.5 text-amber-400">
                            <Loader2 size={12} className="animate-spin" />
                            <span>Updating DB</span>
                          </div>
                        </div>
                      </div>
                    )}
                    
                    {status.type === 'success' && status.processingStatus === 'completed' && (
                      <div className="mt-3 flex items-center gap-2 text-xs text-green-300 bg-green-500/10 p-3 rounded border border-green-500/20">
                        <CheckCircle size={14} />
                        <span>Database updated successfully!</span>
                      </div>
                    )}
                    
                    {status.type === 'success' && (
                      <p className="mt-3 text-xs text-gray-400">
                        Redirecting to extractions page in 2 seconds...
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          {/* Manual Submit Button (if auto-submit didn't work) */}
          {emailFile && status.type === 'idle' && (
            <button
              type="submit"
              className="w-full py-4 rounded-lg font-medium text-white bg-blue-600 hover:bg-blue-700 active:scale-[0.99] transition-all"
            >
              Process Email
            </button>
          )}
        </form>

        {/* Info Card */}
        <div className="mt-8">
          <div className="bg-dark-surface border border-dark-border rounded-lg p-5 flex items-start gap-4">
            <div className="text-3xl font-bold text-green-400 whitespace-nowrap">{">"} 90%</div>
            <div className="text-sm text-gray-400 leading-relaxed">
              When the extraction accuracy score is higher than 90%, the data will be <span className="text-white font-medium">automatically processed</span> and the database will be <span className="text-white font-medium">updated without manual review</span>.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

