import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../environments/environment';

export interface ApiChild { id: number; username: string; }
export interface ApiSubject { subject: string; accuracy_percent: number | null; }
export interface ChatTurn { role: 'user' | 'assistant'; content: string; }

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiUrl;

  children()                       { return this.http.get<{ children: ApiChild[] }>(`${this.base}/parent/children`); }
  summary(id: number, days = 7)    { return this.http.get<{ current_streak_days: number }>(`${this.base}/parent/children/${id}/summary?days=${days}`); }
  topics(id: number, days = 28)    { return this.http.get<{ subjects: ApiSubject[]; needs_help: string[] }>(`${this.base}/parent/children/${id}/topics?days=${days}`); }
  report(id: number, days = 14)    { return this.http.get<{ insights: string[] }>(`${this.base}/parent/children/${id}/report?days=${days}`); }
  chat(message: string)            { return this.http.post<{ reply: string }>(`${this.base}/chat`, { message }); }

  /** Ask the parent assistant a question about one child. The AI reads progress data only. */
  ask(childId: number, question: string, history: ChatTurn[]) {
    return this.http.post<{ answer: string; tools_used: string[] }>(
      `${this.base}/parent/children/${childId}/ask`, { question, history });
  }
}
