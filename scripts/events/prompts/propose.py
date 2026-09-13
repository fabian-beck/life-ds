"""What the proposal is told: read the whole article set and propose the events.

This is the one call that sees a life whole, which is why it is also the one
asked to weigh the events against each other. How much of a life an event turns
on is a comparison, not a property of the event.
"""

from typing import Any, Dict, List, Optional


def build_proposal_prompt(
    page_data: Dict[str, Any],
    summary_data: Dict[str, Any],
    subject: str,
    related_articles: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Build proposal prompt for generating event skeletons and chapters.

    Focus on identifying significant life events and organizing them into chapters.
    NO location/image/source details (the research call adds these).
    """
    summary_text = summary_data.get("extract", "").strip()
    extract_text = page_data.get("extract", "").strip()

    main_article_title = page_data.get("title", subject)

    combined = f"TARGET SUBJECT: {main_article_title}\n"
    combined += "=" * 60 + "\n"
    combined += f"You are creating a biographical timeline for {main_article_title}.\n"
    combined += f"Focus ONLY on events from {main_article_title}'s life.\n"
    combined += "=" * 60 + "\n\n"
    combined += f"MAIN ARTICLE\nPage title: {main_article_title}\nPage URL: {page_data.get('fullurl', '')}\n\n"

    if summary_text:
        combined += f"Summary snippet:\n{summary_text}\n\n"

    if extract_text:
        truncated = extract_text[:12000]
        combined += (
            f"Full extract (truncated to 12k characters if needed):\n{truncated}\n"
        )

    # Include related articles for broad context
    if related_articles and len(related_articles) > 0:
        combined += f"\n\n{'='*60}\nRELATED WIKIPEDIA ARTICLES - Additional context:\n{'='*60}\n"
        combined += f"IMPORTANT: These articles are for CONTEXT ONLY. They provide background information about topics, places, and people connected to {main_article_title}.\n"
        combined += f"DO NOT generate events about the people mentioned in these related articles. Generate events ONLY for {main_article_title}.\n\n"
        for idx, article in enumerate(related_articles, 1):
            combined += f"\n{'='*60}\n"
            combined += f"ARTICLE {idx}: {article.get('title', 'Unknown')}\n"
            combined += f"URL: {article.get('url', '')}\n"
            combined += f"{'='*60}\n\n"

            full_text = article.get("fullText", "")
            if full_text:
                combined += f"{full_text}\n"
            else:
                summary = article.get("summary", "")
                if summary:
                    combined += f"{summary}\n"

        combined += f"\n{'='*60}\n"
        combined += f"END OF RELATED ARTICLES ({len(related_articles)} total)\n"
        combined += f"{'='*60}\n"

    return combined
