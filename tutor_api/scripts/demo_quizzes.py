"""Demo quizzes for Alex and Maya: about a year of quizzes, every question stored.

    python -m scripts.demo_quizzes          # adds quizzes to the existing Alex and Maya (skips anyone who has some)

`scripts.seed_family` calls `seed_quizzes` too, so a fresh demo database already has them.

The story matches the rest of the demo family:
  Alex (Grade 10): strong in Algebra, Forces, Electricity and the Industrial Revolution;
                   weak and getting worse in Cell Biology and Essay Writing.
  Maya (Grade 8):  weak at Fractions but improving fast; strong in Reading and Spelling.
Everything is generated with a fixed random seed, so the same data comes out every time.
"""
import random
from datetime import timedelta

from app import db, progress

# topic key -> (subject, accuracy a year ago, accuracy now, [(question, right answer, [wrong answers])])
ALEX_TOPICS = {
    "algebra": ("Mathematics", .78, .92, [
        ("Solve: 3x + 5 = 20", "x = 5", ["x = 6", "x = 25/3", "x = 15"]),
        ("Simplify: 2(x + 4) - 3", "2x + 5", ["2x + 1", "2x + 4", "x + 5"]),
        ("Factorise: x² + 5x + 6", "(x + 2)(x + 3)", ["(x + 1)(x + 6)", "(x - 2)(x - 3)", "(x + 5)(x + 1)"]),
        ("If y = 2x - 1, what is y when x = 4?", "7", ["9", "8", "3"]),
        ("Solve: x / 4 = 7", "x = 28", ["x = 11", "x = 3", "x = 1.75"]),
        ("Expand: (x + 3)²", "x² + 6x + 9", ["x² + 9", "x² + 3x + 9", "x² + 6x + 6"]),
    ]),
    "geometry": ("Mathematics", .70, .80, [
        ("What is the sum of the interior angles of a triangle?", "180°", ["90°", "360°", "270°"]),
        ("Area of a circle with radius 5 (use π = 3.14)?", "78.5", ["31.4", "15.7", "25"]),
        ("A right triangle has short sides 3 and 4. What is the hypotenuse?", "5", ["7", "6", "25"]),
        ("How many degrees are in a straight line?", "180°", ["90°", "360°", "100°"]),
        ("Area of a rectangle 6 cm by 4 cm?", "24 cm²", ["10 cm²", "20 cm²", "48 cm²"]),
        ("Each interior angle of a regular hexagon is?", "120°", ["108°", "135°", "60°"]),
    ]),
    "quadratic_equations": ("Mathematics", .65, .75, [
        ("Solve x² = 49 (positive root)", "x = 7", ["x = 24.5", "x = 6", "x = 49"]),
        ("What are the roots of x² - 5x + 6 = 0?", "2 and 3", ["1 and 6", "-2 and -3", "5 and 6"]),
        ("In ax² + bx + c = 0, the discriminant is?", "b² - 4ac", ["b² + 4ac", "4ac - b²", "b - 4ac"]),
        ("How many real roots if the discriminant is negative?", "None", ["Two", "One", "Infinite"]),
        ("Solve x² - 9 = 0", "x = 3 or x = -3", ["x = 9", "x = 3 only", "x = 81"]),
        ("What shape is the graph of y = x²?", "A parabola", ["A straight line", "A circle", "A hyperbola"]),
    ]),
    "forces": ("Physics", .80, .90, [
        ("What is the SI unit of force?", "Newton", ["Joule", "Watt", "Pascal"]),
        ("F = ma. If m = 2 kg and a = 5 m/s², what is F?", "10 N", ["7 N", "2.5 N", "25 N"]),
        ("Newton's first law: an object keeps its motion unless...", "a net force acts on it",
         ["it gets heavier", "gravity is zero", "it is in a vacuum"]),
        ("Which force opposes motion between two surfaces?", "Friction", ["Tension", "Gravity", "Thrust"]),
        ("Weight is the force due to...", "Gravity", ["Friction", "Magnetism", "Air pressure"]),
        ("Action and reaction forces are...", "Equal and opposite",
         ["Equal and in the same direction", "Different sizes", "Opposite but unequal"]),
    ]),
    "electricity": ("Physics", .82, .90, [
        ("What is the unit of electric current?", "Ampere", ["Volt", "Ohm", "Watt"]),
        ("Ohm's law: V equals?", "I × R", ["I / R", "I + R", "R / I"]),
        ("A 12 V battery drives 3 A through a resistor. Its resistance?", "4 Ω", ["36 Ω", "9 Ω", "0.25 Ω"]),
        ("In a series circuit the current is...", "The same everywhere",
         ["Larger near the battery", "Zero", "Split between branches"]),
        ("Which material is a good insulator?", "Rubber", ["Copper", "Iron", "Silver"]),
        ("Electrical power equals?", "Voltage × current", ["Voltage / current", "Current / voltage", "Voltage + current"]),
    ]),
    "industrial_revolution": ("History", .88, .95, [
        ("Which country did the Industrial Revolution begin in?", "Britain", ["France", "Germany", "United States"]),
        ("Which improved invention powered factories?", "The steam engine",
         ["The telephone", "The light bulb", "The printing press"]),
        ("Which industry was mechanised first?", "Textiles", ["Car making", "Computing", "Electronics"]),
        ("Many people moved from villages to...", "Cities", ["Islands", "Mountains", "Deserts"]),
        ("Factories made goods...", "In large numbers by machine",
         ["One at a time by hand", "Only on farms", "Only at home"]),
        ("Which fuel mainly powered early steam engines?", "Coal", ["Oil", "Solar", "Gas"]),
    ]),
    "essay_writing": ("English", .55, .38, [
        ("The sentence that states the main idea of a paragraph is the...", "Topic sentence",
         ["Conclusion", "Hook", "Quotation"]),
        ("A thesis statement belongs in the...", "Introduction", ["Conclusion only", "Middle of the essay", "Bibliography"]),
        ("Which word best links two contrasting ideas?", "However", ["Moreover", "Therefore", "Similarly"]),
        ("A strong conclusion should...", "Sum up the argument",
         ["Add a new argument", "Repeat the introduction word for word", "Ask the teacher a question"]),
        ("Evidence in an essay is used to...", "Support a point", ["Fill space", "Replace the thesis", "Change the topic"]),
        ("Which is the best order for a paragraph?", "Point, evidence, explanation",
         ["Explanation, point, evidence", "Evidence, conclusion, point", "Conclusion, point, evidence"]),
    ]),
    "grammar": ("English", .72, .78, [
        ("Choose the correct word: 'They ___ going home.'", "are", ["is", "am", "be"]),
        ("The plural of 'child' is...", "children", ["childs", "childes", "childrens"]),
        ("Which of these is a noun?", "Happiness", ["Quickly", "Run", "Beautiful"]),
        ("The past tense of 'go' is...", "went", ["goed", "gone", "going"]),
        ("Which sentence is correct?", "Its colour is red.",
         ["Its' colour is red.", "It's colour is red.", "Its colour are red."]),
        ("An adverb describes a...", "Verb", ["Noun only", "Pronoun", "Full stop"]),
    ]),
    "cell_division": ("Biology", .62, .68, [
        ("Cell division that makes two identical cells is...", "Mitosis", ["Meiosis", "Osmosis", "Diffusion"]),
        ("Cell division that makes gametes is...", "Meiosis", ["Mitosis", "Respiration", "Digestion"]),
        ("How many chromosomes are in a normal human body cell?", "46", ["23", "44", "48"]),
        ("How many daughter cells does mitosis produce?", "2", ["1", "4", "8"]),
        ("In which stage do chromosomes line up in the middle of the cell?", "Metaphase",
         ["Prophase", "Anaphase", "Telophase"]),
        ("Mitosis is used for...", "Growth and repair", ["Making sperm and egg cells", "Digesting food", "Breathing"]),
    ]),
    "cell_biology": ("Biology", .60, .36, [
        ("Which organelle releases energy for the cell?", "Mitochondrion", ["Nucleus", "Ribosome", "Vacuole"]),
        ("Which part controls the cell's activities?", "Nucleus", ["Cell wall", "Cytoplasm", "Chloroplast"]),
        ("Which structure is in plant cells but not animal cells?", "Cell wall",
         ["Nucleus", "Mitochondria", "Cell membrane"]),
        ("Where does photosynthesis happen?", "Chloroplast", ["Mitochondrion", "Nucleus", "Ribosome"]),
        ("Which part controls what enters and leaves the cell?", "Cell membrane",
         ["Cell wall", "Nucleus", "Cytoplasm"]),
        ("Proteins are made at the...", "Ribosomes", ["Vacuoles", "Lysosomes", "Cell wall"]),
    ]),
}

