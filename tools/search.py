# tools/search.py
# Brave Search API — free tier: 2000 searches/month
import httpx
from config.settings import settings

async def web_search(query: str, max_results: int = 5) -> str:
    api_key = settings.brave_search_api_key
    if not api_key:
        return "Web search not configured. Add BRAVE_SEARCH_API_KEY to .env"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": api_key,
                },
                timeout=10
            )
        data = response.json()
        results = data.get("web", {}).get("results", [])
        if not results:
            return f"No results found for: {query}"
        output = []
        for r in results[:max_results]:
            output.append(
                f"• {r['title']}\n"
                f"  {r['url']}\n"
                f"  {r.get('description', '')[:150]}"
            )
        return f"Search results for '{query}':\n\n" + "\n\n".join(output)
    except Exception as e:
        return f"Search failed: {str(e)}"