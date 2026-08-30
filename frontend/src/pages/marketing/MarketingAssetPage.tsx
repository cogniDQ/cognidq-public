import { Link, useParams, Navigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, LayoutGrid } from 'lucide-react'
import { MARKETING_ASSETS } from './assets'

export default function MarketingAssetPage() {
  const { slug } = useParams<{ slug: string }>()
  const idx = MARKETING_ASSETS.findIndex((a) => a.slug === slug)
  if (idx === -1) return <Navigate to="/marketing" replace />

  const asset = MARKETING_ASSETS[idx]
  const prev = MARKETING_ASSETS[(idx - 1 + MARKETING_ASSETS.length) % MARKETING_ASSETS.length]
  const next = MARKETING_ASSETS[(idx + 1) % MARKETING_ASSETS.length]

  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-10 space-y-8">
      {/* Breadcrumb */}
      <div className="flex items-center justify-between flex-wrap gap-3 text-sm">
        <div className="flex items-center space-x-2 text-gray-400">
          <Link to="/" className="hover:text-white">Home</Link>
          <span>/</span>
          <Link to="/marketing" className="hover:text-white">Marketing Kit</Link>
          <span>/</span>
          <span className="text-white">{asset.category}</span>
        </div>
        <Link
          to="/marketing"
          className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg bg-dark-800 text-gray-200 hover:bg-dark-700 transition"
        >
          <LayoutGrid className="w-4 h-4" />
          <span>All assets</span>
        </Link>
      </div>

      {/* Heading */}
      <div>
        <p className="text-xs uppercase tracking-widest text-violet-400 font-semibold">
          Asset {asset.number} of {MARKETING_ASSETS.length} · {asset.category}
        </p>
        <h1 className="mt-2 text-3xl lg:text-4xl font-black text-white">{asset.title}</h1>
        <p className="mt-2 text-gray-400 max-w-3xl">{asset.description}</p>
      </div>

      {/* Asset preview */}
      <div className="glass border border-dark-700/60 rounded-2xl p-6 lg:p-10 flex items-center justify-center bg-dark-900/40">
        <div className="w-full flex items-center justify-center">
          {asset.render()}
        </div>
      </div>

      {/* Prev / Next */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Link
          to={`/marketing/${prev.slug}`}
          className="group glass border border-dark-700/60 rounded-xl p-5 hover:border-violet-500/50 transition flex items-center space-x-4"
        >
          <ArrowLeft className="w-5 h-5 text-gray-400 group-hover:-translate-x-0.5 transition" />
          <div className="text-left">
            <p className="text-xs uppercase tracking-widest text-gray-500">Previous</p>
            <p className="text-white font-semibold">{prev.number}. {prev.category}</p>
            <p className="text-xs text-gray-400 line-clamp-1">{prev.title}</p>
          </div>
        </Link>
        <Link
          to={`/marketing/${next.slug}`}
          className="group glass border border-dark-700/60 rounded-xl p-5 hover:border-violet-500/50 transition flex items-center justify-end space-x-4 text-right"
        >
          <div>
            <p className="text-xs uppercase tracking-widest text-gray-500">Next</p>
            <p className="text-white font-semibold">{next.number}. {next.category}</p>
            <p className="text-xs text-gray-400 line-clamp-1">{next.title}</p>
          </div>
          <ArrowRight className="w-5 h-5 text-gray-400 group-hover:translate-x-0.5 transition" />
        </Link>
      </div>
    </div>
  )
}