MAYA_TOPICS = {
    "fractions": ("Mathematics", .35, .62, [
        ("1/2 + 1/4 = ?", "3/4", ["2/6", "1/6", "2/4"]),
        ("3/4 - 1/2 = ?", "1/4", ["1/2", "2/2", "3/2"]),
        ("2/3 of 12 = ?", "8", ["6", "9", "2"]),
        ("Which is larger: 3/5 or 2/3?", "2/3", ["3/5", "They are equal", "Cannot tell"]),
        ("1/3 × 3/4 = ?", "1/4", ["3/7", "4/7", "1/12"]),
        ("Write 7/4 as a mixed number", "1 3/4", ["1 1/4", "2 1/4", "1 7/4"]),
    ]),
    "percentages": ("Mathematics", .60, .75, [
        ("What is 10% of 250?", "25", ["2.5", "10", "250"]),
        ("Write 3/4 as a percentage", "75%", ["34%", "60%", "7.5%"]),
        ("50% of 80 = ?", "40", ["50", "30", "160"]),
        ("A $20 item has 25% off. What is the sale price?", "$15", ["$5", "$18", "$17"]),
        ("What is 15% of 60?", "9", ["6", "15", "900"]),
        ("Write 0.35 as a percentage", "35%", ["3.5%", "0.35%", "350%"]),
    ]),
    "equivalent_fractions": ("Mathematics", .50, .70, [
        ("Which fraction equals 1/2?", "4/8", ["2/8", "3/8", "1/4"]),
        ("2/3 = ?/12", "8", ["6", "4", "9"]),
        ("Simplify 6/9", "2/3", ["3/4", "1/3", "6/3"]),
        ("Which fraction equals 3/5?", "9/15", ["6/15", "3/10", "5/3"]),
        ("Simplify 10/25", "2/5", ["1/2", "5/10", "10/5"]),
        ("4/6 equals?", "2/3", ["1/3", "4/3", "3/4"]),
    ]),
    "reading_comprehension": ("English", .85, .92, [
        ("The main idea of a text is...", "What it is mostly about", ["The first word", "The title only", "A small detail"]),
        ("To 'infer' means to...", "Work out from clues", ["Copy exactly", "Ignore details", "Guess without reading"]),
        ("A synonym for 'happy' is...", "Joyful", ["Gloomy", "Angry", "Tired"]),
        ("Which of these is a fact?", "Water boils at 100°C at sea level.",
         ["Winter is the nicest season.", "Dogs are better than cats.", "Maths is boring."]),
        ("The narrator of a story is...", "The voice telling the story",
         ["The main character only", "The author's name", "The title"]),
        ("An antonym of 'ancient' is...", "Modern", ["Old", "Historic", "Aged"]),
    ]),
    "spelling": ("English", .80, .86, [
        ("Which spelling is correct?", "Necessary", ["Neccessary", "Necesary", "Neccesary"]),
        ("Which spelling is correct?", "Separate", ["Seperate", "Separete", "Sepparate"]),
        ("Which spelling is correct?", "Definitely", ["Definately", "Definitly", "Defanitely"]),
        ("Which spelling is correct?", "Receive", ["Recieve", "Receve", "Riceive"]),
        ("Which spelling is correct?", "Beautiful", ["Beutiful", "Beautifull", "Bootiful"]),
        ("Which spelling is correct?", "Environment", ["Enviroment", "Environmant", "Envirenment"]),
    ]),
    "photosynthesis": ("Science", .72, .80, [
        ("Plants make their food by...", "Photosynthesis", ["Respiration", "Digestion", "Evaporation"]),
        ("Which gas do plants take in for photosynthesis?", "Carbon dioxide", ["Oxygen", "Nitrogen", "Hydrogen"]),
        ("Which gas does photosynthesis release?", "Oxygen", ["Carbon dioxide", "Methane", "Helium"]),
        ("Which pigment captures sunlight?", "Chlorophyll", ["Haemoglobin", "Melanin", "Keratin"]),
        ("Which part of a plant does most photosynthesis?", "Leaves", ["Roots", "Stem", "Petals"]),
        ("Plants need water, carbon dioxide and...", "Light", ["Salt", "Sand", "Wind"]),
    ]),
    "states_of_matter": ("Science", .68, .74, [
        ("Ice turning into water is called...", "Melting", ["Freezing", "Evaporation", "Condensation"]),
        ("Water vapour turning into liquid water is...", "Condensation", ["Evaporation", "Melting", "Sublimation"]),
        ("Particles are packed closest together in a...", "Solid", ["Liquid", "Gas", "Plasma"]),
        ("Which state has no fixed shape or volume?", "Gas", ["Solid", "Liquid", "Ice"]),
        ("Water boils at about...", "100°C", ["0°C", "50°C", "212°C"]),
        ("A liquid turning into a solid is...", "Freezing", ["Melting", "Boiling", "Condensation"]),
    ]),
    "rivers": ("Geography", .70, .80, [
        ("Where does a river start?", "Its source", ["Its mouth", "Its delta", "Its estuary"]),
        ("Where does a river meet the sea?", "Its mouth", ["Its source", "Its tributary", "Its meander"]),
        ("A smaller river joining a bigger one is a...", "Tributary", ["Delta", "Meander", "Floodplain"]),
        ("A bend in a river is a...", "Meander", ["Delta", "Source", "Waterfall"]),
        ("The longest river in Africa is the...", "Nile", ["Congo", "Limpopo", "Orange"]),
        ("Flat land beside a river that can flood is a...", "Floodplain", ["Plateau", "Dune", "Peninsula"]),
    ]),
    "climate": ("Geography", .66, .72, [
        ("Weather over a long period is called...", "Climate", ["Season", "Forecast", "Temperature"]),
        ("Which line of latitude is at 0°?", "The Equator",
         ["Tropic of Cancer", "Tropic of Capricorn", "Prime Meridian"]),
        ("Rain caused by air rising over mountains is...", "Relief rainfall",
         ["Frontal rainfall", "Convectional rainfall", "Acid rain"]),
        ("Which instrument measures rainfall?", "Rain gauge", ["Barometer", "Thermometer", "Anemometer"]),
        ("Which instrument measures air pressure?", "Barometer", ["Rain gauge", "Thermometer", "Wind vane"]),
        ("Hot and wet all year describes a...", "Tropical rainforest climate",
         ["Desert climate", "Polar climate", "Mediterranean climate"]),
    ]),
    "ancient_egypt": ("History", .75, .80, [
        ("Which river supported Ancient Egypt?", "The Nile", ["The Amazon", "The Tigris", "The Thames"]),
        ("Egyptian kings were called...", "Pharaohs", ["Emperors", "Sultans", "Caesars"]),
        ("The pyramids were built as...", "Tombs", ["Markets", "Schools", "Palaces"]),
        ("Egyptian writing using pictures is called...", "Hieroglyphics", ["Cuneiform", "Latin", "Runes"]),
        ("Mummification preserved the...", "Body", ["Crops", "Pyramid", "Boat"]),
        ("What did the Egyptians write on?", "Papyrus", ["Silk", "Leather only", "Clay tablets"]),
    ]),
}

