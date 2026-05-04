import pytest
from app.utils.serializers import build_university_summary, build_public_user_summary
from app.modules.catalog.models import University
from app.modules.users.models import User

def test_build_university_summary_none():
    assert build_university_summary(None) is None

def test_build_public_user_summary_none():
    assert build_public_user_summary(None) is None
