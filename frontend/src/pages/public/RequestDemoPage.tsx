/**
 * F134 P11 — Public Demo Request Page (CogniDQ branded)
 *
 * Marketing-style "Book a Demo" page matching the CogniDQ design system.
 */
import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CheckCircle,
  Loader2,
  Send,
  Sparkles,
  ShieldCheck,
  Zap,
  Users,
  CalendarDays,
  Compass,
  PlayCircle,
  ArrowRight,
  Mail,
  Phone,
  MessageCircle,
  ArrowLeft,
} from 'lucide-react'
import Logo from '@/components/Logo'
import { submitDemoRequest, type DemoRequestPayload } from '../../services/demoRequestService'

interface DemoFormState extends DemoRequestPayload {
  job_title?: string
  team_size?: string
  goals?: string
}

const INITIAL: DemoFormState = {
  first_name: '',
  last_name: '',
  email: '',
  company: '',
  use_case: '',
}

const REASONS = [
  { icon: Zap, title: 'AI-powered data quality', body: 'Automate checks, detect issues, and prevent bad data at scale.' },
  { icon: ShieldCheck, title: 'Trusted by data teams', body: 'Built for reliability, security, and enterprise-grade performance.' },
  { icon: PlayCircle, title: 'Quick time to value', body: 'Launch fast with pre-built connectors and templates.' },
  { icon: Users, title: 'Expert support', body: 'Work with data-quality experts who understand your challenges.' },
]

const STEPS = [
  { icon: CalendarDays, title: 'Schedule a demo', body: 'Pick a time that works best for you.' },
  { icon: Compass, title: 'Discovery call', body: 'We learn about your data and challenges.' },
  { icon: PlayCircle, title: 'Live demo', body: 'See CogniDQ in action with your scenario.' },
  { icon: ArrowRight, title: 'Next steps', body: 'Decide what works best to move forward.' },
]

const TRUSTED = ['FINERVA', 'Northbridge', 'DataForge', 'NextWave', 'Altura']

const INPUT_CLS =
  'w-full bg-dark-900/60 border border-dark-700 focus:border-violet-500 focus:ring-2 focus:ring-violet-500/20 rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-500 outline-none transition'

