import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()


def get_llm():
    """환경 변수에 설정된 값을 바탕으로 LLM 객체를 생성하여 반환합니다.

    Returns:
        ChatGroq: Groq 언어 모델 인스턴스
    """
    return ChatGroq(
        api_key=os.getenv("GROQ_API_KEY"),
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    )
