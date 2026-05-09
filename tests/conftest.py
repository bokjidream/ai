"""공유 테스트 픽스처."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture
def mock_llm():
    """get_llm() 반환값을 모킹합니다. 개별 테스트에서 patch와 함께 사용합니다."""
    llm = MagicMock()
    llm.invoke.return_value.content = "모킹된 응답"
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="모킹된 응답"))

    extractor = AsyncMock()
    extractor.ainvoke = AsyncMock(return_value=MagicMock())
    llm.with_structured_output.return_value = extractor

    return llm


@pytest.fixture
def mock_rag_client():
    """rag_client를 모킹합니다. serv_id/serv_nm/serv_dgst 필수 포함."""
    client = MagicMock()
    client.search = AsyncMock(
        return_value=[
            {
                "serv_id": "WLF00000035",
                "serv_nm": "기초연금",
                "serv_dgst": "만 65세 이상 저소득 노인 연금",
                "department": "보건복지부",
                "score": 0.9,
            }
        ]
    )
    client.get_detail = AsyncMock(
        return_value={
            "serv_id": "WLF00000035",
            "serv_nm": "기초연금",
            "required_documents": [],
            "application_method": "",
            "application_url": None,
        }
    )
    return client
