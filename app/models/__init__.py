from app.models.audit_log import AuditLog
from app.models.catalog_proposal import (
    CatalogProposalLog,
    FacultyProposal,
    SubjectProposal,
    UniversityProposal,
)
from app.models.comment import Comment
from app.models.faculty import Faculty
from app.models.material import Material
from app.models.material_file import MaterialFile
from app.models.material_rating import MaterialRating
from app.models.material_report import MaterialReport
from app.models.material_review_log import MaterialReviewLog
from app.models.moderator_scope import ModeratorFacultyScope, ModeratorSubjectScope, ModeratorUniversityScope
from app.models.notification import Notification
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token_session import RefreshTokenSession
from app.models.saved_material import SavedMaterial
from app.models.subject import Subject
from app.models.tag import MaterialTag, Tag
from app.models.university import University
from app.models.user_preference import UserPreference
from app.models.user import User

__all__ = [
    "AuditLog",
    "CatalogProposalLog",
    "Comment",
    "Faculty",
    "FacultyProposal",
    "Material",
    "MaterialFile",
    "MaterialRating",
    "MaterialReport",
    "MaterialReviewLog",
    "ModeratorFacultyScope",
    "ModeratorSubjectScope",
    "ModeratorUniversityScope",
    "Notification",
    "PasswordResetToken",
    "RefreshTokenSession",
    "SavedMaterial",
    "Subject",
    "SubjectProposal",
    "Tag",
    "MaterialTag",
    "University",
    "UniversityProposal",
    "UserPreference",
    "User",
]
