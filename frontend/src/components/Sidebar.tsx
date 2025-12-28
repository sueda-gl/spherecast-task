import { Upload, Database, Eye } from 'lucide-react'

interface SidebarProps {
  currentPage: string
  onNavigate: (page: 'upload' | 'extractions' | 'database') => void
}

export default function Sidebar({ currentPage, onNavigate }: SidebarProps) {
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
                  `}
                >
                  <span className={isActive ? 'text-blue-400' : ''}>{item.icon}</span>
                  <span className="flex-1">{item.name}</span>
                </button>
              </li>
            )
          })}
        </ul>
      </nav>
    </aside>
  )
}

