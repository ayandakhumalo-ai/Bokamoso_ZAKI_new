import { Component, ChangeDetectionStrategy, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { AiChatService } from '../../../ai-chat/ai-chat.service';
import { SelectedChildService } from '../../../../core/selected-child.service';

interface Prompt {
  icon: string;
  label: string;
  message: string;
}

@Component({
  selector: 'app-parent-ai-chat-welcome',
  standalone: true,
  imports: [MatIconModule],
  templateUrl: './parent-ai-chat-welcome.component.html',
  styleUrl: './parent-ai-chat-welcome.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ParentAiChatWelcomeComponent {
  private readonly service = inject(AiChatService);
  private readonly sel = inject(SelectedChildService);

  protected get profile() {
    return this.sel.child().profile;
  }

  // Suggestions use the selected child's name. The assistant answers them from real data.
  protected get prompts(): Prompt[] {
    const n = this.profile.firstName;
    return [
      { icon: 'insights',    label: `How is ${n} doing?`,   message: `How is ${n} doing overall right now?` },
      { icon: 'flag',        label: 'What needs attention?', message: `What does ${n} need to work on most right now?` },
      { icon: 'trending_up', label: 'Recent improvements',   message: `What has ${n} improved at recently?` },
      { icon: 'home',        label: 'Help at home',          message: `How can I help ${n} at home this week?` },
    ];
  }

  protected get stats() {
    const c = this.sel.child();
    return [
      { label: 'GPA',        value: c.parentDashboard.stats[0]?.value ?? '-' },
      { label: 'Attendance', value: c.parentDashboard.stats[1]?.value ?? '-' },
      { label: 'Today',      value: c.profile.timeToday },
      { label: 'Streak',     value: `${c.profile.streakDays} days` },
    ];
  }

  protected send(message: string): void {
    this.service.sendMessage(message);
  }
}
