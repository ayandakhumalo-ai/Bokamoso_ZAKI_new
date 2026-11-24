# Grades tab: install steps

Copy the folder `src/app/features/dashboard/parent/parent-grades/` into the same place in your portal.
It has 6 files: the component (.ts .html .scss), `grades-api.service.ts`, `grades-api.config.ts` and `grades.models.ts`.
It uses no new packages (plain `fetch`, Angular Material icons you already have).

## 1. Point it at your API (grades-api.config.ts)
- `baseUrl`: `http://localhost:8000` while testing, your hosted https address later.
- `getToken`: return the parent's API login token if your portal keeps one. If not, the tab signs in by itself as the
  demo parent (Sarah / demo1234) using `demoLogin`. Set `demoLogin` to `null` before real families use the portal.

## 2. Show it instead of the "Coming soon" page (src/app/app.routes.ts)
Replace the whole `parent/grades` route with:

```ts
{
  path: 'parent/grades',
  loadComponent: () =>
    import('./features/dashboard/parent/parent-grades/parent-grades.component').then(
      m => m.ParentGradesComponent,
    ),
},
```

## 3. Run it
1. Start the API with demo data: `TUTOR_DB=demo.db python -m scripts.seed_family` then `uvicorn app.main:app`
   (or `python -m scripts.demo_quizzes` if your demo.db already exists).
2. `ng serve`, sign in as the parent, open Grades.

If the browser console says CORS, add your site's address to `TUTOR_CORS_ORIGINS` on the API.

## What it does
- Default view is the last 7 days. Week / Month / Year / All time buttons, plus zoom in and zoom out, change the range.
- One bar per quiz, coloured by subject, with its title ("Algebra quiz"), score and date. Scroll sideways for older quizzes.
- Select a subject chip to hide or show that subject. Switch child with the name buttons at the top.
- Select a bar to see every question, the child's answer and the right answer. Escape closes it.
- "Where Alex is struggling" lists weak topics for the same range with the questions they got wrong.
