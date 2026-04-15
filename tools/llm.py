import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


def get_llm():
    """환경 변수에 설정된 값을 바탕으로 LLM 객체를 생성하여 반환합니다.

    Returns:
        ChatGoogleGenerativeAI: 구글 제미나이(Gemini) 언어 모델 인스턴스
    """
    # llm 파트 완성 후 아래로 교체
    # from langchain_community.llms import Ollama
    # return Ollama(
    #     base_url=os.getenv("OLLAMA_BASE_URL"),
    #     model=os.getenv("OLLAMA_MODEL"),
    # )
    return ChatGoogleGenerativeAI(
        api_key=os.getenv("GOOGLE_API_KEY"),
        model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
    )
