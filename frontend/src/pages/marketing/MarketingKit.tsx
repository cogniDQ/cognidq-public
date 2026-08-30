import { Link } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Sparkles } from 'lucide-react'
import { MARKETING_ASSETS } from './assets'

const BRAND_PALETTE = [
  { name: 'Deep Navy', hex: '#0B0F19' },
  { name: 'Slate', hex: '#1A2233' },
  { name: 'Electric Blue', hex: '#3C66F1' },
  { name: 'Violet', hex: '#8B5CF6' },
  { name: 'Trust Green', hex: '#22C55E' },
  { name: 'Cool Gray', hex: '#6B7280' },
  { name: 'Light Gray', hex: '#F3F5F7' },
]

export default function MarketingKit() {
  return (
    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-12 space-y-10">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <Link to="/" className="inline-flex items-center text-sm text-gray-400 hover:text-white transition mb-3">
            <ArrowLeft className="w-4 h-4 mr-1" />
            Back to Home
          </Link>
          <div className="flex items-center space-x-3">
            <Sparkles className="w-7 h-7 text-violet-400" />
            <h1 className="text-4xl font-black text-white">CogniDQ — Marketing Graphics Kit</h1>
          </div>
          <p className="mt-3 text-gray-400 max-w-2xl">
            A collection of branded, ready-to-use marketing graphics to build consistent, impactful communications.
          </p>
        </div>
      </div>

      {/* Brand palette */}
      <div className="glass border border-dark-700/60 rounded-xl p-5">
        <p className="text-xs uppercase tracking-widest text-gray-400 mb-3">Brand Palette</p>
        <div className="grid grid-cols-4 sm:grid-cols-7 gap-3">
          {BRAND_PALETTE.map((c) => (
            <div key={c.hex} className="text-center">
              <div className="w-full aspect-square rounded-lg border border-white/10" style={{ background: c.hex }} />
              <p className="mt-2 text-xs text-gray-200 font-medium">{c.name}</p>
              <p className="text-[10px] text-gray-500">{c.hex}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Asset grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {MARKETING_ASSETS.map((asset) => (
          <Link
            key={asset.slug}
            to={`/marketing/${asset.slug}`}
            className="group glass border border-dark-700/60 rounded-xl overflow-hidden hover:border-violet-500/50 hover:shadow-2xl hover:-translate-y-1 transition"
          >
            <div className="aspect-[4/3] bg-dark-900 flex items-center justify-center p-4 overflow-hidden">
              <div className="origin-center scale-[0.45] sm:scale-[0.5] pointer-events-none">
                {asset.render()}
              </div>
            </div>
            <div className="p-5 border-t border-dark-700/60">
              <p className="text-xs uppercase tracking-widest text-violet-400 font-semibold">
                {asset.number}. {asset.category}
              </p>
              <h3 className="mt-2 text-lg font-bold text-white group-hover:text-violet-300 transition">
                {asset.title}
              </h3>
              <p className="mt-1 text-sm text-gray-400 line-clamp-2">{asset.description}</p>
              <div className="mt-3 inline-flex items-center text-sm font-semibold text-violet-400">
                <span>Open asset</span>
                <ArrowRight className="w-4 h-4 ml-1 group-hover:translate-x-0.5 transition" />
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
