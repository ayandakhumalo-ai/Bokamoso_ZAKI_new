/**
 * Where the Grades tab gets its data. EDIT THIS FILE, it is the only place you need to touch.
 */
export const GRADES_API = {
  /** The tutor API. Use your hosted address (https, no trailing slash) once it is online. */
  baseUrl: 'http://localhost:8000',

  /**
   * The parent's API login token, from however your portal stores it after signing in to the API.
   * Return null if your portal does not keep one: the tab then uses `demoLogin` below.
   */
  getToken: (): string | null => {
    try { return localStorage.getItem('zaki_api_token'); } catch { return null; }
  },

  /**
   * DEMO ONLY. Signs in as the demo parent when getToken() gives nothing, so the tab works in a
   * presentation without a separate login. Set to null before real families use the portal,
   * because a password in front-end code is visible to anyone.
   */
  demoLogin: { username: 'Sarah', password: 'demo1234' } as { username: string; password: string } | null,
};
