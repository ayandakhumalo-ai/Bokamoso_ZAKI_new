export type RangeKey = 'week' | 'month' | 'year' | 'all';

export interface ChildLink { id: number; username: string; }

/** One bar in the chart: a single quiz. */
export interface QuizBar {
  id: number;
  title: string;            // e.g. "Algebra quiz"
  subject: string;          // e.g. "Mathematics"
  topic: string;
  topic_name: string;
  date: string;             // local day, YYYY-MM-DD
  taken_at: string;
  correct: number;
  total: number;
  score_percent: number;
  grade: string;            // A+, A, B+, B, C, D, F
  duration_seconds: number | null;
}

export interface SubjectSummary {
  subject: string;
  quizzes: number;
  average_percent: number;
  best_percent: number;
  lowest_percent: number;
}

export interface QuizReport {
  child: string;
  range: RangeKey;
  start: string;
  end: string;
  first_quiz_date: string | null;
  quiz_count: number;
  average_percent: number | null;
  quizzes: QuizBar[];
  subjects: SubjectSummary[];
}

export interface QuizQuestion {
  number: number;
  topic: string;
  topic_name: string;
  question: string;
  correct_answer: string;
  student_answer: string | null;   // null = skipped
  is_correct: boolean;
}

export interface QuizDetail extends QuizBar { questions: QuizQuestion[]; }

export interface Mistake {
  question: string;
  correct_answer: string;
  student_answer: string | null;
  quiz_id: number;
  quiz_title: string;
  date: string;
}

export interface TopicResult {
  subject: string;
  topic: string;
  topic_name: string;
  questions: number;
  correct: number;
  accuracy_percent: number;
  status: 'weak' | 'developing' | 'strong' | 'not_enough_data';
  quizzes: number;
  recent_mistakes: Mistake[];
}

export interface WeaknessReport {
  child: string;
  range: RangeKey;
  start: string;
  end: string;
  questions_answered: number;
  has_enough_data: boolean;
  weak_topics: TopicResult[];
  strong_topics: TopicResult[];
  topics: TopicResult[];
}
