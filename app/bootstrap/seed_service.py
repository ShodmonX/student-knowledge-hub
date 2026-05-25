from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.core.security import hash_password
from app.db import models as _models  # noqa: F401
from app.db.session import AsyncSessionLocal, engine
from app.modules.users.enums import UserRole
from app.modules.catalog.models import Faculty, Subject, University
from app.modules.users.models import User
from app.utils.slug import slugify

CATALOG_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "data.json"
ADMIN_UNIVERSITY_NAMES = (
    "Mirzo Ulug‘bek nomidagi O‘zbekiston Milliy universiteti",
    "Miroz Ulog'bek nomidagi O'zbekiston Milliy Universiteti",
    "O'zbekiston Milliy Universiteti",
)


async def seed() -> None:
    settings = get_settings()
    try:
        await engine.dispose()
        async with AsyncSessionLocal() as session:
            university_count = await session.scalar(select(func.count(University.id)))
            if university_count:
                print(f"Seed skipped: database already contains {university_count} universities.")
                return

            catalog_entries = load_catalog_seed_entries()
            universities = await seed_catalog(session, catalog_entries)
            if not universities:
                raise SystemExit("Seed failed: no valid universities found in catalog seed data.")

            admin = User(
                full_name=settings.admin_full_name,
                email=settings.admin_email,
                hashed_password=hash_password(settings.admin_password),
                role=UserRole.ADMIN,
                university_id=resolve_admin_university(universities).id,
                is_verified=True,
            )
            session.add(admin)

            await session.commit()
            print(f"Seed completed: {len(universities)} universities, faculties, and admin user were created.")
    except OperationalError as exc:
        db_url = settings.db_url
        if "@postgres:" in db_url:
            raise SystemExit(
                "Seed failed: current DB_URL points to Docker service host 'postgres'. "
                "If you run scripts from the host machine, use localhost in DB_URL or run the script inside the API container."
            ) from exc
        raise SystemExit(f"Seed failed: could not connect to database using DB_URL={db_url}") from exc


def load_catalog_seed_entries(path: Path = CATALOG_SEED_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return _fallback_catalog_seed_entries()

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"Seed failed: catalog seed file must contain a list: {path}")
    return [entry for entry in data if isinstance(entry, dict)]


async def seed_catalog(session, entries: list[dict[str, Any]]) -> list[University]:
    universities: list[University] = []
    university_slugs: set[str] = set()

    for entry in entries:
        university_name = _clean_name(entry.get("name"))
        if not university_name:
            continue

        university_slug = _unique_slug(slugify(university_name), university_slugs)
        university = University(name=university_name, slug=university_slug)
        session.add(university)
        await session.flush()
        universities.append(university)

        faculty_slugs: set[str] = set()
        for faculty_entry in _extract_faculty_entries(entry):
            faculty_name = _clean_name(faculty_entry.get("name"))
            if not faculty_name:
                continue

            faculty = Faculty(
                name=faculty_name,
                slug=_unique_slug(slugify(faculty_name), faculty_slugs),
                university_id=university.id,
            )
            session.add(faculty)
            await session.flush()

            seen_subject_slugs: set[str] = set()
            for subject_entry in faculty_entry.get("subjects", []):
                subject_name = _clean_name(subject_entry.get("name"))
                if not subject_name:
                    continue
                sub_slug = slugify(subject_name)
                if sub_slug in seen_subject_slugs:
                    continue
                seen_subject_slugs.add(sub_slug)
                session.add(
                    Subject(
                        faculty_id=faculty.id,
                        name=subject_name,
                        slug=sub_slug,
                    )
                )

    return universities


def resolve_admin_university(universities: list[University]) -> University:
    if not universities:
        raise SystemExit("Seed failed: admin user cannot be created without a university.")

    by_slug = {university.slug: university for university in universities}
    for university_name in ADMIN_UNIVERSITY_NAMES:
        university = by_slug.get(slugify(university_name))
        if university:
            return university
    return universities[0]


def _extract_faculty_entries(entry: dict[str, Any]) -> list[dict[str, Any]]:
    faculty_entries = [
        {"name": unit.get("name"), "subjects": unit.get("subjects", [])}
        for unit in entry.get("academic_units", [])
        if isinstance(unit, dict) and unit.get("type") == "faculty"
    ]
    if not faculty_entries:
        faculty_entries = [{"name": name} for name in entry.get("input_faculties", [])]

    deduplicated: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for faculty_entry in faculty_entries:
        name = _clean_name(faculty_entry.get("name"))
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        deduplicated.append({"name": name, "subjects": faculty_entry.get("subjects", [])})
    return deduplicated


def _clean_name(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _unique_slug(base_slug: str, used_slugs: set[str]) -> str:
    slug = base_slug
    suffix = 2
    while slug in used_slugs:
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    used_slugs.add(slug)
    return slug


def _fallback_catalog_seed_entries() -> list[dict[str, Any]]:
    return [
        {
            "name": "O'zbekiston Milliy Universiteti",
            "academic_units": [
                {
                    "name": "Matematika",
                    "type": "faculty",
                    "subjects": [
                        {"name": "Chiziqli Algebra", "semester": 1},
                        {"name": "Umumiy Fizika", "semester": 1},
                        {"name": "Algoritmlar va Dasturlash Asoslari", "semester": 1},
                        {"name": "Algebra", "semester": 2},
                        {"name": "Umumiy Fizika", "semester": 3},
                    ],
                },
                {
                    "name": "Amaliy Matematika",
                    "type": "faculty",
                    "subjects": [
                        {"name": "Chiziqli Algebra", "semester": 1},
                        {"name": "Umumiy Fizika", "semester": 1},
                    ],
                },
                {
                    "name": "Fizika",
                    "type": "faculty",
                    "subjects": [
                        {"name": "Chiziqli Algebra", "semester": 1},
                        {"name": "Umumiy Fizika", "semester": 1},
                    ],
                },
            ],
        }
    ]
