"""Read Hermes config.yaml and .env for provider/model setup."""
import os
import yaml

HERMES_HOME = os.path.expanduser("~/.hermes")
CONFIG_PATH = os.path.join(HERMES_HOME, "config.yaml")
ENV_PATH = os.path.join(HERMES_HOME, ".env")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get_providers(cfg):
    """Return list of (name, base_url, api_key, models) tuples from config."""
    out = []
    prov = cfg.get("providers", {})
    for name, p in prov.items():
        out.append((
            name,
            p.get("base_url", ""),
            p.get("api_key", ""),
            p.get("models", []),
            p.get("default_model", "")
        ))
    return out


def get_default_model(cfg):
    return cfg.get("model", {}).get("default", "")


def get_gateway_url(cfg):
    g = cfg.get("gateway", {}).get("platforms", {}).get("api_server", {})
    host = g.get("host", "127.0.0.1")
    port = g.get("port", 8642)
    return f"http://{host}:{port}"
