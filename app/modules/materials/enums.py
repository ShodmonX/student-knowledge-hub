from enum import StrEnum


class FileKind(StrEnum):
    IMAGE = "image"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    OTHER = "other"


class MaterialStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class MaterialType(StrEnum):
    BOOK = "book"
    NOTES = "notes"
    SLIDES = "slides"
    EXAM = "exam"
    ASSIGNMENT = "assignment"
    LAB = "lab"
    CHEATSHEET = "cheatsheet"
    OTHER = "other"


class RejectReason(StrEnum):
    WRONG_SUBJECT = "wrong_subject"
    DUPLICATE = "duplicate"
    UNREADABLE = "unreadable"
    LOW_QUALITY = "low_quality"
    SPAM = "spam"
    COPYRIGHT_OR_POLICY_ISSUE = "copyright_or_policy_issue"
    OTHER = "other"


class ReportStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReviewAction(StrEnum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESUBMITTED = "resubmitted"
    MOVED_SUBJECT = "moved_subject"
    REQUESTED_REVISION = "requested_revision"
    WITHDRAWN = "withdrawn"
    REPORTED = "reported"
    TAKEDOWN = "takedown"
