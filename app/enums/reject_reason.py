from enum import StrEnum


class RejectReason(StrEnum):
    WRONG_SUBJECT = "wrong_subject"
    DUPLICATE = "duplicate"
    UNREADABLE = "unreadable"
    LOW_QUALITY = "low_quality"
    SPAM = "spam"
    COPYRIGHT_OR_POLICY_ISSUE = "copyright_or_policy_issue"
    OTHER = "other"
