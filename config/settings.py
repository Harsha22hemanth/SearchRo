"""Central configuration for SearchRo.

Values come from environment variables (optionally loaded from a ``.env`` file).
Nothing secret is hardcoded here.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

APP_NAME = "SearchRo"
APP_VERSION = "2.0"

DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
LOG_PATH = DATA_DIR / "searchro.log"


def _resolve_db_path() -> Path:
    raw = os.getenv("SEARCHRO_DB_PATH", "").strip()
    if not raw:
        return DATA_DIR / "searchro.db"
    p = Path(raw)
    return p if p.is_absolute() else BASE_DIR / p


# Read at call time by database.db, so tests can monkeypatch it.
DB_PATH: Path = _resolve_db_path()


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


REQUEST_TIMEOUT: float = _float_env("SEARCHRO_REQUEST_TIMEOUT", 10.0)
AI_TIMEOUT: float = _float_env("SEARCHRO_AI_TIMEOUT", 60.0)


def get_openai_key() -> str:
    """Return the OpenAI key from the environment ('' when not configured)."""
    return os.getenv("OPENAI_API_KEY", "").strip()


def get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "").strip() or "gpt-4o-mini"


# ---------------------------------------------------------------- uploads
MAX_UPLOAD_MB = 5
ALLOWED_RESUME_EXTENSIONS = (".pdf", ".docx", ".txt")

# ---------------------------------------------------------------- job sources
REMOTIVE_API_URL = "https://remotive.com/api/remote-jobs"
ARBEITNOW_API_URL = "https://www.arbeitnow.com/api/job-board-api"
ARBEITNOW_MAX_PAGES = 3
HTTP_HEADERS = {"User-Agent": "SearchRo/2.0 (personal job search tool)", "Accept": "application/json"}

# ---------------------------------------------------------------- external search links
LINKEDIN_JOBS_URL = os.getenv("LINKEDIN_JOBS_URL", "https://www.linkedin.com/jobs/search/")
NAUKRI_URL_TEMPLATES = {
    "role_location": os.getenv("NAUKRI_URL_ROLE_LOCATION", "https://www.naukri.com/{role}-jobs-in-{location}"),
    "role_only": os.getenv("NAUKRI_URL_ROLE_ONLY", "https://www.naukri.com/{role}-jobs"),
    "location_only": os.getenv("NAUKRI_URL_LOCATION_ONLY", "https://www.naukri.com/jobs-in-{location}"),
}
NAUKRI_FALLBACK_URL = "https://www.naukri.com/jobs"

# ---------------------------------------------------------------- tracker
APPLICATION_STATUSES = [
    "Saved", "Preparing", "Applied", "Assessment", "Interview", "Offer", "Rejected", "Withdrawn",
]
SUBMITTED_STATUSES = ("Applied", "Assessment", "Interview", "Offer", "Rejected")

# ---------------------------------------------------------------- search options
EMPLOYMENT_TYPES = ["Full-time", "Part-time", "Contract", "Internship"]
EXPERIENCE_LEVELS = ["Entry-level", "Mid-level", "Senior", "Unspecified"]
WORK_MODES = ["Any", "Remote", "Onsite"]
SORT_OPTIONS = ["Relevance", "Newest"]
PAGE_SIZE = 10

FRESHER_PRESETS = [
    "Fresher",
    "Graduate Trainee",
    "Junior Developer",
    "Entry Level Python Developer",
    "Junior Machine Learning Engineer",
    "Data Analyst Fresher",
    "Software Engineering Intern",
    "Associate Software Engineer",
    "Graduate Engineer Trainee",
]

# Transparent keyword rules used for fresher / entry-level detection.
ENTRY_TITLE_KEYWORDS = (
    "fresher", "freshers", "graduate", "trainee", "junior", "jr", "entry level", "entry-level",
    "intern", "internship", "associate", "apprentice", "campus",
)
ENTRY_TEXT_KEYWORDS = (
    "fresher", "freshers", "recent graduate", "new graduate", "fresh graduate", "entry level",
    "entry-level", "no experience required", "no prior experience", "graduate program",
    "graduate programme", "trainee", "internship", "0-1 year", "0-2 year", "0 to 1 year",
    "0 to 2 year", "less than 1 year", "campus hire",
)
SENIOR_TITLE_KEYWORDS = (
    "senior", "sr", "lead", "principal", "staff", "manager", "head of", "architect", "director",
    "vp", "chief", "expert",
)

# ---------------------------------------------------------------- skills vocabulary
# category -> canonical skill -> extra aliases (the canonical name always matches too)
SKILL_CATEGORIES: dict[str, dict[str, list[str]]] = {
    "Programming Languages": {
        "Python": ["python3"], "Java": [], "JavaScript": ["js", "ecmascript"], "TypeScript": [],
        "C++": [], "C#": [], "SQL": ["pl/sql", "t-sql"], "PHP": [], "Go": ["golang"], "Kotlin": [],
        "Swift": [], "Ruby": [], "Rust": [], "Scala": [], "HTML": ["html5"], "CSS": ["css3"],
        "Bash": ["shell scripting"],
    },
    "Frameworks & Libraries": {
        "Django": [], "Flask": [], "FastAPI": [], "Streamlit": [], "React": ["react.js", "reactjs"],
        "Angular": ["angularjs"], "Vue": ["vue.js", "vuejs"], "Node.js": ["nodejs"],
        "Express": ["express.js", "expressjs"],
        "Spring Boot": ["springboot", "spring framework", "spring mvc"], "Hibernate": [],
        "Bootstrap": [], "Tailwind CSS": ["tailwind", "tailwindcss"], "jQuery": [], ".NET": ["dotnet", "asp.net"],
        "Pandas": [], "NumPy": [], "Scikit-learn": ["sklearn", "scikit learn"], "TensorFlow": [],
        "PyTorch": [], "Keras": [], "Matplotlib": [], "Seaborn": [], "OpenCV": [], "Selenium": [],
        "Pytest": [], "BeautifulSoup": ["bs4"],
    },
    "Databases": {
        "MySQL": [], "PostgreSQL": ["postgres"], "SQLite": [], "MongoDB": [], "Oracle": [],
        "Redis": [], "SQL Server": ["mssql", "microsoft sql server"], "Firebase": [],
        "Elasticsearch": [], "Cassandra": [], "DynamoDB": [],
    },
    "Tools & Platforms": {
        "Git": [], "GitHub": [], "GitLab": [], "Docker": [], "Kubernetes": ["k8s"],
        "AWS": ["amazon web services"], "Azure": [], "GCP": ["google cloud"], "Linux": [],
        "Jenkins": [], "CI/CD": ["cicd"], "Jira": [], "Postman": [],
        "VS Code": ["vscode", "visual studio code"], "Jupyter": ["jupyter notebook"],
        "Power BI": ["powerbi"], "Tableau": [], "Excel": ["ms excel", "microsoft excel"],
        "REST APIs": ["rest api", "restful api", "restful apis", "restful", "rest services"],
        "GraphQL": [], "Heroku": [], "Airflow": [], "Spark": ["pyspark", "apache spark"],
        "Hadoop": [], "Kafka": [], "Figma": [],
    },
    "Data Science & ML": {
        "Machine Learning": ["ml"], "Deep Learning": [], "NLP": ["natural language processing"],
        "Computer Vision": [], "Data Analysis": ["data analytics"], "Data Visualization": [],
        "Statistics": [], "EDA": ["exploratory data analysis"], "Feature Engineering": [],
        "LLMs": ["llm", "large language models"], "Generative AI": ["genai"], "ETL": [],
        "Web Scraping": [],
    },
    "Concepts & Practices": {
        "Data Structures": ["dsa"], "Algorithms": [], "OOP": ["oops", "object-oriented", "object oriented"],
        "Agile": ["scrum"], "Microservices": [], "Unit Testing": ["unit tests"],
    },
}
