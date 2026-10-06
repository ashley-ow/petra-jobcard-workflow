from backend.app.config import Settings


def test_blank_keys_select_identity_authentication() -> None:
    settings = Settings(
        azure_search_endpoint="https://example.search.windows.net",
        azure_search_api_key="",
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_deployment="test",
        azure_openai_api_key="",
    )
    assert settings.azure_search_api_key is None
    assert settings.azure_openai_api_key is None
