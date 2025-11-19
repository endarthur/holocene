"""Activity aggregation for LLM context."""

from typing import List
from datetime import datetime, timedelta
from collections import defaultdict

from .models import Activity


class ActivityAggregator:
    """Aggregates activities into LLM-friendly summaries."""

    @staticmethod
    def summarize_activities(activities: List[Activity]) -> str:
        """
        Create a compact summary of activities for LLM analysis.

        Args:
            activities: List of Activity objects

        Returns:
            Formatted string summary
        """
        if not activities:
            return "No activities recorded."

        # Group by type
        by_type = defaultdict(list)
        for activity in activities:
            by_type[activity.activity_type.value].append(activity)

        # Calculate totals
        total_duration = sum(a.duration_minutes or 0 for a in activities)

        # Build summary
        lines = []
        lines.append(f"Total Activities: {len(activities)}")
        if total_duration > 0:
            hours = total_duration // 60
            minutes = total_duration % 60
            lines.append(f"Total Duration: {hours}h {minutes}m")

        lines.append("\nBy Type:")
        for type_name, acts in sorted(by_type.items()):
            type_duration = sum(a.duration_minutes or 0 for a in acts)
            duration_str = f" ({type_duration}m)" if type_duration > 0 else ""
            lines.append(f"  {type_name}: {len(acts)} activities{duration_str}")

        lines.append("\nActivity Timeline:")
        for activity in sorted(activities, key=lambda a: a.timestamp):
            time_str = activity.timestamp.strftime("%H:%M")
            duration_str = f" ({activity.duration_minutes}m)" if activity.duration_minutes else ""
            tags_str = f" [{', '.join(activity.tags)}]" if activity.tags else ""
            lines.append(f"  {time_str} - {activity.description}{duration_str}{tags_str}")

        return "\n".join(lines)

    @staticmethod
    def create_analysis_prompt(
        activities: List[Activity],
        period: str = "today",
        additional_context: str = "",
        journel_context: str = "",
        git_context: str = "",
        include_xkcd: bool = False
    ) -> str:
        """
        Create a prompt for LLM analysis of activities.

        Args:
            activities: List of activities to analyze
            period: Time period being analyzed (e.g., "today", "this week")
            additional_context: Optional additional context
            journel_context: Context from journel projects
            git_context: Context from git activity
            include_xkcd: Whether to include XKCD comic reference

        Returns:
            Formatted prompt string
        """
        summary = ActivityAggregator.summarize_activities(activities)

        # Build context section
        context_parts = []

        if journel_context:
            context_parts.append(f"## Journel Project Context\n\n{journel_context}")

        if git_context:
            context_parts.append(f"## Git Activity Context\n\n{git_context}")

        if additional_context:
            context_parts.append(f"## Additional Context\n\n{additional_context}")

        context_section = "\n\n".join(context_parts) if context_parts else ""

        prompt = f"""I'm reviewing my activities from {period}. Please analyze these patterns and provide insights.

## Tracked Activities

{summary}

{context_section}

Please provide:
1. **Pattern Observations**: What patterns do you notice in my activities and timing?
2. **Flow States**: When did I seem to have focused work sessions?
3. **Activity Balance**: Is there a good mix of different activity types?
4. **Data Source Alignment**: How do tracked activities, journel projects, and git commits align? Notice any divergences - they're important insights!
5. **Gentle Suggestions**: Any observations about time management or work patterns?

Important: Please frame your analysis in observational, non-judgmental language. Focus on patterns rather than prescriptions. No shame or "you should" statements - just neutral observations and gentle insights."""

        # Add XKCD reference if requested
        if include_xkcd:
            prompt += """

## XKCD Reference (Optional Fun!)

If you notice any themes, patterns, or situations that remind you of a relevant XKCD comic, please end your analysis with:

**Relevant XKCD:** [Comic title] - https://xkcd.com/[number]/
Brief explanation of why it's relevant (1-2 sentences)

Only include this if there's a genuinely fitting comic. Don't force it! XKCD often covers: procrastination, productivity, programming, automation, workflows, focus, time management, project management, and "nerd sniping" in general."""

        return prompt

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough estimate of token count (4 chars ≈ 1 token)."""
        return len(text) // 4
