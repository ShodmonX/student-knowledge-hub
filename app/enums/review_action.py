from enum import StrEnum


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
