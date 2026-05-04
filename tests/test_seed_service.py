import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.bootstrap.seed_service import load_catalog_seed_entries, resolve_admin_university, seed_catalog
from app.modules.catalog.models import Faculty, Subject, University


def test_load_catalog_seed_entries_reads_json_file(tmp_path: Path):
    seed_file = tmp_path / "catalog.json"
    seed_file.write_text(
        json.dumps([{"name": "Test University", "input_faculties": ["Test Faculty"]}]),
        encoding="utf-8",
    )

    assert load_catalog_seed_entries(seed_file) == [
        {"name": "Test University", "input_faculties": ["Test Faculty"]}
    ]


def test_load_catalog_seed_entries_falls_back_when_file_is_missing(tmp_path: Path):
    entries = load_catalog_seed_entries(tmp_path / "missing.json")

    assert entries[0]["name"] == "O'zbekiston Milliy Universiteti"
    assert entries[0]["academic_units"][0]["name"] == "Matematika"


def test_load_catalog_seed_entries_rejects_non_list_json(tmp_path: Path):
    seed_file = tmp_path / "catalog.json"
    seed_file.write_text(json.dumps({"name": "Invalid"}), encoding="utf-8")

    with pytest.raises(SystemExit, match="catalog seed file must contain a list"):
        load_catalog_seed_entries(seed_file)


@pytest.mark.asyncio
async def test_seed_catalog_imports_universities_faculties_and_optional_subjects(session):
    universities = await seed_catalog(
        session,
        [
            {
                "name": "Custom University",
                "academic_units": [
                    {
                        "name": "Custom Faculty",
                        "type": "faculty",
                        "subjects": [{"name": "Custom Subject", "semester": 1}],
                    },
                    {"name": "Research Center", "type": "center"},
                ],
            },
            {
                "name": "Input Faculty University",
                "input_faculties": ["Input Faculty", "Input Faculty"],
            },
        ],
    )
    await session.commit()

    assert [item.name for item in universities] == ["Custom University", "Input Faculty University"]
    assert await session.scalar(select(func.count(University.id))) == 2
    assert await session.scalar(select(func.count(Faculty.id))) == 2
    assert await session.scalar(select(func.count(Subject.id))) == 1


def test_resolve_admin_university_prefers_mirzo_ulugbek_national_university():
    universities = [
        University(name="First University", slug="first-university"),
        University(
            name="Mirzo Ulug‘bek nomidagi O‘zbekiston Milliy universiteti",
            slug="mirzo-ulugbek-nomidagi-ozbekiston-milliy-universiteti",
        ),
    ]

    assert resolve_admin_university(universities).name == (
        "Mirzo Ulug‘bek nomidagi O‘zbekiston Milliy universiteti"
    )


def test_resolve_admin_university_falls_back_to_first_university():
    universities = [University(name="First University", slug="first-university")]

    assert resolve_admin_university(universities) is universities[0]
