import { HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';

export const TOKEN_KEY = 'zaki_token';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const token = localStorage.getItem(TOKEN_KEY);
  const authed = token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;
  return next(authed).pipe(
    catchError(err => {
      // An expired token sends you back to sign-in. A wrong password must not.
      if (err.status === 401 && !req.url.endsWith('/auth/login')) {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem('zaki_user');
        window.location.assign('/auth/sign-in');
      }
      return throwError(() => err);
    }),
  );
};