from app.core.exceptions import PolicyViolation


class PolicyService:
    def validate_report_reason(self, reason: str) -> None:
        if not reason.strip():
            raise PolicyViolation("Report reason is required")
