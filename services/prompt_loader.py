from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def load_prompt(name: str) -> str:
    for suffix in (".txt", ".yxy"):
        prompt_path = PROMPTS_DIR / f"{name}{suffix}"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")

    raise FileNotFoundError(f"Prompt introuvable: {name}")
