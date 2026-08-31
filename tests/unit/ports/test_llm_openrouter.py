from repodify.ports.llm import OpenRouterStructuredLLM, StructuredLLM


def test_openrouter_llm_stores_config_and_satisfies_the_port():
    llm = OpenRouterStructuredLLM(
        model="openai/gpt-4o-mini",
        api_key="sk-or-test",
        base_url="https://openrouter.ai/api/v1",
    )
    assert isinstance(llm, StructuredLLM)  # runtime_checkable Protocol
    assert llm._model == "openai/gpt-4o-mini"
    assert llm._api_key == "sk-or-test"
    assert llm._base_url == "https://openrouter.ai/api/v1"
