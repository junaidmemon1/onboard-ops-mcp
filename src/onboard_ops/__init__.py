"""onboard-ops-mcp: run new-teammate onboarding with AI agents."""

from .core import OnboardingService, Task, Teammate, build_checklist

__all__ = ["OnboardingService", "Task", "Teammate", "build_checklist"]
__version__ = "0.1.0"
