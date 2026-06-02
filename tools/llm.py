import os

from dotenv import load_dotenv
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_groq import ChatGroq

load_dotenv(override=True)

# 무료 티어 30 RPM 한도 내에서 여유 있게 유지 (0.4 req/s ≈ 24 RPM)
_rate_limiter = InMemoryRateLimiter(requests_per_second=0.4)


def get_llm() -> ChatGroq:
    """Groq LLM 인스턴스를 반환한다."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise OSError(
            "GROQ_API_KEY 환경변수가 설정되지 않았습니다. .env 파일을 확인해 주세요."
        )
    llm = ChatGroq(
        api_key=api_key,
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        temperature=0,
        max_retries=3,
        rate_limiter=_rate_limiter,
    )
    return llm
