"""Model routing and selection for different tasks."""

from typing import Optional
from ..config.loader import LLMConfig


class ModelRouter:
    """Routes tasks to appropriate models based on task type."""

    def __init__(self, config: LLMConfig):
        """
        Initialize model router.

        Args:
            config: LLM configuration with model mappings
        """
        self.config = config

    def get_model(self, task_type: str = "primary") -> str:
        """
        Get the appropriate model for a task type.

        Args:
            task_type: Type of task (primary, coding, reasoning, etc.)

        Returns:
            Model ID string
        """
        # Map task types to config attributes
        model_map = {
            "primary": self.config.primary,
            "primary_alt": self.config.primary_alt,
            "primary_cheap": self.config.primary_cheap,
            "coding": self.config.coding,
            "reasoning": self.config.reasoning,
            "reasoning_cheap": self.config.reasoning_cheap,
            "verification": self.config.verification,
            "verification_alt": self.config.verification_alt,
            "lightweight": self.config.lightweight,
            "canary": self.config.canary,
            "vision": self.config.vision,
            "vision_powerful": self.config.vision_powerful,
        }

        return model_map.get(task_type, self.config.primary)

    def select_for_analysis(self, activity_count: int, use_cheap: bool = False) -> str:
        """
        Select appropriate model for activity analysis.

        Args:
            activity_count: Number of activities to analyze
            use_cheap: Force use of cheaper model

        Returns:
            Model ID
        """
        # If forced cheap mode, use cheaper model
        if use_cheap:
            return self.get_model("primary_cheap")

        # Otherwise always use primary - we pay per prompt not per token
        # so might as well use the best model!
        return self.get_model("primary")

    def select_for_reasoning(self, complex: bool = False) -> str:
        """
        Select model for reasoning tasks.

        Args:
            complex: Whether this requires complex reasoning

        Returns:
            Model ID
        """
        if complex:
            return self.get_model("reasoning")
        else:
            return self.get_model("reasoning_cheap")
