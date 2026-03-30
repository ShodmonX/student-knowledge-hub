from enum import StrEnum


class UserRole(StrEnum):
    STUDENT = "student"
    MODERATOR = "moderator"
    ADMIN = "admin"
