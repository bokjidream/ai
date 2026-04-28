"""prompts/ 디렉토리에서 프롬프트 파일을 로드하는 유틸리티."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """prompts/ 디렉토리에서 프롬프트 템플릿을 로드합니다.

    Args:
        name: .txt 확장자 없는 파일명.

    Returns:
        프롬프트 내용 문자열.

    Raises:
        FileNotFoundError: 해당 프롬프트 파일이 없을 때.
    """
    path = _PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")
