import {
  Component, ChangeDetectionStrategy, ElementRef, HostListener, Injector, OnInit,
  afterNextRender, computed, inject, signal, viewChild,
} from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { GradesApiError, GradesApiService } from './grades-api.service';
import { ChildLink, QuizBar, QuizDetail, QuizReport, RangeKey, TopicResult, WeaknessReport } from './grades.models';

const SUBJECT_COLORS: Record<string, string> = {
  Mathematics: '#7C3AED', Physics: '#059669', English: '#2563EB', History: '#D97706',
  Biology: '#DC2626', Science: '#0891B2', Geography: '#65A30D', Chemistry: '#DB2777',
};
const FALLBACK_COLORS = ['#0F766E', '#B45309', '#4F46E5', '#BE185D', '#4D7C0F'];

@Component({
  selector: 'app-parent-grades',
  standalone: true,
  imports: [MatIconModule],
  templateUrl: './parent-grades.component.html',
  styleUrl: './parent-grades.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ParentGradesComponent implements OnInit {
  private readonly api = inject(GradesApiService);
  private readonly injector = inject(Injector);
  private readonly scroller = viewChild<ElementRef<HTMLElement>>('scroller');
  private loadSeq = 0;

  readonly ranges: { key: RangeKey; label: string; long: string }[] = [
    { key: 'week', label: 'Week', long: 'the last 7 days' },
    { key: 'month', label: 'Month', long: 'the last 30 days' },
    { key: 'year', label: 'Year', long: 'the last 12 months' },
    { key: 'all', label: 'All time', long: 'everything since the first quiz' },
  ];
  readonly yTicks = [100, 75, 50, 25, 0];

  readonly children = signal<ChildLink[]>([]);
  readonly childId = signal<number | null>(null);
  readonly range = signal<RangeKey>('week');
  readonly report = signal<QuizReport | null>(null);
  readonly weak = signal<WeaknessReport | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly hidden = signal<string[]>([]);
  readonly selected = signal<QuizDetail | null>(null);
  readonly detailLoading = signal(false);
  readonly detailError = signal<string | null>(null);

  readonly rangeIndex = computed(() => this.ranges.findIndex(r => r.key === this.range()));
  readonly rangeInfo = computed(() => this.ranges[this.rangeIndex()]);
  readonly childName = computed(() => this.children().find(c => c.id === this.childId())?.username ?? '');
  readonly subjects = computed(() => this.report()?.subjects ?? []);
  readonly bars = computed(() => (this.report()?.quizzes ?? []).filter(q => !this.hidden().includes(q.subject)));
  readonly trackWidth = computed(() => `max(100%, ${this.bars().length * 68}px)`);
  readonly showYear = computed(() => this.range() === 'year' || this.range() === 'all');
  readonly weakTopics = computed(() => this.weak()?.weak_topics ?? []);
  readonly strongTopics = computed(() => this.weak()?.strong_topics ?? []);

  ngOnInit(): void { void this.start(); }

  private async start(): Promise<void> {
    try {
      const kids = await this.api.children();
      this.children.set(kids);
      if (!kids.length) { this.loading.set(false); this.error.set('No children are linked to this account yet.'); return; }
      this.childId.set(kids[0].id);
      await this.load();
    } catch (e) { this.fail(e); }
  }

  async load(): Promise<void> {
    const id = this.childId();
    if (id === null) return;
    const seq = ++this.loadSeq;
    this.loading.set(true);
    this.error.set(null);
    try {
      const [report, weak] = await Promise.all([this.api.quizzes(id, this.range()), this.api.weaknesses(id, this.range())]);
      if (seq !== this.loadSeq) return;                         // a newer request has replaced this one
      this.report.set(report);
      this.weak.set(weak);
      this.hidden.set([]);
      this.loading.set(false);
      afterNextRender(() => {                                   // newest quizzes are on the right: show them first
        const el = this.scroller()?.nativeElement;
        if (el) el.scrollLeft = el.scrollWidth;
      }, { injector: this.injector });
    } catch (e) { if (seq === this.loadSeq) this.fail(e); }
  }

  private fail(e: unknown): void {
    this.loading.set(false);
    this.error.set(e instanceof GradesApiError ? e.message : 'Something went wrong loading the grades.');
  }

  setRange(key: RangeKey): void { if (key !== this.range()) { this.range.set(key); void this.load(); } }
  /** +1 zooms out to a longer period (week, month, year, all time); -1 zooms back in. */
  zoom(step: 1 | -1): void {
    const next = this.ranges[this.rangeIndex() + step];
    if (next) this.setRange(next.key);
  }
  pickChild(id: number): void { if (id !== this.childId()) { this.childId.set(id); this.selected.set(null); void this.load(); } }

  toggleSubject(subject: string): void {
    this.hidden.update(h => h.includes(subject) ? h.filter(s => s !== subject) : [...h, subject]);
  }

  async open(bar: QuizBar): Promise<void> {
    const id = this.childId();
    if (id === null) return;
    this.detailError.set(null);
    this.detailLoading.set(true);
    this.selected.set({ ...bar, questions: [] });
    try {
      const detail = await this.api.quiz(id, bar.id);
      if (this.selected()?.id === bar.id) this.selected.set(detail);
    } catch (e) {
      this.detailError.set(e instanceof GradesApiError ? e.message : 'Could not load this quiz.');
    }
    this.detailLoading.set(false);
  }

  @HostListener('document:keydown.escape')
  close(): void { this.selected.set(null); }

  // ---- display helpers ----
  color(subject: string): string {
    const known = SUBJECT_COLORS[subject];
    if (known) return known;
    let hash = 0;
    for (const ch of subject) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
    return FALLBACK_COLORS[hash % FALLBACK_COLORS.length];
  }

  band(percent: number): 'good' | 'mid' | 'low' { return percent >= 75 ? 'good' : percent >= 50 ? 'mid' : 'low'; }

  fmtDate(iso: string, withYear = false): string {
    const d = new Date(iso + 'T12:00:00');
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', ...(withYear ? { year: '2-digit' } : {}) });
  }

  rangeText(r: QuizReport): string {
    return `${this.fmtDate(r.start, true)} to ${this.fmtDate(r.end, true)}`;
  }

  minutes(seconds: number | null): string | null { return seconds ? `${Math.max(1, Math.round(seconds / 60))} min` : null; }

  barLabel(q: QuizBar): string {
    return `${q.title}, ${q.subject}, ${q.score_percent} percent, grade ${q.grade}, ${this.fmtDate(q.date, true)}. Open the questions.`;
  }

  trackTopic(_: number, t: TopicResult): string { return t.subject + t.topic; }
}
