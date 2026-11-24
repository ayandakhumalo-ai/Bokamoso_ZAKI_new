import { Component, ChangeDetectionStrategy, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { SelectedChildService } from '../../../../core/selected-child.service';

@Component({
  selector: 'app-parent-report',
  standalone: true,
  imports: [MatIconModule, RouterLink],
  templateUrl: './parent-report.component.html',
  styleUrl: './parent-report.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ParentReportComponent {
  private readonly sel = inject(SelectedChildService);

  // Everything on this page comes from demo-data.ts for whichever child is selected.
  get profile() { return this.sel.child().profile; }
  get days() { return this.sel.child().report.days; }
  get series() { return this.sel.child().report.series; }
  get studyTime() { return this.sel.child().report.studyTime; }
  get maxMinutes() { return this.sel.child().report.maxMinutes; }
  get heatmap() { return this.sel.child().report.heatmap; }
  get milestones() { return this.sel.child().report.milestones; }
  get summaryStats() { return this.sel.child().report.summaryStats; }

  // SVG chart dimensions
  private readonly CX = 40;   // left padding
  private readonly CY = 14;   // top padding
  private readonly CW = 500;  // usable width
  private readonly CH = 150;  // usable height

  scoreToY(score: number): number {
    return this.CY + this.CH - (score / 100) * this.CH;
  }

  dayToX(i: number): number {
    return this.CX + (i / (this.days.length - 1)) * this.CW;
  }

  linePath(scores: number[]): string {
    return scores.map((s, i) => {
      const x = this.dayToX(i);
      const y = this.scoreToY(s);
      if (i === 0) return `M${x},${y}`;
      const px = this.dayToX(i - 1);
      const py = this.scoreToY(scores[i - 1]);
      const mx = (px + x) / 2;
      return `C${mx},${py} ${mx},${y} ${x},${y}`;
    }).join(' ');
  }

  areaPath(scores: number[]): string {
    const line = this.linePath(scores);
    const lastX = this.dayToX(scores.length - 1);
    const firstX = this.dayToX(0);
    const bottom = this.CY + this.CH;
    return `${line} L${lastX},${bottom} L${firstX},${bottom} Z`;
  }

  // Chart grid lines at scores 20, 40, 60, 80, 100
  readonly gridLines = [100, 80, 60, 40, 20].map(s => ({
    score: s,
    y: this.CY + this.CH - (s / 100) * this.CH,
  }));

  studyBarWidth(minutes: number): number {
    return (minutes / this.maxMinutes) * 100;
  }

  heatColor(minutes: number): string {
    if (minutes === 0)   return '#F0F4F8';
    if (minutes < 40)   return '#EDE9FE';
    if (minutes < 75)   return '#C4B5FD';
    if (minutes < 105)  return '#8B5CF6';
    return '#7C3AED';
  }

  heatOpacity(minutes: number): string {
    return minutes === 0 ? '0.5' : '1';
  }

  readonly weekLabels = ['4w ago', '3w ago', '2w ago', 'Last week', 'This week'];
  readonly dayLabels  = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

}
