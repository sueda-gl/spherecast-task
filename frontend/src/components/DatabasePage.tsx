import { useState, useEffect } from 'react'
import { 
  Package, 
  FileText, 
  Building2, 
  Search,
  DollarSign,
  List,
  Link
} from 'lucide-react'

interface PurchaseOrder {
  id: number
  reference_num: string
  supplier_id: number
  delivery_date: string | null
}

interface Product {
  id: number
  sku: string
  title: string
}

interface Supplier {
  id: number
  name: string
  email: string
}

interface PurchaseOrderLine {
  id: number
  purchase_order_id: number
  product_id: number
  quantity: number
  delivery_date: string | null
  unit_price: number | null
  total_price: number | null
  notes: string | null
}

interface SupplierProduct {
  supplier_id: number
  product_id: number
  supplier_sku: string | null
  price_per_unit: number | null
}

type ViewMode = 'purchase_orders' | 'products' | 'suppliers' | 'po_lines' | 'supplier_products'

export default function DatabasePage() {
  const [viewMode, setViewMode] = useState<ViewMode>('purchase_orders')
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [poLines, setPoLines] = useState<PurchaseOrderLine[]>([])
  const [supplierProducts, setSupplierProducts] = useState<SupplierProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')

  useEffect(() => {
    fetchData()
  }, [viewMode])

  const fetchData = async () => {
    setLoading(true)
    try {
      if (viewMode === 'purchase_orders') {
        const response = await fetch('/api/database/purchase-orders')
        const data = await response.json()
        setPurchaseOrders(data.purchase_orders || [])
      } else if (viewMode === 'products') {
        const response = await fetch('/api/database/products')
        const data = await response.json()
        setProducts(data.products || [])
      } else if (viewMode === 'suppliers') {
        const response = await fetch('/api/database/suppliers')
        const data = await response.json()
        setSuppliers(data.suppliers || [])
      } else if (viewMode === 'po_lines') {
        const response = await fetch('/api/database/purchase-order-lines')
        const data = await response.json()
        setPoLines(data.purchase_order_lines || [])
      } else if (viewMode === 'supplier_products') {
        const response = await fetch('/api/database/supplier-products')
        const data = await response.json()
        setSupplierProducts(data.supplier_products || [])
      }
    } catch (error) {
      console.error('Failed to fetch data:', error)
    } finally {
      setLoading(false)
    }
  }


  const filteredPOs = purchaseOrders.filter(po =>
    po.reference_num?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    po.supplier_id.toString().includes(searchTerm) ||
    po.id.toString().includes(searchTerm)
  )

  const filteredProducts = products.filter(p =>
    p.sku?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.title?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const filteredSuppliers = suppliers.filter(s =>
    s.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    s.email?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const filteredPOLines = poLines.filter(line =>
    line.id.toString().includes(searchTerm) ||
    line.purchase_order_id.toString().includes(searchTerm) ||
    line.product_id.toString().includes(searchTerm) ||
    line.quantity.toString().includes(searchTerm)
  )

  const filteredSupplierProducts = supplierProducts.filter(sp =>
    sp.supplier_id.toString().includes(searchTerm) ||
    sp.product_id.toString().includes(searchTerm) ||
    sp.supplier_sku?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  if (loading) {
    return (
      <div className="min-h-screen p-8 flex items-center justify-center">
        <div className="text-gray-400">Loading database...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Production Database</h1>
          <p className="text-gray-400">View all data in your SphereCast database</p>
        </div>

        {/* View Mode Tabs */}
        <div className="mb-6">
          <div className="bg-dark-surface border border-dark-border rounded-lg p-2 inline-flex gap-2 flex-wrap">
            <button
              onClick={() => setViewMode('purchase_orders')}
              className={`
                px-4 py-2 rounded flex items-center gap-2 transition-colors
                ${viewMode === 'purchase_orders'
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-dark-hover'
                }
              `}
            >
              <FileText size={18} />
              Purchase Orders
            </button>
            <button
              onClick={() => setViewMode('po_lines')}
              className={`
                px-4 py-2 rounded flex items-center gap-2 transition-colors
                ${viewMode === 'po_lines'
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-dark-hover'
                }
              `}
            >
              <List size={18} />
              PO Lines
            </button>
            <button
              onClick={() => setViewMode('products')}
              className={`
                px-4 py-2 rounded flex items-center gap-2 transition-colors
                ${viewMode === 'products'
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-dark-hover'
                }
              `}
            >
              <Package size={18} />
              Products
            </button>
            <button
              onClick={() => setViewMode('suppliers')}
              className={`
                px-4 py-2 rounded flex items-center gap-2 transition-colors
                ${viewMode === 'suppliers'
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-dark-hover'
                }
              `}
            >
              <Building2 size={18} />
              Suppliers
            </button>
            <button
              onClick={() => setViewMode('supplier_products')}
              className={`
                px-4 py-2 rounded flex items-center gap-2 transition-colors
                ${viewMode === 'supplier_products'
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-dark-hover'
                }
              `}
            >
              <Link size={18} />
              Supplier Products
            </button>
          </div>
        </div>

        {/* Search Bar */}
        <div className="mb-6">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-500" size={20} />
            <input
              type="text"
              placeholder={`Search ${viewMode.replace('_', ' ')}...`}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-dark-surface border border-dark-border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* Content */}
        {viewMode === 'purchase_orders' && (
          <div className="bg-dark-surface border border-dark-border rounded-lg">
            <div className="p-4 border-b border-dark-border">
              <h2 className="font-semibold text-white">
                Purchase Orders ({filteredPOs.length})
              </h2>
            </div>
            <div className="overflow-x-auto">
              {filteredPOs.length === 0 ? (
                <div className="p-8 text-center text-gray-500">
                  <FileText className="mx-auto mb-3" size={48} />
                  <p>No purchase orders found</p>
                </div>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-dark-border text-left">
                      <th className="p-4 text-gray-400 font-medium">id</th>
                      <th className="p-4 text-gray-400 font-medium">reference_num</th>
                      <th className="p-4 text-gray-400 font-medium">supplier_id</th>
                      <th className="p-4 text-gray-400 font-medium">delivery_date</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-dark-border">
                    {filteredPOs.map((po) => (
                      <tr key={po.id} className="hover:bg-dark-hover transition-colors">
                        <td className="p-4 text-gray-500">{po.id}</td>
                        <td className="p-4 text-white font-medium">{po.reference_num || '-'}</td>
                        <td className="p-4 text-white">{po.supplier_id}</td>
                        <td className="p-4 text-gray-400">
                          {po.delivery_date 
                            ? new Date(po.delivery_date).toLocaleDateString()
                            : '-'
                          }
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {viewMode === 'products' && (
          <div className="bg-dark-surface border border-dark-border rounded-lg">
            <div className="p-4 border-b border-dark-border">
              <h2 className="font-semibold text-white">
                Products ({filteredProducts.length})
              </h2>
            </div>
            <div className="overflow-x-auto">
              {filteredProducts.length === 0 ? (
                <div className="p-8 text-center text-gray-500">
                  <Package className="mx-auto mb-3" size={48} />
                  <p>No products found</p>
                </div>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-dark-border text-left">
                      <th className="p-4 text-gray-400 font-medium">id</th>
                      <th className="p-4 text-gray-400 font-medium">sku</th>
                      <th className="p-4 text-gray-400 font-medium">title</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-dark-border">
                    {filteredProducts.map((product) => (
                      <tr key={product.id} className="hover:bg-dark-hover transition-colors">
                        <td className="p-4 text-gray-500">{product.id}</td>
                        <td className="p-4">
                          <span className="font-mono text-white">{product.sku}</span>
                        </td>
                        <td className="p-4 text-white">{product.title || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {viewMode === 'suppliers' && (
          <div className="bg-dark-surface border border-dark-border rounded-lg">
            <div className="p-4 border-b border-dark-border">
              <h2 className="font-semibold text-white">
                Suppliers ({filteredSuppliers.length})
              </h2>
            </div>
            <div className="overflow-x-auto">
              {filteredSuppliers.length === 0 ? (
                <div className="p-8 text-center text-gray-500">
                  <Building2 className="mx-auto mb-3" size={48} />
                  <p>No suppliers found</p>
                </div>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-dark-border text-left">
                      <th className="p-4 text-gray-400 font-medium">id</th>
                      <th className="p-4 text-gray-400 font-medium">name</th>
                      <th className="p-4 text-gray-400 font-medium">email</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-dark-border">
                    {filteredSuppliers.map((supplier) => (
                      <tr key={supplier.id} className="hover:bg-dark-hover transition-colors">
                        <td className="p-4 text-gray-500">{supplier.id}</td>
                        <td className="p-4 text-white font-medium">{supplier.name}</td>
                        <td className="p-4 text-gray-400">{supplier.email || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {viewMode === 'po_lines' && (
          <div className="bg-dark-surface border border-dark-border rounded-lg">
            <div className="p-4 border-b border-dark-border">
              <h2 className="font-semibold text-white">
                Purchase Order Lines ({filteredPOLines.length})
              </h2>
            </div>
            <div className="overflow-x-auto">
              {filteredPOLines.length === 0 ? (
                <div className="p-8 text-center text-gray-500">
                  <List className="mx-auto mb-3" size={48} />
                  <p>No purchase order lines found</p>
                </div>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-dark-border text-left">
                      <th className="p-4 text-gray-400 font-medium">id</th>
                      <th className="p-4 text-gray-400 font-medium">purchase_order_id</th>
                      <th className="p-4 text-gray-400 font-medium">product_id</th>
                      <th className="p-4 text-gray-400 font-medium">quantity</th>
                      <th className="p-4 text-gray-400 font-medium">delivery_date</th>
                      <th className="p-4 text-gray-400 font-medium">unit_price</th>
                      <th className="p-4 text-gray-400 font-medium">total_price</th>
                      <th className="p-4 text-gray-400 font-medium">notes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-dark-border">
                    {filteredPOLines.map((line) => (
                      <tr key={line.id} className="hover:bg-dark-hover transition-colors">
                        <td className="p-4 text-gray-500">{line.id}</td>
                        <td className="p-4 text-white">{line.purchase_order_id}</td>
                        <td className="p-4 text-white">{line.product_id}</td>
                        <td className="p-4 text-white font-medium">
                          {line.quantity?.toLocaleString() || 0}
                        </td>
                        <td className="p-4 text-gray-400">
                          {line.delivery_date 
                            ? new Date(line.delivery_date).toLocaleDateString()
                            : '-'
                          }
                        </td>
                        <td className="p-4 text-gray-400">
                          {line.unit_price ? `$${line.unit_price.toFixed(2)}` : '-'}
                        </td>
                        <td className="p-4 text-green-400 font-medium">
                          {line.total_price ? `$${line.total_price.toLocaleString()}` : '-'}
                        </td>
                        <td className="p-4 text-gray-400 text-sm">
                          {line.notes || '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {viewMode === 'supplier_products' && (
          <div className="bg-dark-surface border border-dark-border rounded-lg">
            <div className="p-4 border-b border-dark-border">
              <h2 className="font-semibold text-white">
                Supplier Product Mappings ({filteredSupplierProducts.length})
              </h2>
            </div>
            <div className="overflow-x-auto">
              {filteredSupplierProducts.length === 0 ? (
                <div className="p-8 text-center text-gray-500">
                  <Link className="mx-auto mb-3" size={48} />
                  <p>No supplier product mappings found</p>
                </div>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-dark-border text-left">
                      <th className="p-4 text-gray-400 font-medium">supplier_id</th>
                      <th className="p-4 text-gray-400 font-medium">product_id</th>
                      <th className="p-4 text-gray-400 font-medium">supplier_sku</th>
                      <th className="p-4 text-gray-400 font-medium">price_per_unit</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-dark-border">
                    {filteredSupplierProducts.map((sp, idx) => (
                      <tr key={`${sp.supplier_id}-${sp.product_id}-${idx}`} className="hover:bg-dark-hover transition-colors">
                        <td className="p-4 text-white">{sp.supplier_id}</td>
                        <td className="p-4 text-white">{sp.product_id}</td>
                        <td className="p-4">
                          <span className="text-white font-mono">
                            {sp.supplier_sku || '-'}
                          </span>
                        </td>
                        <td className="p-4 text-gray-400">
                          {sp.price_per_unit ? `$${sp.price_per_unit.toFixed(2)}` : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

