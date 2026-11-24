import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from './auth.service';
import { CanActivateChildFn } from '@angular/router';

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (auth.isAuthed()) {
    return true;
  }

  return router.createUrlTree(['/auth/sign-in']);
};

export const roleGuard: CanActivateChildFn = (_route, state) => {
  const u = inject(AuthService).user();
  const router = inject(Router);
  if (u && ((state.url.startsWith('/dashboard/parent') && u.role !== 'parent') ||
            (state.url.startsWith('/dashboard/student') && u.role !== 'student'))) {
    return router.createUrlTree([`/dashboard/${u.role}`]);
  }
  return true;
};
