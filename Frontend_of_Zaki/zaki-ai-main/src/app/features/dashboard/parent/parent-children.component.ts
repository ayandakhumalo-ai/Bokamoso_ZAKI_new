import { Component, ChangeDetectionStrategy, OnInit, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { Router } from '@angular/router';
import { ApiService } from '../../../core/api.service';
import { ChildDemo } from '../../../core/data/demo-data';
import { SelectedChildService } from '../../../core/selected-child.service';

@Component({
  selector: 'app-parent-children',
  standalone: true,
  imports: [MatIconModule],
  template: `
    <div class="wrap">
      <div class="head">
        <h1>My Children</h1>
        <p>Choose a child to open their dashboard or report.</p>
      </div>

      <div class="grid">
        @for (c of children; track c.profile.id) {
          <article class="child-card" [class.selected]="c.profile.id === selectedId()">
            <div class="top">
              <div class="avatar">{{ c.profile.initials }}</div>
              <div class="who">
                <h2>{{ c.profile.name }}</h2>
                <p>{{ c.profile.grade }} · {{ c.profile.school }}</p>
              </div>
              @if (c.profile.deviceOnline) {
                <span class="pill"><span class="dot"></span>Device online</span>
              }
            </div>

            <div class="stats">
              <div><strong>{{ streakOf(c) }}</strong><span>day streak</span></div>
              <div><strong>{{ c.profile.timeToday }}</strong><span>today</span></div>
              <div><strong>#{{ c.profile.rank }}</strong><span>rank</span></div>
            </div>

            <div class="focus">
              <span class="focus-label">Needs attention</span>
              @for (t of helpOf(c); track t) {
                <span class="chip">{{ t }}</span>
              } @empty {
                <span class="ok">Nothing flagged</span>
              }
            </div>

            <div class="actions">
              <button type="button" class="btn primary" (click)="open(c.profile.id, 'dashboard')">
                <mat-icon>dashboard</mat-icon>View dashboard
              </button>
              <button type="button" class="btn" (click)="open(c.profile.id, 'reports')">
                <mat-icon>bar_chart</mat-icon>View report
              </button>
            </div>
          </article>
        }
      </div>
    </div>
  `,
  styles: [`
    :host { display: block; }
    .wrap { padding: 32px; background: #F7F9FC; min-height: 100%; }
    .head h1 { font-size: 24px; font-weight: 800; color: #0A2540; margin: 0 0 6px; letter-spacing: -.02em; }
    .head p { font-size: 14px; color: #697386; margin: 0 0 24px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 20px; }
    .child-card {
      background: #fff; border: 1px solid #E8EDF2; border-radius: 18px; padding: 24px;
      box-shadow: 0 1px 3px rgba(10,37,64,.04), 0 8px 28px rgba(10,37,64,.06);
    }
    .child-card.selected { border-color: #7C3AED; box-shadow: 0 0 0 3px rgba(124,58,237,.12); }
    .top { display: flex; align-items: center; gap: 14px; margin-bottom: 20px; }
    .avatar {
      width: 52px; height: 52px; border-radius: 50%; background: #EDE9FE; color: #7C3AED;
      display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 17px; flex-shrink: 0;
    }
    .who { flex: 1; min-width: 0; }
    .who h2 { font-size: 17px; font-weight: 800; color: #0A2540; margin: 0 0 2px; }
    .who p { font-size: 12.5px; color: #697386; margin: 0; }
    .pill {
      display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 700;
      color: #059669; background: #ECFDF5; border-radius: 100px; padding: 4px 10px; white-space: nowrap;
    }
    .dot { width: 6px; height: 6px; border-radius: 50%; background: #10B981; }
    .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 18px; }
    .stats div { background: #F7F9FC; border-radius: 12px; padding: 10px 8px; text-align: center; }
    .stats strong { display: block; font-size: 16px; font-weight: 800; color: #0A2540; }
    .stats span { font-size: 11px; color: #697386; }
    .focus { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 20px; min-height: 28px; }
    .focus-label { font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #697386; margin-right: 4px; }
    .chip { font-size: 12px; font-weight: 700; color: #B45309; background: #FFFBEB; border: 1px solid rgba(217,119,6,.25); border-radius: 100px; padding: 3px 10px; }
    .ok { font-size: 12.5px; color: #059669; font-weight: 600; }
    .actions { display: flex; gap: 10px; }
    .btn {
      flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 6px;
      border: 1px solid #E8EDF2; background: #fff; color: #0A2540; font: inherit; font-size: 13px; font-weight: 700;
      border-radius: 12px; padding: 10px 12px; cursor: pointer;
    }
    .btn:hover { border-color: #C4B5FD; }
    .btn.primary { background: #7C3AED; border-color: #7C3AED; color: #fff; }
    .btn mat-icon { font-size: 18px; width: 18px; height: 18px; line-height: 18px; }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ParentChildrenComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly sel = inject(SelectedChildService);
  private readonly router = inject(Router);

  readonly children = this.sel.children;
  readonly selectedId = this.sel.selectedId;

  // Live values from the API, keyed by child id. Until they arrive, the demo values are shown.
  private readonly streaks = signal<Record<string, number>>({});
  private readonly needsHelp = signal<Record<string, string[]>>({});

  ngOnInit(): void {
    this.api.children().subscribe({
      next: ({ children }) => {
        for (const demo of this.children) {
          const apiChild = children.find(c => c.username === demo.profile.apiUsername);
          if (!apiChild) continue;
          const id = demo.profile.id;
          this.api.summary(apiChild.id, 7).subscribe({
            next: s => this.streaks.update(m => ({ ...m, [id]: s.current_streak_days })),
            error: () => { /* keep the demo value */ },
          });
          this.api.topics(apiChild.id, 28).subscribe({
            next: t => this.needsHelp.update(m => ({ ...m, [id]: t.needs_help })),
            error: () => { /* keep the demo value */ },
          });
        }
      },
      error: () => { /* API unreachable: keep the demo values */ },
    });
  }

  streakOf(c: ChildDemo): number {
    return this.streaks()[c.profile.id] ?? c.profile.streakDays;
  }

  helpOf(c: ChildDemo): string[] {
    return this.needsHelp()[c.profile.id] ?? c.parentDashboard.focusAreas.map(f => f.title);
  }

  gpaOf(c: ChildDemo): string {
    return c.parentDashboard.stats[0]?.value ?? '-';
  }

  open(id: string, page: 'dashboard' | 'reports'): void {
    this.sel.select(id);
    void this.router.navigate([page === 'reports' ? '/dashboard/parent/reports' : '/dashboard/parent']);
  }
}
