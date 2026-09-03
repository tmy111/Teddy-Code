"""Provider-native renderings of TeddyCode's active tool registry."""

from .registry import _TOOL_SCHEMAS


def native_tool_specs(tools, protocol):
    if protocol not in {"openai", "anthropic"}:
        raise ValueError(f"unsupported native tool protocol: {protocol}")
    specs = []
    for name, tool in tools.items():
        schema_cls = _TOOL_SCHEMAS.get(name)
        parameters = dict(
            schema_cls.model_json_schema()
            if schema_cls is not None
            else _descriptor_json_schema(tool.schema)
        )
        parameters.pop("title", None)
        common = {"name": name, "description": tool.description}
        if protocol == "openai":
            specs.append(
                {
                    "type": "function",
                    **common,
                    "parameters": parameters,
                    # Optional/defaulted Pydantic fields do not use OpenAI's
                    # strict-schema subset, while runtime validation stays on.
                    "strict": False,
                }
            )
        else:
            specs.append({**common, "input_schema": parameters})
    return specs


def native_specs_for_client(client, tools):
    if not getattr(client, "supports_native_tools", False):
        return None
    protocol = str(getattr(client, "native_tool_protocol", ""))
    if protocol not in {"openai", "anthropic"}:
        return None
    return native_tool_specs(tools, protocol)


def _descriptor_json_schema(schema):
    properties = {}
    required = []
    for name, descriptor in dict(schema or {}).items():
        descriptor = str(descriptor)
        base_type = descriptor.split("=", 1)[0].strip()
        json_type = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
        }.get(base_type, "string")
        properties[str(name)] = {"type": json_type}
        if "=" not in descriptor:
            required.append(str(name))
    return {"type": "object", "properties": properties, "required": required}
