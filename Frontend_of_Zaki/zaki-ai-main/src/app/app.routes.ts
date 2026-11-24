import { Routes } from '@angular/router';
import { authGuard, roleGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: 'auth/sign-in', pathMatch: 'full' },
  {
    path: 'ai-chat',
    loadComponent: () =>
      import('./features/ai-chat/ai-chat.component').then(m => m.AiChatComponent),
  },
  {
    path: 'auth/sign-in',
    loadComponent: () =>
      import('./features/auth/sign-in/sign-in.component').then(m => m.SignInComponent),
  },
  {
    path: 'auth/sign-up',
    loadComponent: () =>
      import('./features/auth/sign-up/sign-up.component').then(m => m.SignUpComponent),
  },
  {
    path: 'dashboard',
    loadComponent: () =>
      import('./features/dashboard/dashboard-shell.component').then(
        m => m.DashboardShellComponent,
      ),
    canActivate: [authGuard],
    canActivateChild: [roleGuard],
    children: [
      { path: '', redirectTo: 'student', pathMatch: 'full' },
      {
        path: 'student',
        loadComponent: () =>
          import('./features/dashboard/student/student-dashboard.component').then(
            m => m.StudentDashboardComponent,
          ),
      },
      {
        path: 'student/ai-chat',
        loadComponent: () =>
          import('./features/dashboard/student/student-ai-chat/student-ai-chat.component').then(
            m => m.StudentAiChatComponent,
          ),
      },
      {
        path: 'parent',
        loadComponent: () =>
          import('./features/dashboard/parent/parent-dashboard.component').then(
            m => m.ParentDashboardComponent,
          ),
      },
      {
        path: 'parent/children',
        loadComponent: () =>
          import('./features/dashboard/parent/parent-children.component').then(
            m => m.ParentChildrenComponent,
          ),
      },
      {
        path: 'parent/grades',
        loadComponent: () =>
          import('./features/dashboard/parent/parent-grades/parent-grades.component').then(
            m => m.ParentGradesComponent,
          ),
      },
      {
        path: 'parent/settings',
        loadComponent: () =>
          import('./features/dashboard/parent/parent-settings/parent-settings.component').then(
            m => m.ParentSettingsComponent,
          ),
      },
      {
        path: 'parent/reports',
        loadComponent: () =>
          import('./features/dashboard/parent/parent-report/parent-report.component').then(
            m => m.ParentReportComponent,
          ),
      },
      {
        path: 'parent/ai-chat',
        loadComponent: () =>
          import('./features/dashboard/parent/parent-ai-chat/parent-ai-chat.component').then(
            m => m.ParentAiChatComponent,
          ),
      },
    ],
  },
  { path: '**', redirectTo: 'ai-chat' },
];
