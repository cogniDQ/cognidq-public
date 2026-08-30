import { ReactNode, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Code2, Github, User, LogOut, Settings, ChevronDown, Image } from 'lucide-react'
import { Toaster } from 'react-hot-toast'
import { useAuth } from '../contexts/AuthContext'
import RoleBadge from './RoleBadge'
import RoleStripe from './RoleStripe'
import Logo from './Logo'
import ThemeToggle from '../theme/ThemeToggle'
import { useTheme } from '../theme/ThemeContext'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout, isAuthenticated } = useAuth()
  const { resolved } = useTheme()
  const [showUserMenu, setShowUserMenu] = useState(false)
  const isDark = resolved === 'dark'

  // Only show nav items on profile/settings pages, not on home page
  const isHomePage = location.pathname === '/'
  
  const navItems = !isHomePage ? [
    { path: '/profile', label: 'Profile', icon: User },
    { path: '/settings', label: 'Settings', icon: Settings },
  ] : []

  const handleLogout = async () => {
    await logout()
    navigate('/auth/login')
  }

  return (
    <div className="min-h-screen flex flex-col bg-surface text-content transition-colors">
      <RoleStripe />
      <Toaster position="top-right" toastOptions={{ duration: 4000 }} />
      {/* Ambient background effects — subtle in both themes */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-32 right-0 w-[40rem] h-[40rem] bg-brand/10 rounded-full blur-3xl"></div>
        <div className="absolute -bottom-40 -left-20 w-[40rem] h-[40rem] bg-info/10 rounded-full blur-3xl"></div>
      </div>

      {/* Header */}
      <header className="glass sticky top-0 z-50 border-b border-edge">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="flex items-center group" aria-label="CogniDQ home">
              <div className="relative">
                <Logo variant={isDark ? 'light' : 'full'} className="h-9 w-auto group-hover:scale-105 transition-transform" />
                <div className="absolute inset-0 bg-brand/10 blur-2xl group-hover:bg-brand/20 transition-colors pointer-events-none"></div>
              </div>
              <span className="sr-only">CogniDQ</span>
            </Link>

            <nav className="flex items-center space-x-2">
              {navItems.map((item) => {
                const Icon = item.icon
                const isActive = location.pathname === item.path
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-all ${
                      isActive
                        ? 'bg-brand-soft text-brand font-medium'
                        : 'text-content-muted hover:text-content hover:bg-surface-overlay'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    <span className="hidden sm:inline">{item.label}</span>
                  </Link>
                )
              })}
              
              {isHomePage && (
                <Link
                  to="/hub"
                  className="btn btn-primary btn-sm ml-2"
                >
                  Go to DQ Hub
                </Link>
              )}

              <Link
                to="/marketing"
                className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-all ml-2 ${
                  location.pathname.startsWith('/marketing')
                    ? 'bg-brand-soft text-brand font-medium'
                    : 'text-content-muted hover:text-content hover:bg-surface-overlay'
                }`}
              >
                <Image className="w-4 h-4" />
                <span className="hidden sm:inline">Marketing Kit</span>
              </Link>

              <Link
                to="/request-demo"
                className="ml-2 inline-flex items-center px-4 py-2 rounded-lg bg-brand hover:bg-brand-hover text-white text-sm font-semibold transition-colors shadow-lg shadow-brand/30"
              >
                Request a Demo
              </Link>

              <a
                href="http://localhost:8000/api/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center space-x-2 px-4 py-2 rounded-lg text-content-muted hover:text-content hover:bg-surface-overlay transition-all ml-2"
              >
                <Code2 className="w-4 h-4" />
                <span className="hidden sm:inline">API Docs</span>
              </a>

              <ThemeToggle
                className="ml-2 inline-flex h-9 w-9 items-center justify-center rounded-lg text-content-muted hover:bg-surface-overlay hover:text-content transition-colors"
              />

              {/* User Menu */}
              {isAuthenticated && user ? (
                <div className="relative ml-4 flex items-center gap-3">
                  <RoleBadge />
                  <button
                    onClick={() => setShowUserMenu(!showUserMenu)}
                    className="flex items-center space-x-2 px-3 py-2 rounded-lg text-content hover:bg-surface-overlay transition-all"
                  >
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand to-info flex items-center justify-center">
                      {user.avatar_url ? (
                        <img src={user.avatar_url} alt={user.full_name || user.email} className="w-full h-full rounded-full" />
                      ) : (
                        <span className="text-sm font-medium text-white">
                          {(user.full_name || user.email)[0].toUpperCase()}
                        </span>
                      )}
                    </div>
                    <span className="hidden md:inline text-sm font-medium">{user.full_name || user.email}</span>
                    <ChevronDown className={`w-4 h-4 transition-transform ${showUserMenu ? 'rotate-180' : ''}`} />
                  </button>

                  {/* Dropdown Menu */}
                  {showUserMenu && (
                    <>
                      <div className="fixed inset-0 z-10" onClick={() => setShowUserMenu(false)}></div>
                      <div className="absolute right-0 mt-2 w-56 glass rounded-lg shadow-xl border border-edge z-20">
                        <div className="px-4 py-3 border-b border-edge">
                          <p className="text-sm font-medium text-content">{user.full_name || 'User'}</p>
                          <p className="text-xs text-content-muted truncate">{user.email}</p>
                        </div>
                        <div className="py-2">
                          <button
                            onClick={() => {
                              navigate('/profile')
                              setShowUserMenu(false)
                            }}
                            className="w-full flex items-center space-x-2 px-4 py-2 text-sm text-content hover:bg-surface-overlay transition-colors"
                          >
                            <User className="w-4 h-4" />
                            <span>Profile</span>
                          </button>
                          <button
                            onClick={() => {
                              navigate('/settings')
                              setShowUserMenu(false)
                            }}
                            className="w-full flex items-center space-x-2 px-4 py-2 text-sm text-content hover:bg-surface-overlay transition-colors"
                          >
                            <Settings className="w-4 h-4" />
                            <span>Settings</span>
                          </button>
                        </div>
                        <div className="border-t border-edge py-2">
                          <button
                            onClick={handleLogout}
                            className="w-full flex items-center space-x-2 px-4 py-2 text-sm text-danger hover:bg-surface-overlay transition-colors"
                          >
                            <LogOut className="w-4 h-4" />
                            <span>Logout</span>
                          </button>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              ) : (
                <Link
                  to="/auth/login"
                  className="ml-4 px-4 py-2 bg-brand hover:bg-brand-hover text-white font-medium rounded-lg transition-colors"
                >
                  Sign In
                </Link>
              )}
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 relative z-10">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8">
          {children}
        </div>
      </main>

      {/* Footer */}
      <footer className="glass border-t border-edge mt-auto relative z-10">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 py-8">
          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-sm font-semibold text-content">CogniDQ</p>
              <p className="mt-2 text-xs text-content-muted">
                The AI trust layer for enterprise data quality.
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-content-muted">Product</p>
              <ul className="mt-3 space-y-2 text-sm">
                <li><Link to="/" className="text-content hover:text-brand">Overview</Link></li>
                <li><Link to="/hub" className="text-content hover:text-brand">Open the Hub</Link></li>
                <li><Link to="/request-demo" className="text-content hover:text-brand">Request a demo</Link></li>
              </ul>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-content-muted">Trust</p>
              <ul className="mt-3 space-y-2 text-sm">
                <li><Link to="/trust" className="text-content hover:text-brand">Trust center</Link></li>
                <li><Link to="/security" className="text-content hover:text-brand">Security</Link></li>
                <li><Link to="/privacy" className="text-content hover:text-brand">Privacy</Link></li>
                <li><Link to="/status" className="text-content hover:text-brand">Status</Link></li>
              </ul>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-content-muted">Resources</p>
              <ul className="mt-3 space-y-2 text-sm">
                <li><Link to="/contact" className="text-content hover:text-brand">Contact</Link></li>
                <li>
                  <a
                    href="http://localhost:8000/api/docs"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-content hover:text-brand"
                  >
                    <Code2 className="w-3.5 h-3.5" /> API docs
                  </a>
                </li>
                <li>
                  <a
                    href="https://github.com"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-content hover:text-brand"
                  >
                    <Github className="w-3.5 h-3.5" /> GitHub
                  </a>
                </li>
              </ul>
            </div>
          </div>
          <div className="mt-8 flex flex-col gap-3 border-t border-edge pt-6 sm:flex-row sm:items-center sm:justify-between text-xs text-content-muted">
            <p>© 2026 CogniDQ</p>
            <span className="px-2 py-1 bg-brand-soft text-brand rounded font-mono">v1.0.0</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
