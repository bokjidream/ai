# 초기 환경 세팅 가이드

이 문서는 레포를 처음 클론한 팀원이 로컬 개발 환경을 구축하는 전 과정을 설명합니다.

---

## 사전 준비

### 1. uv 설치

이 프로젝트는 패키지 매니저로 `uv`를 사용합니다. pip 대신 uv를 사용하므로 반드시 먼저 설치해야 합니다.

**macOS / Linux**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell)**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

설치 후 터미널을 재시작하고 확인합니다.
```bash
uv --version
```

---

## 세팅 순서

### 2. 레포 클론

```bash
git clone https://github.com/bokjidream/ai.git
cd ai
```

### 3. 의존성 설치

```bash
uv sync --all-groups
```

`--all-groups` 옵션은 메인 의존성뿐 아니라 `dev`, `test` 그룹까지 함께 설치합니다.
설치가 완료되면 `.venv/` 폴더가 자동으로 생성됩니다. Python 버전은 `.python-version`에 명시된 `3.11`로 고정됩니다.

### 4. 환경 변수 설정

`.env.example`을 복사해 `.env` 파일을 만들고 API 키를 채웁니다.

```bash
cp .env.example .env
```

`.env` 파일을 열어 값을 입력합니다.
```
GOOGLE_API_KEY=발급받은_키_입력
GOOGLE_MODEL=gemini-2.5-flash
```

> Google API 키는 팀 Discord를 참고해 주세요.
> `.env` 파일은 `.gitignore`에 등록되어 있어 절대 커밋되지 않습니다.

### 5. pre-commit 훅 등록

커밋 시 자동으로 코드 품질 검사가 실행되도록 훅을 등록합니다. **최초 1회만** 실행하면 됩니다.

```bash
uv run pre-commit install
```

---

## 동작 확인

세팅이 완료됐으면 아래 명령어로 정상 동작을 확인합니다.

```bash
# 린트 검사
uv run ruff check .

# 포맷 검사
uv run ruff format --check .

# 테스트 실행
uv run pytest tests/ -v

# 애플리케이션 실행
uv run python main.py
```

---

## 패키지 추가 방법

새로운 패키지가 필요할 때는 `pip install` 대신 아래 명령어를 사용합니다.

```bash
# 메인 의존성 추가
uv add 패키지명

# 개발 전용 의존성 추가
uv add --group dev 패키지명

# 테스트 전용 의존성 추가
uv add --group test 패키지명
```

`uv add`를 사용하면 `pyproject.toml`과 `uv.lock`이 자동으로 업데이트됩니다.
반드시 두 파일 모두 커밋해야 다른 팀원도 동일한 환경을 재현할 수 있습니다.

---

## 자주 발생하는 문제

| 증상 | 원인 | 해결 방법 |
|------|------|-----------|
| `uv: command not found` | uv 미설치 | 터미널 재시작 또는 uv 재설치 |
| `GOOGLE_API_KEY not set` | `.env` 파일 없음 | 4번 단계 다시 확인 |
| pre-commit 훅이 실행 안 됨 | 훅 미등록 | `uv run pre-commit install` 실행 |
| 패키지 import 오류 | `.venv` 활성화 안 됨 | `uv run` 접두어 붙여 실행 |
