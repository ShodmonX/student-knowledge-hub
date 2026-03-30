import asyncio

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.enums.user_role import UserRole
from app.models.faculty import Faculty
from app.models.subject import Subject
from app.models.university import University
from app.models.user import User
from app.utils.slug import slugify


async def seed() -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        university = University(name="Demo University", slug=slugify("Demo University"))
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

        faculty_names = ["Engineering", "Economics", "Computer Science"]
        subject_specs = [
            ("Calculus", 1),
            ("Physics", 1),
            ("Programming Fundamentals", 1),
            ("Data Structures", 2),
            ("Database Systems", 3),
        ]
        for faculty_name in faculty_names:
            faculty = Faculty(name=faculty_name, slug=slugify(faculty_name), university_id=university.id)
            session.add(faculty)
            await session.flush()
            for subject_name, semester in subject_specs[:2] if faculty_name != "Computer Science" else subject_specs:
                session.add(
                    Subject(
                        faculty_id=faculty.id,
                        name=subject_name,
                        slug=slugify(subject_name),
                        semester=semester,
                    )
                )

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
