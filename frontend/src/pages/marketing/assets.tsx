import { ReactNode } from 'react'
import {
  Sparkles,
  Share2,
  Calendar,
  Clock,
  Users,
  Zap,
  CheckCircle,
  ShieldCheck,
  BarChart3,
  Lightbulb,
  ArrowRight,
  Target,
  ClipboardEdit,
  GitBranch,
  Activity,
  FileText,
  AlertTriangle,
  TrendingUp,
  Bell,
  Building2,
  UserCog,
  Smile,
  Gauge,
  Database,
  Workflow,
  PieChart,
  PlayCircle,
} from 'lucide-react'
import Logo from '@/components/Logo'

export interface MarketingAssetMeta {
  slug: string
  number: number
  title: string
  category: string
  description: string
  render: () => ReactNode
}

const BRAND_COLORS = {
  navy: '#0B0F19',
  slate: '#1A2233',
  electric: '#3C66F1',
  violet: '#8B5CF6',
  green: '#22C55E',
}

/* ----------------------------- 1. LinkedIn Post ---------------------------- */
function Asset1() {
  return (
    <div className="relative w-full max-w-2xl aspect-[4/3] rounded-2xl overflow-hidden shadow-2xl bg-gradient-to-br from-[#0B0F19] via-[#111827] to-[#1A2233] p-10 flex flex-col justify-between">
      <div className="absolute inset-0 opacity-30 pointer-events-none">
        <div className="absolute -top-20 -right-20 w-80 h-80 bg-violet-500/40 rounded-full blur-3xl" />
        <div className="absolute -bottom-24 -left-10 w-96 h-96 bg-blue-500/30 rounded-full blur-3xl" />
      </div>
      <div className="relative">
        <span className="inline-block px-3 py-1 text-xs font-semibold tracking-widest text-violet-300 bg-violet-500/15 border border-violet-400/30 rounded-full uppercase">
          Announcement
        </span>
        <h2 className="mt-6 text-4xl lg:text-5xl font-black leading-tight text-white">
          AI-Powered Data Quality
          <br />
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-violet-300 to-blue-400">
            You Can Trust
          </span>
        </h2>
        <p className="mt-5 text-gray-300 max-w-md">
          CogniDQ transforms business rules into executable data quality checks—so you can ship trusted data with confidence.
        </p>
      </div>
      <div className="relative grid grid-cols-3 gap-3 text-center">
        {[
          { icon: Zap, label: 'Automate Data Quality' },
          { icon: Lightbulb, label: 'Explainable Results' },
          { icon: ShieldCheck, label: 'Enterprise Ready' },
        ].map((it) => (
          <div key={it.label} className="bg-white/5 border border-white/10 rounded-xl p-3">
            <it.icon className="w-5 h-5 text-violet-300 mx-auto" />
            <p className="mt-2 text-xs text-gray-200 font-medium">{it.label}</p>
          </div>
        ))}
      </div>
      <div className="relative flex items-center justify-between text-sm text-gray-400 mt-6">
        <span>#DataQuality #AITrustLayer #CogniDQ</span>
        <Logo variant="light" className="h-7 w-auto" />
      </div>
    </div>
  )
}

/* --------------------------- 2. Feature Highlight -------------------------- */
function Asset2() {
  return (
    <div className="relative w-full max-w-md aspect-square rounded-2xl overflow-hidden shadow-2xl bg-gradient-to-br from-[#0B0F19] to-[#1A2233] p-10 flex flex-col justify-between">
      <div className="absolute inset-0 opacity-40 pointer-events-none">
        <div className="absolute top-10 right-10 w-72 h-72 bg-violet-500/30 rounded-full blur-3xl" />
      </div>
      <div className="relative flex items-center space-x-2">
        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center">
          <Share2 className="w-5 h-5 text-white" />
        </div>
        <p className="text-xs uppercase tracking-widest text-violet-300 font-semibold">Feature Highlight</p>
      </div>
      <div className="relative">
        <h2 className="text-5xl font-black text-white leading-tight">
          Explainable.
          <br />
          Actionable.
          <br />
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-violet-300 to-blue-400">
            Trusted.
          </span>
        </h2>
        <p className="mt-5 text-gray-300">
          CogniDQ turns business rules into clear, explainable results—no technical skills required.
        </p>
      </div>
      <div className="relative flex items-center">
        <Logo variant="light" className="h-8 w-auto" />
      </div>
    </div>
  )
}

