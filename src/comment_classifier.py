"""
Comment Classifier - Claude API Integration

Classifies Facebook comments using Claude API and generates reply suggestions.
Uses Claude Haiku for cost efficiency.
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

# Import config helper for secrets
try:
    from config import get_secret
except ImportError:
    from dotenv import load_dotenv
    load_dotenv()
    def get_secret(key, default=None):
        return os.getenv(key, default)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import anthropic
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic package not installed. Run: pip install anthropic")


# =============================================================================
# CONSTANTS
# =============================================================================

# Model to use (Haiku is cheapest and fast enough for classification)
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Fallback model if haiku not available
CLAUDE_MODEL_FALLBACK = "claude-3-haiku-20240307"

# Token costs for logging (USD per 1M tokens)
TOKEN_COSTS = {
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
}

# USD to INR conversion (approximate)
USD_TO_INR = 83.0

# System prompt for classification
SYSTEM_PROMPT = """You are GuitarBro's Facebook comment assistant. Your job is to:
1. Classify incoming comments into categories
2. Detect sentiment
3. Generate a friendly reply suggestion

Categories:
- price_objection: Comments about price being high, asking for discounts, comparing prices
- doubt: Skepticism about product quality, "does this really work?", questioning claims
- product_question: Genuine questions about features, specs, usage, shipping, etc.
- positive: Excitement, interest, compliments, "I want this!", tagging friends
- negative: Criticism, bad reviews, expressing disappointment (but not complaints)
- complaint: Service issues, delivery problems, refund requests, angry customers
- other: Spam, random comments, emojis only, unrelated content

Sentiment: positive, neutral, or negative

Reply Guidelines:
- Be friendly and encouraging
- Use Hindi-English mix (Hinglish) naturally
- Keep replies under 200 characters
- For price_objection: Highlight value, offer to DM for special deals
- For doubt: Reassure with social proof, invite to try
- For product_question: Answer helpfully, invite to DM for details
- For positive: Thank them, encourage action
- For negative/complaint: Be empathetic, offer to help via DM
- For other: Skip or give generic friendly response

IMPORTANT: Respond ONLY with valid JSON, no other text."""

USER_PROMPT_TEMPLATE = """Classify this Facebook comment and suggest a reply:

Comment: "{comment_text}"
Commenter Name: {commenter_name}
Post/Ad Context: {ad_context}

