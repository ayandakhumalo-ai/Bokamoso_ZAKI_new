/**
 * ZAKI demo data: one parent (Sarah Johnson) and two children (Alex, Maya).
 *
 * Every array below has EXACTLY the shape of the hardcoded array it replaces:
 *   parent-dashboard.component.ts  -> stats, mastery, todayActivity, aiInsight, focusAreas, achievements
 *   parent-report.component.ts     -> series, studyTime, maxMinutes, heatmap, milestones, summaryStats
 *   student-dashboard.component.ts -> stats, schedule, assignments, grades
 *   parent-dashboard.component.html (hero) -> profile
 *
 * The numbers that the API can produce (subject accuracy, struggling topics, games, practice) come from tutor_api/scripts/seed_family.py and agree with this file.
 * GPA, attendance, rank, grades, schedule, assignments and teacher quotes are school data the
 * API does not have, so they live only here.
 */

export type UserRole = 'student' | 'parent';
export type Tone = 'purple' | 'green' | 'blue' | 'amber' | 'gray' | 'red';

export const DEMO_PASSWORD = 'demo1234'; // the API requires 8+ characters ('demo123' is rejected)

export interface DemoUser {
  id: string;
  email: string;        // what the sign-in form asks for
  password: string;
  role: UserRole;
  name: string;
  initials: string;
  apiUsername: string;  // what POST /auth/login expects (case-sensitive)
  childIds?: string[];  // parent only
}

export const DEMO_USERS: DemoUser[] = [
  { id: 'u1', email: 'student@demo.com', password: DEMO_PASSWORD, role: 'student',
    name: 'Alex Johnson', initials: 'AJ', apiUsername: 'Alex' },
  { id: 'u2', email: 'parent@demo.com', password: DEMO_PASSWORD, role: 'parent',
    name: 'Sarah Johnson', initials: 'SJ', apiUsername: 'Sarah', childIds: ['u1', 'u3'] },
  { id: 'u3', email: 'maya@demo.com', password: DEMO_PASSWORD, role: 'student',
    name: 'Maya Johnson', initials: 'MJ', apiUsername: 'Maya' },
];

/* ---------- shapes ---------- */
export interface StatCard { label: string; value: string; sub: string; icon: string; color: Tone; }
export interface SummaryStat { label: string; value: string; icon: string; color: Tone; }
export interface Mastery { subject: string; score: number; grade: string; color: string; track: string; }
export interface ActivityItem { time: string; icon: string; text: string; detail: string; color: Tone; }
export interface AiInsight { sessions: number; finding: string; detail: string; confidence: number; }
export interface FocusArea {
  id: number; subject: string; title: string; color: 'amber' | 'red'; icon: string;
  quote: string | null; teacher: string; detail: string;
}
export interface Achievement { label: string; icon: string; color: string; bg: string; earned: boolean; }
export interface ChartSeries { name: string; color: string; scores: number[]; }
export interface StudyTime { subject: string; minutes: number; color: string; }
export interface Milestone { icon: string; color: string; bg: string; label: string; date: string; earned: boolean; }
export interface ScheduleItem {
  id: number; time: string; subject: string; teacher: string; room: string;
  status: 'done' | 'current' | 'upcoming';
}
export interface AssignmentItem { id: number; name: string; subject: string; due: string; urgent: boolean; }
export interface GradeItem {
  id: number; subject: string; assignment: string; letter: string; score: string; tier: 'a' | 'b';
}

export interface ChildProfile {
  id: string;              // matches the student's DemoUser id
  apiUsername: string;     // use to find the child's id from GET /parent/children
  name: string;
  firstName: string;
  initials: string;
  grade: string;
  school: string;
  term: string;
  deviceOnline: boolean;
  streakDays: number;
  timeToday: string;       // hero chip
  quizzesToday: number;    // hero chip
  rank: number;            // hero chip
}