YEAR = 340                       # days of history
QUESTIONS_PER_QUIZ = 5


def _ts(days_ago: int, hour: int, minute: int) -> str:
    """UTC timestamp for a local time. Hours are kept at 14 or later so the local day never shifts."""
    day = progress.local_today() - timedelta(days=days_ago)
    return f"{day.isoformat()} {(hour - progress.settings.tz_offset_hours) % 24:02d}:{minute:02d}:00"


def _schedule(rng: random.Random) -> list[int]:
    """Days ago, newest first: four quizzes in the last week, then one every 2 to 5 days back to the start."""
    days = [1, 2, 4, 6]
    day = 8
    while day < YEAR:
        days.append(day)
        day += rng.randint(2, 5)
    return days


def _questions(rng: random.Random, topic: str, bank: list, p_right: float) -> list[dict]:
    """Five questions. How many are right follows the topic's skill, give or take one, so scores look like a
    real child's (a strong topic is mostly 4s and 5s) instead of the wild swings pure coin-flips give."""
    chosen = rng.sample(bank, QUESTIONS_PER_QUIZ)
    n_right = max(0, min(QUESTIONS_PER_QUIZ, round(QUESTIONS_PER_QUIZ * p_right + rng.uniform(-1, 1))))
    right_at = set(rng.sample(range(QUESTIONS_PER_QUIZ), n_right))
    out = []
    for i, (question, right, wrong) in enumerate(chosen):
        if i in right_at:
            answer, ok = right, True
        else:
            answer, ok = (None if rng.random() < 0.05 else rng.choice(wrong)), False
        out.append({"topic": topic, "question": question, "correct_answer": right,
                    "student_answer": answer, "is_correct": ok})
    return out