export default function RequestDemoPage() {
  const [form, setForm] = useState<DemoFormState>(INITIAL)
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
  ) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const extras = [
        form.job_title && `Job title: ${form.job_title}`,
        form.team_size && `Team size: ${form.team_size}`,
        form.goals && `Goal: ${form.goals}`,
        form.use_case,
      ].filter(Boolean)
      const payload: DemoRequestPayload = {
        first_name: form.first_name,
        last_name: form.last_name,
        email: form.email,
        company: form.company,
        use_case: extras.length ? extras.join('\n') : undefined,
      }
      await submitDemoRequest(payload)
      setSubmitted(true)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Something went wrong. Please try again.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-dark-950 via-dark-900 to-dark-950 text-gray-100">
      {/* Top nav */}
      <header className="border-b border-dark-800/60 bg-dark-950/70 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center" aria-label="CogniDQ home">
            <Logo variant="light" className="h-8 w-auto" />
          </Link>
          <Link to="/" className="inline-flex items-center text-sm text-gray-400 hover:text-white transition">
            <ArrowLeft className="w-4 h-4 mr-1" />
            Back to Home
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-32 right-0 w-[36rem] h-[36rem] bg-violet-500/20 rounded-full blur-3xl" />
          <div className="absolute -bottom-20 -left-10 w-[30rem] h-[30rem] bg-blue-500/10 rounded-full blur-3xl" />
        </div>
        <div className="relative max-w-7xl mx-auto px-6 lg:px-8 py-16 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <div>
            <span className="inline-flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-semibold tracking-widest uppercase bg-violet-500/15 text-violet-300 border border-violet-400/30">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Book a Demo</span>
            </span>
            <h1 className="mt-5 text-4xl lg:text-5xl font-black leading-tight">
              Let's build a{' '}
              <span className="bg-clip-text text-transparent bg-gradient-to-r from-violet-300 to-blue-400">
                data quality
              </span>{' '}
              strategy that scales.
            </h1>
            <p className="mt-5 text-gray-300 max-w-xl">
              Book a personalized demo with our experts and see how CogniDQ can help you deliver trusted data with confidence.
            </p>
            <ul className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-sm text-gray-300">
              {['Personalized Demo', 'Expert Consultation', 'No Obligation'].map((t) => (
                <li key={t} className="flex items-center space-x-2">
                  <CheckCircle className="w-4 h-4 text-green-400" />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="hidden lg:flex items-center justify-center">
            <div className="relative w-80 h-80">
              <div className="absolute inset-0 border-2 border-violet-500/40 rotate-45 rounded-3xl" />
              <div className="absolute inset-8 border-2 border-blue-500/40 rounded-3xl" />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-28 h-28 rounded-2xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center shadow-xl">
                  <CheckCircle className="w-14 h-14 text-white" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Form + Why */}
      <section className="relative max-w-7xl mx-auto px-6 lg:px-8 pb-16 grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Form card */}
        <div className="lg:col-span-2 glass border border-dark-700/60 rounded-2xl p-8">
          {submitted ? (
            <div className="text-center space-y-4 py-10">
              <CheckCircle className="mx-auto w-14 h-14 text-green-400" />
              <h2 className="text-2xl font-bold text-white">Request Submitted!</h2>
              <p className="text-gray-300 max-w-md mx-auto">
                Thank you — our team will review your request and reach out to{' '}
                <span className="text-violet-300 font-medium">{form.email}</span> within one business day.
              </p>
              <Link to="/" className="inline-flex items-center text-sm text-violet-300 hover:text-violet-200">
                <ArrowLeft className="w-4 h-4 mr-1" /> Back to Home
              </Link>
            </div>
          ) : (
            <>
              <div>
                <h2 className="text-2xl font-bold text-white">Book a demo</h2>
                <p className="mt-1 text-sm text-gray-400">
                  Fill out the form and we'll be in touch within one business day.
                </p>
              </div>

              {error && (
                <div className="mt-5 rounded-md bg-red-900/40 border border-red-700 px-4 py-3 text-sm text-red-300">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmit} className="mt-6 space-y-5">
                <Field label="Full name" required>
                  <div className="grid grid-cols-2 gap-3">
                    <input name="first_name" value={form.first_name} onChange={handleChange} required className={INPUT_CLS} placeholder="First name" />
                    <input name="last_name" value={form.last_name} onChange={handleChange} required className={INPUT_CLS} placeholder="Last name" />
                  </div>
                </Field>

                <Field label="Work email" required>
                  <input name="email" type="email" value={form.email} onChange={handleChange} required className={INPUT_CLS} placeholder="name@company.com" />
                </Field>

                <Field label="Company" required>
                  <input name="company" value={form.company} onChange={handleChange} required className={INPUT_CLS} placeholder="Enter your company name" />
                </Field>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                  <Field label="Job title">
                    <select name="job_title" value={form.job_title || ''} onChange={handleChange} className={INPUT_CLS}>
                      <option value="">Select your job title</option>
                      <option>Data Engineer</option>
                      <option>Data Analyst</option>
                      <option>Data Scientist</option>
                      <option>Head of Data / CDO</option>
                      <option>Data Governance</option>
                      <option>Other</option>
                    </select>
                  </Field>
                  <Field label="Team size">
                    <select name="team_size" value={form.team_size || ''} onChange={handleChange} className={INPUT_CLS}>
                      <option value="">Select team size</option>
                      <option>1–10</option>
                      <option>11–50</option>
                      <option>51–200</option>
                      <option>201–1,000</option>
                      <option>1,000+</option>
                    </select>
                  </Field>
                </div>

                <Field label="What are you trying to achieve?">
                  <select name="goals" value={form.goals || ''} onChange={handleChange} className={INPUT_CLS}>
                    <option value="">Select your primary use case</option>
                    <option>Automate data quality checks</option>
                    <option>Improve data trust & governance</option>
                    <option>Reduce manual validation effort</option>
                    <option>Detect anomalies and incidents</option>
                    <option>Compliance & audit readiness</option>
                  </select>
                </Field>

                <Field label="Additional details (optional)">
                  <textarea
                    name="use_case"
                    value={form.use_case}
                    onChange={handleChange}
                    rows={3}
                    className={`${INPUT_CLS} resize-none`}
                    placeholder="Tell us about your data quality goals"
                  />
                </Field>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full inline-flex items-center justify-center space-x-2 px-5 py-3 bg-violet-600 hover:bg-violet-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition"
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  <span>{loading ? 'Submitting…' : 'Book My Demo'}</span>
                </button>
                <p className="text-xs text-gray-500 text-center">
                  By submitting, you agree to our <a className="underline hover:text-gray-300">Privacy Policy</a>.
                </p>
              </form>
            </>
          )}
        </div>

        {/* Why enterprises choose CogniDQ */}
        <aside className="space-y-6">
          <div className="glass border border-dark-700/60 rounded-2xl p-6">
            <h3 className="text-lg font-bold text-white">Why enterprises choose CogniDQ</h3>
            <ul className="mt-4 space-y-4">
              {REASONS.map((r) => (
                <li key={r.title} className="flex items-start space-x-3">
                  <div className="mt-0.5 w-9 h-9 rounded-lg bg-violet-500/15 border border-violet-400/30 flex items-center justify-center shrink-0">
                    <r.icon className="w-4 h-4 text-violet-300" />
                  </div>
                  <div>
                    <p className="font-semibold text-white text-sm">{r.title}</p>
                    <p className="text-xs text-gray-400 leading-relaxed">{r.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <div className="glass border border-dark-700/60 rounded-2xl p-6">
            <p className="text-xs uppercase tracking-widest text-gray-400 font-semibold">
              Trusted by data-driven enterprises
            </p>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-gray-300">
              {TRUSTED.map((b) => (
                <span key={b} className="font-semibold tracking-wide">{b}</span>
              ))}
            </div>
          </div>
        </aside>
      </section>

      {/* What to expect */}
      <section className="relative max-w-7xl mx-auto px-6 lg:px-8 pb-16">
        <div className="glass border border-dark-700/60 rounded-2xl p-8">
          <h3 className="text-xl font-bold text-white">What to expect</h3>
          <ol className="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {STEPS.map((s, i) => (
              <li key={s.title} className="relative">
                <div className="w-10 h-10 rounded-lg bg-violet-500/15 border border-violet-400/30 flex items-center justify-center">
                  <s.icon className="w-5 h-5 text-violet-300" />
                </div>
                <p className="mt-3 text-xs uppercase tracking-widest text-gray-500">Step {i + 1}</p>
                <p className="mt-1 text-white font-semibold">{s.title}</p>
                <p className="mt-1 text-sm text-gray-400">{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Questions */}
      <section className="relative max-w-7xl mx-auto px-6 lg:px-8 pb-20">
        <div className="glass border border-dark-700/60 rounded-2xl p-8 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-1">
            <h3 className="text-xl font-bold text-white">Questions before you book?</h3>
            <p className="mt-2 text-sm text-gray-400">We're here to help.</p>
          </div>
          <div className="md:col-span-2 grid grid-cols-1 sm:grid-cols-3 gap-4">
            <ContactTile icon={Mail} label="Email us" value="hello@cognidq.com" />
            <ContactTile icon={Phone} label="Call us" value="+1 (415) 555-0123" />
            <ContactTile icon={MessageCircle} label="Chat with us" value="Available on our website" />
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-dark-800/60">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-gray-500">
          <div className="flex items-center space-x-3">
            <Logo variant="light" className="h-6 w-auto" />
            <span>© 2026 CogniDQ. All rights reserved.</span>
          </div>
          <div className="flex items-center space-x-6">
            <a className="hover:text-gray-300">Privacy Policy</a>
            <a className="hover:text-gray-300">Terms of Service</a>
            <a className="hover:text-gray-300">Security</a>
          </div>
        </div>
      </footer>
    </div>
  )
}

function Field({
  label,
  required,
  children,
}: {
  label: string
  required?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
        {label} {required && <span className="text-red-400">*</span>}
      </label>
      {children}
    </div>
  )
}

function ContactTile({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
}) {
  return (
    <div className="rounded-xl bg-dark-900/40 border border-dark-700/60 p-4">
      <div className="w-9 h-9 rounded-lg bg-violet-500/15 border border-violet-400/30 flex items-center justify-center">
        <Icon className="w-4 h-4 text-violet-300" />
      </div>
      <p className="mt-3 text-xs uppercase tracking-widest text-gray-500">{label}</p>
      <p className="mt-1 text-sm text-white font-medium">{value}</p>
    </div>
  )
}
