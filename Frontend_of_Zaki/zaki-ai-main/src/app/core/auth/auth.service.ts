import { Injectable, signal, computed, inject } from '@angular/core';
import { Router } from '@angular/router';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { DEMO_USERS } from '../data/demo-data';
import { TOKEN_KEY } from './auth.interceptor';

export type UserRole = 'student' | 'parent';

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  initials: string;
  role: UserRole;
}

const STORAGE_KEY = 'zaki_user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly router = inject(Router);
  private readonly http = inject(HttpClient);

  private readonly _user = signal<AuthUser | null>(this.restoreFromStorage());
  readonly user = this._user.asReadonly();
  readonly isAuthed = computed(() => this._user() !== null);

  private restoreFromStorage(): AuthUser | null {
    try {
      // A saved user without a token is an old local-only login, so treat it as signed out.
      if (!localStorage.getItem(TOKEN_KEY)) return null;
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      return JSON.parse(raw) as AuthUser;
    } catch {
      return null;
    }
  }

  async login(email: string, password: string): Promise<{ ok: boolean; error?: string }> {
    const match = DEMO_USERS.find(u => u.email.toLowerCase() === email.trim().toLowerCase());
    if (!match) {
      return { ok: false, error: 'Invalid email or password.' };
    }

    try {
      const res = await firstValueFrom(
        this.http.post<{ access_token: string; role: UserRole }>(
          `${environment.apiUrl}/auth/login`,
          { username: match.apiUsername, password },
        ),
      );

      const authUser: AuthUser = {
        id: match.id,
        email: match.email,
        name: match.name,
        initials: match.initials,
        role: res.role,
      };

      localStorage.setItem(TOKEN_KEY, res.access_token);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(authUser));
      this._user.set(authUser);
      return { ok: true };
    } catch (e) {
      const status = (e as HttpErrorResponse).status;
      if (status === 0) return { ok: false, error: 'Cannot reach the Zaki server. Is the API running?' };
            if (status === 401 || status === 422) return { ok: false, error: 'Invalid email or password.' };
      if (status === 429) return { ok: false, error: 'Too many attempts. Please wait a moment.' };
      return { ok: false, error: 'Sign-in failed. Please try again.' };
    }
  }

  register(_name: string, _email: string, _password: string): { ok: boolean; error?: string } {
    // The API only lets an admin create accounts, so sign-up is switched off for the demo.
    return { ok: false, error: 'Sign-up is not available in the demo. Please sign in with a demo account.' };
  }

  logout(): void {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(TOKEN_KEY);
    this._user.set(null);
    this.router.navigate(['/ai-chat']);
  }

  redirectToDashboard(): void {
    const u = this._user();
    if (!u) {
      this.router.navigate(['/auth/sign-in']);
      return;
    }
    this.router.navigate([`/dashboard/${u.role}`]);
  }
}