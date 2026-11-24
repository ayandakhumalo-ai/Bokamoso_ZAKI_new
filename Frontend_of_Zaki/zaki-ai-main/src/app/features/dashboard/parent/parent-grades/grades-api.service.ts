import { Injectable } from '@angular/core';
import { GRADES_API } from './grades-api.config';
import { ChildLink, QuizDetail, QuizReport, RangeKey, WeaknessReport } from './grades.models';

export class GradesApiError extends Error {
  constructor(message: string, readonly status = 0) { super(message); }
}

@Injectable({ providedIn: 'root' })
export class GradesApiService {
  private demoToken: string | null = null;

  children() { return this.get<{ children: ChildLink[] }>('/parent/children').then(r => r.children); }
  quizzes(childId: number, range: RangeKey) { return this.get<QuizReport>(`/parent/children/${childId}/quizzes?range=${range}`); }
  quiz(childId: number, quizId: number) { return this.get<QuizDetail>(`/parent/children/${childId}/quizzes/${quizId}`); }
  weaknesses(childId: number, range: RangeKey) { return this.get<WeaknessReport>(`/parent/children/${childId}/quizzes/weaknesses?range=${range}`); }

  private async token(): Promise<string> {
    const own = GRADES_API.getToken();
    if (own) return own;
    if (this.demoToken) return this.demoToken;
    const demo = GRADES_API.demoLogin;
    if (!demo) throw new GradesApiError('You are not signed in to the Zaki API.', 401);
    const res = await this.send('/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(demo),
    });
    if (!res.ok) throw new GradesApiError('The demo login was refused by the Zaki API.', res.status);
    this.demoToken = (await res.json()).access_token as string;
    return this.demoToken;
  }

  private async send(path: string, init?: RequestInit): Promise<Response> {
    try {
      return await fetch(GRADES_API.baseUrl + path, init);
    } catch {
      throw new GradesApiError(`Cannot reach the Zaki API at ${GRADES_API.baseUrl}. Is it running?`);
    }
  }

  private async get<T>(path: string, retried = false): Promise<T> {
    const res = await this.send(path, { headers: { Authorization: `Bearer ${await this.token()}` } });
    if (res.status === 401 && !retried && !GRADES_API.getToken()) {   // an old demo token: sign in again once
      this.demoToken = null;
      return this.get<T>(path, true);
    }
    if (!res.ok) {
      throw new GradesApiError(res.status === 403 ? 'This account cannot see grades.' : `The Zaki API answered with an error (${res.status}).`, res.status);
    }
    return res.json() as Promise<T>;
  }
}
