"""TEST D: Agent Zero configuration format and provider compatibility."""
import yaml
import pytest


def test_d1_presets_yaml_format():
    """Verify that generated presets.yaml matches Agent Zero plugin structure."""
    host_url = "http://192.168.31.136:8765"
    model_name = "gemini-3.8-flash-high"

    preset_yaml_str = f"""- name: Default
  chat:
    provider: other
    name: {model_name}
    api_base: "{host_url}/v1"
    ctx_length: 1000000
    ctx_history: 0.7
    vision: true
    max_embeds: 10
    kwargs: {{}}
  utility:
    provider: other
    name: {model_name}
    api_base: "{host_url}/v1"
    ctx_length: 128000
    ctx_input: 0.7
    kwargs: {{}}
  embedding:
    provider: huggingface
    name: sentence-transformers/all-MiniLM-L6-v2
    kwargs: {{}}
"""
    data = yaml.safe_load(preset_yaml_str)
    assert isinstance(data, list)
    assert len(data) >= 1
    default_preset = data[0]
    assert default_preset["name"] == "Default"
    assert default_preset["chat"]["provider"] == "other"
    assert default_preset["chat"]["name"] == model_name
    assert default_preset["chat"]["api_base"] == f"{host_url}/v1"
    assert default_preset["utility"]["provider"] == "other"
