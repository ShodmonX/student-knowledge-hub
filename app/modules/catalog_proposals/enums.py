from enum import StrEnum


class ProposalEntityType(StrEnum):
    UNIVERSITY = "university_proposal"
    FACULTY = "faculty_proposal"
    SUBJECT = "subject_proposal"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
