"""DEMO school records (GPA, attendance, grades, teacher comments, events).

The Zaki device only knows about practice, lessons and games. School data like this would
normally come from the school's own system. For the demo it lives here, keyed by the child's
username (lowercase). Replace this module with a real integration later; the assistant only
ever calls `school_records_for`.
"""

_EVENTS = [
    {"title": "Parent-Teacher Conference", "date": "15 Nov 2026"},
    {"title": "Science Fair", "date": "20 Nov 2026"},
    {"title": "End of Term", "date": "20 Dec 2026"},
]

SCHOOL_RECORDS: dict[str, dict] = {
    "alex": {
        "grade_level": "Grade 10",
        "school": "St. Mary's High School",
        "term": "Term 3, 2026",
        "gpa": 3.7,
        "gpa_change_this_term": "+0.2",
        "standing": "Top 20% of Grade 10",
        "class_rank": 36,
        "grade_cohort_size": 180,
        "attendance_percent": 94,
        "absences_this_term": 2,
        "missing_work": 0,
        "teachers": {"Mathematics": "Mr. Thompson", "English": "Mrs. Davis", "Physics": "Dr. Patel",
                     "History": "Ms. Garcia", "Biology": "Mr. Chen"},
        "recent_grades": [
            {"subject": "Mathematics", "assessment": "Algebra Test", "grade": "A", "score": "88/100"},
            {"subject": "English", "assessment": "Essay Draft", "grade": "B+", "score": "76/100"},
            {"subject": "Physics", "assessment": "Lab Report", "grade": "A", "score": "92/100"},
            {"subject": "History", "assessment": "Chapter Quiz", "grade": "A+", "score": "95/100"},
        ],
        "upcoming_assignments": [
            {"name": "Algebra Homework #7", "subject": "Mathematics", "due": "Tomorrow"},
            {"name": "Essay Final Draft", "subject": "English Literature", "due": "In 3 days"},
            {"name": "Physics Lab Write-up", "subject": "Physics", "due": "In 5 days"},
        ],
        "teacher_comments": [
            {"teacher": "Mrs. Davis (English Literature)",
             "comment": "Struggles with paragraph structure and argument flow; real room to improve here."},
        ],
        "teacher_observed_strengths": ["Analytical thinking", "Historical analysis", "Lab work and science", "Reliability"],
        "teacher_observed_weaknesses": ["Essay structure (English)", "Cellular concepts (Biology)", "Deadline management"],
        "school_events": _EVENTS,
    },
    "maya": {
        "grade_level": "Grade 8",
        "school": "St. Mary's High School",
        "term": "Term 3, 2026",
        "gpa": 3.1,
        "gpa_change_this_term": "+0.1",
        "standing": "Top 40% of Grade 8",
        "class_rank": 62,
        "grade_cohort_size": None,
        "attendance_percent": 97,
        "absences_this_term": 1,
        "missing_work": 0,
        "teachers": {"English": "Ms. Okafor", "Mathematics": "Mr. Thompson", "Science": "Dr. Patel",
                     "Geography": "Mr. Dlamini", "History": "Ms. Garcia"},
        "recent_grades": [
            {"subject": "English", "assessment": "Poetry Quiz", "grade": "A", "score": "92/100"},
            {"subject": "Science", "assessment": "Plant Cell Test", "grade": "A", "score": "85/100"},
            {"subject": "Geography", "assessment": "Map Skills", "grade": "B+", "score": "80/100"},
            {"subject": "Mathematics", "assessment": "Fractions Test", "grade": "C+", "score": "65/100"},
        ],
        "upcoming_assignments": [
            {"name": "Fractions Worksheet 4", "subject": "Mathematics", "due": "Tomorrow"},
            {"name": "Poetry Analysis", "subject": "English Literature", "due": "In 2 days"},
            {"name": "Photosynthesis Diagram", "subject": "Science", "due": "In 4 days"},
        ],
        "teacher_comments": [
            {"teacher": "Mr. Thompson (Mathematics)",
             "comment": "Works hard and is improving, but adding fractions with different denominators still trips her up."},
        ],
        "teacher_observed_strengths": ["Reading and comprehension", "Creative work", "Effort"],
        "teacher_observed_weaknesses": ["Fractions (Mathematics)", "History dates and timelines"],
        "school_events": _EVENTS,
    },
}


def school_records_for(username: str) -> dict | None:
    return SCHOOL_RECORDS.get(username.strip().lower())
