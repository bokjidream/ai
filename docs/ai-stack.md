# AI 스택 패키지 설명

이 프로젝트의 핵심 AI 로직을 구성하는 패키지들을 설명합니다.

---

## LangGraph `1.1.6`

**역할**: 멀티 에이전트 오케스트레이션 프레임워크

이 프로젝트의 가장 핵심 패키지입니다. 복지 상담의 각 단계(인터뷰 → 분석 → 서류 안내 → 초안 작성 → 리포트)를 독립된 에이전트 노드로 분리하고, 노드 간 전환 조건과 순환 루프를 그래프 구조로 정의합니다.

**이 프로젝트에서 담당하는 것**
- 5개 에이전트 노드의 실행 순서와 분기 조건 제어
- `AgentState`를 통해 노드 간 데이터(사용자 프로필, 후보 서비스 목록 등) 공유
- 정보 누락 시 인터뷰 노드로 재진입하는 순환 루프 구현

**핵심 개념**

```python
from langgraph.graph import StateGraph
from graph.state import AgentState

builder = StateGraph(AgentState)
builder.add_node("interview", interview_node)
builder.add_node("analysis", analysis_node)
builder.add_edge("interview", "analysis")
graph = builder.compile()
```

- `StateGraph`: 상태를 공유하는 에이전트 그래프
- `add_node`: 에이전트 함수를 그래프의 노드로 등록
- `add_edge` / `add_conditional_edges`: 노드 간 전환 규칙 정의
- `compile()`: 그래프를 실행 가능한 형태로 빌드

---

## LangChain Core `1.2.29`

**역할**: LangChain 생태계의 기반 인터페이스

LangGraph, langchain-google-genai, langchain-community가 모두 공통으로 사용하는 기반 패키지입니다. 직접 import해서 사용하기보다는 다른 패키지들이 내부적으로 의존합니다.

**이 프로젝트에서 담당하는 것**
- `ChatPromptTemplate`, `HumanMessage`, `AIMessage` 등 공통 메시지 타입 제공
- LLM 호출 결과를 파싱하는 Output Parser 인터페이스 제공
- 모든 LLM 공급자(Google, Ollama 등)가 따르는 공통 인터페이스 정의

---

## langchain-google-genai `4.2.1`

**역할**: Google Gemini 모델 연동

개발 단계에서 사용하는 LLM 공급자 패키지입니다. `tools/llm.py`의 `get_llm()`이 이 패키지를 통해 Gemini API를 호출합니다. 추후 로컬 Llama 환경이 구축되면 `langchain-community`의 Ollama로 교체할 예정입니다.

**이 프로젝트에서 담당하는 것**
- Gemini API 호출 및 응답 수신
- LangGraph 에이전트 노드 내에서 LLM 추론 수행

```python
# tools/llm.py
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    api_key=os.getenv("GOOGLE_API_KEY"),
    model="gemini-2.5-flash",
)
```

> **Ollama로 전환 시**: `tools/llm.py`의 주석 처리된 Ollama 코드로 교체하고 `.env`의 `OLLAMA_*` 값을 설정합니다.

---

## langchain-community `0.4.1`

**역할**: 서드파티 통합 패키지 (Ollama, ChromaDB 등)

LangChain 공식 팀이 아닌 커뮤니티에서 관리하는 외부 도구 연동 패키지입니다.

**이 프로젝트에서 담당하는 것**
- **현재**: 의존성으로만 설치되어 있으며 직접 사용하지 않음
- **추후 사용 예정**:
  - `Ollama` — 로컬 Llama 모델 연동 (LLM 파트 완성 후)
  - `Chroma` — ChromaDB Vector Store 연동 (RAG 파트 완성 후)

```python
# 추후 LLM 교체 시
from langchain_community.llms import Ollama

# 추후 RAG 연동 시
from langchain_community.vectorstores import Chroma
```

---

## Pydantic `2.13.0`

**역할**: 데이터 유효성 검증 및 타입 강제

에이전트 간에 주고받는 데이터의 형태를 명확하게 정의하고, 잘못된 값이 들어왔을 때 즉시 오류를 발생시킵니다.

**이 프로젝트에서 담당하는 것**

`graph/state.py`의 `UserProfile`과 `WelfareCandidate` 모델 정의에 사용됩니다.

```python
# graph/state.py
from pydantic import BaseModel

class UserProfile(BaseModel):
    age: int | None = None
    monthly_income: int | None = None  # 만원 단위
    disability: bool | None = None
```

- 에이전트가 `age`에 문자열을 넣으려 하면 즉시 `ValidationError` 발생
- `None` 기본값으로 인터뷰 중 점진적으로 필드를 채우는 패턴 지원
- LangGraph의 `AgentState` 내 중첩 모델로 활용

---

## python-dotenv `1.2.2`

**역할**: `.env` 파일의 환경 변수를 프로세스에 로드

API 키, 서버 주소 등 민감한 설정값을 코드에 하드코딩하지 않고 `.env` 파일로 분리하여 관리할 수 있게 합니다.

**이 프로젝트에서 담당하는 것**

`main.py`와 `tools/llm.py` 최상단에서 호출됩니다.

```python
from dotenv import load_dotenv
load_dotenv()  # .env 파일을 읽어 os.environ에 등록

# 이후 어디서든 사용 가능
import os
api_key = os.getenv("GOOGLE_API_KEY")
```
