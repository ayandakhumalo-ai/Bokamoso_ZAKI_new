import { Component, ChangeDetectionStrategy, OnInit, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { ApiService, ApiSubject } from '../../../core/api.service';
import { ChildDemo, Mastery } from '../../../core/data/demo-data';
import { SelectedChildService } from '../../../core/selected-child.service';

@Component({
  selector: 'app-parent-dashboard',
  standalone: true,
  imports: [MatIconModule, RouterLink],
  templateUrl: './parent-dashboard.component.html',
  styleUrl: './parent-dashboard.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ParentDashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly sel = inject(SelectedChildService);

  // Circumference of ring circle (r=36): 2π×36
  readonly RING_C = 226.2;

  ringOffset(score: number): number {
    return this.RING_C - (score / 100) * this.RING_C;
  }

  // School data the API does not have comes from demo-data.ts, for whichever child is selected.
  private get child(): ChildDemo { return this.sel.child(); }
  get children(): readonly ChildDemo[] { return this.sel.children; }
  get profile() { return this.child.profile; }
  get stats() { return this.child.parentDashboard.stats; }
  get todayActivity() { return this.child.parentDashboard.todayActivity; }
  get aiInsight() { return this.child.parentDashboard.aiInsight; }
  get focusAreas() { return this.child.parentDashboard.focusAreas; }
  get achievements() { return this.child.parentDashboard.achievements; }

  // Start with the demo values, then the API replaces them. If the API is down, these stay.
  readonly streak = signal<number>(0);
  readonly mastery = signal<Mastery[]>([]);

  ngOnInit(): void {
    this.loadChild();
  }

  switchTo(id: string): void {
    if (id === this.sel.selectedId()) return;
    this.sel.select(id);
    this.loadChild();
  }

  private loadChild(): void {
    const demo = this.child;
    this.streak.set(demo.profile.streakDays);
    this.mastery.set(demo.parentDashboard.mastery);

    this.api.children().subscribe({
      next: ({ children }) => {
        const apiChild = children.find(c => c.username === demo.profile.apiUsername);
        if (!apiChild) return;

        this.api.summary(apiChild.id, 7).subscribe({
          next: s => { if (this.isCurrent(demo)) this.streak.set(s.current_streak_days); },
          error: () => { /* keep the demo value */ },
        });

        this.api.topics(apiChild.id, 28).subscribe({
          next: t => {
            if (!this.isCurrent(demo)) return;
            const live = this.toMastery(demo, t.subjects);
            if (live.length > 0) this.mastery.set(live);
          },
          error: () => { /* keep the demo values */ },
        });
      },
      error: () => { /* API unreachable: keep the demo values */ },
    });
  }

  // Ignore a late answer if the parent has already switched to another child.
  private isCurrent(demo: ChildDemo): boolean {
    return this.sel.selectedId() === demo.profile.id;
  }

  private toMastery(demo: ChildDemo, subjects: ApiSubject[]): Mastery[] {
    const styles = new Map<string, Mastery>();
    for (const m of demo.parentDashboard.mastery) styles.set(m.subject, m);

    const result: Mastery[] = [];
    for (const s of subjects) {
      const base = styles.get(s.subject);
      if (!base || s.accuracy_percent === null) continue;
      const score = Math.round(s.accuracy_percent);
      result.push({ subject: s.subject, score, grade: this.letter(score), color: base.color, track: base.track });
    }
    return result.sort((x, y) => y.score - x.score);
  }

  private letter(n: number): string {
    return n >= 95 ? 'A+' : n >= 85 ? 'A' : n >= 75 ? 'B+' : n >= 70 ? 'B' : n >= 65 ? 'C+' : n >= 60 ? 'C' : 'D';
  }
}