/* ------------------------------ 3. Webinar Banner -------------------------- */
function Asset3() {
  return (
    <div className="relative w-full max-w-3xl aspect-[16/10] rounded-2xl overflow-hidden shadow-2xl bg-gradient-to-br from-[#0B0F19] via-[#111827] to-[#1A2233] p-12">
      <div className="absolute inset-0 opacity-30 pointer-events-none">
        <div className="absolute top-1/2 right-0 w-[28rem] h-[28rem] bg-violet-500/30 rounded-full blur-3xl" />
        <div className="absolute -bottom-20 -left-10 w-80 h-80 bg-blue-500/20 rounded-full blur-3xl" />
      </div>
      <div className="relative grid grid-cols-2 gap-8 h-full">
        <div className="flex flex-col justify-between">
          <div className="flex items-center space-x-3">
            <Logo variant="light" className="h-7 w-auto" />
            <span className="ml-1 px-3 py-1 text-xs uppercase tracking-widest bg-green-500/20 text-green-300 border border-green-400/30 rounded-full">
              Live Webinar
            </span>
          </div>
          <div>
            <h2 className="text-3xl lg:text-4xl font-black text-white leading-tight">
              From Rules to Reliability:
              <br />
              The AI Advantage for
              <br />
              <span className="bg-clip-text text-transparent bg-gradient-to-r from-violet-300 to-blue-400">
                Data Quality
              </span>
            </h2>
            <div className="mt-6 space-y-2 text-gray-300 text-sm">
              <div className="flex items-center space-x-2"><Calendar className="w-4 h-4 text-violet-400" /><span>June 18, 2025</span></div>
              <div className="flex items-center space-x-2"><Clock className="w-4 h-4 text-violet-400" /><span>11:00 AM ET</span></div>
              <div className="flex items-center space-x-2"><Users className="w-4 h-4 text-violet-400" /><span>Data Quality Experts</span></div>
            </div>
            <button className="mt-6 inline-flex items-center space-x-2 px-5 py-2.5 bg-violet-600 hover:bg-violet-700 text-white text-sm font-semibold rounded-lg transition">
              <span>Register Now</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className="relative flex items-center justify-center">
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-64 h-64 border-2 border-violet-500/40 rotate-45 rounded-3xl" />
            <div className="absolute w-48 h-48 border-2 border-blue-500/40 rotate-12 rounded-3xl" />
            <div className="absolute w-32 h-32 bg-violet-500/20 rounded-3xl flex items-center justify-center">
              <Sparkles className="w-12 h-12 text-violet-300" />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* --------------------------- 4. Product Release Banner --------------------- */
function Asset4() {
  return (
    <div className="relative w-full max-w-4xl aspect-[16/9] rounded-2xl overflow-hidden shadow-2xl bg-gradient-to-br from-[#0B0F19] via-[#111827] to-[#1A2233] p-12 grid grid-cols-2 gap-8 items-center">
      <div className="absolute inset-0 opacity-30 pointer-events-none">
        <div className="absolute -top-10 left-1/3 w-96 h-96 bg-violet-500/30 rounded-full blur-3xl" />
      </div>
      <div className="relative">
        <div className="flex items-center mb-4">
          <Logo variant="light" className="h-7 w-auto" />
        </div>
        <span className="inline-block px-3 py-1 text-xs font-semibold tracking-widest bg-green-500/20 text-green-300 border border-green-400/30 rounded-full uppercase">
          New Release
        </span>
        <h2 className="mt-5 text-4xl lg:text-5xl font-black text-white leading-tight">
          CogniDQ 2.0
          <br />
          Smarter Checks.
          <br />
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-violet-300 to-blue-400">
            Stronger Trust.
          </span>
        </h2>
        <ul className="mt-6 space-y-2 text-gray-300 text-sm">
          {['Advanced Rule Intelligence', 'Improved Explainability', 'Faster Performance at Scale'].map((f) => (
            <li key={f} className="flex items-center space-x-2">
              <CheckCircle className="w-4 h-4 text-green-400" />
              <span>{f}</span>
            </li>
          ))}
        </ul>
        <button className="mt-6 px-5 py-2.5 bg-violet-600 hover:bg-violet-700 text-white text-sm font-semibold rounded-lg">
          Explore What's New
        </button>
      </div>
      <div className="relative bg-[#0B1220] border border-white/10 rounded-xl p-5 shadow-xl">
        <div className="flex items-center justify-between border-b border-white/10 pb-3 mb-3">
          <p className="text-white text-sm font-semibold">Rule Execution</p>
          <span className="text-xs text-gray-400">Status</span>
        </div>
        <div className="space-y-2">
          {['Row Count Check', 'Null Check', 'Format Check', 'Referential Integrity', 'Business Rule'].map((r) => (
            <div key={r} className="flex items-center justify-between text-sm">
              <span className="text-gray-300">{r}</span>
              <span className="px-2 py-0.5 text-xs bg-green-500/15 text-green-300 border border-green-400/30 rounded">Passed</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ------------------------------ 5. Case Study ------------------------------ */
function Asset5() {
  return (
    <div className="relative w-full max-w-3xl aspect-[16/9] rounded-2xl overflow-hidden shadow-2xl bg-white p-10 grid grid-cols-3 gap-6">
      <div className="col-span-2 flex flex-col justify-between">
        <div className="flex items-center justify-between">
          <span className="text-xs uppercase tracking-widest font-semibold text-violet-600">Case Study</span>
          <Logo variant="full" className="h-6 w-auto" />
        </div>
        <h2 className="text-3xl lg:text-4xl font-black text-gray-900 leading-tight">
          How FinServ Co. Achieved
          <br />
          <span className="text-violet-600">99% Data Quality Accuracy</span>
          <br />
          with CogniDQ
        </h2>
        <div className="grid grid-cols-3 gap-3 text-center">
          {[
            { v: '99%', l: 'Data Quality Accuracy', icon: BarChart3 },
            { v: '60%', l: 'Reduction in Manual Effort', icon: Zap },
            { v: '3x', l: 'Faster Issue Resolution', icon: Lightbulb },
          ].map((s) => (
            <div key={s.l} className="bg-gray-50 border border-gray-200 rounded-xl p-3">
              <s.icon className="w-5 h-5 text-violet-600 mx-auto" />
              <p className="mt-1 text-xl font-black text-gray-900">{s.v}</p>
              <p className="text-[10px] text-gray-500 leading-tight">{s.l}</p>
            </div>
          ))}
        </div>
        <a className="text-sm font-semibold text-violet-600 inline-flex items-center space-x-1">
          <span>Read the full story</span>
          <ArrowRight className="w-4 h-4" />
        </a>
      </div>
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-5 flex flex-col justify-center">
        <span className="text-3xl text-violet-600 font-black">"</span>
        <p className="text-sm text-gray-700 leading-relaxed">
          CogniDQ helped us operationalize data quality and build trust across every team.
        </p>
        <p className="mt-3 text-xs font-semibold text-gray-900">— Head of Data Governance</p>
        <p className="text-xs text-gray-500">FinServ Co.</p>
      </div>
    </div>
  )
}

/* ------------------------------- 6. Email Header --------------------------- */
function Asset6() {
  return (
    <div className="relative w-full max-w-3xl aspect-[16/9] rounded-2xl overflow-hidden shadow-2xl bg-gradient-to-br from-[#0B0F19] via-[#111827] to-[#1A2233] p-12 grid grid-cols-2 gap-8 items-center">
      <div className="absolute inset-0 opacity-30 pointer-events-none">
        <div className="absolute -bottom-20 -right-10 w-96 h-96 bg-violet-500/30 rounded-full blur-3xl" />
      </div>
      <div className="relative">
        <div className="flex items-center">
          <Logo variant="light" className="h-7 w-auto" />
        </div>
        <p className="mt-2 text-xs uppercase tracking-widest text-violet-300 font-semibold">
          AI Trust Layer for Enterprise Data Quality
        </p>
        <h2 className="mt-5 text-4xl font-black text-white leading-tight">
          Trusted Data.
          <br />
          Better Decisions.
          <br />
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-violet-300 to-blue-400">
            Stronger Outcomes.
          </span>
        </h2>
      </div>
      <div className="relative flex items-center justify-center">
        <div className="relative w-56 h-56">
          <div className="absolute inset-0 border-2 border-violet-500/40 rotate-45 rounded-3xl" />
          <div className="absolute inset-6 border-2 border-blue-500/40 rounded-3xl" />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center shadow-xl">
              <CheckCircle className="w-10 h-10 text-white" />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ----------------------- 7. Website Feature Section ------------------------ */
function Asset7() {
  const features = [
    { icon: Share2, title: 'AI-Powered Rules', body: 'Convert natural language rules into executable data quality checks in seconds.' },
    { icon: ShieldCheck, title: 'Explainable Results', body: 'Get clear, SQL-based results you can understand, validate, and trust.' },
    { icon: BarChart3, title: 'Enterprise Scale', body: 'Built for performance, governance, and security across complex ecosystems.' },
    { icon: Lightbulb, title: 'Actionable Insights', body: 'Surface issues, track trends, and drive data quality improvements.' },
  ]
  return (
    <div className="relative w-full max-w-4xl rounded-2xl overflow-hidden shadow-2xl bg-white p-12 text-center">
      <div className="flex items-center justify-center mb-6">
        <Logo variant="full" className="h-8 w-auto" />
      </div>
      <span className="text-xs uppercase tracking-widest font-semibold text-violet-600">Why CogniDQ</span>
      <h2 className="mt-2 text-3xl lg:text-4xl font-black text-gray-900">An AI Trust Layer for Your Data</h2>
      <p className="mt-3 text-gray-600 max-w-2xl mx-auto">
        CogniDQ empowers data teams to define, automate, and trust data quality at scale—with clarity, speed, and confidence.
      </p>
      <div className="mt-8 grid grid-cols-2 lg:grid-cols-4 gap-4">
        {features.map((f) => (
          <div key={f.title} className="border border-gray-200 rounded-xl p-5 text-left hover:shadow-lg transition">
            <div className="w-10 h-10 rounded-lg bg-violet-50 flex items-center justify-center">
              <f.icon className="w-5 h-5 text-violet-600" />
            </div>
            <h3 className="mt-3 font-bold text-gray-900">{f.title}</h3>
            <p className="mt-1 text-xs text-gray-600 leading-relaxed">{f.body}</p>
            <a className="mt-3 inline-flex text-xs font-semibold text-violet-600 items-center space-x-1">
              <span>Learn more</span><ArrowRight className="w-3 h-3" />
            </a>
          </div>
        ))}
      </div>
    </div>
  )
}

/* --------------------------------- 8. CTA ---------------------------------- */
function Asset8() {
  return (
    <div className="relative w-full max-w-md aspect-[4/5] rounded-2xl overflow-hidden shadow-2xl bg-gradient-to-br from-[#0B0F19] via-[#111827] to-[#1A2233] p-10 flex flex-col justify-between">
      <div className="absolute inset-0 opacity-30 pointer-events-none">
        <div className="absolute -bottom-24 -left-10 w-96 h-96 bg-violet-500/30 rounded-full blur-3xl" />
      </div>
      <div className="relative">
        <div className="flex items-center mb-5">
          <Logo variant="light" className="h-7 w-auto" />
        </div>
        <span className="inline-block px-3 py-1 text-xs font-semibold tracking-widest text-violet-300 bg-violet-500/15 border border-violet-400/30 rounded-full uppercase">
          Ready to Get Started?
        </span>
        <h2 className="mt-6 text-4xl font-black text-white leading-tight">
          Elevate Your Data Quality
          <br />
          with{' '}
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-violet-300 to-blue-400">
            AI You Can Trust
          </span>
        </h2>
        <p className="mt-4 text-gray-300 text-sm">
          Join leading data teams who rely on CogniDQ to deliver trusted data at scale.
        </p>
      </div>
      <div className="relative space-y-3">
        <button className="w-full px-5 py-3 bg-violet-600 hover:bg-violet-700 text-white font-semibold rounded-lg">
          Book a Demo
        </button>
        <button className="w-full px-5 py-3 bg-white/5 hover:bg-white/10 border border-white/10 text-white font-semibold rounded-lg">
          Explore the DQ Hub
        </button>
      </div>
    </div>
  )
}

/* ---------------------------- 9. Dark Hero Banner -------------------------- */
function Asset9() {
  return (
    <div className="relative w-full max-w-5xl aspect-[16/8] rounded-2xl overflow-hidden shadow-2xl bg-gradient-to-br from-[#0B0F19] via-[#111827] to-[#1A2233] p-12">
      <div className="absolute inset-0 opacity-30 pointer-events-none">
        <div className="absolute top-1/3 right-1/4 w-[28rem] h-[28rem] bg-violet-500/30 rounded-full blur-3xl" />
        <div className="absolute -bottom-20 -left-10 w-80 h-80 bg-blue-500/20 rounded-full blur-3xl" />
      </div>
      <div className="relative flex items-center justify-between mb-10">
        <div className="flex items-center">
          <Logo variant="light" className="h-8 w-auto" />
        </div>
        <nav className="flex items-center space-x-6 text-sm text-gray-300">
          {['Product', 'Solutions', 'Resources', 'Company'].map((n) => (
            <span key={n} className="hover:text-white">{n}</span>
          ))}
          <button className="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white text-sm font-semibold rounded-lg">
            Book a Demo
          </button>
        </nav>
      </div>
      <div className="relative grid grid-cols-2 gap-8 items-center">
        <div>
          <span className="inline-block px-3 py-1 text-xs font-semibold tracking-widest text-violet-300 bg-violet-500/15 border border-violet-400/30 rounded-full uppercase">
            AI-Powered Data Quality
          </span>
          <h2 className="mt-5 text-4xl lg:text-5xl font-black text-white leading-tight">
            Transform Business Rules
            <br />
            into Executable
            <br />
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-violet-300 to-blue-400">
              Data Quality Checks
            </span>
          </h2>
          <p className="mt-4 text-gray-300 max-w-md">
            CogniDQ's AI trust layer automatically generates, explains, and monitors data quality—so you can trust every decision.
          </p>
          <div className="mt-6 flex space-x-3">
            <button className="px-5 py-2.5 bg-violet-600 hover:bg-violet-700 text-white text-sm font-semibold rounded-lg">
              Book a Demo
            </button>
            <button className="px-5 py-2.5 bg-white/5 hover:bg-white/10 border border-white/10 text-white text-sm font-semibold rounded-lg">
              Explore the Platform
            </button>
          </div>
        </div>
        <div className="relative flex items-center justify-center">
          <div className="relative w-72 h-72">
            <div className="absolute inset-0 border-2 border-violet-500/40 rotate-45 rounded-3xl" />
            <div className="absolute inset-6 border-2 border-blue-500/40 rounded-3xl" />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-24 h-24 rounded-2xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center shadow-xl">
                <CheckCircle className="w-12 h-12 text-white" />
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="relative mt-8 pt-6 border-t border-white/10 flex items-center justify-between text-xs text-gray-400">
        <span>TRUSTED BY DATA-DRIVEN ENTERPRISES</span>
        <div className="flex items-center space-x-6 text-gray-300">
          {['FINERVA', 'Northbridge', 'DataForge', 'NextWave', 'Altura'].map((b) => (
            <span key={b} className="font-semibold tracking-wide">{b}</span>
          ))}
        </div>
      </div>
    </div>
  )
}

/* --------------------------- 10. Product Icon Set -------------------------- */
const PRODUCT_ICONS = [
  { n: 1, icon: Target, title: 'Business Intent', sub: 'Capture what matters' },
  { n: 2, icon: ClipboardEdit, title: 'Control Builder', sub: 'Design quality rules' },
  { n: 3, icon: GitBranch, title: 'Data Flow', sub: 'Map and orchestrate' },
  { n: 4, icon: Activity, title: 'Monitoring', sub: 'Observe in real time' },
  { n: 5, icon: FileText, title: 'Evidence', sub: 'Trace and verify' },
  { n: 6, icon: AlertTriangle, title: 'Issue Management', sub: 'Triage and resolve' },
  { n: 7, icon: TrendingUp, title: 'Incident Escalation', sub: 'Route and escalate' },
  { n: 8, icon: Bell, title: 'Alerting', sub: 'Notify what matters' },
  { n: 9, icon: Building2, title: 'Governance', sub: 'Policy and standards' },
  { n: 10, icon: UserCog, title: 'RBAC / Security', sub: 'Protect and control' },
  { n: 11, icon: Smile, title: 'AI Assistant', sub: 'Ask. Analyze. Act.' },
  { n: 12, icon: Gauge, title: 'Trust Dashboard', sub: 'Measure and assure' },
  { n: 13, icon: Database, title: 'Data Source Connection', sub: 'Connect any source' },
  { n: 14, icon: Workflow, title: 'Workflow', sub: 'Define and automate' },
  { n: 15, icon: PieChart, title: 'Reporting', sub: 'Communicate insights' },
  { n: 16, icon: PlayCircle, title: 'Automation', sub: 'Run and optimize' },
]

function ProductIconCard({
  n,
  icon: Icon,
  title,
  sub,
}: (typeof PRODUCT_ICONS)[number]) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-3 text-center hover:shadow-md transition">
      <div className="mx-auto w-12 h-12 rounded-xl bg-violet-50 border border-violet-100 flex items-center justify-center">
        <Icon className="w-6 h-6 text-violet-600" strokeWidth={1.75} />
      </div>
      <p className="mt-2 text-xs font-bold text-gray-900">
        {n}. {title}
      </p>
      <p className="text-[10px] text-gray-500 leading-tight">{sub}</p>
    </div>
  )
}

function Asset10() {
  return (
    <div className="relative w-full max-w-5xl rounded-2xl overflow-hidden shadow-2xl bg-gradient-to-br from-gray-50 to-white p-10">
      <div className="flex items-start justify-between mb-6 flex-wrap gap-3">
        <div>
          <Logo variant="full" className="h-7 w-auto" />
          <p className="mt-1 text-xs text-gray-500">The AI trust layer for enterprise data quality</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-widest font-semibold text-violet-600">
            Product Icon Set
          </p>
          <h2 className="text-2xl font-black text-gray-900">16 core product concepts</h2>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-3">
        {PRODUCT_ICONS.map((it) => (
          <ProductIconCard key={it.n} {...it} />
        ))}
      </div>
    </div>
  )
}

/* ------------------------ 11. Visual Motifs / Backgrounds ------------------ */
function HexagonGrid() {
  const cells: ReactNode[] = []
  for (let r = 0; r < 4; r++) {
    for (let c = 0; c < 5; c++) {
      const x = c * 30 + (r % 2 ? 15 : 0)
      const y = r * 26
      cells.push(
        <polygon
          key={`${r}-${c}`}
          points={`${x + 15},${y} ${x + 28},${y + 8} ${x + 28},${y + 22} ${x + 15},${y + 30} ${x + 2},${y + 22} ${x + 2},${y + 8}`}
          fill="none"
          stroke="#8B5CF6"
          strokeOpacity={0.5}
          strokeWidth={1}
        />,
      )
    }
  }
  return (
    <svg viewBox="0 0 160 110" className="w-full h-full">
      {cells}
    </svg>
  )
}

function NodeConnection() {
  return (
    <svg viewBox="0 0 160 110" className="w-full h-full">
      <line x1="30" y1="30" x2="80" y2="55" stroke="#8B5CF6" strokeOpacity={0.5} strokeWidth={1.5} />
      <line x1="80" y1="55" x2="130" y2="30" stroke="#3C66F1" strokeOpacity={0.5} strokeWidth={1.5} />
      <line x1="80" y1="55" x2="30" y2="80" stroke="#22C55E" strokeOpacity={0.5} strokeWidth={1.5} />
      <line x1="80" y1="55" x2="130" y2="80" stroke="#8B5CF6" strokeOpacity={0.5} strokeWidth={1.5} />
      <circle cx="30" cy="30" r="5" fill="#8B5CF6" />
      <circle cx="130" cy="30" r="5" fill="#3C66F1" />
      <circle cx="30" cy="80" r="5" fill="#22C55E" />
      <circle cx="130" cy="80" r="5" fill="#8B5CF6" />
      <circle cx="80" cy="55" r="7" fill="#3C66F1" />
    </svg>
  )
}

function ShieldCheckMotif() {
  return (
    <svg viewBox="0 0 100 110" className="h-full w-auto">
      <defs>
        <linearGradient id="sh" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#A78BFA" />
          <stop offset="1" stopColor="#3C66F1" />
        </linearGradient>
      </defs>
      <path d="M50 8 L86 22 V58 C86 80 70 96 50 102 C30 96 14 80 14 58 V22 Z" fill="none" stroke="url(#sh)" strokeWidth="2.5" />
      <path d="M34 56 L46 68 L70 42" fill="none" stroke="url(#sh)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function DataDots() {
  const dots: ReactNode[] = []
  const seed = [
    [20, 30], [40, 20], [60, 35], [80, 25], [100, 40], [120, 28], [140, 38],
    [25, 60], [55, 70], [85, 60], [115, 72], [145, 64],
    [30, 90], [70, 92], [110, 88], [140, 95],
  ]
  seed.forEach(([x, y], i) => {
    dots.push(<circle key={i} cx={x} cy={y} r={2.5} fill={i % 3 === 0 ? '#3C66F1' : i % 3 === 1 ? '#8B5CF6' : '#22C55E'} fillOpacity={0.85} />)
  })
  return (
    <svg viewBox="0 0 160 110" className="w-full h-full">
      {dots}
    </svg>
  )
}

function GradientOrbs() {
  return (
    <div className="relative w-full h-full">
      <div className="absolute left-6 top-4 w-20 h-20 rounded-full" style={{ background: 'radial-gradient(circle at 30% 30%, #C4B5FD, #6D28D9 70%, transparent 80%)' }} />
      <div className="absolute right-8 bottom-3 w-12 h-12 rounded-full" style={{ background: 'radial-gradient(circle at 30% 30%, #A7F3D0, #059669 70%, transparent 80%)' }} />
    </div>
  )
}

function GradientBlobs() {
  return (
    <svg viewBox="0 0 160 110" className="w-full h-full">
      <defs>
        <linearGradient id="bl" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#8B5CF6" />
          <stop offset="1" stopColor="#3C66F1" />
        </linearGradient>
      </defs>
      <path d="M30 60 C 30 30, 70 20, 90 35 C 120 50, 130 80, 100 95 C 70 110, 30 95, 30 60 Z" fill="url(#bl)" opacity={0.85} />
    </svg>
  )
}

function SoftGrid() {
  return (
    <svg viewBox="0 0 160 110" className="w-full h-full">
      {[...Array(9)].map((_, i) => (
        <line key={`v${i}`} x1={i * 20} y1="0" x2={i * 20} y2="110" stroke="#CBD5E1" strokeOpacity={0.5} strokeWidth={0.6} />
      ))}
      {[...Array(7)].map((_, i) => (
        <line key={`h${i}`} x1="0" y1={i * 18} x2="160" y2={i * 18} stroke="#CBD5E1" strokeOpacity={0.5} strokeWidth={0.6} />
      ))}
    </svg>
  )
}

function FlowLines() {
  return (
    <svg viewBox="0 0 160 110" className="w-full h-full">
      <path d="M10 30 C 50 30, 50 80, 100 80 L 150 80" fill="none" stroke="#3C66F1" strokeWidth="2" />
      <path d="M10 55 C 60 55, 60 30, 110 30 L 150 30" fill="none" stroke="#8B5CF6" strokeWidth="2" />
      <path d="M10 80 C 40 80, 40 55, 90 55 L 150 55" fill="none" stroke="#22C55E" strokeWidth="2" />
      <circle cx="150" cy="30" r="3" fill="#8B5CF6" />
      <circle cx="150" cy="55" r="3" fill="#22C55E" />
      <circle cx="150" cy="80" r="3" fill="#3C66F1" />
    </svg>
  )
}

const MOTIFS = [
  { title: 'Hexagon Grid', el: <HexagonGrid /> },
  { title: 'Node & Connection', el: <NodeConnection /> },
  { title: 'Shield & Check', el: <ShieldCheckMotif /> },
  { title: 'Data Dots', el: <DataDots /> },
  { title: 'Gradient Orbs', el: <GradientOrbs /> },
  { title: 'Gradient Blobs', el: <GradientBlobs /> },
  { title: 'Soft Grid', el: <SoftGrid /> },
  { title: 'Flow Lines', el: <FlowLines /> },
]

function Asset11() {
  return (
    <div className="relative w-full max-w-5xl rounded-2xl overflow-hidden shadow-2xl bg-white p-10">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-6">
        <div>
          <p className="text-xs uppercase tracking-widest font-semibold text-violet-600">
            Visual Motifs & Background Elements
          </p>
          <h2 className="text-2xl font-black text-gray-900">A cohesive visual language</h2>
        </div>
        <Logo variant="full" className="h-7 w-auto" />
      </div>
      <div className="grid grid-cols-4 gap-4">
        {MOTIFS.map((m) => (
          <div key={m.title} className="text-center">
            <div className="aspect-[16/11] rounded-xl border border-gray-200 bg-gray-50 flex items-center justify-center overflow-hidden p-2">
              {m.el}
            </div>
            <p className="mt-2 text-xs font-semibold text-gray-700">{m.title}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ----------------------- 12. Gradient & Shape Language --------------------- */
function Asset12() {
  return (
    <div className="relative w-full max-w-5xl rounded-2xl overflow-hidden shadow-2xl bg-white p-10">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-6">
        <div>
          <p className="text-xs uppercase tracking-widest font-semibold text-violet-600">
            Gradient & Shape Language
          </p>
          <h2 className="text-2xl font-black text-gray-900">Brand-aligned forms & gradients</h2>
        </div>
        <Logo variant="full" className="h-7 w-auto" />
      </div>
      <div className="grid grid-cols-5 gap-4">
        <div className="aspect-square rounded-xl" style={{ background: 'linear-gradient(135deg, #8B5CF6, #3C66F1)' }} />
        <div className="aspect-square rounded-xl" style={{ clipPath: 'polygon(20% 0, 100% 0, 80% 100%, 0 100%)', background: 'linear-gradient(135deg, #A78BFA, #3C66F1)' }} />
        <div className="aspect-square flex items-center justify-center">
          <svg viewBox="0 0 100 100" className="w-full h-full">
            <defs>
              <linearGradient id="hx" x1="0" x2="1" y1="0" y2="1">
                <stop offset="0" stopColor="#8B5CF6" />
                <stop offset="1" stopColor="#3C66F1" />
              </linearGradient>
            </defs>
            <polygon points="50,8 88,28 88,72 50,92 12,72 12,28" fill="url(#hx)" />
          </svg>
        </div>
        <div className="aspect-square rounded-full" style={{ background: 'radial-gradient(circle at 30% 30%, #C4B5FD, #6D28D9 70%, #1E1B4B 100%)' }} />
        <div className="aspect-square rounded-full" style={{ background: 'radial-gradient(circle at 35% 35%, #DDD6FE 0%, #C4B5FD 30%, transparent 75%)' }} />
      </div>
      <p className="mt-6 text-sm text-gray-500 max-w-2xl">
        Use these primitives to build covers, hero illustrations, and section dividers. Always keep gradients within the brand palette.
      </p>
    </div>
  )
}

/* -------------------- 13. From Intent to Quality Controls ------------------ */
function Asset13() {
  return (
    <div className="relative w-full max-w-5xl rounded-2xl overflow-hidden shadow-2xl bg-white p-10">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-8">
        <div>
          <p className="text-xs uppercase tracking-widest font-semibold text-violet-600">
            Illustration Example
          </p>
          <h2 className="text-2xl font-black text-gray-900">From Intent to Quality Controls</h2>
        </div>
        <Logo variant="full" className="h-7 w-auto" />
      </div>
      <div className="grid grid-cols-3 gap-6 items-center relative">
        {/* connector dots */}
        <div className="hidden md:block absolute left-1/3 right-1/3 top-1/2 -translate-y-1/2 h-px bg-[repeating-linear-gradient(to_right,#8B5CF6_0,#8B5CF6_3px,transparent_3px,transparent_8px)]" />
        <Step icon={Target} title="Business Intent" body="Define what success looks like" />
        <Step
          custom={
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center shadow-lg">
              <Sparkles className="w-7 h-7 text-white" />
            </div>
          }
          title="CogniDQ AI"
          body="Understands, analyzes and recommends with confidence"
        />
        <Step icon={CheckCircle} title="Data Quality Controls" body="Executable rules with clear outcomes and evidence" />
      </div>
    </div>
  )
}

function Step({
  icon: Icon,
  custom,
  title,
  body,
}: {
  icon?: React.ComponentType<{ className?: string; strokeWidth?: number }>
  custom?: ReactNode
  title: string
  body: string
}) {
  return (
    <div className="text-center">
      <div className="mx-auto flex items-center justify-center">
        {custom ?? (
          <div className="w-16 h-16 rounded-2xl bg-violet-50 border border-violet-100 flex items-center justify-center">
            {Icon && <Icon className="w-8 h-8 text-violet-600" strokeWidth={1.75} />}
          </div>
        )}
      </div>
      <p className="mt-3 font-bold text-gray-900">{title}</p>
      <p className="text-xs text-gray-500 mt-1 max-w-[200px] mx-auto leading-relaxed">{body}</p>
    </div>
  )
}

/* ------------------------------ 14. Icon Size Guide ------------------------ */
function Asset14() {
  const SIZES = [16, 20, 24, 32, 48, 64]
  return (
    <div className="relative w-full max-w-4xl rounded-2xl overflow-hidden shadow-2xl bg-white p-10">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-8">
        <div>
          <p className="text-xs uppercase tracking-widest font-semibold text-violet-600">Icon Size Guide</p>
          <h2 className="text-2xl font-black text-gray-900">Sizes (Examples)</h2>
        </div>
        <Logo variant="full" className="h-7 w-auto" />
      </div>
      <div className="flex items-end justify-between gap-4">
        {SIZES.map((s) => (
          <div key={s} className="text-center">
            <div className="flex items-end justify-center" style={{ height: 72 }}>
              <Share2 className="text-violet-600" style={{ width: s, height: s }} strokeWidth={1.75} />
            </div>
            <p className="mt-3 text-xs font-semibold text-gray-700">{s}px</p>
          </div>
        ))}
      </div>
      <p className="mt-8 text-sm text-gray-500">
        Use 16–24px in dense UI, 32–48px in feature blocks, and 64px for hero illustrations.
      </p>
    </div>
  )
}

/* ----------------- 15. Stroke, Corner Radius & Line Joins ------------------ */
function Asset15() {
  return (
    <div className="relative w-full max-w-5xl rounded-2xl overflow-hidden shadow-2xl bg-white p-10">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-8">
        <div>
          <p className="text-xs uppercase tracking-widest font-semibold text-violet-600">
            Stroke, Corner Radius & Line Joins
          </p>
          <h2 className="text-2xl font-black text-gray-900">Geometry rules for icons</h2>
        </div>
        <Logo variant="full" className="h-7 w-auto" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Stroke */}
        <div className="border border-gray-200 rounded-xl p-5 text-center">
          <p className="text-sm font-bold text-gray-900">Primary Stroke</p>
          <div className="my-4 flex items-center justify-center gap-3">
            <svg viewBox="0 0 80 80" className="w-20 h-20">
              <polygon points="40,8 70,24 70,56 40,72 10,56 10,24" fill="none" stroke="#8B5CF6" strokeWidth="3" strokeLinejoin="round" />
            </svg>
            <span className="text-sm font-semibold text-violet-600">2 px</span>
          </div>
          <p className="text-xs text-gray-500">Use a consistent 2px stroke for all product icons.</p>
        </div>

        {/* Corner radius */}
        <div className="border border-gray-200 rounded-xl p-5 text-center">
          <p className="text-sm font-bold text-gray-900">Corner Radius</p>
          <div className="my-4 flex items-center justify-center gap-6">
            <div>
              <div className="w-16 h-16 mx-auto border-2 border-violet-500 rounded-md" />
              <p className="text-xs text-gray-500 mt-1">6 px</p>
            </div>
            <div>
              <div className="w-16 h-16 mx-auto border-2 border-violet-500 rounded-2xl" />
              <p className="text-xs text-gray-500 mt-1">10 px</p>
            </div>
          </div>
          <p className="text-xs text-gray-500">Use 6px on small icons, 10px+ on large containers.</p>
        </div>

        {/* Line cap & join */}
        <div className="border border-gray-200 rounded-xl p-5 text-center">
          <p className="text-sm font-bold text-gray-900">Line Cap & Join</p>
          <div className="my-4 flex items-center justify-center gap-6">
            <div>
              <svg viewBox="0 0 60 30" className="w-20 h-10">
                <line x1="6" y1="15" x2="54" y2="15" stroke="#8B5CF6" strokeWidth="6" strokeLinecap="round" />
              </svg>
              <p className="text-xs text-gray-500 mt-1">Round Cap</p>
            </div>
            <div>
              <svg viewBox="0 0 60 40" className="w-20 h-12">
                <polyline points="8,32 30,8 52,32" fill="none" stroke="#8B5CF6" strokeWidth="6" strokeLinejoin="round" strokeLinecap="round" />
              </svg>
              <p className="text-xs text-gray-500 mt-1">Round Join</p>
            </div>
          </div>
          <p className="text-xs text-gray-500">Always use rounded caps and joins for a friendly feel.</p>
        </div>
      </div>
    </div>
  )
}

export const MARKETING_ASSETS: MarketingAssetMeta[] = [
  {
    slug: 'linkedin-announcement',
    number: 1,
    title: 'AI-Powered Data Quality You Can Trust',
    category: 'LinkedIn Announcement Post',
    description: 'A bold square post introducing CogniDQ to your network on LinkedIn.',
    render: Asset1,
  },
  {
    slug: 'feature-highlight',
    number: 2,
    title: 'Explainable. Actionable. Trusted.',
    category: 'Feature Highlight Social Tile',
    description: 'A social tile distilling the CogniDQ value prop into three pillars.',
    render: Asset2,
  },
  {
    slug: 'webinar-banner',
    number: 3,
    title: 'From Rules to Reliability',
    category: 'Webinar / Event Banner',
    description: 'A webinar promo banner with date, time, and registration CTA.',
    render: Asset3,
  },
  {
    slug: 'product-release',
    number: 4,
    title: 'CogniDQ 2.0 — Smarter Checks. Stronger Trust.',
    category: 'Product Release Banner',
    description: 'A dark release banner spotlighting CogniDQ 2.0 capabilities.',
    render: Asset4,
  },
  {
    slug: 'case-study',
    number: 5,
    title: 'FinServ Co. — 99% Data Quality Accuracy',
    category: 'Case Study Banner',
    description: 'A case-study banner with headline metrics and a customer quote.',
    render: Asset5,
  },
  {
    slug: 'email-header',
    number: 6,
    title: 'Trusted Data. Better Decisions. Stronger Outcomes.',
    category: 'Email Header',
    description: 'An email-header hero suitable for newsletters and announcements.',
    render: Asset6,
  },
  {
    slug: 'website-features',
    number: 7,
    title: 'An AI Trust Layer for Your Data',
    category: 'Website Feature Section (Mockup)',
    description: 'A four-column feature section for the marketing website.',
    render: Asset7,
  },
  {
    slug: 'cta-block',
    number: 8,
    title: 'Elevate Your Data Quality',
    category: 'CTA Block',
    description: 'A high-contrast CTA block with primary and secondary actions.',
    render: Asset8,
  },
  {
    slug: 'dark-hero',
    number: 9,
    title: 'Transform Business Rules into Executable Data Quality Checks',
    category: 'Dark Hero Banner Concept',
    description: 'A full-width dark hero with brand nav and trust strip.',
    render: Asset9,
  },
  {
    slug: 'product-icon-set',
    number: 10,
    title: 'CogniDQ Product Icon Set',
    category: 'Iconography — Product Icons',
    description: '16 core product concepts rendered as a consistent icon set.',
    render: Asset10,
  },
  {
    slug: 'visual-motifs',
    number: 11,
    title: 'Visual Motifs & Background Elements',
    category: 'Iconography — Motifs',
    description: 'Hexagon grid, nodes, shields, dots, orbs, blobs, soft grid and flow lines.',
    render: Asset11,
  },
  {
    slug: 'gradient-shapes',
    number: 12,
    title: 'Gradient & Shape Language',
    category: 'Iconography — Gradients',
    description: 'Brand-aligned gradient primitives and shape vocabulary.',
    render: Asset12,
  },
  {
    slug: 'intent-to-controls',
    number: 13,
    title: 'From Intent to Quality Controls',
    category: 'Iconography — Illustration Example',
    description: 'A three-step illustration: Business Intent → CogniDQ AI → Quality Controls.',
    render: Asset13,
  },
  {
    slug: 'icon-size-guide',
    number: 14,
    title: 'Icon Size Guide',
    category: 'Iconography — Sizing',
    description: 'Recommended icon sizes from 16 px through 64 px.',
    render: Asset14,
  },
  {
    slug: 'stroke-corner-join',
    number: 15,
    title: 'Stroke, Corner Radius & Line Joins',
    category: 'Iconography — Geometry',
    description: 'Geometry rules: 2px primary stroke, 6/10px radii, rounded caps and joins.',
    render: Asset15,
  },
]

export { BRAND_COLORS }
