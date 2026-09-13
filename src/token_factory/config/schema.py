"""JSON Schema definitions for Token Factory config files."""

ENDPOINTS_SCHEMA = {
    "type": "object",
    "required": ["version", "endpoints"],
    "properties": {
        "version": {"type": "string"},
        "endpoints": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "host", "port", "model", "role"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "host": {"type": "string", "minLength": 1},
                    "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                    "model": {"type": "string", "minLength": 1},
                    "role": {
                        "type": "string",
                        "enum": ["coding", "general", "reasoning", "vision", "fast"],
                    },
                    "hardware": {
                        "type": "string",
                        "enum": ["instinct", "epyc", "radeon", "unknown"],
                    },
                    "accelerator": {"type": "string"},
                    "aim_support": {
                        "type": "string",
                        "enum": ["optimized", "preview", "unoptimized", "general"],
                    },
                    "weight": {"type": "number", "minimum": 0},
                    "enabled": {"type": "boolean"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "description": {"type": "string"},
                },
            },
        },
    },
}

POLICIES_SCHEMA = {
    "type": "object",
    "required": ["version", "policy"],
    "properties": {
        "version": {"type": "string"},
        "policy": {
            "type": "object",
            "required": ["name", "routes"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "virtual_model": {"type": "string"},
                "priority_mode": {
                    "type": "string",
                    "enum": ["quality", "cost", "latency", "balanced", "edge", "enterprise"],
                },
                "fallback": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "chain": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "routes": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["name", "domains", "endpoint_ref"],
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "priority": {"type": "integer"},
                            "domains": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string"},
                            },
                            "endpoint_ref": {"type": "string"},
                            "lora_name": {"type": "string"},
                            "use_reasoning": {"type": "boolean"},
                        },
                    },
                },
                "signals": {
                    "type": "object",
                    "properties": {
                        "domains": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["name"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}

TOKEN_FACTORY_SCHEMA = {
    "type": "object",
    "required": ["version", "cluster"],
    "properties": {
        "version": {"type": "string"},
        "virtual_model": {"type": "string"},
        "cluster": {
            "type": "object",
            "required": ["namespaces"],
            "properties": {
                "namespaces": {"type": "object"},
                "gateway_name": {"type": "string"},
                "gateway_namespace": {"type": "string"},
            },
        },
        "components": {
            "type": "object",
            "properties": {
                "semantic_router": {"type": "object"},
                "envoy_ai_gateway": {"type": "object"},
                "envoy_gateway": {"type": "object"},
                "observability": {"type": "object"},
            },
        },
        "paths": {
            "type": "object",
            "properties": {
                "endpoints": {"type": "string"},
                "policies": {"type": "string"},
                "catalog": {"type": "string"},
                "output_dir": {"type": "string"},
            },
        },
    },
}

AIM_CATALOG_SCHEMA = {
    "type": "object",
    "required": ["version", "metadata", "accelerators", "aims"],
    "properties": {
        "version": {"type": "string"},
        "metadata": {"type": "object"},
        "accelerators": {"type": "object"},
        "aims": {"type": "array"},
    },
}
