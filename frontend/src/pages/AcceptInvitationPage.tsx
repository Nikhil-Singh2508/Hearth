import { useState } from 'react'
import { ApiError, authApi } from '../lib/api'

export default function AcceptInvitationPage() {
  const [error, setError] = useState('')
  const [accepted, setAccepted] = useState(false)
  const [busy, setBusy] = useState(false)
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setBusy(true)
    const form = new FormData(event.currentTarget)
    const password = String(form.get('password') ?? '')
    if (password !== String(form.get('confirm_password') ?? '')) { setError('Passwords do not match.'); setBusy(false); return }
    try {
      await authApi.acceptInvitation({ token: String(form.get('token')).trim(), display_name: String(form.get('display_name')).trim(), password })
      setAccepted(true)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not accept the invitation. Try again.')
    } finally { setBusy(false) }
  }
  return <main className="auth-page"><section className="auth-card">
    <a className="brand auth-brand" href="/"><span className="brand-icon">h</span><span>hearth<small>PROPERTY CARE</small></span></a>
    {accepted ? <><h1>Account created</h1><p className="auth-subtitle">Your tenant account is ready. Sign in with your email and new password.</p><a className="button primary auth-submit accept-login" href="/">Go to sign in</a></> : <>
      <h1>Accept your invitation</h1><p className="auth-subtitle">Create your account to access your rental information.</p>
      {error && <div className="form-alert" role="alert">{error}</div>}
      <form onSubmit={submit}>
        <label htmlFor="token">Invitation token</label><textarea id="token" name="token" required minLength={30} autoComplete="off" />
        <label htmlFor="display-name">Your name</label><input id="display-name" name="display_name" required maxLength={160} autoComplete="name" />
        <label htmlFor="new-password">Password (at least 8 characters)</label><input id="new-password" name="password" type="password" required minLength={8} autoComplete="new-password" />
        <label htmlFor="confirm-password">Confirm password</label><input id="confirm-password" name="confirm_password" type="password" required minLength={8} autoComplete="new-password" />
        <button className="button primary auth-submit" disabled={busy}>{busy ? 'Creating account…' : 'Create tenant account'}</button>
      </form>
    </>}
  </section><p className="auth-copyright">© Hearth · Rental management</p></main>
}
