import { Injectable, signal, computed, inject } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { Conversation, ConversationGroup } from '../../../ai-chat/models/conversation';
import { Message } from '../../../ai-chat/models/message';
import { ApiService, ChatTurn } from '../../../../core/api.service';
import { ChildDemo } from '../../../../core/data/demo-data';
import { SelectedChildService } from '../../../../core/selected-child.service';

function startOfDayMs(date: Date): number {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

@Injectable()
export class ParentAiChatService {
  private readonly api = inject(ApiService);
  private readonly sel = inject(SelectedChildService);

  // Each conversation is about one child. Switching child starts a fresh conversation.
  private readonly convChild = new Map<string, string>();
  private readonly apiIds = new Map<string, number>();

  private readonly _conversations = signal<Conversation[]>([]);
  private readonly _activeId = signal<string | null>(null);
  private readonly _isResponding = signal(false);

  readonly conversations = this._conversations.asReadonly();
  readonly activeId = this._activeId.asReadonly();
  readonly isResponding = this._isResponding.asReadonly();

  readonly activeConversation = computed(() =>
    this._conversations().find(c => c.id === this._activeId()) ?? null
  );

  readonly groupedConversations = computed((): ConversationGroup[] => {
    const now = new Date();
    const todayMs = startOfDayMs(now);
    const yesterdayMs = todayMs - 86_400_000;
    const sevenDaysMs = todayMs - 7 * 86_400_000;

    const groups: ConversationGroup[] = [
      { label: 'Today', conversations: [] },
      { label: 'Yesterday', conversations: [] },
      { label: 'Previous 7 days', conversations: [] },
    ];

    for (const conv of this._conversations()) {
      const t = conv.createdAt.getTime();
      if (t >= todayMs) groups[0].conversations.push(conv);
      else if (t >= yesterdayMs) groups[1].conversations.push(conv);
      else if (t >= sevenDaysMs) groups[2].conversations.push(conv);
    }

    return groups;
  });

  selectConversation(id: string): void { this._activeId.set(id); }
  startNewConversation(): void { this._activeId.set(null); }

  deleteConversation(id: string): void {
    this._conversations.update(cs => cs.filter(c => c.id !== id));
    if (this._activeId() === id) this._activeId.set(null);
  }

  sendMessage(content: string): void {
    const trimmed = content.trim();
    if (!trimmed || this._isResponding()) return;

    const child = this.sel.child();
    let convId = this._activeId();
    if (convId && this.convChild.get(convId) !== child.profile.id) convId = null;

    if (!convId) {
      const newConv: Conversation = {
        id: crypto.randomUUID(),
        title: trimmed.slice(0, 60),
        messages: [],
        createdAt: new Date(),
      };
      this._conversations.update(cs => [newConv, ...cs]);
      this._activeId.set(newConv.id);
      this.convChild.set(newConv.id, child.profile.id);
      convId = newConv.id;
    }
    const activeId: string = convId;

    // Earlier messages of this conversation give the assistant context for follow-up questions.
    const history: ChatTurn[] = (this._conversations().find(c => c.id === activeId)?.messages ?? [])
      .slice(-6)
      .map(m => ({ role: m.role, content: m.content }));

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    };

    this._conversations.update(cs =>
      cs.map(c => c.id === activeId ? { ...c, messages: [...c.messages, userMsg] } : c)
    );

    this._isResponding.set(true);
    void this.answer(activeId, child, trimmed, history);
  }

  private async answer(convId: string, child: ChildDemo, question: string, history: ChatTurn[]): Promise<void> {
    let text: string;
    try {
      const apiId = await this.apiChildId(child);
      if (apiId === null) throw new HttpErrorResponse({ status: 404 });
      const res = await firstValueFrom(this.api.ask(apiId, question, history));
      text = res.answer;
    } catch (e) {
      text = this.errorText(e);
    }

    const aiMsg: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: text,
      timestamp: new Date(),
    };
    this._conversations.update(cs =>
      cs.map(c => c.id === convId ? { ...c, messages: [...c.messages, aiMsg] } : c)
    );
    this._isResponding.set(false);
  }

  /** The API knows children by username and id; the demo data knows them by its own id. */
  private async apiChildId(child: ChildDemo): Promise<number | null> {
    const cached = this.apiIds.get(child.profile.id);
    if (cached !== undefined) return cached;

    const { children } = await firstValueFrom(this.api.children());
    for (const c of children) {
      const match = this.sel.children.find(d => d.profile.apiUsername === c.username);
      if (match) this.apiIds.set(match.profile.id, c.id);
    }
    return this.apiIds.get(child.profile.id) ?? null;
  }

  private errorText(e: unknown): string {
    const status = e instanceof HttpErrorResponse ? e.status : -1;
    switch (status) {
      case 0:   return "I can't reach the Zaki server right now. Please check that it is running and try again.";
      case 404: return "I couldn't find this child's records. Please check the child is linked to your account.";
      case 429: return 'You are asking quickly. Please wait a few seconds and try again.';
      case 503: return "The AI assistant isn't available right now. Please check that the AI service is running or online, and try again.";
      default:  return 'Something went wrong while I was looking that up. Please try again.';
    }
  }
}
