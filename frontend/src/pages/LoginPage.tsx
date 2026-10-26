import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { ApiError, authApi, type AuthUser } from '../lib/api'

const schema = z.object({ email: z.string().email('Enter a valid email address.'), password: z.string().min(1, 'Enter your password.') })
type FormData = z.infer<typeof schema>

export default function LoginPage({ onLogin }: { onLogin: (user: AuthUser) => void }) {
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({ resolver: zodResolver(schema) })
  const submit = handleSubmit(async ({ email, password }) => {
    setError('')
    setSubmitting(true)
    try { onLogin(await authApi.login(email, password)) }
    catch (cause) {
      setError(cause instanceof ApiError && cause.status === 401
        ? 'Sign-in failed. Check your email and password, then try again.'
        : 'The sign-in service is unavailable right now. Try again in a moment.')
    }
    finally { setSubmitting(false) }
  })
  return <main className="auth-page"><section className="auth-card">
    <a className="brand auth-brand" href="/"><span className="brand-icon">h</span><span>hearth<small>PROPERTY CARE</small></span></a>
    <h1>Welcome back</h1><p className="auth-subtitle">Sign in to manage your rental portfolio.</p>
    {error && <div className="form-alert" role="alert">{error}</div>}
    <form onSubmit={submit} noValidate>
      <label htmlFor="email">Email address</label><input id="email" type="email" autoComplete="username" {...register('email')} aria-invalid={!!errors.email}/>{errors.email&&<span className="field-error">{errors.email.message}</span>}
      <label htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" {...register('password')} aria-invalid={!!errors.password}/>{errors.password&&<span className="field-error">{errors.password.message}</span>}
      <button className="button primary auth-submit" disabled={submitting}>{submitting?'Signing in…':'Sign in'}</button>
    </form>
    <p className="auth-footnote">Accounts are created by invitation or owner setup. Public registration is disabled.</p>
  </section><p className="auth-copyright">© Hearth · Rental management</p></main>
}