export interface ChildDemo {
  profile: ChildProfile;
  parentDashboard: {
    stats: StatCard[]; mastery: Mastery[]; todayActivity: ActivityItem[];
    aiInsight: AiInsight; focusAreas: FocusArea[]; achievements: Achievement[];
  };
  report: {
    days: string[]; series: ChartSeries[]; studyTime: StudyTime[]; maxMinutes: number;
    heatmap: number[][]; milestones: Milestone[]; summaryStats: SummaryStat[];
  };
  studentDashboard: {
    stats: StatCard[]; schedule: ScheduleItem[]; assignments: AssignmentItem[]; grades: GradeItem[];
  };
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/* ====================== ALEX JOHNSON · Grade 10 ====================== */
const ALEX: ChildDemo = {
  profile: {
    id: 'u1', apiUsername: 'Alex', name: 'Alex Johnson', firstName: 'Alex', initials: 'AJ',
    grade: 'Grade 10', school: "St. Mary's High School", term: 'Term 3, 2026',
    deviceOnline: true, streakDays: 7, timeToday: '1h 42m', quizzesToday: 3, rank: 36,
  },
  parentDashboard: {
    stats: [
      { label: 'Overall GPA',    value: '3.7',    sub: 'Top 20% · Grade 10',     icon: 'school',          color: 'purple' },
      { label: 'Attendance',     value: '94%',    sub: '2 absences this term',   icon: 'event_available', color: 'green'  },
      { label: 'Today on Zaki',  value: '1h 42m', sub: '3 quizzes · 2 games',    icon: 'schedule',        color: 'blue'   },
      { label: 'Avg Quiz Score', value: '8.3/10', sub: 'Across 3 quizzes today', icon: 'quiz',            color: 'amber'  },
    ],
    mastery: [
      { subject: 'History',     score: 95, grade: 'A+', color: '#D97706', track: '#FEF3C7' },
      { subject: 'Physics',     score: 92, grade: 'A',  color: '#059669', track: '#D1FAE5' },
      { subject: 'Mathematics', score: 88, grade: 'A',  color: '#7C3AED', track: '#EDE9FE' },
      { subject: 'English',     score: 76, grade: 'B+', color: '#2563EB', track: '#DBEAFE' },
      { subject: 'Biology',     score: 74, grade: 'B',  color: '#DC2626', track: '#FEE2E2' },
    ],
    // Newest first. 12+8+10 min quizzes, 18+14 min games, 22+18 min lessons = 102 min = 1h 42m.
    todayActivity: [
      { time: '4:25 PM', icon: 'sports_esports',     text: 'Memory Match',             detail: 'Completed · 14 min',            color: 'green'  },
      { time: '4:10 PM', icon: 'quiz',               text: 'English Vocabulary Quiz',  detail: '8 / 10 correct · 10 min',       color: 'amber'  },
      { time: '3:42 PM', icon: 'quiz',               text: 'Algebra Quiz',             detail: '8 / 10 correct · 12 min',       color: 'purple' },
      { time: '3:12 PM', icon: 'sports_esports',     text: 'Maths Word Game',          detail: 'Level 7 reached · 18 min',      color: 'green'  },
      { time: '2:52 PM', icon: 'menu_book',          text: 'Physics: Forces',          detail: 'Chapter 6 completed · 18 min',  color: 'blue'   },
      { time: '2:30 PM', icon: 'menu_book',          text: 'Biology: Cell Division',   detail: 'Chapter 4 completed · 22 min',  color: 'blue'   },
      { time: '2:05 PM', icon: 'quiz',               text: 'History Quiz',             detail: '9 / 10 correct · 8 min',        color: 'amber'  },
      { time: '1:45 PM', icon: 'power_settings_new', text: 'Zaki device connected',    detail: 'Session started',               color: 'gray'   },
    ],
    aiInsight: {
      sessions: 47,
      finding: 'Written expression needs attention',
      detail: 'Across 12 English sessions, Alex consistently struggles to structure arguments. The pattern appears in 8 of 12 essay-type exercises.',
      confidence: 94,
    },
    focusAreas: [
      {
        id: 1, subject: 'English', title: 'Essay Writing', color: 'amber', icon: 'edit',
        quote: '"Alex struggles with paragraph structure and argument flow — there is real room to improve here."',
        teacher: 'Mrs. Davis · English Literature',
        detail: 'Practice 2 short essays per week on argument structure. Ask Mrs. Davis for her marking rubric.',
      },
      {
        id: 2, subject: 'Biology', title: 'Cell Biology', color: 'red', icon: 'biotech',
        quote: null, teacher: 'Mr. Chen · Biology',
        detail: 'A dip to 74/100 shows a gap in cellular biology. 20–30 min daily on Khan Academy closes this in 2–3 weeks.',
      },
    ],
    achievements: [
      { label: '7-Day Streak', icon: 'local_fire_department', color: '#D97706', bg: '#FFFBEB', earned: true  },
      { label: 'Quiz Master',  icon: 'emoji_events',          color: '#059669', bg: '#ECFDF5', earned: true  },
      { label: 'Top 20%',      icon: 'workspace_premium',     color: '#7C3AED', bg: '#F5F3FF', earned: true  },
      { label: 'Perfect Week', icon: 'star',                  color: '#9CAAB6', bg: '#F0F4F8', earned: false },
    ],
  },
  report: {
    days: DAYS,
    series: [
      { name: 'Mathematics', color: '#7C3AED', scores: [82, 85, 84, 88, 87, 88, 88] },
      { name: 'Physics',     color: '#059669', scores: [88, 90, 89, 91, 92, 91, 92] },
      { name: 'English',     color: '#2563EB', scores: [72, 74, 73, 75, 76, 75, 76] },
      { name: 'History',     color: '#D97706', scores: [93, 94, 95, 94, 95, 95, 95] },
      { name: 'Biology',     color: '#DC2626', scores: [78, 76, 74, 75, 74, 74, 74] },
    ],
    studyTime: [ // minutes per week, sums to 602 = 10h 02m
      { subject: 'Physics',     minutes: 148, color: '#059669' },
      { subject: 'Mathematics', minutes: 132, color: '#7C3AED' },
      { subject: 'History',     minutes: 120, color: '#D97706' },
      { subject: 'English',     minutes: 105, color: '#2563EB' },
      { subject: 'Biology',     minutes: 97,  color: '#DC2626' },
    ],
    maxMinutes: 160,
    heatmap: [ // 5 weeks x 7 days, study minutes
      [45, 60, 30,  0,  90, 120, 45],
      [70, 85,  0, 60, 110, 100, 50],
      [80, 95, 70, 75, 120, 110, 65],
      [85, 100, 90, 0, 115, 130, 70],
      [90, 102, 95, 0, 120,   0,  0],
    ],
    milestones: [
      { icon: 'local_fire_department', color: '#D97706', bg: '#FFFBEB', label: '7-Day Streak', date: 'This week', earned: true  },
      { icon: 'emoji_events',          color: '#059669', bg: '#ECFDF5', label: 'Quiz Master',  date: 'Oct 6',     earned: true  },
      { icon: 'workspace_premium',     color: '#7C3AED', bg: '#F5F3FF', label: 'Top 20% Rank', date: 'Oct 3',     earned: true  },
      { icon: 'bolt',                  color: '#2563EB', bg: '#EFF6FF', label: '50 Sessions',  date: 'Oct 1',     earned: true  },
      { icon: 'star',                  color: '#9CAAB6', bg: '#F0F4F8', label: 'Perfect Week', date: 'Locked',    earned: false },
      { icon: 'psychology',            color: '#9CAAB6', bg: '#F0F4F8', label: 'Deep Learner', date: 'Locked',    earned: false },
    ],
    summaryStats: [
      { label: 'Sessions this week', value: '12', icon: 'devices',     color: 'purple' },
      { label: 'Total study time',   value: '10h 02m', icon: 'schedule',    color: 'blue'   },
      { label: 'Avg quiz score',     value: '84%', icon: 'quiz',        color: 'green'  },
      { label: 'Week improvement',   value: '+4.2%', icon: 'trending_up', color: 'amber'  },
    ],
  },
  studentDashboard: {
    stats: [
      { label: 'GPA',        value: '3.7', sub: '+0.2 this term',       icon: 'trending_up',     color: 'purple' },
      { label: 'Attendance', value: '94%', sub: '2 absences this term', icon: 'event_available', color: 'green'  },
      { label: 'Due Soon',   value: '3',   sub: 'assignments pending',  icon: 'assignment_late', color: 'amber'  },
      { label: 'Credits',    value: '45',  sub: 'of 120 earned',        icon: 'school',          color: 'blue'   },
    ],
    schedule: [
      { id: 1, time: '08:00', subject: 'Mathematics',        teacher: 'Mr. Thompson', room: 'Room 201',  status: 'done' },
      { id: 2, time: '10:00', subject: 'English Literature', teacher: 'Mrs. Davis',   room: 'Room 105',  status: 'current' },
      { id: 3, time: '12:00', subject: 'Lunch Break',        teacher: '',             room: 'Cafeteria', status: 'upcoming' },
      { id: 4, time: '13:00', subject: 'Physics',            teacher: 'Dr. Patel',    room: 'Lab 3',     status: 'upcoming' },
      { id: 5, time: '15:00', subject: 'History',            teacher: 'Ms. Garcia',   room: 'Room 302',  status: 'upcoming' },
    ],
    assignments: [
      { id: 1, name: 'Algebra Homework #7',  subject: 'Mathematics',        due: 'Tomorrow',  urgent: true  },
      { id: 2, name: 'Essay Final Draft',    subject: 'English Literature', due: 'In 3 days', urgent: false },
      { id: 3, name: 'Physics Lab Write-up', subject: 'Physics',            due: 'In 5 days', urgent: false },
    ],
    grades: [
      { id: 1, subject: 'Mathematics', assignment: 'Algebra Test',  letter: 'A',  score: '88/100', tier: 'a' },
      { id: 2, subject: 'English',     assignment: 'Essay Draft',   letter: 'B+', score: '76/100', tier: 'b' },
      { id: 3, subject: 'Physics',     assignment: 'Lab Report',    letter: 'A',  score: '92/100', tier: 'a' },
      { id: 4, subject: 'History',     assignment: 'Chapter Quiz',  letter: 'A+', score: '95/100', tier: 'a' },
    ],
  },
};

/* ====================== MAYA JOHNSON · Grade 8 ====================== */
const MAYA: ChildDemo = {
  profile: {
    id: 'u3', apiUsername: 'Maya', name: 'Maya Johnson', firstName: 'Maya', initials: 'MJ',
    grade: 'Grade 8', school: "St. Mary's High School", term: 'Term 3, 2026',
    deviceOnline: true, streakDays: 3, timeToday: '1h 05m', quizzesToday: 2, rank: 62,
  },
  parentDashboard: {
    stats: [
      { label: 'Overall GPA',    value: '3.1',    sub: 'Top 40% · Grade 8',      icon: 'school',          color: 'purple' },
      { label: 'Attendance',     value: '97%',    sub: '1 absence this term',    icon: 'event_available', color: 'green'  },
      { label: 'Today on Zaki',  value: '1h 05m', sub: '2 quizzes · 1 game',     icon: 'schedule',        color: 'blue'   },
      { label: 'Avg Quiz Score', value: '7.5/10', sub: 'Across 2 quizzes today', icon: 'quiz',            color: 'amber'  },
    ],
    mastery: [
      { subject: 'English',     score: 92, grade: 'A',  color: '#2563EB', track: '#DBEAFE' },
      { subject: 'Science',     score: 85, grade: 'A',  color: '#059669', track: '#D1FAE5' },
      { subject: 'Geography',   score: 80, grade: 'B+', color: '#0891B2', track: '#CFFAFE' },
      { subject: 'History',     score: 77, grade: 'B+', color: '#D97706', track: '#FEF3C7' },
      { subject: 'Mathematics', score: 65, grade: 'C+', color: '#7C3AED', track: '#EDE9FE' },
    ],
    // 9 + 20 + 15 + 11 + 10 = 65 min = 1h 05m
    todayActivity: [
      { time: '3:55 PM', icon: 'quiz',               text: 'Fractions Quiz',                 detail: '6 / 10 correct · 10 min',       color: 'purple' },
      { time: '3:35 PM', icon: 'menu_book',          text: 'Maths: Equivalent Fractions',    detail: 'Lesson completed · 11 min',     color: 'blue'   },
      { time: '3:10 PM', icon: 'sports_esports',     text: 'Hangman',                        detail: 'Completed · 15 min',            color: 'green'  },
      { time: '2:40 PM', icon: 'menu_book',          text: 'Science: Photosynthesis',        detail: 'Chapter 3 completed · 20 min',  color: 'blue'   },
      { time: '2:15 PM', icon: 'quiz',               text: 'Reading Comprehension Quiz',     detail: '9 / 10 correct · 9 min',        color: 'amber'  },
      { time: '1:50 PM', icon: 'power_settings_new', text: 'Zaki device connected',          detail: 'Session started',               color: 'gray'   },
    ],
    aiInsight: {
      sessions: 31,
      finding: 'Fractions are the main hurdle in Maths',
      detail: 'Across 9 Maths sessions, Maya is improving on fractions (35% to 47% accuracy in two weeks) but still struggles with unlike denominators. The pattern appears in 6 of 9 fraction exercises.',
      confidence: 91,
    },
    focusAreas: [
      {
        id: 1, subject: 'Mathematics', title: 'Fractions', color: 'amber', icon: 'calculate',
        quote: '"Maya works hard and is improving, but adding fractions with different denominators still trips her up."',
        teacher: 'Mr. Thompson · Mathematics',
        detail: 'Practise finding common denominators for 10 minutes a day. Ask Mr. Thompson for the fractions worksheet set.',
      },
      {
        id: 2, subject: 'History', title: 'Timelines and Dates', color: 'red', icon: 'history_edu',
        quote: null, teacher: 'Ms. Garcia · History',
        detail: 'Ancient history scores sit at 77%. Making a simple timeline of key events and reviewing it twice a week usually helps dates stick.',
      },
    ],
    achievements: [
      { label: '3-Day Streak', icon: 'local_fire_department', color: '#D97706', bg: '#FFFBEB', earned: true  },
      { label: 'Reading Star', icon: 'emoji_events',          color: '#059669', bg: '#ECFDF5', earned: true  },
      { label: 'Top 40%',      icon: 'workspace_premium',     color: '#7C3AED', bg: '#F5F3FF', earned: true  },
      { label: 'Perfect Week', icon: 'star',                  color: '#9CAAB6', bg: '#F0F4F8', earned: false },
    ],
  },
  report: {
    days: DAYS,
    series: [
      { name: 'English',     color: '#2563EB', scores: [89, 90, 91, 92, 91, 92, 92] },
      { name: 'Science',     color: '#059669', scores: [82, 83, 84, 85, 86, 85, 85] },
      { name: 'Geography',   color: '#0891B2', scores: [78, 79, 79, 80, 81, 80, 80] },
      { name: 'History',     color: '#D97706', scores: [75, 76, 76, 77, 78, 77, 77] },
      { name: 'Mathematics', color: '#7C3AED', scores: [58, 60, 61, 63, 64, 65, 65] },
    ],
    studyTime: [ // sums to 460 = 7h 40m
      { subject: 'English',     minutes: 120, color: '#2563EB' },
      { subject: 'Mathematics', minutes: 110, color: '#7C3AED' },
      { subject: 'Science',     minutes: 105, color: '#059669' },
      { subject: 'Geography',   minutes: 65,  color: '#0891B2' },
      { subject: 'History',     minutes: 60,  color: '#D97706' },
    ],
    maxMinutes: 160,
    heatmap: [
      [30, 45,  0, 40,  60, 70, 30],
      [40, 55, 35,  0,  65, 80, 40],
      [50, 60, 45, 50,  70, 75,  0],
      [55, 65, 50,  0,  75, 90, 45],
      [60, 65, 0,   0,   0,  0,  0],
    ],
    milestones: [
      { icon: 'local_fire_department', color: '#D97706', bg: '#FFFBEB', label: '3-Day Streak',    date: 'This week', earned: true  },
      { icon: 'emoji_events',          color: '#059669', bg: '#ECFDF5', label: 'Reading Star',    date: 'Oct 12',    earned: true  },
      { icon: 'bolt',                  color: '#2563EB', bg: '#EFF6FF', label: '25 Sessions',     date: 'Oct 8',     earned: true  },
      { icon: 'workspace_premium',     color: '#7C3AED', bg: '#F5F3FF', label: 'Top 40% Rank',    date: 'Oct 3',     earned: true  },
      { icon: 'star',                  color: '#9CAAB6', bg: '#F0F4F8', label: 'Fraction Master', date: 'Locked',    earned: false },
      { icon: 'psychology',            color: '#9CAAB6', bg: '#F0F4F8', label: 'Perfect Week',    date: 'Locked',    earned: false },
    ],
    summaryStats: [
      { label: 'Sessions this week', value: '9', icon: 'devices',     color: 'purple' },
      { label: 'Total study time',   value: '7h 40m', icon: 'schedule',    color: 'blue'   },
      { label: 'Avg quiz score',     value: '76%', icon: 'quiz',        color: 'green'  },
      { label: 'Week improvement',   value: '+3.1%', icon: 'trending_up', color: 'amber'  },
    ],
  },
  studentDashboard: {
    stats: [
      { label: 'GPA',        value: '3.1', sub: '+0.1 this term',       icon: 'trending_up',     color: 'purple' },
      { label: 'Attendance', value: '97%', sub: '1 absence this term',  icon: 'event_available', color: 'green'  },
      { label: 'Due Soon',   value: '3',   sub: 'assignments pending',  icon: 'assignment_late', color: 'amber'  },
      { label: 'Credits',    value: '18',  sub: 'of 120 earned',        icon: 'school',          color: 'blue'   },
    ],
    schedule: [
      { id: 1, time: '08:00', subject: 'English Literature', teacher: 'Ms. Okafor',   room: 'Room 104',  status: 'done' },
      { id: 2, time: '10:00', subject: 'Mathematics',        teacher: 'Mr. Thompson', room: 'Room 201',  status: 'current' },
      { id: 3, time: '12:00', subject: 'Lunch Break',        teacher: '',             room: 'Cafeteria', status: 'upcoming' },
      { id: 4, time: '13:00', subject: 'Science',            teacher: 'Dr. Patel',    room: 'Lab 2',     status: 'upcoming' },
      { id: 5, time: '14:30', subject: 'Geography',          teacher: 'Mr. Dlamini',  room: 'Room 210',  status: 'upcoming' },
    ],
    assignments: [
      { id: 1, name: 'Fractions Worksheet 4',  subject: 'Mathematics',        due: 'Tomorrow',  urgent: true  },
      { id: 2, name: 'Poetry Analysis',        subject: 'English Literature', due: 'In 2 days', urgent: false },
      { id: 3, name: 'Photosynthesis Diagram', subject: 'Science',            due: 'In 4 days', urgent: false },
    ],
    grades: [
      { id: 1, subject: 'English',     assignment: 'Poetry Quiz',     letter: 'A',  score: '92/100', tier: 'a' },
      { id: 2, subject: 'Science',     assignment: 'Plant Cell Test', letter: 'A',  score: '85/100', tier: 'a' },
      { id: 3, subject: 'Geography',   assignment: 'Map Skills',      letter: 'B+', score: '80/100', tier: 'b' },
      { id: 4, subject: 'Mathematics', assignment: 'Fractions Test',  letter: 'C+', score: '65/100', tier: 'b' },
    ],
  },
};

export const DEMO_CHILDREN: ChildDemo[] = [ALEX, MAYA];

export function childFor(userId: string): ChildDemo | undefined {
  return DEMO_CHILDREN.find(c => c.profile.id === userId);
}
