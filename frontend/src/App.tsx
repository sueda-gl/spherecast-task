import { useState } from 'react'
import Sidebar from './components/Sidebar'
import UploadPage from './components/UploadPage'
import ExtractionsPage from './components/ExtractionsPage'
import DatabasePage from './components/DatabasePage'

type Page = 'upload' | 'extractions' | 'database'

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('upload')

  return (
    <div className="flex min-h-screen bg-dark-bg">
      <Sidebar currentPage={currentPage} onNavigate={setCurrentPage} />
      <main className="flex-1 ml-64">
        {currentPage === 'upload' && (
          <UploadPage onNavigateToExtractions={() => setCurrentPage('extractions')} />
        )}
        {currentPage === 'extractions' && <ExtractionsPage />}
        {currentPage === 'database' && <DatabasePage />}
      </main>
    </div>
  )
}

export default App

