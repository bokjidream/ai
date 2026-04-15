# 개발 도구 패키지 설명

코드 품질 관리, 테스트, 패키지 관리에 사용하는 개발 도구들을 설명합니다.

---

## uv

**역할**: 패키지 매니저 및 가상환경 관리

기존의 `pip` + `venv` 조합을 대체하는 현대적인 Python 패키지 매니저입니다. Rust로 작성되어 pip보다 10~100배 빠릅니다. `pyproject.toml` 하나로 의존성, 가상환경, Python 버전을 통합 관리합니다.

**자주 쓰는 명령어**

| 명령어 | 설명 |
|--------|------|
| `uv sync --all-groups` | 전체 의존성 설치 (클론 후 최초 1회) |
| `uv add 패키지명` | 패키지 추가 및 pyproject.toml 자동 업데이트 |
| `uv add --group dev 패키지명` | dev 그룹에 패키지 추가 |
| `uv run 명령어` | .venv 환경에서 명령어 실행 |
| `uv lock` | uv.lock 갱신 |

**의존성 그룹 구조**

```toml
# pyproject.toml

[project]
dependencies = [...]        # 프로덕션 의존성

[dependency-groups]
dev = [...]                 # 개발 도구 (ruff, pre-commit)
test = [...]                # 테스트 도구 (pytest)
```

> `uv.lock` 파일은 모든 패키지의 정확한 버전과 해시값을 기록합니다. 반드시 git에 커밋해야 팀원 전원이 동일한 환경을 재현할 수 있습니다.

---

## ruff `0.15.10`

**역할**: 린터(Linter) + 포매터(Formatter)

기존에 별도로 사용하던 `flake8`, `black`, `isort`를 하나로 통합한 도구입니다. Rust로 작성되어 매우 빠릅니다.

**이 프로젝트의 설정** (`pyproject.toml`)

| 설정 | 값 | 의미 |
|------|----|------|
| `line-length` | 88 | 한 줄 최대 길이 |
| `convention` | google | Google 스타일 Docstring 강제 |
| `select` | E, F, W, I, UP, D, B, TCH | 검사할 규칙 집합 |

**사용 방법**

```bash
# 린트 검사 (문제 목록 출력)
uv run ruff check .

# 린트 검사 + 자동 수정
uv run ruff check --fix .

# 포맷 적용
uv run ruff format .

# 포맷 확인만 (수정 없이)
uv run ruff format --check .
```

**VSCode 자동화**

`.vscode/settings.json`에 설정되어 있어 파일 저장 시 자동으로 lint fix와 import 정렬이 적용됩니다. 별도로 실행하지 않아도 됩니다.

---

## pre-commit `4.5.1`

**역할**: 커밋 전 자동 코드 품질 검사

`git commit` 실행 시 자동으로 ruff를 돌려 린트/포맷 기준을 통과하지 못한 코드가 커밋되는 것을 차단합니다.

**훅 등록** (최초 1회)

```bash
uv run pre-commit install
```

**동작 방식**

```
git commit -m "feat: 인터뷰 에이전트 추가"
  │
  ├─ ruff (lint fix) ──── 통과 → 커밋 완료
  │                  └── 실패 → 커밋 차단, 파일 자동 수정 후 재스테이징 필요
  │
  └─ ruff-format ──────── 통과 → 커밋 완료
                    └── 실패 → 커밋 차단, 파일 자동 포맷 후 재스테이징 필요
```

**훅이 차단했을 때**

```bash
# pre-commit이 파일을 자동 수정한 경우, 수정된 파일을 다시 스테이징 후 재커밋
git add .
git commit -m "feat: 인터뷰 에이전트 추가"
```

---

## pytest `9.0.3`

**역할**: 테스트 프레임워크

Python 표준 테스트 도구입니다. `tests/` 폴더 아래의 `test_*.py` 파일을 자동으로 탐지하여 실행합니다.

**사용 방법**

```bash
# 전체 테스트 실행
uv run pytest tests/ -v

# 특정 파일만 실행
uv run pytest tests/test_state.py -v

# 특정 테스트 함수만 실행
uv run pytest tests/test_state.py::test_user_profile -v
```

**테스트 파일 작성 규칙**

- 파일명: `test_*.py` 형식
- 함수명: `test_` 로 시작
- 위치: `tests/` 폴더 하위

```python
# tests/test_state.py 예시
from graph.state import UserProfile

def test_user_profile_default_values():
    profile = UserProfile()
    assert profile.age is None
    assert profile.disability is None
```

---

## pytest-asyncio `1.3.0`

**역할**: 비동기 함수 테스트 지원

LangGraph의 에이전트 노드는 `async` 함수로 작성될 수 있습니다. 일반 pytest는 `async def` 테스트 함수를 실행할 수 없는데, 이 패키지가 그 문제를 해결합니다.

**사용 방법**

```python
import pytest

@pytest.mark.asyncio
async def test_interview_agent():
    result = await interview_node(state)
    assert result["missing_fields"] == []
```
