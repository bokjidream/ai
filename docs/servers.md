# 서버 실행 가이드

## 포트 정리

| 서버 | 포트 | 역할 |
|------|------|------|
| Web | 3000 | 프론트엔드 |
| AI | 8000 | 메인 API 서버 (웹이 직접 호출) |
| RAG | 8001 | 복지 서비스 검색 |
| hwnv LLM | 8002 | 인터뷰 AI (질문 생성 · 답변 추출) |
| MLX | 11434 | 로컬 LLM 모델 서버 |

---

## 실행 방법

### 외부 LLM 사용 시 (RAG → AI → Web 순서)

```bash
# 1. RAG 서버 (venv 활성화 필요)
uvicorn src.api.main:app --reload --port 8001

# 2. AI 서버
uv run uvicorn server:app --reload --port 8000

# 3. Web
npm run dev
```

### 로컬 LLM 사용 시 (MLX → hwnv → RAG → AI → Web 순서)

```bash
# 1. MLX 모델 서버 (venv 활성화 필요)
mlx_lm.server \
  --model mlx-community/gemma-4-e4b-it-8bit \
  --port 11434 \
  --host 0.0.0.0

# 2. hwnv LLM 서버 (venv 활성화 필요)
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload --reload-include '*.yaml'

# 3. RAG 서버 (venv 활성화 필요)
uvicorn src.api.main:app --reload --port 8001

# 4. AI 서버
uv run uvicorn server:app --reload --port 8000

# 5. Web
npm run dev
```

---

## venv 안내

| 서버 | 패키지 관리 | venv 필요 여부 |
|------|------------|--------------|
| Web | npm | 불필요 |
| AI | uv | 불필요 (`uv run`이 자동 관리) |
| RAG | pip | **필요** — 실행 전 venv 활성화 |
| hwnv LLM | pip | **필요** — 실행 전 venv 활성화 |
| MLX | pip | **필요** — 실행 전 venv 활성화 |

venv 활성화 방법:
```bash
source .venv/bin/activate  # Mac/Linux
```
