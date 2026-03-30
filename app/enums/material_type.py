from enum import StrEnum


class MaterialType(StrEnum):
    BOOK = "book"
    NOTES = "notes"
    SLIDES = "slides"
    EXAM = "exam"
    ASSIGNMENT = "assignment"
    LAB = "lab"
    CHEATSHEET = "cheatsheet"
    OTHER = "other"
