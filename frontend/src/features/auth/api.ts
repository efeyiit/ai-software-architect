import { z } from 'zod';

const sessionSchema = z.strictObject({ user_id: z.string().min(1), csrf_token: z.string().min(1) });

export type Session = z.infer<typeof sessionSchema>;
export type AuthErrorKind = 'configuration' | 'unavailable' | 'failed';

export class AuthApiError extends Error {
  constructor(readonly kind: AuthErrorKind, message: string, readonly status?: number) { super(message); this.name = 'AuthApiError'; }
}

function errorCode(body: unknown) {
  if (!body || typeof body !== 'object') return '';
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === 'object' && detail && 'code' in detail && typeof detail.code === 'string') return detail.code;
  if (typeof detail === 'string') return detail;
  return '';
}

export const authApi = {
  async session(): Promise<Session | null> {
    let response: Response;
    try { response = await fetch('/auth/me', { credentials: 'include', headers: { Accept: 'application/json' } }); }
    catch { throw new AuthApiError('unavailable', 'Ariadne kimlik doğrulama servisine ulaşılamadı.'); }
    if (response.status === 401) return null;
    if (!response.ok) {
      let body: unknown;
      try { body = await response.json(); } catch { body = undefined; }
      const code = errorCode(body);
      throw new AuthApiError(response.status === 503 && (code === 'configuration_unavailable' || code === 'configuration_error') ? 'configuration' : response.status >= 500 ? 'unavailable' : 'failed', code, response.status);
    }
    let body: unknown;
    try { body = await response.json(); } catch { throw new AuthApiError('failed', 'Oturum yanıtı okunamadı.', response.status); }
    const parsed = sessionSchema.safeParse(body);
    if (!parsed.success) throw new AuthApiError('failed', 'Oturum yanıtı beklenen sözleşmeye uymuyor.', response.status);
    return parsed.data;
  },
  async logout(session: Session): Promise<void> {
    let response: Response;
    try { response = await fetch('/auth/logout', { method: 'POST', credentials: 'include', headers: { 'X-Ariadne-CSRF': session.csrf_token, Accept: 'application/json' } }); }
    catch { throw new AuthApiError('unavailable', 'Oturum kapatma servisine ulaşılamadı.'); }
    if (!response.ok) throw new AuthApiError(response.status >= 500 ? 'unavailable' : 'failed', 'Oturum kapatılamadı.', response.status);
  },
};
