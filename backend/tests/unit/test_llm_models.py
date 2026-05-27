from app.services.llm_models import _parse_models_payload
from app.services.llm_provider_registry import _rule_based_models


def test_parse_models_payload_openai_shape():
    models = _parse_models_payload({"data": [{"id": "GigaChat"}, {"id": "GigaChat-2-Pro"}]})
    assert models == ["GigaChat", "GigaChat-2-Pro"]


def test_rule_based_models():
    assert _rule_based_models() == ["rule-based-llm"]