Respond with JSON:
{{
    "category": "one of: price_objection, doubt, product_question, positive, negative, complaint, other",
    "sentiment": "one of: positive, neutral, negative",
    "confidence": 0.0 to 1.0,
    "reasoning": "brief explanation of classification",
    "suggested_reply": "friendly reply in Hinglish (under 200 chars)",
    "should_reply": true or false (false for spam/trolls)
}}"""


# =============================================================================
# CLASSIFIER CLASS
# =============================================================================

class CommentClassifier:
    """
    Classifies Facebook comments using Claude API.

    Usage:
        classifier = CommentClassifier()
        result = classifier.classify_comment(
            comment_text="Bhai ye guitar kitne ka hai?",
            commenter_name="Rahul",
            ad_context="Guitar Learning Course Ad"
        )
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the classifier.

        Args:
            api_key: Anthropic API key (falls back to ANTHROPIC_API_KEY env var)
        """
        self.api_key = api_key or get_secret('ANTHROPIC_API_KEY')
        self.client = None
        self.model = CLAUDE_MODEL
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0

        if not ANTHROPIC_AVAILABLE:
            logger.error("anthropic package not available")
            return

        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set")
            return

        try:
            self.client = anthropic.Anthropic(api_key=self.api_key)
            logger.info("CommentClassifier initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")

    def is_available(self) -> bool:
        """Check if classifier is ready to use."""
        return self.client is not None

    def classify_comment(
        self,
        comment_text: str,
        commenter_name: str = "User",
        ad_context: str = "Facebook Post"
    ) -> Dict[str, Any]:
        """
        Classify a single comment.

        Args:
            comment_text: The comment text to classify
            commenter_name: Name of the commenter
            ad_context: Context about the post/ad

        Returns:
            Dictionary with classification results:
            {
                "success": bool,
                "category": str,
                "sentiment": str,
                "confidence": float,
                "reasoning": str,
                "suggested_reply": str,
                "should_reply": bool,
                "tokens_used": {"input": int, "output": int},
                "cost_usd": float,
                "cost_inr": float,
                "error": str (if failed)
            }
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "Classifier not available. Check API key.",
                "category": "other",
                "sentiment": "neutral",
                "confidence": 0.0,
                "suggested_reply": "",
                "should_reply": False
            }

        # Skip very short or empty comments
        if not comment_text or len(comment_text.strip()) < 2:
            return {
                "success": True,
                "category": "other",
                "sentiment": "neutral",
                "confidence": 1.0,
                "reasoning": "Empty or too short comment",
                "suggested_reply": "",
                "should_reply": False,
                "tokens_used": {"input": 0, "output": 0},
                "cost_usd": 0.0,
                "cost_inr": 0.0
            }

        # Build the prompt
        user_prompt = USER_PROMPT_TEMPLATE.format(
            comment_text=comment_text[:500],  # Limit comment length
            commenter_name=commenter_name or "User",
            ad_context=ad_context or "Facebook Post"
        )

        try:
            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Extract tokens used
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            # Calculate cost
            costs = TOKEN_COSTS.get(self.model, TOKEN_COSTS[CLAUDE_MODEL_FALLBACK])
            cost_usd = (input_tokens * costs["input"] / 1_000_000) + \
                       (output_tokens * costs["output"] / 1_000_000)
            cost_inr = cost_usd * USD_TO_INR

            # Update totals
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_cost_usd += cost_usd

            # Parse response
            response_text = response.content[0].text.strip()

            # Try to parse JSON
            try:
                # Handle potential markdown code blocks
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]

                result = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    raise ValueError(f"Could not parse JSON from response: {response_text[:200]}")

            # Validate and normalize result
            category = result.get("category", "other")
            if category not in ["price_objection", "doubt", "product_question",
                               "positive", "negative", "complaint", "other"]:
                category = "other"

            sentiment = result.get("sentiment", "neutral")
            if sentiment not in ["positive", "neutral", "negative"]:
                sentiment = "neutral"

            confidence = float(result.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            return {
                "success": True,
                "category": category,
                "sentiment": sentiment,
                "confidence": confidence,
                "reasoning": result.get("reasoning", ""),
                "suggested_reply": result.get("suggested_reply", ""),
                "should_reply": result.get("should_reply", True),
                "tokens_used": {"input": input_tokens, "output": output_tokens},
                "cost_usd": cost_usd,
                "cost_inr": cost_inr
            }

        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            return {
                "success": False,
                "error": f"API error: {str(e)}",
                "category": "other",
                "sentiment": "neutral",
                "confidence": 0.0,
                "suggested_reply": "",
                "should_reply": False
            }
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return {
                "success": False,
                "error": str(e),
                "category": "other",
                "sentiment": "neutral",
                "confidence": 0.0,
                "suggested_reply": "",
                "should_reply": False
            }

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get cumulative usage statistics."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
            "total_cost_inr": self.total_cost_usd * USD_TO_INR
        }

    def reset_usage_stats(self):
        """Reset usage statistics."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_classifier_instance = None

def get_classifier() -> CommentClassifier:
    """Get or create the global classifier instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = CommentClassifier()
    return _classifier_instance


def classify_comment(
    comment_text: str,
    commenter_name: str = "User",
    ad_context: str = "Facebook Post"
) -> Dict[str, Any]:
    """
    Convenience function to classify a comment.

    Args:
        comment_text: The comment to classify
        commenter_name: Name of commenter
        ad_context: Context about the post/ad

    Returns:
        Classification result dictionary
    """
    classifier = get_classifier()
    return classifier.classify_comment(comment_text, commenter_name, ad_context)


def check_classifier_status() -> Dict[str, Any]:
    """Check if classifier is properly configured."""
    api_key = get_secret('ANTHROPIC_API_KEY')

    status = {
        "anthropic_installed": ANTHROPIC_AVAILABLE,
        "api_key_set": bool(api_key),
        "api_key_preview": f"{api_key[:10]}..." if api_key else None,
        "ready": False,
        "message": ""
    }

    if not ANTHROPIC_AVAILABLE:
        status["message"] = "Install anthropic: pip install anthropic"
    elif not api_key:
        status["message"] = "Set ANTHROPIC_API_KEY in .env file"
    else:
        classifier = get_classifier()
        status["ready"] = classifier.is_available()
        status["message"] = "Ready" if status["ready"] else "Failed to initialize client"

    return status
