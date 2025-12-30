import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, Mail, CheckCircle, AlertCircle, Loader2, FileText } from 'lucide-react'

interface UploadStatus {
  type: 'idle' | 'uploading' | 'success' | 'error'
  message?: string
  result?: any
}

interface UploadPageProps {
  onNavigateToExtractions?: () => void
}

export default function UploadPage({ onNavigateToExtractions }: UploadPageProps) {
  const [emailFile, setEmailFile] = useState<File | null>(null)
  const [status, setStatus] = useState<UploadStatus>({ type: 'idle' })

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      const file = acceptedFiles[0]
      setEmailFile(file)
      // Auto-submit when file is dropped
      handleUpload(file)
    }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'message/rfc822': ['.eml'],
      'application/octet-stream': ['.eml'],
    },
    maxFiles: 1,
  })

  const handleUpload = async (file: File) => {
    setStatus({ type: 'uploading', message: 'Processing email and document...' })

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

      setStatus({
        type: 'success',
        message: `Extraction complete! ${data.message || ''}`,
        result: data,
      })

      // Navigate to extractions page after 2 seconds
      setTimeout(() => {
        if (onNavigateToExtractions) {
          onNavigateToExtractions()
        }
      }, 2000)
    } catch (error) {
      setStatus({
        type: 'error',
        message: error instanceof Error ? error.message : 'Processing failed',
      })
    }
  }

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
              `}
            >
              {status.type === 'uploading' && (
                <Loader2 className="text-blue-400 animate-spin flex-shrink-0" size={20} />
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
                    {status.result.status === 'processing' && (
                      <div className="mt-3 flex items-center gap-2 text-xs text-blue-300 bg-blue-500/10 p-3 rounded border border-blue-500/20">
                        <Loader2 size={14} className="animate-spin" />
                        <span>Master LLM processing database operations in background...</span>
                      </div>
                    )}
                    <p className="mt-3 text-xs text-gray-400">
                      Redirecting to extractions page in 2 seconds...
                    </p>
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

        {/* Info Cards */}
        <div className="grid grid-cols-3 gap-4 mt-8">
          <div className="bg-dark-surface border border-dark-border rounded-lg p-4">
            <div className="text-2xl font-bold text-white mb-1">{">"} 90%</div>
            <div className="text-sm text-gray-400">Auto-processed</div>
          </div>
          <div className="bg-dark-surface border border-dark-border rounded-lg p-4">
            <div className="text-2xl font-bold text-white mb-1">75-90%</div>
            <div className="text-sm text-gray-400">Queued for review</div>
          </div>
          <div className="bg-dark-surface border border-dark-border rounded-lg p-4">
            <div className="text-2xl font-bold text-white mb-1">{"<"} 75%</div>
            <div className="text-sm text-gray-400">Manual review</div>
          </div>
        </div>
      </div>
    </div>
  )
}