def _seed_student(user_id: int, topics: dict, seed: int) -> int:
    rng = random.Random(seed)
    keys = list(topics)
    count = 0
    for days_ago in _schedule(rng):
        topic = keys[(count * 3) % len(keys)] if days_ago <= 14 else rng.choice(keys)   # last fortnight: a spread of topics
        subject, p_old, p_now, bank = topics[topic]
        progress_through_year = 1 - days_ago / YEAR                                # 0 a year ago, 1 today
        p_right = p_old + (p_now - p_old) * progress_through_year
        questions = _questions(rng, topic, bank, p_right)
        title = topic.replace("_", " ").title() + " quiz"
        db.add_quiz(user_id, subject, topic, title, questions,
                    duration_sec=90 + 35 * len(questions) + rng.randint(-20, 40),
                    created_at=_ts(days_ago, rng.randint(15, 19), rng.randint(0, 59)))
        count += 1
    return count


def seed_quizzes(alex_id: int, maya_id: int) -> dict:
    return {"alex": _seed_student(alex_id, ALEX_TOPICS, 11), "maya": _seed_student(maya_id, MAYA_TOPICS, 22)}


def main() -> None:
    db.init_db()
    for name, topics, seed in (("Alex", ALEX_TOPICS, 11), ("Maya", MAYA_TOPICS, 22)):
        user = db.get_user_by_name(name)
        if user is None:
            print(f"  {name}: no such user, skipped (run scripts.seed_family first)")
        elif db.first_quiz_date(user["id"]):
            print(f"  {name}: already has quizzes, skipped")
        else:
            print(f"  {name}: added {_seed_student(user['id'], topics, seed)} quizzes")


if __name__ == "__main__":
    main()
