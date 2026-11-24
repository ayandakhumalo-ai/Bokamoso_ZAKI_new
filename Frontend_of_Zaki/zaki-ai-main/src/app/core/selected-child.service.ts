import { Injectable, computed, signal } from '@angular/core';
import { ChildDemo, DEMO_CHILDREN } from './data/demo-data';

const KEY = 'zaki_selected_child';
const FIRST: ChildDemo = DEMO_CHILDREN[0]!;

/** Remembers which child the parent is looking at, so every parent page shows the same child. */
@Injectable({ providedIn: 'root' })
export class SelectedChildService {
  readonly children: readonly ChildDemo[] = DEMO_CHILDREN;

  private readonly _id = signal<string>(this.restore());
  readonly selectedId = this._id.asReadonly();
  readonly child = computed<ChildDemo>(
    () => this.children.find(c => c.profile.id === this._id()) ?? FIRST,
  );

  select(id: string): void {
    if (!this.children.some(c => c.profile.id === id)) return;
    this._id.set(id);
    try { localStorage.setItem(KEY, id); } catch { /* storage unavailable: ignore */ }
  }

  private restore(): string {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved && DEMO_CHILDREN.some(c => c.profile.id === saved)) return saved;
    } catch { /* ignore */ }
    return FIRST.profile.id;
  }
}
