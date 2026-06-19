from pathlib import Path


def test_daily_workflow_injects_optional_ai_env_without_logging_secrets() -> None:
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "daily.yml"
    text = workflow.read_text(encoding="utf-8")

    assert "AI_ENABLED: ${{ secrets.AI_ENABLED || vars.AI_ENABLED || 'false' }}" in text
    assert "AI_API_KEY: ${{ secrets.AI_API_KEY }}" in text
    assert "AI_BASE_URL: ${{ secrets.AI_BASE_URL || vars.AI_BASE_URL || 'https://api.openai.com/v1' }}" in text
    assert "AI_MODEL: ${{ secrets.AI_MODEL || vars.AI_MODEL }}" in text
    assert "AI_TIMEOUT_SECONDS: ${{ secrets.AI_TIMEOUT_SECONDS || vars.AI_TIMEOUT_SECONDS || '20' }}" in text
    assert "echo $AI_API_KEY" not in text
    assert "echo ${AI_API_KEY}" not in text
