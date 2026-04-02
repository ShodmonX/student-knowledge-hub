from __future__ import annotations

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


async def seed() -> None:
    settings = get_settings()
    try:
        await engine.dispose()
        async with AsyncSessionLocal() as session:
            university_count = await session.scalar(select(func.count(University.id)))
            if university_count:
                print(f"Seed skipped: database already contains {university_count} universities.")
                return

            university = University(name="O'zbekiston Milliy Universiteti", slug=slugify("O'zbekiston Milliy Universiteti"))
            session.add(university)
            await session.flush()

            admin = User(
                full_name=settings.admin_full_name,
                email=settings.admin_email,
                hashed_password=hash_password(settings.admin_password),
                role=UserRole.ADMIN,
                university_id=university.id,
                is_verified=True,
            )
            session.add(admin)

            faculty_names = ["Matematika", "Amaliy Matematika", "Fizika"]
            subject_specs = [
                ("Chiziqli Algebra", 1),
                ("Umumiy Fizika", 1),
                ("Algoritmlar va Dasturlash Asoslari", 1),
                ("Algebra", 2),
                ("Umumiy Fizika", 3),
            ]
            for faculty_name in faculty_names:
                faculty = Faculty(name=faculty_name, slug=slugify(faculty_name), university_id=university.id)
                session.add(faculty)
                await session.flush()
                faculty_subjects = subject_specs if faculty_name == "Matematika" else subject_specs[:2]
                for subject_name, semester in faculty_subjects:
                    session.add(
                        Subject(
                            faculty_id=faculty.id,
                            name=subject_name,
                            slug=slugify(subject_name),
                            semester=semester,
                        )
                    )

            await session.commit()
            print("Seed completed: O'zbekiston Milliy Universiteti, faculties, subjects, and admin user were created.")
    except OperationalError as exc:
        db_url = settings.db_url
        if "@postgres:" in db_url:
            raise SystemExit(
                "Seed failed: current DB_URL points to Docker service host 'postgres'. "
                "If you run scripts from the host machine, use localhost in DB_URL or run the script inside the API container."
            ) from exc
        raise SystemExit(f"Seed failed: could not connect to database using DB_URL={db_url}") from exc
