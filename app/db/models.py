from app.modules.admin.scope_models import (
    ModeratorFacultyScope,
    ModeratorSubjectScope,
    ModeratorUniversityScope,
)
from app.modules.audit.models import AuditLog
from app.modules.auth.models import (
    EmailOutbox,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshTokenSession,
)
from app.modules.catalog.models import Faculty, Subject, University
from app.modules.catalog_proposals.models import (
    CatalogProposalLog,
    FacultyProposal,
    SubjectProposal,
    UniversityProposal,
)
from app.modules.community.models import Comment, MaterialRating
from app.modules.materials.models import Material, MaterialFile, MaterialReport, MaterialReviewLog, MaterialDownload
from app.modules.notifications.models import Notification
from app.modules.tags.models import MaterialTag, Tag
from app.modules.telegram.models import TelegramEventOutbox, TelegramLink, TelegramLinkSession
from app.modules.users.models import SavedMaterial, User, UserPreference

__all__ = [
    "AuditLog",
    "CatalogProposalLog",
    "Comment",
    "Faculty",
    "FacultyProposal",
    "Material",
    "MaterialFile",
    "MaterialDownload",
    "MaterialRating",
    "MaterialReport",
    "MaterialReviewLog",
    "MaterialTag",
    "ModeratorFacultyScope",
    "ModeratorSubjectScope",
    "ModeratorUniversityScope",
    "Notification",
    "EmailVerificationToken",
    "EmailOutbox",
    "PasswordResetToken",
    "RefreshTokenSession",
    "SavedMaterial",
    "Subject",
    "SubjectProposal",
    "Tag",
    "TelegramEventOutbox",
    "TelegramLink",
    "TelegramLinkSession",
    "University",
    "UniversityProposal",
    "User",
    "UserPreference",
]
